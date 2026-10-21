from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .acceso import SESION_SUCURSAL, intentar_acceso, sucursales_permitidas
from .models import Sucursal


def acceso(request):
    """Inicio de sesión (E7 · Fig. 23 y 24)."""
    if request.user.is_authenticated:
        return redirect("core:inicio")
    contexto = {"sucursales": Sucursal.objects.filter(activa=True).order_by("id")}
    if request.method == "POST":
        resultado = intentar_acceso(
            request, request.POST.get("usuario"), request.POST.get("contrasena"), request.POST.get("sucursal")
        )
        if resultado.ok:
            u = resultado.usuario
            messages.success(request, f"Bienvenido(a), {u.nombre_completo}", extra_tags=f"Permisos del rol {u.rol.nombre} habilitados.")
            siguiente = request.GET.get("next", "")
            if url_has_allowed_host_and_scheme(siguiente, allowed_hosts={request.get_host()}):
                return redirect(siguiente)
            return redirect("core:inicio")
        contexto.update(
            {
                "resultado": resultado,
                "usuario_capturado": request.POST.get("usuario", ""),
                "sucursal_capturada": request.POST.get("sucursal", ""),
            }
        )
    return render(request, "usuarios/acceso.html", contexto)


@require_POST
def salir(request):
    logout(request)
    return redirect("usuarios:acceso")


@require_POST
@login_required
def cambiar_sucursal(request):
    try:
        elegida = int(request.POST.get("sucursal", ""))
    except ValueError:
        elegida = None
    permitidas = {s.pk: s for s in sucursales_permitidas(request.user)}
    if elegida in permitidas:
        request.session[SESION_SUCURSAL] = elegida
        messages.info(request, f"Almacén activo: {permitidas[elegida].nombre}")
    else:
        messages.error(request, "No tienes acceso a ese almacén.")
    siguiente = request.POST.get("siguiente", "")
    if not url_has_allowed_host_and_scheme(siguiente, allowed_hosts={request.get_host()}):
        siguiente = "core:inicio"
    return redirect(siguiente)
