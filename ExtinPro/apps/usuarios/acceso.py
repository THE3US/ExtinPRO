"""
Inicio de sesión con bloqueo (E7 · CP-01-01 a CP-01-04, diagrama de estados de Usuario).

- Campos vacíos: mensaje y no cuenta como intento.
- Contraseña incorrecta: «Intento N de 3»; al tercero la cuenta queda bloqueada.
- Cuenta bloqueada: solo un Administrador la reactiva (pantalla Usuarios).
- Para no revelar qué usuarios existen, un usuario inexistente recibe los mismos mensajes
  (con un contador guardado en la sesión del navegador).
"""
from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth import authenticate, login
from django.db.models import F

from .models import Sucursal, Usuario

MAX = settings.SPVCI["INTENTOS_ACCESO"]
CLAVE_SESION = "intentos_anonimos"
SESION_SUCURSAL = "sucursal_activa_id"


@dataclass
class ResultadoAcceso:
    ok: bool
    mensaje: str = ""
    bloqueado: bool = False
    intentos: int = 0
    usuario: Usuario | None = None


def mensaje_bloqueo():
    return f"Cuenta bloqueada. Se registraron {MAX} intentos fallidos. Solicita al administrador que la reactive."


def intentar_acceso(request, nombre_usuario, password, sucursal_id):
    nombre_usuario = (nombre_usuario or "").strip().lower()
    if not nombre_usuario or not password:
        return ResultadoAcceso(False, "Escribe tu usuario y tu contraseña.")

    usuario = Usuario.objects.select_related("rol", "sucursal").filter(nombre_usuario=nombre_usuario).first()
    if usuario is not None and usuario.bloqueado:
        return ResultadoAcceso(False, mensaje_bloqueo(), bloqueado=True, intentos=MAX)

    autenticado = authenticate(request, nombre_usuario=nombre_usuario, password=password)
    if autenticado is None:
        if usuario is not None and usuario.activo:
            Usuario.objects.filter(pk=usuario.pk, intentos_fallidos__lt=MAX).update(intentos_fallidos=F("intentos_fallidos") + 1)
            usuario.refresh_from_db(fields=["intentos_fallidos"])
            n = usuario.intentos_fallidos
        else:
            n = min(request.session.get(CLAVE_SESION, 0) + 1, MAX)
            request.session[CLAVE_SESION] = n
        if n >= MAX:
            return ResultadoAcceso(False, mensaje_bloqueo(), bloqueado=True, intentos=n)
        return ResultadoAcceso(
            False, f"Usuario o contraseña incorrectos. Intento {n} de {MAX}; al tercero la cuenta se bloquea.", intentos=n
        )

    sucursal = Sucursal.objects.filter(pk=sucursal_id, activa=True).first() if sucursal_id else None
    if sucursal is None:
        sucursal = autenticado.sucursal
    if not autenticado.puede_elegir_sucursal and sucursal.pk != autenticado.sucursal_id:
        return ResultadoAcceso(False, f"Tu usuario está asignado a {autenticado.sucursal.nombre}. Elige esa sucursal.")

    Usuario.objects.filter(pk=autenticado.pk).update(intentos_fallidos=0)
    request.session.pop(CLAVE_SESION, None)
    login(request, autenticado)
    request.session[SESION_SUCURSAL] = sucursal.pk
    return ResultadoAcceso(True, usuario=autenticado)


def sucursales_permitidas(usuario):
    if usuario.puede_elegir_sucursal:
        return list(Sucursal.objects.filter(activa=True).order_by("id"))
    return [usuario.sucursal]
