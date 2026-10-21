from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from apps.catalogo.models import CATEGORIAS, Producto
from apps.core.models import Bitacora
from apps.usuarios.decoradores import requiere_modulo

from .fisico import ConteoError, autorizar_ajuste, capturar, cerrar_conteo, iniciar_conteo
from .models import InventarioFisico, MovimientoInventario
from .services import estado_stock, existencias, kardex

ESTADOS = ["Disponible", "Bajo mínimo", "Agotado", "Descontinuado"]
CERO = Decimal("0")


def _sucursal_filtro(request, valor):
    try:
        return next((s for s in request.sucursales_consulta if s.pk == int(valor)), None)
    except (TypeError, ValueError):
        return None


@requiere_modulo("inventario")
def consulta(request):
    """Inventario: vista general (E7 · Fig. 4, 5 y 6 · PROD-04 / PROD-05)."""
    f = {k: request.GET.get(k, "").strip() for k in ("q", "cat", "alm", "est")}
    sucursales = list(request.sucursales_consulta)
    productos = list(
        Producto.objects.exclude(tipo=Producto.Tipo.SERVICIO).select_related("modelo_extintor").order_by("sku")
    )
    ex = existencias(sucursales=sucursales, productos=productos)
    todas = []
    for p in productos:
        for s in sucursales:
            cant = ex[(p.id, s.id)]
            todas.append({"producto": p, "sucursal": s, "existencia": cant, "estado": estado_stock(p, cant)})

    q = f["q"].lower()
    alm = _sucursal_filtro(request, f["alm"])

    def coincide(x):
        p = x["producto"]
        if q and not (
            q in p.nombre.lower() or q in p.sku.lower() or (p.codigo_barras and q in p.codigo_barras) or q == str(p.id)
        ):
            return False
        if f["cat"] and p.categoria != f["cat"]:
            return False
        if alm and x["sucursal"].pk != alm.pk:
            return False
        if f["est"] and x["estado"][1] != f["est"]:
            return False
        return True

    filas = [x for x in todas if coincide(x)]
    pagina = Paginator(filas, 10).get_page(request.GET.get("page"))
    activos = [p for p in productos if p.activo]
    ctx = {
        "f": f,
        "sucursales_filtro": sucursales,
        "pagina": pagina,
        "total_filas": len(filas),
        "categorias": [c for c in CATEGORIAS if c != "Servicios"],
        "estados": ESTADOS,
        "n_activos": len(activos),
        "n_descontinuados": len(productos) - len(activos),
        "n_servicios": Producto.objects.filter(tipo=Producto.Tipo.SERVICIO).count(),
        "unidades": sum((x["existencia"] for x in todas), CERO),
        "unidades_por_sucursal": [(s, sum((x["existencia"] for x in todas if x["sucursal"] == s), CERO)) for s in sucursales],
        "n_bajo": sum(1 for x in todas if x["estado"][1] == "Bajo mínimo"),
        "n_agotados": sum(1 for x in todas if x["estado"][1] == "Agotado"),
        "filtros_activos": any(f.values()),
    }
    return render(request, "inventario/consulta.html", ctx)


@requiere_modulo("inventario")
def detalle(request, pk):
    """Panel lateral con la ficha del producto (E7 · Fig. 7)."""
    p = get_object_or_404(Producto.objects.select_related("modelo_extintor", "proveedor"), pk=pk)
    ex = existencias(sucursales=list(request.sucursales_consulta), productos=[p])
    filas = []
    for s in request.sucursales_consulta:
        cant = ex[(p.id, s.id)]
        pct = min(100, int(cant / p.stock_maximo * 100)) if p.stock_maximo else 0
        filas.append({"sucursal": s, "existencia": cant, "estado": estado_stock(p, cant), "pct": pct})
    total = sum((f["existencia"] for f in filas), CERO)
    return render(
        request,
        "inventario/_detalle.html",
        {"p": p, "filas": filas, "total": total, "estado": estado_stock(p, total), "modelo": getattr(p, "modelo_extintor", None)},
    )


@requiere_modulo("inventario")
def historial(request, pk):
    """Historial: kárdex (Fig. 8) y cambios en el registro (Fig. 9)."""
    p = get_object_or_404(Producto, pk=pk)
    sucursal = _sucursal_filtro(request, request.GET.get("sucursal"))
    tab = request.GET.get("tab", "m")
    movs = kardex(p, sucursal=sucursal) if tab == "m" else []
    if sucursal is None:
        movs = [m for m in movs if m.sucursal in request.sucursales_consulta] if tab == "m" else []
    cambios = Bitacora.objects.filter(entidad="PRODUCTO", registro_id=p.pk).select_related("usuario")[:60] if tab == "c" else []
    total = MovimientoInventario.objects.filter(producto=p, sucursal__in=[sucursal] if sucursal else list(request.sucursales_consulta)).count()
    return render(
        request,
        "inventario/_historial.html",
        {"p": p, "sucursal": sucursal, "tab": tab, "movs": movs, "cambios": cambios, "total_movs": total},
    )


# ------------------------------------------------------------------ Inventario físico

@requiere_modulo("inventario_fisico")
def conteos(request):
    if request.method == "POST":
        try:
            conteo = iniciar_conteo(sucursal=request.sucursal, usuario=request.user, observaciones=request.POST.get("observaciones", ""))
        except ConteoError as e:
            messages.error(request, e.errores[0])
            return redirect("inventario:conteos")
        messages.success(request, f"Conteo {conteo.folio} iniciado en {request.sucursal.nombre}.")
        return redirect("inventario:conteo", pk=conteo.pk)
    lista = InventarioFisico.objects.filter(sucursal__in=request.sucursales).select_related("sucursal", "creado_por", "autorizado_por")
    return render(request, "inventario/conteos.html", {"conteos": lista[:100]})


@requiere_modulo("inventario_fisico")
def conteo(request, pk):
    c = get_object_or_404(InventarioFisico.objects.select_related("sucursal"), pk=pk, sucursal__in=request.sucursales)
    errores = []
    if request.method == "POST":
        accion = request.POST.get("accion")
        try:
            if accion in ("guardar", "cerrar") and c.estado == InventarioFisico.Estado.ABIERTO:
                fisicas, notas = {}, {}
                for d in c.detalles.all():
                    raw = request.POST.get(f"fisica_{d.id}")
                    if raw is not None:
                        try:
                            fisicas[d.id] = Decimal(raw)
                        except InvalidOperation:
                            fisicas[d.id] = None
                    notas[d.id] = request.POST.get(f"obs_{d.id}", "").strip()
                capturar(c, fisicas, notas)
                if accion == "cerrar":
                    cerrar_conteo(c, request.user)
                    messages.success(request, f"Conteo {c.folio} cerrado. Falta la autorización del Gerente.")
                else:
                    messages.info(request, "Conteo guardado.")
                return redirect("inventario:conteo", pk=c.pk)
            if accion == "autorizar":
                autorizar_ajuste(c, request.user)
                messages.success(request, f"Ajustes de {c.folio} aplicados al kárdex.")
                return redirect("inventario:conteo", pk=c.pk)
        except ConteoError as e:
            errores = e.errores
    detalles = list(c.detalles.select_related("producto").order_by("producto__categoria", "producto__sku"))
    return render(
        request,
        "inventario/conteo.html",
        {"c": c, "detalles": detalles, "errores": errores, "con_diferencia": sum(1 for d in detalles if d.diferencia)},
    )


