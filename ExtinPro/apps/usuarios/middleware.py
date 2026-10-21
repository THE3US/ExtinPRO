from django.utils.functional import SimpleLazyObject

from .acceso import SESION_SUCURSAL, sucursales_permitidas
from .models import Sucursal


class SucursalActivaMiddleware:
    """
    request.sucursal = almacén activo de la sesión (selector del encabezado).
    request.sucursales = almacenes que el usuario puede operar (vender, recibir, contar).
    request.sucursales_consulta = todos los almacenes activos: la consulta de existencias
    (PROD-04, CP-02) muestra «Almacén: Todos» para cualquier rol, solo lectura.
    Siempre se valida contra lo que el usuario puede operar; nunca se confía en el navegador.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.sucursal = None
        request.sucursales = []
        request.sucursales_consulta = []
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            permitidas = sucursales_permitidas(user)
            request.sucursales = permitidas
            request.sucursales_consulta = SimpleLazyObject(lambda: list(Sucursal.objects.filter(activa=True).order_by("id")))
            elegida = request.session.get(SESION_SUCURSAL)
            request.sucursal = next((s for s in permitidas if s.pk == elegida), None) or (permitidas[0] if permitidas else None)
            if request.sucursal and elegida != request.sucursal.pk:
                request.session[SESION_SUCURSAL] = request.sucursal.pk
        return self.get_response(request)
