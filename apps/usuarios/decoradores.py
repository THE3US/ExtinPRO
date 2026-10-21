from functools import wraps

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .roles import MODULOS


def requiere_modulo(modulo, seccion=None):
    """Exige sesión y que el rol del usuario tenga el módulo (E7 · Fig. 15 «Acceso restringido»)."""

    def decorador(vista):
        @wraps(vista)
        @login_required
        def envoltura(request, *args, **kwargs):
            request.seccion = seccion or modulo
            if not request.user.puede(modulo):
                return render(
                    request,
                    "core/restringido.html",
                    {"modulo_nombre": MODULOS.get(modulo, modulo), "modulo": modulo},
                    status=403,
                )
            return vista(request, *args, **kwargs)

        return envoltura

    return decorador
