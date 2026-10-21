from django.urls import path

from . import views

app_name = "reportes"

urlpatterns = [
    path("valor/", views.valor, name="valor"),
    path("valor/reporte/", views.valor_reporte, name="valor_reporte"),
    path("ventas/", views.ventas, name="ventas"),
    path("ventas/imprimir/", views.ventas_imprimir, name="ventas_imprimir"),
]
