import re

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.catalogo.models import Producto
from apps.core.services import siguiente_folio
from apps.usuarios.decoradores import requiere_modulo

from .models import SolicitudWeb

SERVICIOS = [
    ("ext", "Venta de extintores", "PQS, CO₂, agua y clase K. Te ayudamos a elegir el tipo y la capacidad según el riesgo de tu espacio."),
    ("gauge", "Recarga", "Recarga del agente extintor y revisión de componentes. Te avisamos cuándo toca la siguiente."),
    ("clock", "Mantenimiento", "Revisión preventiva y correctiva del equipo, con registro del trabajo realizado."),
    ("mount", "Instalación", "Colocación de soportes y gabinetes a la altura y en la ubicación adecuadas."),
    ("sign", "Señalización", "Señales fotoluminiscentes de equipo contra incendio y de rutas de evacuación."),
    ("book", "Capacitación", "Uso básico del extintor para tu equipo de trabajo, con práctica guiada."),
]
AUDIENCIAS = [
    ("Hogares", "Saber qué equipo necesitan, cuánto cuesta y cómo recibir orientación.", "Lenguaje simple, respuestas directas y contacto visible."),
    ("Comercios y oficinas", "Organizar compra, mantenimiento y señalización, y coordinar horarios.", "Servicios claros, alcance por escrito y seguimiento."),
    ("Empresas e industria", "Información técnica, cantidades, documentación y coordinación operativa.", "Especificaciones verificadas y atención estructurada."),
    ("Instituciones", "Trazabilidad, cotizaciones formales y claridad en alcances y tiempos.", "Documentación ordenada y requisitos confirmados."),
]
RE_CORREO = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")


def destacados():
    qs = Producto.objects.filter(activo=True).exclude(tipo=Producto.Tipo.SERVICIO).select_related("modelo_extintor")
    extintores = list(qs.filter(tipo=Producto.Tipo.EXTINTOR).order_by("sku")[:3])
    otros = list(qs.exclude(tipo=Producto.Tipo.EXTINTOR).filter(categoria="Señalización").order_by("sku")[:1])
    return (extintores + otros)[:4]


def inicio(request, contexto=None):
    """Sitio web público (E7 · Fig. 1 y 2)."""
    ctx = {
        "servicios": SERVICIOS,
        "audiencias": AUDIENCIAS,
        "productos": destacados(),
        "tipos_espacio": SolicitudWeb.TIPOS_ESPACIO,
        "enviada": request.GET.get("enviada", ""),
        "datos": {},
    }
    ctx.update(contexto or {})
    return render(request, "sitio/inicio.html", ctx, status=400 if (contexto or {}).get("errores") else 200)


def validar(datos):
    errores = []
    if len(datos["nombre"]) < 3:
        errores.append("Escribe tu nombre (mínimo 3 caracteres).")
    digitos = re.sub(r"\D", "", datos["contacto"])
    tel_ok = len(digitos) == 10 and not re.search(r"[A-Za-z@]", datos["contacto"])
    if not tel_ok and not RE_CORREO.match(datos["contacto"]):
        errores.append("Escribe un teléfono de 10 dígitos o un correo válido.")
    if not datos["privacidad"]:
        errores.append("Para enviar la solicitud acepta el aviso de privacidad.")
    return errores


@require_POST
def cotizacion(request):
    """Formulario de contacto (CP-08-01 a CP-08-03)."""
    datos = {
        "nombre": request.POST.get("nombre", "").strip(),
        "contacto": request.POST.get("contacto", "").strip(),
        "tipo_espacio": request.POST.get("tipo_espacio", ""),
        "servicio": request.POST.get("servicio", ""),
        "mensaje": request.POST.get("mensaje", "").strip()[:2000],
        "privacidad": request.POST.get("privacidad") == "on",
    }
    if datos["tipo_espacio"] not in SolicitudWeb.TIPOS_ESPACIO:
        datos["tipo_espacio"] = SolicitudWeb.TIPOS_ESPACIO[0]
    if datos["servicio"] not in SolicitudWeb.SERVICIOS:
        datos["servicio"] = SolicitudWeb.SERVICIOS[0]
    errores = validar(datos)
    if errores:
        return inicio(request, {"errores": errores, "datos": datos})
    with transaction.atomic():
        s = SolicitudWeb.objects.create(
            folio=siguiente_folio(SolicitudWeb, "folio", "WEB-", 4, "solicitud_web"),
            nombre=datos["nombre"],
            contacto=datos["contacto"],
            tipo_espacio=datos["tipo_espacio"],
            servicio=datos["servicio"],
            mensaje=datos["mensaje"],
            acepto_privacidad=True,
        )
    return redirect(f"/?enviada={s.folio}#contacto")


@requiere_modulo("reporte_ventas", seccion="solicitudes")
def solicitudes(request):
    if request.method == "POST":
        s = get_object_or_404(SolicitudWeb, pk=request.POST.get("id"))
        s.atendida = not s.atendida
        s.save(update_fields=["atendida"])
        messages.success(request, f"{s.folio} marcada como {'atendida' if s.atendida else 'pendiente'}.")
        return redirect("sitio:solicitudes")
    return render(request, "sitio/solicitudes.html", {"solicitudes": SolicitudWeb.objects.all()[:200]})
