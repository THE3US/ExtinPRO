from django import forms


class FormularioSPVCI:
    """Aplica las clases visuales del demo (inp / sel / txt) a los widgets."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            w = campo.widget
            if isinstance(w, (forms.Select, forms.SelectMultiple)):
                w.attrs.setdefault("class", "sel")
            elif isinstance(w, forms.Textarea):
                w.attrs.setdefault("class", "txt")
                w.attrs.setdefault("rows", 3)
            elif isinstance(w, forms.CheckboxInput):
                pass
            else:
                w.attrs.setdefault("class", "inp")
