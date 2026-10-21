import re
from decimal import Decimal

from django import forms

from apps.core.forms import FormularioSPVCI

from .models import Cliente, ModeloExtintor, Producto, Proveedor

TASAS = [("0.1600", "IVA 16 %"), ("0.0800", "IVA 8 % (región fronteriza)"), ("0.0000", "Tasa 0 % / exento")]


class ProductoForm(FormularioSPVCI, forms.ModelForm):
    tasa_iva = forms.TypedChoiceField(label="IVA", choices=TASAS, coerce=Decimal)
    motivo = forms.CharField(
        label="Motivo del cambio",
        required=False,
        max_length=200,
        help_text="Queda en el historial de cambios cuando modificas precios, mínimo o estado.",
    )

    class Meta:
        model = Producto
        fields = [
            "sku", "codigo_barras", "nombre", "marca", "tipo", "unidad_medida", "categoria", "proveedor",
            "precio_compra", "precio_venta", "tasa_iva", "stock_minimo", "activo", "descripcion",
        ]
        widgets = {"descripcion": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["proveedor"].queryset = Proveedor.objects.filter(activo=True)
        if self.instance.pk:
            self.initial["tasa_iva"] = f"{self.instance.tasa_iva:.4f}"

    def clean_sku(self):
        return self.cleaned_data["sku"].strip().upper()

    def clean_codigo_barras(self):
        cb = (self.cleaned_data.get("codigo_barras") or "").strip()
        if cb and not re.fullmatch(r"[0-9]{8,14}", cb):
            raise forms.ValidationError("El código de barras debe tener de 8 a 14 dígitos.")
        return cb or None

    def clean(self):
        d = super().clean()
        tipo = d.get("tipo")
        if tipo == Producto.Tipo.SERVICIO:
            d["unidad_medida"] = Producto.Unidad.SERVICIO
            d["stock_minimo"] = Decimal("0")
            d["categoria"] = "Servicios"
            self.instance.unidad_medida, self.instance.stock_minimo, self.instance.categoria = "SERVICIO", Decimal("0"), "Servicios"
        elif tipo == Producto.Tipo.EXTINTOR and d.get("unidad_medida") != Producto.Unidad.PIEZA:
            self.add_error("unidad_medida", "Un extintor se maneja por pieza.")
        elif tipo and tipo != Producto.Tipo.SERVICIO and d.get("unidad_medida") == Producto.Unidad.SERVICIO:
            self.add_error("unidad_medida", "Solo los servicios usan la unidad «Servicio».")
        if self.instance.pk:
            cambios = [c for c in ("precio_venta", "precio_compra", "stock_minimo", "activo") if c in self.changed_data]
            if cambios and len((d.get("motivo") or "").strip()) < 5:
                self.add_error("motivo", "Escribe el motivo del cambio (mínimo 5 caracteres).")
        return d


class ModeloExtintorForm(FormularioSPVCI, forms.ModelForm):
    class Meta:
        model = ModeloExtintor
        fields = ["tipo_agente", "capacidad", "unidad_capacidad", "modelo", "meses_entre_recargas"]


class ClienteForm(FormularioSPVCI, forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ["tipo_persona", "nombre_razon_social", "rfc", "telefono", "correo", "direccion_fiscal", "descuento_pct", "activo"]

    def clean_rfc(self):
        rfc = (self.cleaned_data.get("rfc") or "").strip().upper()
        if rfc and not re.fullmatch(r"[A-ZÑ&]{3,4}[0-9]{6}[A-Z0-9]{3}", rfc):
            raise forms.ValidationError("RFC con formato inválido (12 o 13 caracteres).")
        return rfc or None

    def clean_descuento_pct(self):
        v = self.cleaned_data.get("descuento_pct") or Decimal("0")
        if v < 0 or v > 50:
            raise forms.ValidationError("El descuento debe estar entre 0 y 50 %.")
        return v


class ProveedorForm(FormularioSPVCI, forms.ModelForm):
    class Meta:
        model = Proveedor
        fields = ["nombre_razon_social", "rfc", "telefono", "correo", "direccion", "activo"]

    def clean_rfc(self):
        rfc = (self.cleaned_data.get("rfc") or "").strip().upper()
        if rfc and not re.fullmatch(r"[A-ZÑ&]{3,4}[0-9]{6}[A-Z0-9]{3}", rfc):
            raise forms.ValidationError("RFC con formato inválido (12 o 13 caracteres).")
        return rfc or None
