"""
Entregable 6 · Figura 5 (COTIZACION, DETALLE_COTIZACION, VENTA, DETALLE_VENTA,
DETALLE_VENTA_EXTINTOR, COMPROBANTE) y Figura 6 (CAJA, SESION_CAJA, ARQUEO_CAJA, PAGO).
"""
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Length, Now, Trim
from django.db.models.lookups import GreaterThanOrEqual
from django.utils import timezone

from apps.core.db import FechaLocal, ck_en, ck_no_vacio

CENT = Decimal("0.01")


def redondear(valor):
    return Decimal(valor).quantize(CENT, rounding=ROUND_HALF_UP)


# ------------------------------------------------------------------ Cotizaciones

class Cotizacion(models.Model):
    class Estado(models.TextChoices):
        BORRADOR = "BORRADOR", "Borrador"
        EMITIDA = "EMITIDA", "Emitida"
        ACEPTADA = "ACEPTADA", "Aceptada"
        RECHAZADA = "RECHAZADA", "Rechazada"
        VENCIDA = "VENCIDA", "Vencida"
        CANCELADA = "CANCELADA", "Cancelada"

    id = models.BigAutoField(primary_key=True, db_column="cotizacion_id")
    cliente = models.ForeignKey("catalogo.Cliente", on_delete=models.PROTECT, db_column="cliente_id", related_name="cotizaciones")
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, db_column="creado_por", related_name="+")
    folio = models.CharField(max_length=30)
    fecha_emision = models.DateTimeField(default=timezone.now, db_default=Now())
    vigencia_hasta = models.DateField()
    estado = models.CharField(max_length=15, choices=Estado.choices, default="BORRADOR", db_default="BORRADOR")
    observaciones = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "cotizacion"
        db_table_comment = "Presupuesto emitido a un cliente. Conserva propuestas comerciales sin afectar existencias."
        verbose_name = "cotización"
        verbose_name_plural = "cotizaciones"
        constraints = [
            models.UniqueConstraint(fields=["folio"], name="uq_cotizacion_folio"),
            models.CheckConstraint(
                condition=GreaterThanOrEqual(F("vigencia_hasta"), FechaLocal("fecha_emision")),
                name="ck_cotizacion_vigencia_hasta",
            ),
            ck_en("estado", ["BORRADOR", "EMITIDA", "ACEPTADA", "RECHAZADA", "VENCIDA", "CANCELADA"], "ck_cotizacion_estado"),
        ]

    def __str__(self):
        return self.folio


class DetalleCotizacion(models.Model):
    id = models.BigAutoField(primary_key=True, db_column="detalle_cotizacion_id")
    cotizacion = models.ForeignKey(Cotizacion, on_delete=models.CASCADE, db_column="cotizacion_id", related_name="detalles")
    producto = models.ForeignKey("catalogo.Producto", on_delete=models.PROTECT, db_column="producto_id", related_name="+")
    cantidad = models.DecimalField(max_digits=12, decimal_places=3)
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=2)
    descuento = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"), db_default=Decimal("0"))
    tasa_iva = models.DecimalField(max_digits=5, decimal_places=4, default=Decimal("0.16"), db_default=Decimal("0.16"))

    class Meta:
        db_table = "detalle_cotizacion"
        db_table_comment = "Partidas de una cotización. Resuelve la relación N:M entre COTIZACION y PRODUCTO."
        constraints = [
            models.CheckConstraint(condition=Q(cantidad__gt=0), name="ck_detalle_cotizacion_cantidad"),
            models.CheckConstraint(condition=Q(precio_unitario__gte=0), name="ck_detalle_cotizacion_precio_unitario"),
            models.CheckConstraint(
                condition=Q(descuento__gte=0) & Q(descuento__lte=F("cantidad") * F("precio_unitario")),
                name="ck_detalle_cotizacion_descuento",
            ),
            models.CheckConstraint(condition=Q(tasa_iva__gte=0) & Q(tasa_iva__lte=1), name="ck_detalle_cotizacion_tasa_iva"),
        ]


# ------------------------------------------------------------------ Caja

class Caja(models.Model):
    id = models.BigAutoField(primary_key=True, db_column="caja_id")
    sucursal = models.ForeignKey("usuarios.Sucursal", on_delete=models.PROTECT, db_column="sucursal_id", related_name="cajas")
    codigo = models.CharField("código", max_length=20)
    nombre = models.CharField("nombre", max_length=60)
    activa = models.BooleanField("activa", default=True, db_default=True)

    class Meta:
        db_table = "caja"
        db_table_comment = "Terminal o caja física del punto de venta donde se reciben pagos y se realizan cortes."
        verbose_name = "caja"
        verbose_name_plural = "cajas"
        ordering = ["sucursal_id", "codigo"]
        constraints = [
            models.UniqueConstraint(fields=["sucursal", "codigo"], name="uq_caja_sucursal_codigo"),
            ck_no_vacio("codigo", "ck_caja_codigo"),
        ]

    def __str__(self):
        return f"{self.codigo} · {self.nombre}"


class SesionCaja(models.Model):
    class Estado(models.TextChoices):
        ABIERTA = "ABIERTA", "Abierta"
        CERRADA = "CERRADA", "Cerrada"

    id = models.BigAutoField(primary_key=True, db_column="sesion_caja_id")
    caja = models.ForeignKey(Caja, on_delete=models.PROTECT, db_column="caja_id", related_name="sesiones")
    abierto_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, db_column="abierto_por", related_name="+")
    cerrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, db_column="cerrado_por", related_name="+"
    )
    fecha_apertura = models.DateTimeField("apertura", default=timezone.now, db_default=Now())
    fondo_inicial = models.DecimalField("fondo inicial", max_digits=12, decimal_places=2, default=Decimal("0"), db_default=Decimal("0"))
    fecha_cierre = models.DateTimeField("cierre", null=True, blank=True)
    estado = models.CharField("estado", max_length=10, choices=Estado.choices, default="ABIERTA", db_default="ABIERTA")

    class Meta:
        db_table = "sesion_caja"
        db_table_comment = (
            "Periodo (turno) entre la apertura y el cierre de una caja. Controla fondo inicial, responsables y pagos."
        )
        verbose_name = "sesión de caja"
        verbose_name_plural = "sesiones de caja"
        ordering = ["-id"]
        constraints = [
            models.CheckConstraint(condition=Q(fondo_inicial__gte=0), name="ck_sesion_caja_fondo_inicial"),
            models.CheckConstraint(condition=Q(fecha_cierre__gte=F("fecha_apertura")), name="ck_sesion_caja_fecha_cierre"),
            ck_en("estado", ["ABIERTA", "CERRADA"], "ck_sesion_caja_estado"),
            models.CheckConstraint(
                condition=Q(estado="ABIERTA", fecha_cierre__isnull=True, cerrado_por__isnull=True)
                | Q(estado="CERRADA", fecha_cierre__isnull=False, cerrado_por__isnull=False),
                name="ck_sesion_caja_cierre",
            ),
            # Una caja no puede tener más de una sesión ABIERTA al mismo tiempo (índice único parcial).
            models.UniqueConstraint(fields=["caja"], condition=Q(estado="ABIERTA"), name="uq_sesion_caja_abierta"),
        ]

    def __str__(self):
        return f"Sesión {self.id} · {self.caja}"


class ArqueoCaja(models.Model):
    id = models.BigAutoField(primary_key=True, db_column="arqueo_id")
    sesion_caja = models.ForeignKey(SesionCaja, on_delete=models.PROTECT, db_column="sesion_caja_id", related_name="arqueos")
    realizado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, db_column="realizado_por", related_name="+")
    efectivo_esperado = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"), db_default=Decimal("0"))
    efectivo_contado = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"), db_default=Decimal("0"))
    tarjeta_esperado = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"), db_default=Decimal("0"))
    tarjeta_reportado = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"), db_default=Decimal("0"))
    diferencia = models.GeneratedField(
        expression=(F("efectivo_contado") - F("efectivo_esperado")) + (F("tarjeta_reportado") - F("tarjeta_esperado")),
        output_field=models.DecimalField(max_digits=12, decimal_places=2),
        db_persist=True,
    )
    fecha_arqueo = models.DateTimeField(default=timezone.now, db_default=Now())
    observaciones = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "arqueo_caja"
        db_table_comment = (
            "Corte de una sesión de caja: compara importes esperados contra contados y conserva las diferencias."
        )
        verbose_name = "arqueo de caja"
        verbose_name_plural = "arqueos de caja"
        constraints = [
            models.UniqueConstraint(fields=["sesion_caja"], name="uq_arqueo_sesion"),
            models.CheckConstraint(condition=Q(efectivo_esperado__gte=0), name="ck_arqueo_caja_efectivo_esperado"),
            models.CheckConstraint(condition=Q(efectivo_contado__gte=0), name="ck_arqueo_caja_efectivo_contado"),
            models.CheckConstraint(condition=Q(tarjeta_esperado__gte=0), name="ck_arqueo_caja_tarjeta_esperado"),
            models.CheckConstraint(condition=Q(tarjeta_reportado__gte=0), name="ck_arqueo_caja_tarjeta_reportado"),
            models.CheckConstraint(
                condition=Q(diferencia=0) | Q(observaciones__isnull=False), name="ck_arqueo_justifica_diferencia"
            ),
        ]


# ------------------------------------------------------------------ Ventas

class Venta(models.Model):
    class Estado(models.TextChoices):
        ABIERTA = "ABIERTA", "Abierta"
        COMPLETADA = "COMPLETADA", "Completada"
        CANCELADA = "CANCELADA", "Cancelada"

    id = models.BigAutoField(primary_key=True, db_column="venta_id")
    sucursal = models.ForeignKey("usuarios.Sucursal", on_delete=models.PROTECT, db_column="sucursal_id", related_name="ventas")
    cliente = models.ForeignKey("catalogo.Cliente", on_delete=models.PROTECT, db_column="cliente_id", related_name="ventas")
    sesion_caja = models.ForeignKey(SesionCaja, on_delete=models.PROTECT, db_column="sesion_caja_id", related_name="ventas")
    cotizacion = models.ForeignKey(
        Cotizacion, on_delete=models.PROTECT, null=True, blank=True, db_column="cotizacion_id", related_name="ventas"
    )
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, db_column="creado_por", related_name="+")
    cancelado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, db_column="cancelado_por", related_name="+"
    )
    folio = models.CharField("folio", max_length=30)
    fecha_venta = models.DateTimeField("fecha", default=timezone.now, db_default=Now())
    estado = models.CharField("estado", max_length=12, choices=Estado.choices, default="ABIERTA", db_default="ABIERTA")
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"), db_default=Decimal("0"))
    descuento_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"), db_default=Decimal("0"))
    iva_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"), db_default=Decimal("0"))
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"), db_default=Decimal("0"))
    motivo_cancelacion = models.TextField("motivo de cancelación", null=True, blank=True)
    # EXTENSIÓN al E6: identificador que genera el navegador; un reintento no duplica la venta.
    uuid_operacion = models.UUIDField("UUID de operación", null=True, blank=True)

    class Meta:
        db_table = "venta"
        db_table_comment = "Operación comercial realizada a un cliente. Encabeza partidas, impuestos, pagos y comprobantes."
        verbose_name = "venta"
        verbose_name_plural = "ventas"
        ordering = ["-fecha_venta", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["folio"], name="uq_venta_folio"),
            models.UniqueConstraint(fields=["uuid_operacion"], name="uq_venta_uuid_operacion"),
            ck_en("estado", ["ABIERTA", "COMPLETADA", "CANCELADA"], "ck_venta_estado"),
            models.CheckConstraint(condition=Q(subtotal__gte=0), name="ck_venta_subtotal"),
            models.CheckConstraint(
                condition=Q(descuento_total__gte=0) & Q(descuento_total__lte=F("subtotal")), name="ck_venta_descuento_total"
            ),
            models.CheckConstraint(condition=Q(iva_total__gte=0), name="ck_venta_iva_total"),
            models.CheckConstraint(
                condition=Q(total=F("subtotal") - F("descuento_total") + F("iva_total")), name="ck_venta_total"
            ),
            models.CheckConstraint(
                condition=(
                    Q(estado="CANCELADA", cancelado_por__isnull=False, motivo_cancelacion__isnull=False)
                    & GreaterThanOrEqual(Length(Trim("motivo_cancelacion")), 10)
                )
                | (~Q(estado="CANCELADA") & Q(cancelado_por__isnull=True, motivo_cancelacion__isnull=True)),
                name="ck_venta_cancelacion",
            ),
        ]
        indexes = [models.Index(fields=["sucursal", "fecha_venta"], name="ix_venta_sucursal_fecha")]

    def __str__(self):
        return self.folio


class DetalleVenta(models.Model):
    id = models.BigAutoField(primary_key=True, db_column="detalle_venta_id")
    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, db_column="venta_id", related_name="detalles")
    producto = models.ForeignKey("catalogo.Producto", on_delete=models.PROTECT, db_column="producto_id", related_name="+")
    cantidad = models.DecimalField(max_digits=12, decimal_places=3)
    precio_unitario = models.DecimalField("precio unitario (histórico)", max_digits=12, decimal_places=2)
    descuento = models.DecimalField("descuento", max_digits=12, decimal_places=2, default=Decimal("0"), db_default=Decimal("0"))
    tasa_iva = models.DecimalField("tasa de IVA (histórica)", max_digits=5, decimal_places=4, default=Decimal("0.16"), db_default=Decimal("0.16"))

    class Meta:
        db_table = "detalle_venta"
        db_table_comment = "Partidas de una venta con valores históricos. Resuelve la relación N:M entre VENTA y PRODUCTO."
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(condition=Q(cantidad__gt=0), name="ck_detalle_venta_cantidad"),
            models.CheckConstraint(condition=Q(precio_unitario__gte=0), name="ck_detalle_venta_precio_unitario"),
            models.CheckConstraint(
                condition=Q(descuento__gte=0) & Q(descuento__lte=F("cantidad") * F("precio_unitario")),
                name="ck_detalle_venta_descuento",
            ),
            models.CheckConstraint(condition=Q(tasa_iva__gte=0) & Q(tasa_iva__lte=1), name="ck_detalle_venta_tasa_iva"),
        ]

    # Importes derivados (el E6 guarda solo los valores base de la partida)
    @property
    def importe(self):
        return redondear(self.cantidad * self.precio_unitario)

    @property
    def base(self):
        return self.importe - self.descuento

    @property
    def iva(self):
        return redondear(self.base * self.tasa_iva)

    @property
    def total(self):
        return self.base + self.iva

    @property
    def descuento_pct(self):
        if not self.importe:
            return Decimal("0")
        return (self.descuento / self.importe * 100).quantize(Decimal("0.01"))


class DetalleVentaExtintor(models.Model):
    pk = models.CompositePrimaryKey("detalle_venta_id", "extintor_id")
    detalle_venta = models.ForeignKey(DetalleVenta, on_delete=models.CASCADE, db_column="detalle_venta_id", related_name="series")
    extintor = models.ForeignKey("catalogo.Extintor", on_delete=models.PROTECT, db_column="extintor_id", related_name="+")

    class Meta:
        db_table = "detalle_venta_extintor"
        db_table_comment = "Series entregadas en una partida de venta. Identifica exactamente qué unidades físicas salieron del inventario."
        constraints = [models.UniqueConstraint(fields=["extintor"], name="uq_det_venta_extintor_serie")]


class Pago(models.Model):
    class Metodo(models.TextChoices):
        EFECTIVO = "EFECTIVO", "Efectivo"
        TARJETA = "TARJETA", "Tarjeta"

    class Tipo(models.TextChoices):
        COBRO = "COBRO", "Cobro"
        DEVOLUCION = "DEVOLUCION", "Devolución"

    class Estado(models.TextChoices):
        CONFIRMADO = "CONFIRMADO", "Confirmado"
        CANCELADO = "CANCELADO", "Cancelado"

    id = models.BigAutoField(primary_key=True, db_column="pago_id")
    venta = models.ForeignKey(Venta, on_delete=models.PROTECT, db_column="venta_id", related_name="pagos")
    sesion_caja = models.ForeignKey(SesionCaja, on_delete=models.PROTECT, db_column="sesion_caja_id", related_name="pagos")
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, db_column="registrado_por", related_name="+")
    metodo = models.CharField("método", max_length=10, choices=Metodo.choices)
    tipo = models.CharField("tipo", max_length=12, choices=Tipo.choices, default="COBRO", db_default="COBRO")
    monto = models.DecimalField("monto", max_digits=12, decimal_places=2)
    fecha_pago = models.DateTimeField(default=timezone.now, db_default=Now())
    # Solo la autorización de la terminal. Nunca número de tarjeta ni CVV.
    referencia = models.CharField("referencia", max_length=100, null=True, blank=True)
    estado = models.CharField("estado", max_length=12, choices=Estado.choices, default="CONFIRMADO", db_default="CONFIRMADO")

    class Meta:
        db_table = "pago"
        db_table_comment = "Importe recibido o devuelto por una venta. Permite efectivo, tarjeta y pagos combinados."
        ordering = ["id"]
        constraints = [
            ck_en("metodo", ["EFECTIVO", "TARJETA"], "ck_pago_metodo"),
            ck_en("tipo", ["COBRO", "DEVOLUCION"], "ck_pago_tipo"),
            models.CheckConstraint(condition=Q(monto__gt=0), name="ck_pago_monto"),
            ck_en("estado", ["CONFIRMADO", "CANCELADO"], "ck_pago_estado"),
            models.CheckConstraint(
                condition=~Q(metodo="TARJETA") | Q(referencia__isnull=False), name="ck_pago_referencia_tarjeta"
            ),
        ]


class Comprobante(models.Model):
    class Tipo(models.TextChoices):
        TICKET = "TICKET", "Ticket"
        NOTA_VENTA = "NOTA_VENTA", "Nota de venta"
        FACTURA = "FACTURA", "Factura"

    class Estado(models.TextChoices):
        EMITIDO = "EMITIDO", "Emitido"
        CANCELADO = "CANCELADO", "Cancelado"

    id = models.BigAutoField(primary_key=True, db_column="comprobante_id")
    venta = models.ForeignKey(Venta, on_delete=models.PROTECT, db_column="venta_id", related_name="comprobantes")
    tipo = models.CharField(max_length=15, choices=Tipo.choices)
    serie = models.CharField(max_length=15, default="A", db_default="A")
    folio = models.CharField(max_length=40)
    fecha_emision = models.DateTimeField(default=timezone.now, db_default=Now())
    estado = models.CharField(max_length=12, choices=Estado.choices, default="EMITIDO", db_default="EMITIDO")
    uuid_fiscal = models.CharField(max_length=40, null=True, blank=True)

    class Meta:
        db_table = "comprobante"
        db_table_comment = "Ticket, nota de venta o factura emitida para una venta; conserva tipo, serie y folio."
        constraints = [
            models.UniqueConstraint(fields=["tipo", "serie", "folio"], name="uq_comprobante_tipo_serie_folio"),
            models.UniqueConstraint(fields=["uuid_fiscal"], name="uq_comprobante_uuid_fiscal"),
            ck_en("tipo", ["TICKET", "NOTA_VENTA", "FACTURA"], "ck_comprobante_tipo"),
            ck_en("estado", ["EMITIDO", "CANCELADO"], "ck_comprobante_estado"),
            models.CheckConstraint(
                condition=Q(uuid_fiscal__isnull=True)
                | Q(tipo="FACTURA", uuid_fiscal__iregex=r"^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$"),
                name="ck_comprobante_uuid_factura",
            ),
        ]
