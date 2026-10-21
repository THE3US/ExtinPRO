from django.urls import path

from . import admin_views, views

app_name = "usuarios"

urlpatterns = [
    path("acceso/", views.acceso, name="acceso"),
    path("salir/", views.salir, name="salir"),
    path("almacen/", views.cambiar_sucursal, name="cambiar_sucursal"),
    path("administracion/usuarios/", admin_views.lista, name="lista"),
    path("administracion/usuarios/nuevo/", admin_views.formulario, name="nuevo"),
    path("administracion/usuarios/<int:pk>/", admin_views.formulario, name="editar"),
    path("administracion/usuarios/<int:pk>/reactivar/", admin_views.reactivar, name="reactivar"),
    path("administracion/sucursales/", admin_views.sucursales, name="sucursales"),
    path("administracion/sucursales/nueva/", admin_views.sucursal_form, name="sucursal_nueva"),
    path("administracion/sucursales/<int:pk>/", admin_views.sucursal_form, name="sucursal_editar"),
    path("administracion/cajas/nueva/", admin_views.caja_form, name="caja_nueva"),
    path("administracion/cajas/<int:pk>/", admin_views.caja_form, name="caja_editar"),
]
