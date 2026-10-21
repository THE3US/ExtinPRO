from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("", include("apps.sitio.urls")),  # sitio web público
    path("", include("apps.usuarios.urls")),  # acceso, salir, administración de usuarios
    path("", include("apps.core.urls")),
    path("ventas/", include("apps.ventas.urls")),
    path("", include("apps.compras.urls")),  # recepcion/ y abastecimiento/
    path("inventario/", include("apps.inventario.urls")),
    path("reportes/", include("apps.reportes.urls")),
    path("administracion/", include("apps.catalogo.urls")),
    path("admin/", admin.site.urls),  # administración técnica de Django (rol Administrador)
]

handler404 = "apps.core.views.error_404"

admin.site.site_header = "ExtinPro · administración técnica"
admin.site.site_title = "ExtinPro"
admin.site.index_title = "Tablas del Entregable 6"
