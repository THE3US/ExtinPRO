"""Servicios compartidos: folios consecutivos, bitácora y fechas hábiles."""
from datetime import timedelta

from django.db import connection
from django.db.models import IntegerField, Max
from django.db.models.functions import Cast, Substr
from django.utils import timezone

from .models import Bitacora

# Llaves de candado (pg_advisory_xact_lock de 64 bits) para generar folios sin huecos ni duplicados.
CANDADO_FOLIO = {"venta": 900_001, "orden_compra": 900_002, "recepcion": 900_003, "solicitud_web": 900_004}


def siguiente_folio(modelo, campo, prefijo, digitos, clave):
    """
    Folio consecutivo con prefijo, p. ej. VT-000124. Serializa la generación con un candado
    de transacción, así que debe llamarse dentro de transaction.atomic().
    """
    if not connection.in_atomic_block:
        raise RuntimeError("siguiente_folio debe llamarse dentro de una transacción.")
    with connection.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(%s)", [CANDADO_FOLIO[clave]])
    ultimo = (
        modelo.objects.filter(**{f"{campo}__startswith": prefijo})
        .annotate(n=Cast(Substr(campo, len(prefijo) + 1), IntegerField()))
        .aggregate(m=Max("n"))["m"]
        or 0
    )
    return f"{prefijo}{ultimo + 1:0{digitos}d}"


def registrar_bitacora(*, usuario, entidad, registro_id, accion, campo="", anterior=None, nuevo=None, motivo=None):
    return Bitacora.objects.create(
        usuario=usuario if getattr(usuario, "is_authenticated", False) else None,
        entidad=entidad,
        registro_id=registro_id,
        accion=accion,
        campo=campo,
        valor_anterior=None if anterior is None else str(anterior),
        valor_nuevo=None if nuevo is None else str(nuevo),
        motivo=motivo,
    )


def hoy():
    return timezone.localdate()


def sumar_dias_habiles(fecha, dias):
    """Suma días hábiles saltando domingos (regla del demo para la entrega prevista)."""
    while dias > 0:
        fecha += timedelta(days=1)
        if fecha.weekday() != 6:
            dias -= 1
    return fecha
