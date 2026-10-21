from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from apps.catalogo.models import Producto, Proveedor
from apps.core.services import hoy, sumar_dias_habiles
from apps.inventario.services import estado_stock, existencias
from apps.usuarios.decoradores import requiere_modulo

from .models import OrdenCompra, RecepcionCompra
from .services import (
    CompraError,
    LineaRecepcion,
    LineaSolicitud,
    autorizar_orden,
    cancelar_recepcion,
    en_camino,
    enviar_solicitud,
    fecha_confirmacion,
    guardar_borrador,
    partidas_pendientes,
    prioridad,
    registrar_recepcion,
    sugerencias_abastecimiento,
    totales_recepcion,
)

CERO = Decimal("0")


def _dec(v, defecto=CERO):
    try:
        return Decimal(str(v)) if v not in (None, "") else defecto
    except InvalidOperation:
        return defecto


# ================================================================== Recibo de mercancía

def _ordenes_pendientes(request):
    return (
        OrdenCompra.objects.filter(
            sucursal__in=request.sucursales, estado__in=[OrdenCompra.Estado.AUTORIZADA, OrdenCompra.Estado.PARCIAL]
        )
        .select_related("proveedor", "sucursal")
        .order_by("folio")
    )


def _lineas_desde_orden(orden):
    return [
        {"detalle_orden_id": d.id, "producto": d.producto, "pendiente": p, "cantidad": p, "costo": d.costo_unitario, "en_oc": True}
        for d, p in partidas_pendientes(orden)
        if p > 0
    ]


def _lineas_desde_recepcion(rec):
    pend = {d.id: p for d, p in partidas_pendientes(rec.orden_compra)}
    out = []
    for d in rec.detalles.select_related("producto", "detalle_orden"):
        base = pend.get(d.detalle_orden_id, CERO)
        if rec.estado == RecepcionCompra.Estado.APLICADA:
            base += d.cantidad_recibida  # lo que estaba pendiente antes de aplicar
        out.append(
            {"detalle_orden_id": d.detalle_orden_id, "producto": d.producto, "pendiente": base if rec.estado != "CANCELADA" else d.detalle_orden.cantidad,
             "cantidad": d.cantidad_recibida, "costo": d.costo_unitario_real, "en_oc": True,
             "importe": (d.cantidad_recibida * d.costo_unitario_real).quantize(Decimal("0.01"))}
        )
    return out


def _lineas_post(request, orden):
    detalles = {d.id: (d, p) for d, p in partidas_pendientes(orden)} if orden else {}
    productos = {str(p.pk): p for p in Producto.objects.filter(pk__in=request.POST.getlist("producto"))}
    lineas = []
    for det_id, prod_id, cant, costo in zip(
        request.POST.getlist("detalle_orden"),
        request.POST.getlist("producto"),
        request.POST.getlist("cantidad"),
        request.POST.getlist("costo"),
    ):
        p = productos.get(prod_id)
        if p is None:
            continue
        det = int(det_id) if det_id.isdigit() and int(det_id) in detalles and detalles[int(det_id)][0].producto_id == p.pk else None
        lineas.append(
            {"detalle_orden_id": det, "producto": p, "pendiente": detalles[det][1] if det else CERO,
             "cantidad": _dec(cant), "costo": _dec(costo), "en_oc": det is not None}
        )
    return lineas


def _ctx_recepcion(request, rec, orden, lineas, datos, errores=None):
    bloqueada = rec is not None and rec.estado in (RecepcionCompra.Estado.APLICADA, RecepcionCompra.Estado.CANCELADA)
    pendientes = list(_ordenes_pendientes(request))
    if orden and orden not in pendientes:
        pendientes.insert(0, orden)
    otros = Producto.objects.filter(activo=True).exclude(tipo=Producto.Tipo.SERVICIO).order_by("sku")
    t = totales_recepcion([LineaRecepcion(l["detalle_orden_id"], l["producto"], l["cantidad"], l["costo"]) for l in lineas])
    recientes = RecepcionCompra.objects.filter(orden_compra__sucursal__in=request.sucursales).select_related(
        "orden_compra__proveedor", "orden_compra__sucursal"
    ).prefetch_related("detalles")[:6]
    for r in recientes:
        r.totales = totales_recepcion(
            [LineaRecepcion(d.detalle_orden_id, None, d.cantidad_recibida, d.costo_unitario_real) for d in r.detalles.all()]
        )
    return {
        "rec": rec,
        "orden": orden,
        "lineas": lineas,
        "datos": datos,
        "errores": errores or [],
        "bloqueada": bloqueada,
        "proveedores": Proveedor.objects.filter(activo=True),
        "ordenes": pendientes,
        "otros_productos": otros,
        "totales": t,
        "recientes": recientes,
        "total_recepciones": RecepcionCompra.objects.filter(orden_compra__sucursal__in=request.sucursales).count(),
        "confirmado": fecha_confirmacion(rec) if rec and rec.estado != "BORRADOR" else None,
        "iva_pct": int(Decimal(settings.SPVCI["IVA"]) * 100),
        "partidas_oc": partidas_pendientes(orden) if orden else [],
    }


@requiere_modulo("recepcion")
def recepcion(request):
    """Recibo de mercancía (E7 · Fig. 13 y 25 a 29 · SPVCI-OC-06 / OC-07)."""
    rec = None
    if request.GET.get("r"):
        rec = get_object_or_404(
            RecepcionCompra.objects.select_related("orden_compra__proveedor", "orden_compra__sucursal"),
            pk=request.GET["r"],
            orden_compra__sucursal__in=request.sucursales,
        )
        orden = rec.orden_compra
        lineas = _lineas_desde_recepcion(rec)
        datos = {"fecha": rec.fecha_recepcion.date(), "documento": rec.documento_proveedor or "", "observaciones": rec.observaciones or "", "proveedor": orden.proveedor_id}
    else:
        orden = None
        if request.GET.get("oc"):
            orden = get_object_or_404(OrdenCompra, pk=request.GET["oc"], sucursal__in=request.sucursales)
        elif request.GET.get("proveedor"):
            orden = _ordenes_pendientes(request).filter(proveedor_id=request.GET["proveedor"]).first()
        else:
            orden = _ordenes_pendientes(request).first()
        lineas = _lineas_desde_orden(orden) if orden else []
        datos = {"fecha": hoy(), "documento": "", "observaciones": "", "proveedor": orden.proveedor_id if orden else request.GET.get("proveedor", "")}
    return render(request, "compras/recepcion.html", _ctx_recepcion(request, rec, orden, lineas, datos))


@require_POST
@requiere_modulo("recepcion")
def recepcion_guardar(request):
    rec = None
    if request.POST.get("recepcion"):
        rec = get_object_or_404(RecepcionCompra, pk=request.POST["recepcion"], orden_compra__sucursal__in=request.sucursales)
    accion = request.POST.get("accion")
    if accion == "descartar":
        if rec is not None and rec.estado == RecepcionCompra.Estado.BORRADOR:
            cancelar_recepcion(rec, request.user, "")
        messages.info(request, "Captura descartada")
        return redirect("compras:recepcion")
    if accion == "cancelar" and rec is not None:
        try:
            cancelar_recepcion(rec, request.user, request.POST.get("motivo", ""))
        except CompraError as e:
            messages.error(request, "No se pudo cancelar la recepción", extra_tags=e.errores[0])
        else:
            messages.warning(request, f"Recepción {rec.folio_recepcion} cancelada", extra_tags="Se registró la reversa en el kárdex.")
        return redirect(reverse("compras:recepcion") + f"?r={rec.pk}")

    orden = OrdenCompra.objects.filter(pk=request.POST.get("orden") or 0, sucursal__in=request.sucursales).select_related("proveedor", "sucursal").first()
    fecha = parse_date(request.POST.get("fecha", "") or "")
    lineas = _lineas_post(request, orden)
    datos = {
        "fecha": fecha,
        "documento": request.POST.get("documento", "").strip(),
        "observaciones": request.POST.get("observaciones", "").strip(),
        "proveedor": request.POST.get("proveedor", ""),
    }
    objetos = [LineaRecepcion(l["detalle_orden_id"], l["producto"], l["cantidad"], l["costo"]) for l in lineas]
    try:
        kwargs = dict(recepcion=rec, orden=orden, fecha=fecha, documento=datos["documento"], observaciones=datos["observaciones"], lineas=objetos, usuario=request.user)
        if accion == "borrador":
            if orden is None:
                raise CompraError(["Selecciona el número de orden de compra."])
            rec = guardar_borrador(**kwargs)
            messages.info(request, "Borrador guardado", extra_tags=f"{rec.folio_recepcion} no afecta el inventario hasta registrarse.")
        else:
            if orden is None:
                raise CompraError(["Selecciona el proveedor.", "Selecciona el número de orden de compra."])
            rec = registrar_recepcion(**kwargs)
            rec.orden_compra.refresh_from_db()
            unidades = totales_recepcion(objetos)["unidades"]
            messages.success(
                request,
                f"Recepción {rec.folio_recepcion} confirmada",
                extra_tags=f"Stock actualizado: +{unidades.normalize():f} unidades en {orden.sucursal.corto}. {orden.folio} quedó como “{rec.orden_compra.get_estado_display()}”.",
            )
    except CompraError as e:
        ctx = _ctx_recepcion(request, rec, orden, lineas, datos, e.errores)
        return render(request, "compras/recepcion.html", ctx, status=400)
    return redirect(reverse("compras:recepcion") + f"?r={rec.pk}")


@requiere_modulo("recepcion")
def comprobante_recepcion(request, pk):
    rec = get_object_or_404(
        RecepcionCompra.objects.select_related("orden_compra__proveedor", "orden_compra__sucursal", "recibido_por"),
        pk=pk,
        orden_compra__sucursal__in=request.sucursales,
    )
    lineas = _lineas_desde_recepcion(rec)
    t = totales_recepcion([LineaRecepcion(l["detalle_orden_id"], l["producto"], l["cantidad"], l["costo"]) for l in lineas])
    parcial = rec.orden_compra.estado == OrdenCompra.Estado.PARCIAL
    return render(
        request,
        "compras/comprobante_recepcion.html",
        {"rec": rec, "lineas": lineas, "t": t, "confirmado": fecha_confirmacion(rec), "parcial": parcial},
    )


# ================================================================== Abastecimiento

def _info_productos(productos, sucursales):
    ex = existencias(sucursales=sucursales, productos=productos)
    info = {}
    for p in productos:
        for s in sucursales:
            cant = ex[(p.id, s.id)]
            camino = en_camino(p.id, s.id)
            clase, texto = estado_stock(p, cant)
            info[f"{p.id}-{s.id}"] = {
                "existencia": str(cant),
                "estado": texto,
                "clase": clase,
                "en_camino": str(camino),
                "sugerida": str(max(CERO, p.stock_maximo - cant - camino)),
                "prioridad": prioridad(p, cant),
            }
    return info


@requiere_modulo("abastecimiento")
def abastecimiento(request):
    """Solicitud de reabastecimiento (E7 · Fig. 35 a 37 · SPVCI-OC-01 a OC-04)."""
    enviadas = []
    if request.GET.get("enviadas"):
        ids = [int(x) for x in request.GET["enviadas"].split(",") if x.isdigit()]
        enviadas = list(OrdenCompra.objects.filter(pk__in=ids, sucursal__in=request.sucursales).select_related("proveedor", "sucursal").prefetch_related("detalles__producto"))
    lineas = [] if enviadas else sugerencias_abastecimiento(request.sucursales)
    productos = list(Producto.objects.filter(activo=True).exclude(tipo=Producto.Tipo.SERVICIO).select_related("proveedor").order_by("sku"))
    return render(
        request,
        "compras/abastecimiento.html",
        {
            "lineas": lineas,
            "enviadas": enviadas,
            "proveedores": Proveedor.objects.filter(activo=True),
            "productos": productos,
            "datos_productos": {
                str(p.id): {"sku": p.sku, "nombre": p.nombre, "costo": str(p.precio_compra), "min": str(p.stock_minimo),
                            "max": str(p.stock_maximo), "prov": p.proveedor_id}
                for p in productos
            },
            "datos_existencias": _info_productos(productos, request.sucursales),
            "datos_proveedores": {str(p.id): p.nombre_razon_social for p in Proveedor.objects.filter(activo=True)},
            "datos_sucursales": {str(s.id): s.corto for s in request.sucursales},
            "entrega_prevista": sumar_dias_habiles(hoy(), settings.SPVCI["DIAS_ENTREGA_PROVEEDOR"]),
            "errores": request.session.pop("abas_errores", []),
            "total_enviadas": sum((o.importe() for o in enviadas), CERO),
        },
    )


def _lineas_solicitud(request):
    seleccion = set(request.POST.getlist("sel"))
    productos = {str(p.pk): p for p in Producto.objects.filter(pk__in=request.POST.getlist("producto"))}
    proveedores = {str(p.pk): p for p in Proveedor.objects.filter(activo=True)}
    sucursales = {str(s.pk): s for s in request.sucursales}
    lineas = []
    for i, (pid, sid, prov, cant, pri) in enumerate(
        zip(request.POST.getlist("producto"), request.POST.getlist("sucursal"), request.POST.getlist("proveedor"),
            request.POST.getlist("cantidad"), request.POST.getlist("prioridad"))
    ):
        if str(i) not in seleccion or pid not in productos or sid not in sucursales:
            continue
        try:
            c = Decimal(cant)
        except InvalidOperation:
            c = None
        lineas.append(LineaSolicitud(productos[pid], sucursales[sid], proveedores.get(prov), c, pri))
    return lineas


@require_POST
@requiere_modulo("abastecimiento")
def abastecimiento_enviar(request):
    lineas = _lineas_solicitud(request)
    if request.POST.get("accion") == "vista_previa":
        grupos = {}
        for l in lineas:
            if l.proveedor and l.cantidad and l.cantidad > 0:
                grupos.setdefault((l.proveedor.pk, l.sucursal.pk), []).append(l)
        ordenes = [
            {
                "folio": "(por asignar)", "fecha_orden": hoy(), "proveedor": ls[0].proveedor, "sucursal": ls[0].sucursal,
                "fecha_estimada": sumar_dias_habiles(hoy(), settings.SPVCI["DIAS_ENTREGA_PROVEEDOR"]), "estado": "PREVIA",
                "creado_por": request.user, "observaciones": request.POST.get("observaciones", ""),
                "lineas": [{"producto": l.producto, "cantidad": l.cantidad, "costo": l.producto.precio_compra, "importe": l.cantidad * l.producto.precio_compra} for l in ls],
            }
            for ls in grupos.values()
        ]
        return render(request, "compras/comprobante_oc.html", {"ordenes": _con_totales(ordenes), "previa": True})
    try:
        ordenes = enviar_solicitud(lineas=lineas, usuario=request.user, observaciones=request.POST.get("observaciones", "").strip())
    except CompraError as e:
        messages.error(request, "Revisa la solicitud", extra_tags=e.errores[0])
        request.session["abas_errores"] = e.errores
        return redirect("compras:abastecimiento")
    pend = ordenes[0].estado == OrdenCompra.Estado.BORRADOR
    messages.success(request, "Solicitud enviada", extra_tags=", ".join(o.folio for o in ordenes) + (" · pendiente de autorización" if pend else " · por recibir"))
    return redirect(reverse("compras:abastecimiento") + f"?enviadas={','.join(str(o.pk) for o in ordenes)}")


def _con_totales(ordenes):
    iva = Decimal(settings.SPVCI["IVA"])
    for o in ordenes:
        sub = sum((l["importe"] for l in o["lineas"]), CERO).quantize(Decimal("0.01"))
        o.update({"subtotal": sub, "iva": (sub * iva).quantize(Decimal("0.01")), "total": (sub * (1 + iva)).quantize(Decimal("0.01"))})
    return ordenes


@requiere_modulo("abastecimiento")
def pedidos(request):
    """Consultar pedidos anteriores (E7 · Fig. 14 · SPVCI-OC-05) y autorizar (CP-05-05)."""
    if request.method == "POST":
        orden = get_object_or_404(OrdenCompra, pk=request.POST.get("orden"), sucursal__in=request.sucursales)
        try:
            autorizar_orden(orden, request.user)
        except CompraError as e:
            messages.error(request, e.errores[0])
        else:
            messages.success(request, f"{orden.folio} autorizada", extra_tags=f"Enviada a {orden.proveedor.nombre_razon_social}.")
        return redirect(request.get_full_path())
    estado = request.GET.get("estado", "")
    qs = OrdenCompra.objects.filter(sucursal__in=request.sucursales).select_related("proveedor", "sucursal").prefetch_related("detalles")
    if estado in OrdenCompra.Estado.values:
        qs = qs.filter(estado=estado)
    return render(request, "compras/pedidos.html", {"ordenes": qs[:200], "estado": estado, "estados": OrdenCompra.Estado.choices})


@requiere_modulo("abastecimiento")
def comprobante_oc(request):
    ids = [int(x) for x in request.GET.get("ids", "").split(",") if x.isdigit()]
    ordenes = []
    for o in OrdenCompra.objects.filter(pk__in=ids, sucursal__in=request.sucursales).select_related("proveedor", "sucursal", "creado_por").prefetch_related("detalles__producto"):
        ordenes.append(
            {
                "folio": o.folio, "fecha_orden": o.fecha_orden, "proveedor": o.proveedor, "sucursal": o.sucursal,
                "fecha_estimada": o.fecha_estimada, "estado": o.estado, "estado_txt": o.get_estado_display(),
                "creado_por": o.creado_por, "observaciones": o.observaciones,
                "lineas": [{"producto": d.producto, "cantidad": d.cantidad, "costo": d.costo_unitario, "importe": d.cantidad * d.costo_unitario} for d in o.detalles.all()],
            }
        )
    return render(request, "compras/comprobante_oc.html", {"ordenes": _con_totales(ordenes), "previa": False})
