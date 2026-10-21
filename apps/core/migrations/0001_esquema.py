"""
Crea el esquema "extinpro" antes que cualquier otra tabla (incluidas las de Django),
igual que el script del Entregable 6. La conexión usa search_path=extinpro,public.
"""
from django.conf import settings
from django.db import migrations


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    run_before = [
        ("contenttypes", "0001_initial"),
        ("auth", "0001_initial"),
        ("sessions", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql=f'CREATE SCHEMA IF NOT EXISTS "{settings.DB_SCHEMA}"',
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
