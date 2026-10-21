"""
EXTENSIÓN al E6: tabla BITACORA.

Guarda el «Historial de cambios del producto» del E7 (Fig. 9: valor anterior, valor nuevo,
usuario y motivo) y las acciones sensibles que pide la arquitectura: cancelaciones,
autorizaciones, ajustes y cambios de permisos. Solo se inserta; nunca se edita.
"""
from django.conf import settings
from django.db import models
from django.db.models.functions import Now
from django.utils import timezone


class Bitacora(models.Model):
    id = models.BigAutoField(primary_key=True, db_column="bitacora_id")
    fecha = models.DateTimeField("fecha", default=timezone.now, db_default=Now())
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, db_column="usuario_id", related_name="+"
    )
    entidad = models.CharField("entidad", max_length=40)  # PRODUCTO, VENTA, RECEPCION_COMPRA, USUARIO…
    registro_id = models.BigIntegerField("id del registro")
    accion = models.CharField("acción", max_length=40)  # ALTA, CAMBIO, CANCELACION, AUTORIZACION…
    campo = models.CharField("campo", max_length=60, blank=True, default="")
    valor_anterior = models.TextField("valor anterior", null=True, blank=True)
    valor_nuevo = models.TextField("valor nuevo", null=True, blank=True)
    motivo = models.TextField("motivo", null=True, blank=True)

    class Meta:
        db_table = "bitacora"
        db_table_comment = "Historial de cambios y acciones sensibles (extensión del Entregable 6)."
        verbose_name = "registro de bitácora"
        verbose_name_plural = "bitácora"
        ordering = ["-fecha", "-id"]
        indexes = [models.Index(fields=["entidad", "registro_id"], name="ix_bitacora_registro")]

    def __str__(self):
        return f"{self.fecha:%Y-%m-%d %H:%M} {self.entidad}#{self.registro_id} {self.accion} {self.campo}"
