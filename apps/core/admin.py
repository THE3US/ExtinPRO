"""
Administración técnica (/admin/): permite consultar las 29 tablas del Entregable 6.
Kárdex, ventas, pagos y bitácora son de solo lectura: se corrigen con movimientos
compensatorios desde la aplicación, nunca editándolos.
"""
from django.apps import apps
from django.contrib import admin



SOLO_LECTURA = {
    "inventario.movimientoinventario",
    "ventas.venta",
    "ventas.detalleventa",
    "ventas.pago",
    "ventas.comprobante",
    "ventas.arqueocaja",
    "compras.detallerecepcion",
    "core.bitacora",
}


class SoloLectura(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


def registrar_todo():
    for app_label in ("usuarios", "catalogo", "compras", "inventario", "ventas", "servicio", "sitio", "core"):
        for modelo in apps.get_app_config(app_label).get_models():
            if admin.site.is_registered(modelo):
                continue
            clave = modelo._meta.label_lower
            if clave == "ventas.detalleventaextintor":
                continue  # llave primaria compuesta: el admin de Django no la soporta
            campos = [f.name for f in modelo._meta.concrete_fields][:7]
            attrs = {"list_display": campos}
            base = SoloLectura if clave in SOLO_LECTURA else admin.ModelAdmin
            admin.site.register(modelo, type(f"{modelo.__name__}Admin", (base,), attrs))


registrar_todo()
