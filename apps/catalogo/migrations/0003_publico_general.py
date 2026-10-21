"""El E6 exige cliente en toda venta: se crea el registro «Público general»."""
from django.db import migrations


def crear(apps, schema_editor):
    Cliente = apps.get_model("catalogo", "Cliente")
    Cliente.objects.get_or_create(
        tipo_persona="PUBLICO_GENERAL",
        defaults={"nombre_razon_social": "Público general", "rfc": "XAXX010101000"},
    )


class Migration(migrations.Migration):
    dependencies = [("catalogo", "0002_initial")]
    operations = [migrations.RunPython(crear, migrations.RunPython.noop)]
