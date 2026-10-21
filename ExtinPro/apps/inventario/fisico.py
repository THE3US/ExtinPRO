"""
Inventario físico (conteo) y ajustes autorizados.

En el Entregable 6, un movimiento AJUSTE solo puede originarse en un renglón de
DETALLE_INVENTARIO_FISICO. Por eso las existencias iniciales y las correcciones se
capturan con un conteo: ABIERTO → CERRADO → AJUSTADO (autoriza Gerente o Administrador).
"""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.catalogo.models import Producto
from apps.core.services import registrar_bitacora

from .models import DetalleInventarioFisico, InventarioFisico, MovimientoInventario
from .services import StockInsuficiente, existencias, registrar_movimiento

CERO = Decimal("0")


class ConteoError(Exception):
    def __init__(self, errores):
        self.errores = errores if isinstance(errores, list) else [errores]
        super().__init__("; ".join(self.errores))


@transaction.atomic
def iniciar_conteo(*, sucursal, usuario, observaciones=""):
    productos = list(Producto.objects.filter(activo=True).exclude(tipo=Producto.Tipo.SERVICIO).order_by("categoria", "sku"))
    if not productos:
        raise ConteoError("No hay productos activos para contar. Da de alta productos primero.")
    conteo = InventarioFisico.objects.create(sucursal=sucursal, creado_por=usuario, observaciones=observaciones or None)
    ex = existencias(sucursales=[sucursal], productos=productos)
    DetalleInventarioFisico.objects.bulk_create(
        [
            DetalleInventarioFisico(
                inventario_fisico=conteo,
                producto=p,
                existencia_sistema=max(ex[(p.id, sucursal.id)], CERO),
                existencia_fisica=max(ex[(p.id, sucursal.id)], CERO),
            )
            for p in productos
        ]
    )
    return conteo


@transaction.atomic
def capturar(conteo, fisicas, observaciones=None):
    """fisicas: {detalle_id: Decimal}. Solo mientras el conteo está ABIERTO."""
    conteo = InventarioFisico.objects.select_for_update().get(pk=conteo.pk)
    if conteo.estado != InventarioFisico.Estado.ABIERTO:
        raise ConteoError("El conteo ya está cerrado.")
    errores = []
    for d in conteo.detalles.select_related("producto"):
        if d.id in fisicas:
            v = fisicas[d.id]
            if v is None or v < 0:
                errores.append(f"{d.producto.sku}: la existencia física debe ser 0 o mayor.")
                continue
            d.existencia_fisica = v
            if observaciones and observaciones.get(d.id) is not None:
                d.observaciones = observaciones[d.id] or None
            d.save(update_fields=["existencia_fisica", "observaciones"])
    if errores:
        raise ConteoError(errores)
    return conteo


@transaction.atomic
def cerrar_conteo(conteo, usuario):
    conteo = InventarioFisico.objects.select_for_update().get(pk=conteo.pk)
    if conteo.estado != InventarioFisico.Estado.ABIERTO:
        raise ConteoError("El conteo ya está cerrado.")
    conteo.estado = InventarioFisico.Estado.CERRADO
    conteo.fecha_cierre = timezone.now()
    conteo.save(update_fields=["estado", "fecha_cierre"])
    return conteo


@transaction.atomic
def autorizar_ajuste(conteo, usuario):
    """Genera un AJUSTE por cada diferencia ≠ 0 y deja el conteo AJUSTADO."""
    if not usuario.puede("autorizar_oc"):  # Gerente o Administrador
        raise ConteoError("Solo el Gerente o el Administrador autorizan ajustes de inventario.")
    conteo = InventarioFisico.objects.select_for_update().select_related("sucursal").get(pk=conteo.pk)
    if conteo.estado != InventarioFisico.Estado.CERRADO:
        raise ConteoError("Cierra el conteo antes de autorizar los ajustes.")
    errores = []
    for d in conteo.detalles.select_related("producto"):
        dif = d.existencia_fisica - d.existencia_sistema
        if dif == 0:
            continue
        try:
            registrar_movimiento(
                sucursal=conteo.sucursal,
                producto=d.producto,
                tipo=MovimientoInventario.Tipo.AJUSTE,
                cantidad=abs(dif),
                costo_unitario=d.producto.precio_compra,
                usuario=usuario,
                detalle_inventario=d,
                observaciones=d.observaciones or f"Conteo físico {conteo.folio}",
            )
        except StockInsuficiente as exc:
            errores.append(
                f"{d.producto.sku}: hubo salidas después del conteo; la existencia actual "
                f"({exc.disponible}) ya no permite restar {abs(dif)}. Inicia un conteo nuevo."
            )
    if errores:
        raise ConteoError(errores)
    conteo.estado = InventarioFisico.Estado.AJUSTADO
    conteo.autorizado_por = usuario
    conteo.save(update_fields=["estado", "autorizado_por"])
    registrar_bitacora(usuario=usuario, entidad="INVENTARIO_FISICO", registro_id=conteo.id, accion="AUTORIZACION",
                       campo="Estado", anterior="Cerrado", nuevo="Ajustado", motivo=conteo.observaciones)
    return conteo
