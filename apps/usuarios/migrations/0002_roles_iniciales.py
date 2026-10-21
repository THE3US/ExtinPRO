"""Datos iniciales de la tabla ROL (Entregable 7 · sección 2.2)."""
from django.db import migrations

ROLES = [
    ("Administrador", "Configura el sistema, usuarios y catálogos; acceso total.", True),
    ("Gerente", "Supervisa la operación: autoriza órdenes y cancelaciones, consulta reportes.", True),
    ("Almacenista", "Recibe mercancía, consulta existencias y solicita abastecimiento.", False),
    ("Cajero", "Registra ventas y cobra en el punto de venta.", False),
    ("Técnico", "Atiende órdenes de servicio técnico (recarga y mantenimiento).", False),
]


def crear_roles(apps, schema_editor):
    Rol = apps.get_model("usuarios", "Rol")
    for nombre, descripcion, cancela in ROLES:
        Rol.objects.get_or_create(nombre=nombre, defaults={"descripcion": descripcion, "puede_cancelar_venta": cancela})


class Migration(migrations.Migration):
    dependencies = [("usuarios", "0001_initial")]
    operations = [migrations.RunPython(crear_roles, migrations.RunPython.noop)]
