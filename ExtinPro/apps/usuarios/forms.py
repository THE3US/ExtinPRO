import re

from django import forms
from django.contrib.auth import password_validation

from apps.core.forms import FormularioSPVCI
from apps.ventas.models import Caja

from .models import Rol, Sucursal, Usuario


class UsuarioForm(FormularioSPVCI, forms.ModelForm):
    password = forms.CharField(
        label="Contraseña", widget=forms.PasswordInput(render_value=False), required=False, strip=False,
        help_text="Mínimo 8 caracteres. En edición, déjala vacía para conservar la actual.",
    )

    class Meta:
        model = Usuario
        fields = ["nombre_completo", "nombre_usuario", "rol", "sucursal", "activo"]
        help_texts = {"nombre_usuario": "Minúsculas, números, punto, guion o guion bajo (4 a 60).",
                      "sucursal": "Almacén asignado. Gerente y Administrador pueden operar cualquier almacén."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["sucursal"].queryset = Sucursal.objects.filter(activa=True)
        self.fields["rol"].queryset = Rol.objects.all()
        if self.instance.pk is None:
            self.fields["password"].required = True

    def clean_nombre_usuario(self):
        u = self.cleaned_data["nombre_usuario"].strip().lower()
        if not re.fullmatch(r"[a-z0-9._-]{4,60}", u):
            raise forms.ValidationError("Usa de 4 a 60 caracteres: minúsculas, números, punto, guion o guion bajo.")
        return u

    def clean_password(self):
        p = self.cleaned_data.get("password")
        if p:
            password_validation.validate_password(p, self.instance)
        return p

    def save(self, commit=True):
        u = super().save(commit=False)
        if self.cleaned_data.get("password"):
            u.set_password(self.cleaned_data["password"])
        if commit:
            u.save()
        return u


class SucursalForm(FormularioSPVCI, forms.ModelForm):
    class Meta:
        model = Sucursal
        fields = ["nombre", "direccion", "telefono", "activa"]


class CajaForm(FormularioSPVCI, forms.ModelForm):
    class Meta:
        model = Caja
        fields = ["sucursal", "codigo", "nombre", "activa"]
