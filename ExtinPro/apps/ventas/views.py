import json
import uuid
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Max
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from apps.catalogo.models import CATEGORIAS, Cliente, Producto
from apps.core.services import hoy
from apps.inventario.services import estado_stock, existencias
from apps.usuarios.decoradores import requiere_modulo

from .models import Caja, Pago, SesionCaja, Venta
from .services import (
    LineaVenta,
    VentaError,
    abrir_sesion,
    cancelar_venta,
    cerrar_sesion,
    puede_cambiar_precio,
    registrar_venta,
    totales_sesion,
)

SESION_CAJA = "sesion_caja_id"


def sesion_actual(request):
    """Sesión de caja que usa este navegador, validada contra el almacén activo."""
    sid = request.session.get(SESION_CAJA)
    s = (
        SesionCaja.objects.select_related("caja__sucursal", "abierto_por")
        .filter(pk=sid, estado=SesionCaja.Estado.ABIERTA, caja__sucursal=request.sucursal)
        .first()
        if sid
        else None
    )
    if s is None:
        s = (
            SesionCaja.objects.select_related("caja__sucursal", "abierto_por")
            .filter(estado=SesionCaja.Estado.ABIERTA, caja__sucursal=request.sucursal, abierto_por=request.user)
            .first()
        )
        if s:
            request.session[SESION_CAJA] = s.pk
    return s


def folio_siguiente():
    ultimo = Venta.objects.filter(folio__startswith="VT-").aggregate(m=Max("folio"))["m"]
    n = int(ultimo[3:]) + 1 if ultimo else 1
    return f"VT-{n:06d}"


@requiere_modulo("ventas")
def pos(request):
    """Ventas: punto de venta (E7 · Fig. 30 a 34)."""
    sesion = sesion_actual(request)
    if sesion is None:
        cajas = Caja.objects.filter(sucursal=request.sucursal, activa=True).order_by("codigo")
        abiertas = {s.caja_id: s for s in SesionCaja.objects.filter(caja__in=cajas, estado="ABIERTA").select_related("abierto_por")}
        return render(request, "ventas/abrir_caja.html", {"cajas": [(c, abiertas.get(c.id)) for c in cajas]})

    productos = list(Producto.objects.filter(activo=True).select_related("modelo_extintor").order_by("categoria", "sku"))
    ex = existencias(sucursales=[request.sucursal], productos=productos)
    for p in productos:
        p.existencia = None if p.es_servicio else ex[(p.id, request.sucursal.id)]
    clientes = Cliente.objects.filter(activo=True).order_by("id")
    datos = {
        str(p.id): {
            "id": p.id,
            "sku": p.sku,
            "nombre": p.nombre,
            "cat": p.categoria,
            "tipo": p.tipo,
            "cb": p.codigo_barras or "",
            "precio": str(p.precio_venta),
            "iva": str(p.tasa_iva),
            "min": str(p.stock_minimo),
            "stock": None if p.existencia is None else str(p.existencia),
            "unidad": p.unidad_medida,
        }
        for p in productos
    }
    return render(
        request,
        "ventas/pos.html",
        {
            "sesion": sesion,
            "productos": productos,
            "categorias": ["Todos"] + [c for c in CATEGORIAS if any(p.categoria == c for p in productos)],
            "clientes": clientes,
            "datos_productos": datos,
            "datos_clientes": {str(c.id): {"desc": str(c.descuento_pct), "correo": c.correo or ""} for c in clientes},
            "folio": folio_siguiente(),
            "ahora": hoy(),
            "puede_precio": puede_cambiar_precio(request.user),
            "uuid": uuid.uuid4(),
        },
    )


@require_POST
@requiere_modulo("ventas")
def caja_abrir(request):
    caja = get_object_or_404(Caja, pk=request.POST.get("caja"), sucursal=request.sucursal, activa=True)
    existente = SesionCaja.objects.filter(caja=caja, estado="ABIERTA").first()
    if existente:
        request.session[SESION_CAJA] = existente.pk
        messages.info(request, f"Usando la sesión abierta de {caja.codigo}.")
        return redirect("ventas:pos")
    try:
        fondo = Decimal(request.POST.get("fondo_inicial") or "0")
        s = abrir_sesion(caja=caja, usuario=request.user, fondo_inicial=fondo)
    except (VentaError, InvalidOperation) as e:
        messages.error(request, getattr(e, "errores", ["Fondo inicial inválido."])[0])
        return redirect("ventas:pos")
    request.session[SESION_CAJA] = s.pk
    messages.success(request, f"Caja {caja.codigo} abierta", extra_tags=f"Fondo inicial ${s.fondo_inicial:,.2f}")
    return redirect("ventas:pos")


@requiere_modulo("ventas")
def caja(request):
    """Corte de caja: arqueo y cierre de la sesión (ARQUEO_CAJA)."""
    sesion = sesion_actual(request)
    errores = []
    if request.method == "POST" and sesion:
        try:
            arqueo = cerrar_sesion(
                sesion=sesion,
                usuario=request.user,
                efectivo_contado=Decimal(request.POST.get("efectivo_contado") or "0"),
                tarjeta_reportado=Decimal(request.POST.get("tarjeta_reportado") or "0"),
                observaciones=request.POST.get("observaciones", ""),
            )
        except InvalidOperation:
            errores = ["Captura importes válidos."]
        except VentaError as e:
            errores = e.errores
        else:
            request.session.pop(SESION_CAJA, None)
            arqueo.refresh_from_db()
            messages.success(request, f"Caja {sesion.caja.codigo} cerrada", extra_tags=f"Diferencia del arqueo: ${arqueo.diferencia:,.2f}")
            return redirect("ventas:caja")
    historial = (
        SesionCaja.objects.filter(caja__sucursal=request.sucursal)
        .select_related("caja", "abierto_por", "cerrado_por")
        .prefetch_related("arqueos")
        .order_by("-id")[:15]
    )
    return render(
        request,
        "ventas/caja.html",
        {"sesion": sesion, "totales": totales_sesion(sesion) if sesion else None, "historial": historial, "errores": errores},
    )


def _decimal(valor, defecto=None):
    if valor in (None, ""):
        return defecto
    try:
        return Decimal(str(valor))
    except InvalidOperation:
        raise VentaError("Hay un importe o cantidad con formato inválido.")


@require_POST
@requiere_modulo("ventas")
def registrar(request):
    """API del POS: registra la venta y devuelve el ticket y las existencias después de la venta."""
    sesion = sesion_actual(request)
    if sesion is None:
        return JsonResponse({"ok": False, "errores": ["Abre la caja para vender."]}, status=409)
    try:
        data = json.loads(request.body)
        cliente = get_object_or_404(Cliente, pk=int(data.get("cliente")), activo=True)
        lineas = [
            LineaVenta(
                producto_id=int(l["producto"]),
                cantidad=_decimal(l.get("cantidad"), Decimal("0")),
                descuento_pct=_decimal(l.get("desc"), Decimal("0")),
                precio_unitario=_decimal(l.get("precio")),
            )
            for l in data.get("lineas", [])
        ]
        res = registrar_venta(
            sesion=sesion,
            usuario=request.user,
            cliente=cliente,
            lineas=lineas,
            metodo=data.get("metodo"),
            recibido=_decimal(data.get("recibido")),
            referencia=str(data.get("referencia") or ""),
            uuid_operacion=uuid.UUID(str(data.get("uuid"))),
        )
    except VentaError as e:
        return JsonResponse({"ok": False, "errores": e.errores}, status=400)
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return JsonResponse({"ok": False, "errores": ["Solicitud inválida."]}, status=400)

    v = res.venta
    ticket = render_to_string(
        "ventas/_ticket.html", {"v": v, "pagado": res.pagado, "cambio": res.cambio}, request=request
    )
    return JsonResponse(
        {
            "ok": True,
            "creada": res.creada,
            "folio": v.folio,
            "total": str(v.total),
            "pagado": str(res.pagado),
            "cambio": str(res.cambio),
            "metodo": v.pagos.first().get_metodo_display() if v.pagos.exists() else "",
            "ticket_url": f"/ventas/{v.pk}/ticket/",
            "ticket_html": ticket,
            "correo": v.cliente.correo or "",
            "existencias": [
                {"id": e["producto"].id, "sku": e["producto"].sku, "antes": str(e["antes"]), "despues": str(e["despues"]),
                 "estado": e["estado"][1], "clase": e["estado"][0]}
                for e in res.existencias
            ],
            "alertas": [
                {"sku": a["producto"].sku, "existencia": str(a["existencia"]), "minimo": str(a["producto"].stock_minimo)}
                for a in res.alertas
            ],
            "siguiente_folio": folio_siguiente(),
        },
        status=201 if res.creada else 200,
    )


@requiere_modulo("ventas")
def ticket(request, pk):
    v = get_object_or_404(Venta.objects.select_related("cliente", "sucursal", "creado_por"), pk=pk, sucursal__in=request.sucursales)
    pago = v.pagos.filter(tipo=Pago.Tipo.COBRO).first()
    return render(request, "ventas/ticket.html", {"v": v, "pagado": pago.monto if pago else v.total, "cambio": None})


@requiere_modulo("ventas")
def lista(request):
    desde = parse_date(request.GET.get("desde", "") or "") or hoy()
    hasta = parse_date(request.GET.get("hasta", "") or "") or hoy()
    qs = (
        Venta.objects.filter(sucursal__in=request.sucursales, fecha_venta__date__gte=desde, fecha_venta__date__lte=hasta)
        .select_related("cliente", "creado_por", "sucursal")
        .prefetch_related("pagos")
    )
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(folio__icontains=q)
    pagina = Paginator(qs, 25).get_page(request.GET.get("page"))
    return render(request, "ventas/lista.html", {"pagina": pagina, "desde": desde, "hasta": hasta, "q": q})


@requiere_modulo("ventas")
def detalle(request, pk):
    v = get_object_or_404(
        Venta.objects.select_related("cliente", "sucursal", "creado_por", "cancelado_por", "sesion_caja__caja"),
        pk=pk,
        sucursal__in=request.sucursales,
    )
    errores = []
    if request.method == "POST":
        try:
            cancelar_venta(venta=v, usuario=request.user, motivo=request.POST.get("motivo", ""), sesion_actual=sesion_actual(request))
        except PermissionDenied as e:
            errores = [str(e)]
        except VentaError as e:
            errores = e.errores
        else:
            messages.warning(request, f"Venta {v.folio} cancelada", extra_tags="Se registró la reversa en el kárdex.")
            return redirect("ventas:detalle", pk=v.pk)
    detalles = list(v.detalles.select_related("producto"))
    for d in detalles:
        d.estado_actual = estado_stock(d.producto, Decimal("1"))
    pago = v.pagos.filter(tipo=Pago.Tipo.COBRO).first()
    return render(
        request,
        "ventas/detalle.html",
        {"v": v, "detalles": detalles, "pagos": v.pagos.select_related("sesion_caja__caja"), "errores": errores,
         "pagado": pago.monto if pago else v.total, "cambio": None},
    )
