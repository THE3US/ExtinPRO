"""Filtros y etiquetas de plantilla que replican los formatos y componentes del Demo v2."""
from decimal import Decimal, InvalidOperation

from django import template
from django.utils import timezone
from django.utils.html import escape, format_html
from django.utils.http import urlencode
from django.utils.safestring import mark_safe

from apps.core.iconos import ICONOS

register = template.Library()
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def _dec(v):
    try:
        return Decimal(v)
    except (InvalidOperation, TypeError, ValueError):
        return None


@register.filter
def dinero(v):
    """1250 → $1,250.00 (formato es-MX del demo)."""
    d = _dec(v)
    if d is None:
        return ""
    signo = "-" if d < 0 else ""
    return f"{signo}${abs(d):,.2f}"


@register.filter
def cantidad(v):
    """5.000 → 5 ; 2.500 → 2.5 ; 1500 → 1,500"""
    d = _dec(v)
    if d is None:
        return ""
    if d == d.to_integral_value():
        return f"{int(d):,}"
    return f"{d.normalize():,f}"


@register.filter
def entero(v):
    d = _dec(v)
    return "" if d is None else f"{int(d):,}"


@register.filter
def porcentaje(v, decimales=1):
    d = _dec(v)
    if d is None:
        return ""
    return f"{d:.{int(decimales)}f} %"


@register.filter
def fecha(v):
    """2026-10-19 → 19 oct 2026"""
    if not v:
        return "—"
    if hasattr(v, "hour"):
        v = timezone.localtime(v) if timezone.is_aware(v) else v
    return f"{v.day} {MESES[v.month - 1]} {v.year}"


@register.filter
def fecha_hora(v):
    if not v:
        return "—"
    v = timezone.localtime(v) if timezone.is_aware(v) else v
    return f"{v.day} {MESES[v.month - 1]} {v.year} · {v:%H:%M}"


@register.filter
def iso(v):
    return v.isoformat() if v else ""


@register.simple_tag
def icono(nombre, clase="i"):
    return format_html('<svg class="{}" viewBox="0 0 24 24" aria-hidden="true">{}</svg>', clase, mark_safe(ICONOS.get(nombre, "")))


@register.simple_tag
def pill(clase, texto):
    return format_html('<span class="pill {}">{}</span>', clase, texto)


@register.simple_tag(takes_context=True)
def query(context, **kwargs):
    """Conserva los filtros de la URL y cambia los indicados (paginación)."""
    q = context["request"].GET.copy()
    for k, v in kwargs.items():
        q[k] = v
    return "?" + urlencode(sorted(q.lists()), doseq=True)


@register.simple_tag
def arte_producto(producto, alto=64):
    """Ilustración SVG genérica por tipo de producto (prodArt del demo)."""
    alto = int(alto)
    ancho = round(alto * 0.75)
    if producto.tipo == "EXTINTOR":
        agente = getattr(getattr(producto, "modelo_extintor", None), "tipo_agente", None) or _agente_por_sku(producto.sku)
        etiqueta = {"CO2": "CO₂", "AGUA": "H₂O", "ACETATO_POTASIO": "K"}.get(agente, "PQS")
        cuerpo = "#B8C1CD" if etiqueta in ("K", "H₂O") else "#E30613"
        boquilla = (
            '<path d="M30 15 L38 10 L41 22 L35 21 Z" fill="#252A30"/>'
            if etiqueta == "CO₂"
            else '<path d="M30 14 C38 14 40 20 40 30" stroke="#252A30" stroke-width="2.4" fill="none" stroke-linecap="round"/>'
        )
        return mark_safe(
            f'<svg viewBox="0 0 48 64" width="{ancho}" height="{alto}" aria-hidden="true"><rect x="19" y="5" width="10" height="7" rx="1.5" fill="#0B2F61"/>'
            f'<path d="M24 7 L34 3" stroke="#0B2F61" stroke-width="2.4" stroke-linecap="round"/>{boquilla}'
            f'<rect x="13" y="12" width="22" height="49" rx="8" fill="{cuerpo}"/><rect x="13" y="26" width="22" height="15" fill="#fff"/>'
            f'<text x="24" y="37" text-anchor="middle" font-family="Montserrat,Arial" font-weight="800" font-size="8.5" fill="#0B2F61">{etiqueta}</text>'
            f'<rect x="16" y="15" width="3" height="40" rx="1.5" fill="#fff" opacity=".25"/></svg>'
        )
    if producto.categoria == "Señalización":
        verde = producto.sku.upper().startswith("SEN-RUT")
        interior = (
            '<path d="M18 30h22m-7-7 8 7-8 7" stroke="#fff" stroke-width="4" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
            if verde
            else '<rect x="27" y="20" width="10" height="22" rx="3" fill="#fff"/><path d="M30 20v-3h4v3M34 18l6-2" stroke="#fff" stroke-width="2.2" fill="none"/>'
        )
        return mark_safe(
            f'<svg viewBox="0 0 64 64" width="{alto}" height="{alto}" aria-hidden="true">'
            f'<rect x="8" y="12" width="48" height="36" rx="3" fill="{"#1B7A47" if verde else "#E30613"}"/>{interior}</svg>'
        )
    tam = round(alto * 0.6)
    sku = producto.sku.upper()
    if producto.tipo == "SERVICIO":
        nombre = "gauge" if "REC" in sku else "wrench"
    else:
        nombre = (
            "gauge" if sku.startswith("INS-MAN") else "mount" if sku.startswith("ACC-SOP") else "wrench" if sku.startswith("INS-VAL") else "box"
        )
    return mark_safe(
        f'<svg viewBox="0 0 24 24" width="{tam}" height="{tam}" style="stroke:#0B2F61;fill:none;stroke-width:1.6;'
        f'stroke-linecap:round;stroke-linejoin:round" aria-hidden="true">{ICONOS[nombre]}</svg>'
    )


def _agente_por_sku(sku):
    sku = sku.upper()
    if "CO2" in sku:
        return "CO2"
    if "AGU" in sku:
        return "AGUA"
    if "-K-" in sku:
        return "ACETATO_POTASIO"
    return "PQS"


@register.simple_tag
def celda_producto(producto, extra=""):
    return format_html(
        '<div class="prod-cell"><span class="prod-thumb">{}</span><div><b>{}</b><small>{}{}</small></div></div>',
        arte_producto(producto, 32),
        producto.nombre,
        producto.sku,
        extra,
    )


@register.simple_tag
def codigo_barras(codigo, ancho=220, alto=70):
    """Código EAN-13 en SVG (eanSVG del demo). Si no es EAN-13 válido, muestra solo el texto."""
    codigo = (codigo or "").strip()
    if len(codigo) != 13 or not codigo.isdigit():
        return format_html('<span class="mono">{}</span>', codigo or "—")
    L = ["0001101", "0011001", "0010011", "0111101", "0100011", "0110001", "0101111", "0111011", "0110111", "0001011"]
    G = ["0100111", "0110011", "0011011", "0100001", "0011101", "0111001", "0000101", "0010001", "0001001", "0010111"]
    R = ["1110010", "1100110", "1101100", "1000010", "1011100", "1001110", "1010000", "1000100", "1001000", "1110100"]
    P = ["LLLLLL", "LLGLGG", "LLGGLG", "LLGGGL", "LGLLGG", "LGGLLG", "LGGGLL", "LGLGLG", "LGLGGL", "LGGLGL"]
    d = [int(c) for c in codigo]
    bits = "101"
    for i in range(1, 7):
        bits += (L if P[d[0]][i - 1] == "L" else G)[d[i]]
    bits += "01010"
    for i in range(7, 13):
        bits += R[d[i]]
    bits += "101"
    w, h = int(ancho), int(alto)
    mw = w / (len(bits) + 14)
    rects = []
    for i, b in enumerate(bits):
        if b == "1":
            guarda = i < 3 or 45 <= i < 50 or i >= 92
            rects.append(f'<rect x="{(7 + i) * mw:.2f}" y="0" width="{mw:.2f}" height="{h - 8 if guarda else h - 16}" fill="#252A30"/>')

    def t(x, s):
        return f'<text x="{x:.2f}" y="{h - 1}" font-family="IBM Plex Mono,monospace" font-size="{mw * 7:.2f}" fill="#252A30" text-anchor="middle">{s}</text>'

    textos = t(3 * mw, d[0]) + t((7 + 3 + 21) * mw, codigo[1:7]) + t((7 + 50 + 21) * mw, codigo[7:])
    return mark_safe(
        f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="Código de barras {escape(codigo)}">{"".join(rects)}{textos}</svg>'
    )
