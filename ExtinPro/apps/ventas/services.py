"""
Ventas y caja. Casos de uso SPVCI-VT-01 a VT-04 · casos de prueba CP-03 y CP-06.

registrar_venta() crea VENTA, DETALLE_VENTA, PAGO, COMPROBANTE y los movimientos
SALIDA_VENTA en una sola transacción: si algo falla, no queda nada registrado.
"""
import re
import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from apps.catalogo.models import Cliente, Producto
from apps.core.services import registrar_bitacora, siguiente_folio
from apps.inventario.models import MovimientoInventario
from apps.inventario.services import (
    bloquear_existencias,
    estado_stock,
    existencia,
    formato_cantidad,
    registrar_movimiento,
)

from .models import ArqueoCaja, Caja, Comprobante, DetalleVenta, Pago, SesionCaja, Venta, redondear

CERO = Decimal("0")
DESC_MAX = Decimal(settings.SPVCI["DESCUENTO_MAXIMO"])
RE_REFERENCIA = re.compile(r"^\d{4,12}$")


class VentaError(Exception):
    def __init__(self, errores):
        self.errores = errores if isinstance(errores, list) else [errores]
        super().__init__("; ".join(self.errores))


def pesos(v):
    return f"${Decimal(v):,.2f}"


# ================================================================== Caja

def sesion_abierta(caja):
    return SesionCaja.objects.filter(caja=caja, estado=SesionCaja.Estado.ABIERTA).first()


def abrir_sesion(*, caja, usuario, fondo_inicial):
    fondo = Decimal(fondo_inicial or 0)
    if fondo < 0:
        raise VentaError("El fondo inicial no puede ser negativo.")
    if not caja.activa:
        raise VentaError("La caja está inactiva.")
    try:
        with transaction.atomic():
            return SesionCaja.objects.create(caja=caja, abierto_por=usuario, fondo_inicial=fondo)
    except IntegrityError:  # uq_sesion_caja_abierta
        raise VentaError(f"La caja {caja.codigo} ya tiene una sesión abierta.")


def totales_sesion(sesion):
    def suma(metodo, tipo):
        return (
            sesion.pagos.filter(metodo=metodo, tipo=tipo, estado=Pago.Estado.CONFIRMADO).aggregate(t=Sum("monto"))["t"]
            or CERO
        )

    ef = sesion.fondo_inicial + suma("EFECTIVO", "COBRO") - suma("EFECTIVO", "DEVOLUCION")
    tj = suma("TARJETA", "COBRO") - suma("TARJETA", "DEVOLUCION")
    ventas = sesion.ventas.filter(estado=Venta.Estado.COMPLETADA)
    return {
        "efectivo_esperado": ef,
        "tarjeta_esperado": tj,
        "ventas": ventas.count(),
        "importe_ventas": ventas.aggregate(t=Sum("total"))["t"] or CERO,
    }


@transaction.atomic
def cerrar_sesion(*, sesion, usuario, efectivo_contado, tarjeta_reportado, observaciones=""):
    """Corte de caja: crea ARQUEO_CAJA y cierra la sesión."""
    sesion = SesionCaja.objects.select_for_update().get(pk=sesion.pk)
    if sesion.estado != SesionCaja.Estado.ABIERTA:
        raise VentaError("La sesión ya está cerrada.")
    t = totales_sesion(sesion)
    ef, tj = Decimal(efectivo_contado), Decimal(tarjeta_reportado)
    if ef < 0 or tj < 0:
        raise VentaError("Los importes contados no pueden ser negativos.")
    diferencia = (ef - t["efectivo_esperado"]) + (tj - t["tarjeta_esperado"])
    observaciones = (observaciones or "").strip()
    if diferencia != 0 and not observaciones:
        raise VentaError(f"Hay una diferencia de {pesos(diferencia)}: explica el motivo en observaciones.")
    arqueo = ArqueoCaja.objects.create(
        sesion_caja=sesion,
        realizado_por=usuario,
        efectivo_esperado=max(t["efectivo_esperado"], CERO),
        efectivo_contado=ef,
        tarjeta_esperado=max(t["tarjeta_esperado"], CERO),
        tarjeta_reportado=tj,
        observaciones=observaciones or None,
    )
    sesion.estado = SesionCaja.Estado.CERRADA
    sesion.cerrado_por = usuario
    sesion.fecha_cierre = timezone.now()
    sesion.save(update_fields=["estado", "cerrado_por", "fecha_cierre"])
    return arqueo


# ================================================================== Venta

@dataclass
class LineaVenta:
    producto_id: int
    cantidad: Decimal
    descuento_pct: Decimal = CERO
    precio_unitario: Decimal | None = None  # None = precio de catálogo


@dataclass
class Calculo:
    producto: Producto
    cantidad: Decimal
    precio_unitario: Decimal
    descuento_pct: Decimal
    importe: Decimal = CERO
    descuento: Decimal = CERO
    iva: Decimal = CERO

    def __post_init__(self):
        self.importe = redondear(self.cantidad * self.precio_unitario)
        self.descuento = redondear(self.importe * self.descuento_pct / 100)
        self.iva = redondear((self.importe - self.descuento) * self.producto.tasa_iva)


@dataclass
class ResultadoVenta:
    venta: Venta
    creada: bool
    pagado: Decimal = CERO
    cambio: Decimal = CERO
    existencias: list = field(default_factory=list)  # [{producto, antes, despues, estado}]
    alertas: list = field(default_factory=list)  # productos que quedaron en o bajo el mínimo


def calcular_totales(calculos):
    subtotal = sum((c.importe for c in calculos), CERO)
    descuento = sum((c.descuento for c in calculos), CERO)
    iva = sum((c.iva for c in calculos), CERO)
    return {"subtotal": subtotal, "descuento": descuento, "iva": iva, "total": subtotal - descuento + iva}


def puede_cambiar_precio(usuario):
    return usuario.puede("reporte_ventas")  # Gerente y Administrador


def _validar_lineas(lineas, productos, usuario):
    errores = []
    if not lineas:
        errores.append("Agrega al menos un producto a la venta.")
    for l in lineas:
        p = productos.get(l.producto_id)
        if p is None:
            errores.append("Uno de los productos no existe o está inactivo.")
            continue
        if l.cantidad is None or l.cantidad < 1:
            errores.append(f"{p.sku}: la cantidad debe ser mayor o igual a 1.")
        elif p.unidad_medida in ("PIEZA", "SERVICIO") and l.cantidad != l.cantidad.to_integral_value():
            errores.append(f"{p.sku}: la cantidad debe ser un número entero de piezas.")
        if l.precio_unitario is not None and l.precio_unitario != p.precio_venta:
            if not puede_cambiar_precio(usuario):
                errores.append(f"{p.sku}: tu rol no puede modificar el precio de lista.")
            elif l.precio_unitario <= 0:
                errores.append(f"{p.sku}: el precio unitario debe ser mayor a 0.")
        if l.descuento_pct is None or l.descuento_pct < 0 or l.descuento_pct > DESC_MAX:
            errores.append(f"{p.sku}: el descuento debe estar entre 0 y {DESC_MAX:.0f} %.")
    return errores


def validar_pago(metodo, total, recibido, referencia):
    if metodo not in (Pago.Metodo.EFECTIVO, Pago.Metodo.TARJETA):
        return ["Selecciona el método de pago."]
    if metodo == Pago.Metodo.EFECTIVO and (recibido is None or recibido < total):
        return [f"El importe recibido ({pesos(recibido or 0)}) es menor que el total ({pesos(total)})."]
    if metodo == Pago.Metodo.TARJETA and not RE_REFERENCIA.match((referencia or "").strip()):
        return ["Captura la referencia de autorización de la terminal (4 a 12 dígitos)."]
    return []


def registrar_venta(*, sesion, usuario, cliente, lineas, metodo, recibido=None, referencia="", uuid_operacion=None):
    """Registra la venta completa. Devuelve ResultadoVenta (creada=False si el UUID ya existía)."""
    uuid_operacion = uuid_operacion or uuid.uuid4()
    previa = Venta.objects.filter(uuid_operacion=uuid_operacion).first()
    if previa:
        return ResultadoVenta(venta=previa, creada=False, pagado=previa.total)
    try:
        with transaction.atomic():
            return _registrar(sesion, usuario, cliente, lineas, metodo, recibido, referencia, uuid_operacion)
    except IntegrityError:
        previa = Venta.objects.filter(uuid_operacion=uuid_operacion).first()
        if previa:  # dos envíos simultáneos del mismo cobro: gana el primero
            return ResultadoVenta(venta=previa, creada=False, pagado=previa.total)
        raise


def _registrar(sesion, usuario, cliente, lineas, metodo, recibido, referencia, uuid_operacion):
    sesion = SesionCaja.objects.select_for_update().select_related("caja__sucursal").get(pk=sesion.pk)
    if sesion.estado != SesionCaja.Estado.ABIERTA:
        raise VentaError("La sesión de caja está cerrada. Abre la caja para vender.")
    sucursal = sesion.caja.sucursal
    if not cliente or not cliente.activo:
        raise VentaError("Selecciona un cliente activo.")

    ids = {l.producto_id for l in lineas}
    productos = {p.id: p for p in Producto.objects.filter(pk__in=ids, activo=True)}
    errores = _validar_lineas(lineas, productos, usuario)
    if errores:
        raise VentaError(errores)

    calculos = [
        Calculo(
            producto=productos[l.producto_id],
            cantidad=l.cantidad,
            precio_unitario=l.precio_unitario if l.precio_unitario is not None else productos[l.producto_id].precio_venta,
            descuento_pct=l.descuento_pct,
        )
        for l in lineas
    ]
    tot = calcular_totales(calculos)
    errores = validar_pago(metodo, tot["total"], recibido, referencia)

    # Existencias: candado por producto y verificación dentro de la transacción (VT-02).
    requeridas = {}
    for c in calculos:
        if not c.producto.es_servicio:
            requeridas[c.producto.id] = requeridas.get(c.producto.id, CERO) + c.cantidad
    bloquear_existencias([(sucursal.id, pid) for pid in requeridas])
    antes = {pid: existencia(sucursal, productos[pid]) for pid in requeridas}
    for pid, cant in requeridas.items():
        if cant > antes[pid]:
            errores.append(
                f"{productos[pid].sku}: stock insuficiente (disponible {formato_cantidad(antes[pid])} en "
                f"{sucursal.corto}, solicitado {formato_cantidad(cant)})."
            )
    if errores:
        raise VentaError(errores)

    venta = Venta.objects.create(
        sucursal=sucursal,
        cliente=cliente,
        sesion_caja=sesion,
        creado_por=usuario,
        folio=siguiente_folio(Venta, "folio", "VT-", 6, "venta"),
        estado=Venta.Estado.COMPLETADA,
        subtotal=tot["subtotal"],
        descuento_total=tot["descuento"],
        iva_total=tot["iva"],
        total=tot["total"],
        uuid_operacion=uuid_operacion,
    )
    for c in calculos:
        detalle = DetalleVenta.objects.create(
            venta=venta,
            producto=c.producto,
            cantidad=c.cantidad,
            precio_unitario=c.precio_unitario,
            descuento=c.descuento,
            tasa_iva=c.producto.tasa_iva,
        )
        if c.precio_unitario != c.producto.precio_venta:
            registrar_bitacora(usuario=usuario, entidad="VENTA", registro_id=venta.id, accion="CAMBIO_PRECIO",
                               campo=c.producto.sku, anterior=c.producto.precio_venta, nuevo=c.precio_unitario)
        if not c.producto.es_servicio:
            registrar_movimiento(
                sucursal=sucursal,
                producto=c.producto,
                tipo=MovimientoInventario.Tipo.SALIDA_VENTA,
                cantidad=c.cantidad,
                costo_unitario=c.producto.precio_compra,
                usuario=usuario,
                detalle_venta=detalle,
                observaciones=f"Venta {venta.folio}",
            )
    if venta.total > 0:
        Pago.objects.create(
            venta=venta,
            sesion_caja=sesion,
            registrado_por=usuario,
            metodo=metodo,
            tipo=Pago.Tipo.COBRO,
            monto=venta.total,
            referencia=(referencia or "").strip() or None if metodo == Pago.Metodo.TARJETA else None,
        )
    Comprobante.objects.create(venta=venta, tipo=Comprobante.Tipo.TICKET, serie="A", folio=venta.folio)

    resultado = ResultadoVenta(venta=venta, creada=True)
    resultado.pagado = recibido if metodo == Pago.Metodo.EFECTIVO else venta.total
    resultado.cambio = (recibido - venta.total) if metodo == Pago.Metodo.EFECTIVO else CERO
    for pid, cant in requeridas.items():
        p = productos[pid]
        despues = antes[pid] - cant
        resultado.existencias.append({"producto": p, "antes": antes[pid], "despues": despues, "estado": estado_stock(p, despues)})
        if despues <= p.stock_minimo:
            resultado.alertas.append({"producto": p, "existencia": despues})
    return resultado


@transaction.atomic
def cancelar_venta(*, venta, usuario, motivo, sesion_actual=None):
    """
    Cancelación autorizada (rol.puede_cancelar_venta). No borra nada:
    - REVERSA en el kárdex por cada partida con existencias;
    - si la sesión original sigue abierta, los cobros pasan a CANCELADO; si ya se cerró,
      se registra un PAGO de tipo DEVOLUCION en la sesión abierta actual;
    - el comprobante queda CANCELADO y la venta CANCELADA con motivo (≥ 10 caracteres).
    """
    if not usuario.rol.puede_cancelar_venta:
        raise PermissionDenied("Tu rol no puede cancelar ventas.")
    motivo = (motivo or "").strip()
    if len(motivo) < 10:
        raise VentaError("Escribe el motivo de la cancelación (mínimo 10 caracteres).")
    venta = Venta.objects.select_for_update().select_related("sesion_caja", "sucursal").get(pk=venta.pk)
    if venta.estado != Venta.Estado.COMPLETADA:
        raise VentaError(f"La venta {venta.folio} no se puede cancelar ({venta.get_estado_display().lower()}).")

    cobros = list(venta.pagos.filter(tipo=Pago.Tipo.COBRO, estado=Pago.Estado.CONFIRMADO))
    if venta.sesion_caja.estado == SesionCaja.Estado.ABIERTA:
        Pago.objects.filter(pk__in=[p.pk for p in cobros]).update(estado=Pago.Estado.CANCELADO)
    elif cobros:
        if sesion_actual is None or sesion_actual.estado != SesionCaja.Estado.ABIERTA or sesion_actual.caja.sucursal_id != venta.sucursal_id:
            raise VentaError(f"La caja de esa venta ya se cerró: abre una caja en {venta.sucursal.nombre} para registrar la devolución del dinero.")
        for p in cobros:
            Pago.objects.create(
                venta=venta, sesion_caja=sesion_actual, registrado_por=usuario, metodo=p.metodo,
                tipo=Pago.Tipo.DEVOLUCION, monto=p.monto, referencia=p.referencia,
            )
    for d in venta.detalles.select_related("producto"):
        if not d.producto.es_servicio:
            registrar_movimiento(
                sucursal=venta.sucursal,
                producto=d.producto,
                tipo=MovimientoInventario.Tipo.REVERSA,
                cantidad=d.cantidad,
                costo_unitario=d.producto.precio_compra,
                usuario=usuario,
                detalle_venta=d,
                observaciones=f"Cancelación de {venta.folio}: {motivo}",
            )
    venta.comprobantes.update(estado=Comprobante.Estado.CANCELADO)
    venta.estado = Venta.Estado.CANCELADA
    venta.cancelado_por = usuario
    venta.motivo_cancelacion = motivo
    venta.save(update_fields=["estado", "cancelado_por", "motivo_cancelacion"])
    registrar_bitacora(usuario=usuario, entidad="VENTA", registro_id=venta.id, accion="CANCELACION",
                       campo="Estado", anterior="Completada", nuevo="Cancelada", motivo=motivo)
    return venta


def metodo_de(venta):
    p = venta.pagos.filter(tipo=Pago.Tipo.COBRO).first()
    return p


def publico_general():
    return Cliente.objects.filter(tipo_persona=Cliente.TipoPersona.PUBLICO_GENERAL).order_by("id").first()


def cajas_de(sucursal):
    return Caja.objects.filter(sucursal=sucursal, activa=True).order_by("codigo")

