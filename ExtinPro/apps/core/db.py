"""
Ayudantes para declarar las restricciones del Entregable 6 con sus mismos nombres.

Ejemplo: ck_no_vacio("nombre", "ck_sucursal_nombre") genera
    CONSTRAINT ck_sucursal_nombre CHECK (char_length(btrim(nombre)) > 0)
"""
from django.db.models import CheckConstraint, DateField, Func, Q
from django.db.models.functions import Length, Trim
from django.db.models.lookups import GreaterThan


def ck_no_vacio(campo, nombre):
    return CheckConstraint(condition=GreaterThan(Length(Trim(campo)), 0), name=nombre)


def ck_en(campo, valores, nombre):
    return CheckConstraint(condition=Q(**{f"{campo}__in": list(valores)}), name=nombre)


def ck_regex(campo, patron, nombre, ignorar_mayusculas=False):
    lookup = "iregex" if ignorar_mayusculas else "regex"
    return CheckConstraint(condition=Q(**{f"{campo}__{lookup}": patron}), name=nombre)


# Expresiones regulares del Entregable 6
RE_TELEFONO = r"^[0-9+() -]{7,20}$"
RE_RFC = r"^[A-ZÑ&]{3,4}[0-9]{6}[A-Z0-9]{3}$"
RE_CORREO = r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$"
RE_CODIGO_BARRAS = r"^[0-9]{8,14}$"
RE_NOMBRE_USUARIO = r"^[a-z0-9._-]{4,60}$"


class FechaLocal(Func):
    """(campo AT TIME ZONE 'America/Mexico_City')::date — igual que en las CHECK del Entregable 6."""

    template = "((%(expressions)s AT TIME ZONE 'America/Mexico_City')::date)"
    output_field = DateField()
