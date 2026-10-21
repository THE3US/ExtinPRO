"""
Entregable 6 · Figura 3: ORDEN_COMPRA, DETALLE_ORDEN_COMPRA, RECEPCION_COMPRA, DETALLE_RECEPCION.
"""
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import F, Q, Sum
from django.db.models.functions import Now
from django.db.models.lookups import GreaterThanOrEqual
from django.utils import timezone

from apps.core.db import FechaLocal, ck_en



class OrdenCompra(models.Model):
    class Estado(models.TextChoices):
        BORRADOR = "BORRADOR", "Por autorizar"
        AUTORIZADA = "AUTORIZADA", "Enviada · por recibir"
        PARCIAL = "PARCIAL", "Parcial"
        RECIBIDA = "RECIBIDA", "Recibida"
        CANCELADA = "CANCELADA", "Cancelada"

    id = models.BigAutoField(primary_key=True, db_column="orden_compra_id")
    proveedor = models.ForeignKey(
        "catalogo.Proveedor", on_delete=models.PROTECT, db_column="proveedor_id", related_name="ordenes"
    )
    sucursal = models.ForeignKey(
        "usuarios.Sucursal", on_delete=models.PROTECT, db_column="sucursal_id", related_name="ordenes"
    )
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, db_column="creado_por", related_name="+"
    )
    folio = models.CharField("folio", max_length=30)
    fecha_orden = models.DateTimeField("fecha", default=timezone.now, db_default=Now())
    fecha_estimada = models.DateField("entrega prevista", null=True, blank=True)
    estado = models.CharField("estado", max_length=15, choices=Estado.choices, default="BORRADOR", db_default="BORRADOR")
    observaciones = models.TextField("observaciones", null=True, blank=True)

    class Meta:
        db_table = "orden_compra"
        db_table_comment = "Solicitud formal de mercancía a un proveedor; antecede a la recepción."
        verbose_name = "orden de compra"
        verbose_name_plural = "órdenes de compra"
        ordering = ["-id"]
        constraints = [
            models.UniqueConstraint(fields=["folio"], name="uq_orden_compra_folio"),
            models.CheckConstraint(
                condition=GreaterThanOrEqual(F("fecha_estimada"), FechaLocal("fecha_orden")),
                name="ck_orden_compra_fecha_estimada",
            ),
            ck_en("estado", ["BORRADOR", "AUTORIZADA", "PARCIAL", "RECIBIDA", "CANCELADA"], "ck_orden_compra_estado"),
        ]

    def __str__(self):
        return self.folio

    @property
    def pendiente_de_recibir(self):
        return self.estado in (self.Estado.AUTORIZADA, self.Estado.PARCIAL)

    def importe(self):
        return sum((d.cantidad * d.costo_unitario for d in self.detalles.all()), Decimal("0")).quantize(Decimal("0.01"))


class DetalleOrdenCompra(models.Model):
    id = models.BigAutoField(primary_key=True, db_column="detalle_orden_id")
    orden_compra = models.ForeignKey(
        OrdenCompra, on_delete=models.CASCADE, db_column="orden_compra_id", related_name="detalles"
    )
    producto = models.ForeignKey(
        "catalogo.Producto", on_delete=models.PROTECT, db_column="producto_id", related_name="+"
    )
    cantidad = models.DecimalField("cantidad", max_digits=12, decimal_places=3)
    costo_unitario = models.DecimalField("costo unitario", max_digits=12, decimal_places=2)
    tasa_iva = models.DecimalField(
        "tasa de IVA", max_digits=5, decimal_places=4, default=Decimal("0.16"), db_default=Decimal("0.16")
    )

    class Meta:
        db_table = "detalle_orden_compra"
        db_table_comment = (
            "Partidas solicitadas en una orden de compra. Resuelve la relación N:M entre "
            "ORDEN_COMPRA y PRODUCTO."
        )
        verbose_name = "partida de orden de compra"
        verbose_name_plural = "partidas de orden de compra"
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["orden_compra", "producto"], name="uq_det_orden_producto"),
            models.UniqueConstraint(fields=["id", "producto"], name="uq_det_orden_id_producto"),
            models.CheckConstraint(condition=Q(cantidad__gt=0), name="ck_detalle_orden_compra_cantidad"),
            models.CheckConstraint(condition=Q(costo_unitario__gte=0), name="ck_detalle_orden_compra_costo_unitario"),
            models.CheckConstraint(
                condition=Q(tasa_iva__gte=0) & Q(tasa_iva__lte=1), name="ck_detalle_orden_compra_tasa_iva"
            ),
        ]

    def recibido(self):
        """Unidades recibidas en recepciones APLICADAS."""
        total = self.recepciones.filter(recepcion__estado=RecepcionCompra.Estado.APLICADA).aggregate(
            t=Sum("cantidad_recibida")
        )["t"]
        return total or Decimal("0")

    def pendiente(self):
        return max(self.cantidad - self.recibido(), Decimal("0"))


class RecepcionCompra(models.Model):
    class Estado(models.TextChoices):
        BORRADOR = "BORRADOR", "Borrador"
        APLICADA = "APLICADA", "Aplicada"
        CANCELADA = "CANCELADA", "Cancelada"

    id = models.BigAutoField(primary_key=True, db_column="recepcion_id")
    orden_compra = models.ForeignKey(
        OrdenCompra, on_delete=models.PROTECT, db_column="orden_compra_id", related_name="recepciones"
    )
    recibido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, db_column="recibido_por", related_name="+"
    )
    folio_recepcion = models.CharField("folio", max_length=30)
    fecha_recepcion = models.DateTimeField("fecha de recepción", default=timezone.now, db_default=Now())
    documento_proveedor = models.CharField("factura o remisión", max_length=60, null=True, blank=True)
    estado = models.CharField("estado", max_length=12, choices=Estado.choices, default="BORRADOR", db_default="BORRADOR")
    # EXTENSIÓN al E6: motivo de una recepción parcial o de su cancelación (E7 · CP-04-03, CP-04-08).
    observaciones = models.TextField("observaciones", null=True, blank=True)

    class Meta:
        db_table = "recepcion_compra"
        db_table_comment = (
            "Evento de recepción (total o parcial) de una orden de compra. Separa lo solicitado de "
            "lo realmente recibido."
        )
        verbose_name = "recepción de compra"
        verbose_name_plural = "recepciones de compra"
        ordering = ["-id"]
        constraints = [
            models.UniqueConstraint(fields=["folio_recepcion"], name="uq_recepcion_folio"),
            ck_en("estado", ["BORRADOR", "APLICADA", "CANCELADA"], "ck_recepcion_compra_estado"),
        ]

    def __str__(self):
        return self.folio_recepcion


class DetalleRecepcion(models.Model):
    id = models.BigAutoField(primary_key=True, db_column="detalle_recepcion_id")
    recepcion = models.ForeignKey(
        RecepcionCompra, on_delete=models.CASCADE, db_column="recepcion_id", related_name="detalles"
    )
    # La FK compuesta (detalle_orden_id, producto_id) → detalle_orden_compra se crea en la migración 0002.
    detalle_orden = models.ForeignKey(
        DetalleOrdenCompra, on_delete=models.PROTECT, db_column="detalle_orden_id", related_name="recepciones"
    )
    producto = models.ForeignKey(
        "catalogo.Producto", on_delete=models.PROTECT, db_column="producto_id", related_name="+"
    )
    cantidad_recibida = models.DecimalField("cantidad recibida", max_digits=12, decimal_places=3)
    costo_unitario_real = models.DecimalField("costo unitario real", max_digits=12, decimal_places=2)

    class Meta:
        db_table = "detalle_recepcion"
        db_table_comment = (
            "Productos y cantidades efectivamente recibidos. Permite recepciones parciales, costo "
            "real y alta de series."
        )
        verbose_name = "partida recibida"
        verbose_name_plural = "partidas recibidas"
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["recepcion", "detalle_orden"], name="uq_det_recepcion_partida"),
            models.UniqueConstraint(fields=["id", "producto"], name="uq_det_recepcion_id_producto"),
            models.CheckConstraint(condition=Q(cantidad_recibida__gt=0), name="ck_detalle_recepcion_cantidad_recibida"),
            models.CheckConstraint(
                condition=Q(costo_unitario_real__gte=0), name="ck_detalle_recepcion_costo_unitario_real"
            ),
        ]
