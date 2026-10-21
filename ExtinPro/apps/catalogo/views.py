"""Administración de catálogos (las pantallas de alta/cambio quedaron pendientes en el E7; usan el mismo estilo)."""
from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.core.services import registrar_bitacora
from apps.usuarios.decoradores import requiere_modulo

from .forms import ClienteForm, ModeloExtintorForm, ProductoForm, ProveedorForm
from .models import Cliente, Producto, Proveedor

CAMPOS_AUDITADOS = {
    "precio_venta": "Precio de venta",
    "precio_compra": "Precio de compra",
    "stock_minimo": "Stock mínimo",
    "activo": "Estado",
}


def _valor(campo, v):
    if campo == "activo":
        return "Activo" if v else "Descontinuado"
    if campo.startswith("precio"):
        return f"${v:,.2f}"
    return f"{v.normalize():f}" if hasattr(v, "normalize") else str(v)


@requiere_modulo("administracion", seccion="productos")
def productos(request):
    q = request.GET.get("q", "").strip()
    qs = Producto.objects.select_related("proveedor").order_by("sku")
    if q:
        qs = qs.filter(Q(sku__icontains=q) | Q(nombre__icontains=q) | Q(codigo_barras=q))
    return render(request, "catalogo/productos.html", {"productos": qs, "q": q})


@requiere_modulo("administracion", seccion="productos")
def producto_form(request, pk=None):
    producto = get_object_or_404(Producto, pk=pk) if pk else None
    modelo = getattr(producto, "modelo_extintor", None) if producto else None
    antes = {c: getattr(producto, c) for c in CAMPOS_AUDITADOS} if producto else {}
    form = ProductoForm(request.POST or None, instance=producto)
    form_ext = ModeloExtintorForm(request.POST or None, instance=modelo, prefix="ext")
    if request.method == "POST":
        es_extintor = request.POST.get("tipo") == Producto.Tipo.EXTINTOR
        if form.is_valid() and (not es_extintor or form_ext.is_valid()):
            with transaction.atomic():
                p = form.save()
                if es_extintor:
                    m = form_ext.save(commit=False)
                    m.producto = p
                    m.save()
                elif modelo is not None and not modelo.series.exists():
                    modelo.delete()  # dejó de ser extintor
                motivo = form.cleaned_data.get("motivo") or None
                if producto is None:
                    registrar_bitacora(usuario=request.user, entidad="PRODUCTO", registro_id=p.pk, accion="ALTA",
                                       campo="Alta en catálogo", anterior="—", nuevo=p.sku, motivo=motivo or "Registro inicial")
                else:
                    for campo, etiqueta in CAMPOS_AUDITADOS.items():
                        if antes[campo] != getattr(p, campo):
                            registrar_bitacora(usuario=request.user, entidad="PRODUCTO", registro_id=p.pk, accion="CAMBIO",
                                               campo=etiqueta, anterior=_valor(campo, antes[campo]), nuevo=_valor(campo, getattr(p, campo)), motivo=motivo)
            messages.success(request, f"Producto {p.sku} guardado.")
            return redirect("catalogo:productos")
    return render(
        request,
        "parciales/formulario.html",
        {
            "form": form,
            "formularios_extra": [{"titulo": "Datos del modelo de extintor (solo para tipo «Extintor»)", "form": form_ext}],
            "titulo": f"Editar {producto.sku}" if producto else "Nuevo producto",
            "ayuda": "Precios sin IVA. El stock máximo de referencia se calcula como el mayor entre mínimo × 3 y mínimo + 6.",
            "volver": reverse("catalogo:productos"),
        },
    )


@requiere_modulo("administracion", seccion="clientes")
def clientes(request):
    return render(
        request,
        "catalogo/clientes.html",
        {"clientes": Cliente.objects.order_by("id"), "proveedores": Proveedor.objects.order_by("nombre_razon_social")},
    )


def _form_generico(request, form_cls, modelo, pk, titulo, ayuda=""):
    obj = get_object_or_404(modelo, pk=pk) if pk else None
    form = form_cls(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        o = form.save()
        messages.success(request, f"{modelo._meta.verbose_name.capitalize()} «{o}» guardado.")
        return redirect("catalogo:clientes")
    return render(
        request,
        "parciales/formulario.html",
        {"form": form, "titulo": (f"Editar {obj}" if obj else titulo), "ayuda": ayuda, "volver": reverse("catalogo:clientes")},
    )


@requiere_modulo("administracion", seccion="clientes")
def cliente_form(request, pk=None):
    return _form_generico(request, ClienteForm, Cliente, pk, "Nuevo cliente", "El descuento del cliente se aplica por omisión en el punto de venta (máx. 50 %).")


@requiere_modulo("administracion", seccion="clientes")
def proveedor_form(request, pk=None):
    return _form_generico(request, ProveedorForm, Proveedor, pk, "Nuevo proveedor")

