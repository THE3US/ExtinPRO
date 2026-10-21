from django.urls import path

from . import views

app_name = "catalogo"

urlpatterns = [
    path("productos/", views.productos, name="productos"),
    path("productos/nuevo/", views.producto_form, name="producto_nuevo"),
    path("productos/<int:pk>/", views.producto_form, name="producto_editar"),
    path("clientes/", views.clientes, name="clientes"),
    path("clientes/nuevo/", views.cliente_form, name="cliente_nuevo"),
    path("clientes/<int:pk>/", views.cliente_form, name="cliente_editar"),
    path("proveedores/nuevo/", views.proveedor_form, name="proveedor_nuevo"),
    path("proveedores/<int:pk>/", views.proveedor_form, name="proveedor_editar"),
]
