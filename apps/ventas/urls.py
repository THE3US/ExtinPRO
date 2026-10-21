from django.urls import path

from . import views

app_name = "ventas"

urlpatterns = [
    path("", views.pos, name="pos"),
    path("api/registrar/", views.registrar, name="registrar"),
    path("caja/", views.caja, name="caja"),
    path("caja/abrir/", views.caja_abrir, name="caja_abrir"),
    path("registradas/", views.lista, name="lista"),
    path("<int:pk>/", views.detalle, name="detalle"),
    path("<int:pk>/ticket/", views.ticket, name="ticket"),
]
