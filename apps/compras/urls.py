from django.urls import path

from . import views

app_name = "compras"

urlpatterns = [
    path("recepcion/", views.recepcion, name="recepcion"),
    path("recepcion/guardar/", views.recepcion_guardar, name="recepcion_guardar"),
    path("recepcion/<int:pk>/comprobante/", views.comprobante_recepcion, name="comprobante_recepcion"),
    path("abastecimiento/", views.abastecimiento, name="abastecimiento"),
    path("abastecimiento/enviar/", views.abastecimiento_enviar, name="abastecimiento_enviar"),
    path("abastecimiento/pedidos/", views.pedidos, name="pedidos"),
    path("abastecimiento/comprobante/", views.comprobante_oc, name="comprobante_oc"),
]
