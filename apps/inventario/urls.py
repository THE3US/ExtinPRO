from django.urls import path

from . import views

app_name = "inventario"

urlpatterns = [
    path("", views.consulta, name="consulta"),
    path("producto/<int:pk>/", views.detalle, name="detalle"),
    path("producto/<int:pk>/historial/", views.historial, name="historial"),
    path("fisico/", views.conteos, name="conteos"),
    path("fisico/<int:pk>/", views.conteo, name="conteo"),
]
