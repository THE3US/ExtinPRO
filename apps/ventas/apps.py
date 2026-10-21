from django.apps import AppConfig


class VentasConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.ventas"
    label = "ventas"
    verbose_name = "Cotizaciones, ventas y caja"
