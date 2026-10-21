from django.urls import path

from . import views

app_name = "sitio"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("cotizacion/", views.cotizacion, name="cotizacion"),
    path("solicitudes/", views.solicitudes, name="solicitudes"),
]
