"""Administración de usuarios, sucursales y cajas (rol Administrador)."""
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.core.services import registrar_bitacora
from apps.usuarios.decoradores import requiere_modulo
from apps.ventas.models import Caja

from .forms import CajaForm, SucursalForm, UsuarioForm
from .models import Sucursal, Usuario


@requiere_modulo("administracion", seccion="usuarios")
def lista(request):
    usuarios = Usuario.objects.select_related("rol", "sucursal").order_by("-activo", "nombre_completo")
    return render(request, "usuarios/lista.html", {"usuarios": usuarios})


@requiere_modulo("administracion", seccion="usuarios")
def formulario(request, pk=None):
    usuario = get_object_or_404(Usuario, pk=pk) if pk else None
    antes = (usuario.rol.nombre, usuario.sucursal_id, usuario.activo) if usuario else None
    form = UsuarioForm(request.POST or None, instance=usuario)
    if request.method == "POST" and form.is_valid():
        if usuario and usuario.pk == request.user.pk and (form.cleaned_data["rol"].nombre != usuario.rol.nombre or not form.cleaned_data["activo"]):
            form.add_error(None, "No puedes cambiar tu propio rol ni desactivar tu propia cuenta.")
        else:
            u = form.save()
            if antes is None:
                registrar_bitacora(usuario=request.user, entidad="USUARIO", registro_id=u.pk, accion="ALTA", campo="Rol", nuevo=u.rol.nombre)
            else:
                if antes[0] != u.rol.nombre:
                    registrar_bitacora(usuario=request.user, entidad="USUARIO", registro_id=u.pk, accion="CAMBIO", campo="Rol", anterior=antes[0], nuevo=u.rol.nombre)
                if antes[2] != u.activo:
                    registrar_bitacora(usuario=request.user, entidad="USUARIO", registro_id=u.pk, accion="CAMBIO", campo="Activo", anterior=antes[2], nuevo=u.activo)
            messages.success(request, f"Usuario {u.nombre_usuario} guardado.")
            return redirect("usuarios:lista")
    return render(
        request,
        "parciales/formulario.html",
        {"form": form, "titulo": f"Editar {usuario.nombre_usuario}" if usuario else "Nuevo usuario",
         "ayuda": "El rol define los módulos del menú (E7 · sección 2.2).", "volver": reverse("usuarios:lista")},
    )


@require_POST
@requiere_modulo("administracion", seccion="usuarios")
def reactivar(request, pk):
    """Desbloquea una cuenta tras 3 intentos fallidos (CP-01-03)."""
    u = get_object_or_404(Usuario, pk=pk)
    Usuario.objects.filter(pk=u.pk).update(intentos_fallidos=0)
    registrar_bitacora(usuario=request.user, entidad="USUARIO", registro_id=u.pk, accion="REACTIVACION", campo="Bloqueo", anterior="Bloqueada", nuevo="Activa")
    messages.success(request, f"Cuenta {u.nombre_usuario} reactivada.")
    return redirect("usuarios:lista")


@requiere_modulo("administracion", seccion="sucursales")
def sucursales(request):
    return render(
        request,
        "usuarios/sucursales.html",
        {"sucursales": Sucursal.objects.order_by("id"), "cajas": Caja.objects.select_related("sucursal").order_by("sucursal_id", "codigo")},
    )


@requiere_modulo("administracion", seccion="sucursales")
def sucursal_form(request, pk=None):
    obj = get_object_or_404(Sucursal, pk=pk) if pk else None
    form = SucursalForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        s = form.save()
        messages.success(request, f"Sucursal «{s.nombre}» guardada.")
        return redirect("usuarios:sucursales")
    return render(request, "parciales/formulario.html", {"form": form, "titulo": f"Editar {obj}" if obj else "Nueva sucursal", "volver": reverse("usuarios:sucursales"),
                                                           "ayuda": "En la interfaz las sucursales se muestran como almacenes (p. ej. «Almacén Matriz»)."})


@requiere_modulo("administracion", seccion="sucursales")
def caja_form(request, pk=None):
    obj = get_object_or_404(Caja, pk=pk) if pk else None
    form = CajaForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        c = form.save()
        messages.success(request, f"Caja {c.codigo} guardada.")
        return redirect("usuarios:sucursales")
    return render(request, "parciales/formulario.html", {"form": form, "titulo": f"Editar caja {obj.codigo}" if obj else "Nueva caja", "volver": reverse("usuarios:sucursales")})
