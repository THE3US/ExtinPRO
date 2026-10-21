"""
Existencias y kárdex.

El Entregable 6 no tiene tabla de saldos: la existencia es la suma con signo de
MOVIMIENTO_INVENTARIO. En la BD, la cantidad siempre es positiva y el signo se deduce
del tipo y del origen del movimiento (misma regla que la vista v_kardex):

    ENTRADA_COMPRA                       → +
    SALIDA_VENTA, CONSUMO_SERVICIO       → −
    AJUSTE                               → signo de la diferencia del conteo físico
    REVERSA de una entrada (recepción)   → −
    REVERSA de un ajuste                 → signo contrario a la diferencia
    REVERSA de una venta o de un consumo → +

Concurrencia: antes de registrar una salida se toma un candado de transacción
(pg_advisory_xact_lock) por sucursal y producto, y la existencia se vuelve a calcular
dentro del candado. Así dos cajas no pueden vender la última pieza al mismo tiempo.
"""
from collections import defaultdict
from datetime import datetime, time
from decimal import Decimal

from django.db import connection
from django.db.models import Case, DecimalField, F, Sum, Value, When
from django.db.models.functions import Coalesce, Sign
from django.utils import timezone

from apps.catalogo.models import Producto

from .models import MovimientoInventario

T = MovimientoInventario.Tipo
DEC = DecimalField(max_digits=14, decimal_places=3)
CERO = Decimal("0")


class StockInsuficiente(Exception):
    def __init__(self, producto, sucursal, disponible, solicitado):
        self.producto, self.sucursal, self.disponible, self.solicitado = producto, sucursal, disponible, solicitado
        super().__init__(
            f"Stock insuficiente: {producto.sku} tiene {formato_cantidad(disponible)} en {sucursal.corto} "
            f"y se necesitan {formato_cantidad(solicitado)}."
        )


def formato_cantidad(valor):
    valor = Decimal(valor)
    return f"{valor.normalize():f}" if valor != valor.to_integral() else f"{int(valor)}"


def cantidad_con_signo():
    """Expresión ORM equivalente a la columna cantidad_con_signo de la vista v_kardex."""
    dif = F("detalle_inventario__diferencia")
    return Case(
        When(tipo=T.ENTRADA_COMPRA, then=F("cantidad")),
        When(tipo__in=[T.SALIDA_VENTA, T.CONSUMO_SERVICIO], then=-F("cantidad")),
        When(tipo=T.AJUSTE, then=Sign(dif) * F("cantidad")),
        When(detalle_recepcion__isnull=False, then=-F("cantidad")),
        When(detalle_inventario__isnull=False, then=-Sign(dif) * F("cantidad")),
        default=F("cantidad"),
        output_field=DEC,
    )


def signo(tipo, *, detalle_recepcion=None, detalle_inventario=None, diferencia=None):
    """La misma regla en Python, para validar un movimiento antes de guardarlo."""
    if tipo == T.ENTRADA_COMPRA:
        return 1
    if tipo in (T.SALIDA_VENTA, T.CONSUMO_SERVICIO):
        return -1
    if tipo == T.AJUSTE:
        return 1 if diferencia > 0 else -1
    if detalle_recepcion is not None:
        return -1
    if detalle_inventario is not None:
        return -1 if diferencia > 0 else 1
    return 1


def fin_del_dia(fecha):
    return timezone.make_aware(datetime.combine(fecha, time.max))


# ------------------------------------------------------------------ Consultas

def existencia(sucursal, producto, hasta=None):
    qs = MovimientoInventario.objects.filter(sucursal=sucursal, producto=producto)
    if hasta is not None:
        qs = qs.filter(fecha_movimiento__lte=fin_del_dia(hasta))
    return qs.aggregate(e=Coalesce(Sum(cantidad_con_signo()), Value(CERO), output_field=DEC))["e"]


def existencias(hasta=None, sucursales=None, productos=None):
    """{(producto_id, sucursal_id): existencia} para todos los pares con movimientos."""
    qs = MovimientoInventario.objects.all()
    if hasta is not None:
        qs = qs.filter(fecha_movimiento__lte=fin_del_dia(hasta))
    if sucursales is not None:
        qs = qs.filter(sucursal__in=sucursales)
    if productos is not None:
        qs = qs.filter(producto__in=productos)
    filas = qs.values("producto_id", "sucursal_id").annotate(e=Sum(cantidad_con_signo())).order_by()
    return defaultdict(lambda: CERO, {(f["producto_id"], f["sucursal_id"]): f["e"] for f in filas})


def estado_stock(producto, cantidad):
    """(clase CSS, texto) igual que estadoStock() del demo."""
    if not producto.activo:
        return "off", "Descontinuado"
    if cantidad <= 0:
        return "crit", "Agotado"
    if cantidad <= producto.stock_minimo:
        return "warn", "Bajo mínimo"
    return "ok", "Disponible"


def alertas_stock(sucursales):
    """Productos activos (no servicios) con existencia ≤ mínimo, por sucursal (PROD-05)."""
    productos = list(Producto.objects.filter(activo=True).exclude(tipo=Producto.Tipo.SERVICIO).order_by("sku"))
    ex = existencias(sucursales=sucursales, productos=productos)
    alertas = []
    for p in productos:
        for s in sucursales:
            cant = ex[(p.id, s.id)]
            if cant <= p.stock_minimo:
                alertas.append({"producto": p, "sucursal": s, "existencia": cant, "estado": estado_stock(p, cant)})
    return alertas


# ------------------------------------------------------------------ Escritura

def bloquear_existencias(pares):
    """Candado de transacción por (sucursal_id, producto_id), en orden fijo para evitar interbloqueos."""
    if not connection.in_atomic_block:
        raise RuntimeError("Los movimientos de inventario deben registrarse dentro de transaction.atomic().")
    with connection.cursor() as cur:
        for sucursal_id, producto_id in sorted(set(pares)):
            cur.execute("SELECT pg_advisory_xact_lock(%s, %s)", [int(sucursal_id), int(producto_id)])


def registrar_movimiento(*, sucursal, producto, tipo, cantidad, usuario, costo_unitario=CERO, observaciones=None,
                         detalle_recepcion=None, detalle_venta=None, material_servicio=None, detalle_inventario=None,
                         validar_existencia=True):
    """
    Inserta un movimiento validando que una salida no deje la existencia en negativo.
    Debe llamarse dentro de una transacción; toma el candado de la existencia.
    """
    if producto.es_servicio:
        raise ValueError(f"{producto.sku} es un servicio: no lleva existencias.")
    cantidad = Decimal(cantidad)
    if cantidad <= 0:
        raise ValueError("La cantidad del movimiento debe ser mayor a 0.")
    bloquear_existencias([(sucursal.id, producto.id)])
    diferencia = detalle_inventario.diferencia if detalle_inventario is not None else None
    if diferencia is None and detalle_inventario is not None:
        diferencia = detalle_inventario.existencia_fisica - detalle_inventario.existencia_sistema
    s = signo(tipo, detalle_recepcion=detalle_recepcion, detalle_inventario=detalle_inventario, diferencia=diferencia)
    if s < 0 and validar_existencia:
        disponible = existencia(sucursal, producto)
        if disponible < cantidad:
            raise StockInsuficiente(producto, sucursal, disponible, cantidad)
    return MovimientoInventario.objects.create(
        sucursal=sucursal,
        producto=producto,
        tipo=tipo,
        cantidad=cantidad,
        costo_unitario=costo_unitario,
        registrado_por=usuario,
        observaciones=observaciones,
        detalle_recepcion=detalle_recepcion,
        detalle_venta=detalle_venta,
        material_servicio=material_servicio,
        detalle_inventario=detalle_inventario,
    )


def kardex(producto, sucursal=None, limite=40):
    """Movimientos más recientes con su cantidad con signo y la existencia resultante."""
    qs = MovimientoInventario.objects.filter(producto=producto).select_related(
        "sucursal", "registrado_por", "detalle_recepcion__recepcion", "detalle_venta__venta", "detalle_inventario__inventario_fisico"
    )
    if sucursal is not None:
        qs = qs.filter(sucursal=sucursal)
    movs = list(qs.annotate(delta=cantidad_con_signo()).order_by("-fecha_movimiento", "-id")[:limite])
    actuales = existencias(productos=[producto])
    corrida = {}
    for m in movs:
        corrida.setdefault(m.sucursal_id, actuales[(producto.id, m.sucursal_id)])
        m.existencia_despues = corrida[m.sucursal_id]
        corrida[m.sucursal_id] -= m.delta
        m.referencia = referencia_de(m)
    return movs


def referencia_de(m):
    if m.detalle_recepcion_id:
        return m.detalle_recepcion.recepcion.folio_recepcion
    if m.detalle_venta_id:
        return m.detalle_venta.venta.folio
    if m.detalle_inventario_id:
        return m.detalle_inventario.inventario_fisico.folio
    if m.material_servicio_id:
        return f"SRV-{m.material_servicio_id}"
    return "—"
