"""
Compras: abastecimiento (órdenes de compra) y recibo de mercancía.

Casos de uso del E7: SPVCI-OC-01 a OC-08 · casos de prueba CP-04 y CP-05.
"""
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.catalogo.models import Producto
from apps.core.services import hoy, registrar_bitacora, siguiente_folio, sumar_dias_habiles
from apps.core.templatetags.spvci import fecha as fecha_texto
from apps.inventario.models import MovimientoInventario
from apps.inventario.services import StockInsuficiente, existencias, formato_cantidad, registrar_movimiento

from .models import DetalleOrdenCompra, DetalleRecepcion, OrdenCompra, RecepcionCompra

CERO = Decimal("0")
CENT = Decimal("0.01")
IVA = Decimal(settings.SPVCI["IVA"])


class CompraError(Exception):
    """Errores de validación. .errores tiene la lista completa para mostrarla en pantalla."""

    def __init__(self, errores):
        self.errores = errores if isinstance(errores, list) else [errores]
        super().__init__("; ".join(self.errores))


def dinero(v):
    return Decimal(v).quantize(CENT, rounding=ROUND_HALF_UP)


# ================================================================== Órdenes de compra

def recibido_por_partida(orden):
    filas = (
        DetalleRecepcion.objects.filter(detalle_orden__orden_compra=orden, recepcion__estado=RecepcionCompra.Estado.APLICADA)
        .values("detalle_orden_id")
        .annotate(t=Sum("cantidad_recibida"))
    )
    return {f["detalle_orden_id"]: f["t"] for f in filas}


def partidas_pendientes(orden):
    """[(detalle_orden, pendiente)] de una orden, en el orden de captura."""
    recibido = recibido_por_partida(orden)
    out = []
    for d in orden.detalles.select_related("producto").order_by("id"):
        out.append((d, max(d.cantidad - recibido.get(d.id, CERO), CERO)))
    return out


def actualizar_estado_orden(orden):
    pend = partidas_pendientes(orden)
    recibido_algo = any(p < d.cantidad for d, p in pend)
    if all(p == 0 for _, p in pend):
        orden.estado = OrdenCompra.Estado.RECIBIDA
    elif recibido_algo:
        orden.estado = OrdenCompra.Estado.PARCIAL
    else:
        orden.estado = OrdenCompra.Estado.AUTORIZADA
    orden.save(update_fields=["estado"])
    return orden.estado


def en_camino(producto_id, sucursal_id):
    """Unidades pendientes de recibir en órdenes vigentes (BORRADOR, AUTORIZADA o PARCIAL)."""
    ordenes = OrdenCompra.objects.filter(
        sucursal_id=sucursal_id,
        estado__in=[OrdenCompra.Estado.BORRADOR, OrdenCompra.Estado.AUTORIZADA, OrdenCompra.Estado.PARCIAL],
        detalles__producto_id=producto_id,
    ).distinct()
    total = CERO
    for o in ordenes:
        for d, p in partidas_pendientes(o):
            if d.producto_id == producto_id:
                total += p
    return total


def prioridad(producto, cantidad):
    if cantidad <= 0 or cantidad <= (producto.stock_minimo * Decimal("0.5")).to_integral_value(rounding="ROUND_CEILING"):
        return "Alta"
    if cantidad <= producto.stock_minimo:
        return "Media"
    return "Baja"


def sugerencias_abastecimiento(sucursales):
    """
    Lista automática (CP-05-01): productos en o bajo el mínimo por almacén.
    Cantidad para pedir = stock máximo − existencia − en camino.
    """
    productos = list(Producto.objects.filter(activo=True).exclude(tipo=Producto.Tipo.SERVICIO).select_related("proveedor"))
    ex = existencias(sucursales=sucursales, productos=productos)
    lineas = []
    for p in productos:
        for s in sucursales:
            cant = ex[(p.id, s.id)]
            if cant <= p.stock_minimo:
                camino = en_camino(p.id, s.id)
                sug = max(CERO, p.stock_maximo - cant - camino)
                lineas.append(
                    {
                        "producto": p,
                        "sucursal": s,
                        "proveedor_id": p.proveedor_id,
                        "existencia": cant,
                        "en_camino": camino,
                        "sugerida": sug,
                        "cantidad": sug,
                        "prioridad": prioridad(p, cant),
                        "seleccionada": sug > 0,
                    }
                )
    orden = {"Alta": 0, "Media": 1, "Baja": 2}
    lineas.sort(key=lambda x: (orden[x["prioridad"]], x["proveedor_id"] or 0, x["producto"].sku))
    return lineas


@dataclass
class LineaSolicitud:
    producto: Producto
    sucursal: object
    proveedor: object
    cantidad: Decimal
    prioridad: str = "Media"


def validar_solicitud(lineas):
    errores = []
    if not lineas:
        errores.append("Selecciona al menos un producto.")
    for l in lineas:
        etiqueta = f"{l.producto.sku} ({l.sucursal.corto})"
        if l.cantidad is None or l.cantidad < 1 or l.cantidad != l.cantidad.to_integral_value():
            errores.append(f"{etiqueta}: la cantidad solicitada debe ser un entero mayor o igual a 1.")
        elif l.cantidad > l.producto.stock_maximo * 2:
            errores.append(
                f"{l.producto.sku}: {formato_cantidad(l.cantidad)} excede el doble del stock máximo "
                f"({formato_cantidad(l.producto.stock_maximo * 2)}); ajusta la cantidad."
            )
        if l.proveedor is None:
            errores.append(f"{l.producto.sku}: selecciona el proveedor.")
    return errores


@transaction.atomic
def enviar_solicitud(*, lineas, usuario, observaciones=""):
    """
    Genera una orden de compra por proveedor y almacén (CP-05-02).
    Si la envía un Almacenista queda «Por autorizar» (BORRADOR); si la envía Gerente o
    Administrador queda «Enviada · por recibir» (AUTORIZADA) — CP-05-05.
    """
    errores = validar_solicitud(lineas)
    if errores:
        raise CompraError(errores)
    autoriza = usuario.puede("autorizar_oc")
    estado = OrdenCompra.Estado.AUTORIZADA if autoriza else OrdenCompra.Estado.BORRADOR
    grupos = OrderedDict()
    for l in lineas:
        grupos.setdefault((l.proveedor.id, l.sucursal.id), []).append(l)
    entrega = sumar_dias_habiles(hoy(), settings.SPVCI["DIAS_ENTREGA_PROVEEDOR"])
    ordenes = []
    for (_, _), ls in grupos.items():
        folio = siguiente_folio(OrdenCompra, "folio", "OC-", 4, "orden_compra")
        orden = OrdenCompra.objects.create(
            proveedor=ls[0].proveedor,
            sucursal=ls[0].sucursal,
            creado_por=usuario,
            folio=folio,
            fecha_estimada=entrega,
            estado=estado,
            observaciones=observaciones or None,
        )
        por_producto = OrderedDict()
        for l in ls:
            por_producto[l.producto.id] = por_producto.get(l.producto.id, CERO) + l.cantidad
        for pid, cant in por_producto.items():
            p = next(x.producto for x in ls if x.producto.id == pid)
            DetalleOrdenCompra.objects.create(
                orden_compra=orden, producto=p, cantidad=cant, costo_unitario=p.precio_compra, tasa_iva=p.tasa_iva
            )
        registrar_bitacora(usuario=usuario, entidad="ORDEN_COMPRA", registro_id=orden.id, accion="ALTA",
                           campo="Estado", nuevo=orden.get_estado_display(), motivo=observaciones or None)
        ordenes.append(orden)
    return ordenes


@transaction.atomic
def autorizar_orden(orden, usuario):
    if not usuario.puede("autorizar_oc"):
        raise CompraError("Tu rol no puede autorizar órdenes de compra.")
    orden = OrdenCompra.objects.select_for_update().get(pk=orden.pk)
    if orden.estado != OrdenCompra.Estado.BORRADOR:
        raise CompraError(f"{orden.folio} no está pendiente de autorización.")
    orden.estado = OrdenCompra.Estado.AUTORIZADA
    if not orden.fecha_estimada:
        orden.fecha_estimada = sumar_dias_habiles(hoy(), settings.SPVCI["DIAS_ENTREGA_PROVEEDOR"])
    orden.save(update_fields=["estado", "fecha_estimada"])
    registrar_bitacora(usuario=usuario, entidad="ORDEN_COMPRA", registro_id=orden.id, accion="AUTORIZACION",
                       campo="Estado", anterior="Por autorizar", nuevo=orden.get_estado_display())
    return orden


# ================================================================== Recibo de mercancía

@dataclass
class LineaRecepcion:
    detalle_orden_id: int | None
    producto: Producto
    cantidad: Decimal
    costo: Decimal


def totales_recepcion(lineas):
    unidades = sum((l.cantidad for l in lineas), CERO)
    sub = dinero(sum((l.cantidad * l.costo for l in lineas), CERO))
    iva = dinero(sub * IVA)
    return {"unidades": unidades, "subtotal": sub, "iva": iva, "total": sub + iva}


def validar_recepcion(*, orden, fecha, lineas, observaciones, completo=True):
    """Mismas validaciones y mensajes que validarRec() del demo (CP-04-02, 03, 05, 06)."""
    errores = []
    if orden is None:
        errores.append("Selecciona el número de orden de compra.")
    if not fecha:
        errores.append("Captura la fecha de recepción.")
    elif fecha > hoy():
        errores.append(f"La fecha de recepción no puede ser posterior a hoy ({fecha_texto(hoy())}).")
    if orden is not None and not orden.pendiente_de_recibir and orden.estado != OrdenCompra.Estado.BORRADOR:
        errores.append(f"{orden.folio} no tiene partidas por recibir ({orden.get_estado_display().lower()}).")
    if orden is not None and orden.estado == OrdenCompra.Estado.BORRADOR:
        errores.append(f"{orden.folio} aún no está autorizada por el Gerente.")
    if not completo or orden is None:
        return errores
    pend = {d.id: p for d, p in partidas_pendientes(orden)}
    if not lineas or all(l.cantidad <= 0 for l in lineas):
        errores.append("Captura al menos un producto con cantidad recibida mayor a 0.")
    for l in lineas:
        sku = l.producto.sku
        if l.detalle_orden_id not in pend:
            errores.append(f"{sku} no forma parte de {orden.folio}. Retíralo o registra una orden nueva.")
        elif l.cantidad > pend[l.detalle_orden_id]:
            errores.append(
                f"{sku}: se recibieron {formato_cantidad(l.cantidad)} y la orden sólo tiene "
                f"{formato_cantidad(pend[l.detalle_orden_id])} pendientes."
            )
        if not l.costo or l.costo <= 0:
            errores.append(f"{sku}: el costo unitario debe ser mayor a 0.")
    total_pendiente = sum(pend.values(), CERO)
    total_recibido = sum((l.cantidad for l in lineas if l.detalle_orden_id in pend), CERO)
    if total_recibido < total_pendiente and len((observaciones or "").strip()) < 5:
        errores.append("La recepción es parcial: describe el motivo en observaciones.")
    return errores


def es_parcial(orden, lineas):
    pend = sum((p for _, p in partidas_pendientes(orden)), CERO)
    return sum((l.cantidad for l in lineas), CERO) < pend


def _fecha_hora(fecha):
    ahora = timezone.localtime()
    return timezone.make_aware(datetime.combine(fecha, ahora.time())) if fecha != ahora.date() else ahora


def _guardar_detalles(recepcion, lineas):
    recepcion.detalles.all().delete()
    for l in lineas:
        if l.cantidad > 0:
            DetalleRecepcion.objects.create(
                recepcion=recepcion,
                detalle_orden_id=l.detalle_orden_id,
                producto=l.producto,
                cantidad_recibida=l.cantidad,
                costo_unitario_real=l.costo,
            )


@transaction.atomic
def guardar_borrador(*, recepcion, orden, fecha, documento, observaciones, lineas, usuario):
    """CP-04-07: el borrador se conserva sin afectar el inventario."""
    errores = validar_recepcion(orden=orden, fecha=fecha, lineas=lineas, observaciones=observaciones, completo=False)
    ajenos = [l.producto.sku for l in lineas if l.detalle_orden_id is None]
    if ajenos:
        errores.append(f"{', '.join(ajenos)} no forma parte de {orden.folio}. Retíralo para guardar el borrador.")
    if errores:
        raise CompraError(errores)
    if recepcion is None:
        recepcion = RecepcionCompra(
            folio_recepcion=siguiente_folio(RecepcionCompra, "folio_recepcion", f"REC-{hoy():%Y}-", 4, "recepcion"),
            recibido_por=usuario,
        )
    elif recepcion.estado != RecepcionCompra.Estado.BORRADOR:
        raise CompraError("Solo se puede editar una recepción en borrador.")
    recepcion.orden_compra = orden
    recepcion.fecha_recepcion = _fecha_hora(fecha)
    recepcion.documento_proveedor = documento or None
    recepcion.observaciones = observaciones or None
    recepcion.estado = RecepcionCompra.Estado.BORRADOR
    recepcion.save()
    _guardar_detalles(recepcion, lineas)
    return recepcion


@transaction.atomic
def registrar_recepcion(*, recepcion, orden, fecha, documento, observaciones, lineas, usuario):
    """
    Confirma la recepción (CP-04-01 / CP-04-04): guarda las partidas, suma existencias con
    movimientos ENTRADA_COMPRA y actualiza el estado de la orden (Recibida o Parcial).
    """
    orden = OrdenCompra.objects.select_for_update().get(pk=orden.pk)  # serializa recepciones de la misma OC
    errores = validar_recepcion(orden=orden, fecha=fecha, lineas=lineas, observaciones=observaciones)
    if errores:
        raise CompraError(errores)
    lineas = [l for l in lineas if l.cantidad > 0]
    if recepcion is None:
        recepcion = RecepcionCompra(
            folio_recepcion=siguiente_folio(RecepcionCompra, "folio_recepcion", f"REC-{hoy():%Y}-", 4, "recepcion"),
        )
    elif recepcion.estado != RecepcionCompra.Estado.BORRADOR:
        raise CompraError("Esta recepción ya fue registrada.")
    recepcion.orden_compra = orden
    recepcion.recibido_por = usuario
    recepcion.fecha_recepcion = _fecha_hora(fecha)
    recepcion.documento_proveedor = documento or None
    recepcion.observaciones = observaciones or None
    recepcion.estado = RecepcionCompra.Estado.APLICADA
    recepcion.save()
    _guardar_detalles(recepcion, lineas)
    for d in recepcion.detalles.select_related("producto"):
        registrar_movimiento(
            sucursal=orden.sucursal,
            producto=d.producto,
            tipo=MovimientoInventario.Tipo.ENTRADA_COMPRA,
            cantidad=d.cantidad_recibida,
            costo_unitario=d.costo_unitario_real,
            usuario=usuario,
            detalle_recepcion=d,
            observaciones=f"Recepción {recepcion.folio_recepcion} de {orden.folio}",
        )
    actualizar_estado_orden(orden)
    return recepcion


@transaction.atomic
def cancelar_recepcion(recepcion, usuario, motivo):
    """
    Borrador → se descarta. Aplicada → movimientos REVERSA en el kárdex y la orden vuelve a
    quedar pendiente (CP-04-08).
    """
    motivo = (motivo or "").strip()
    recepcion = RecepcionCompra.objects.select_for_update().select_related("orden_compra__sucursal").get(pk=recepcion.pk)
    if recepcion.estado == RecepcionCompra.Estado.CANCELADA:
        raise CompraError("La recepción ya está cancelada.")
    if recepcion.estado == RecepcionCompra.Estado.BORRADOR:
        recepcion.estado = RecepcionCompra.Estado.CANCELADA
        recepcion.save(update_fields=["estado"])
        return recepcion
    if len(motivo) < 5:
        raise CompraError("Escribe el motivo (mínimo 5 caracteres).")
    orden = OrdenCompra.objects.select_for_update().get(pk=recepcion.orden_compra_id)
    try:
        for d in recepcion.detalles.select_related("producto"):
            registrar_movimiento(
                sucursal=orden.sucursal,
                producto=d.producto,
                tipo=MovimientoInventario.Tipo.REVERSA,
                cantidad=d.cantidad_recibida,
                costo_unitario=d.costo_unitario_real,
                usuario=usuario,
                detalle_recepcion=d,
                observaciones=motivo,
            )
    except StockInsuficiente as exc:
        raise CompraError(
            f"No se puede cancelar: {exc.producto.sku} ya no tiene existencia suficiente en "
            f"{exc.sucursal.corto} para revertir la entrada."
        ) from exc
    recepcion.estado = RecepcionCompra.Estado.CANCELADA
    recepcion.observaciones = f"{recepcion.observaciones + ' · ' if recepcion.observaciones else ''}Cancelada: {motivo}"
    recepcion.save(update_fields=["estado", "observaciones"])
    actualizar_estado_orden(orden)
    registrar_bitacora(usuario=usuario, entidad="RECEPCION_COMPRA", registro_id=recepcion.id, accion="CANCELACION",
                       campo="Estado", anterior="Aplicada", nuevo="Cancelada", motivo=motivo)
    return recepcion


def fecha_confirmacion(recepcion):
    m = MovimientoInventario.objects.filter(
        detalle_recepcion__recepcion=recepcion, tipo=MovimientoInventario.Tipo.ENTRADA_COMPRA
    ).order_by("fecha_movimiento").first()
    return m.fecha_movimiento if m else None
