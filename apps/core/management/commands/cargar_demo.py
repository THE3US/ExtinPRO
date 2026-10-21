"""
Carga los datos de ejemplo del prototipo (Demo v2 / Entregable 7) en la base de datos.

Son los mismos datos con los que se ejecutaron los 47 casos de prueba del E7:
usuarios gerente01 / cajero01 / almacen01 / admin (contraseña demo2026), 18 productos,
OC-0045 a OC-0048, 638 ventas desde el 1 de mayo de 2026 y el kárdex completo.
El archivo datos_demo_e7.json se generó ejecutando el código del prototipo.

Uso:
    python manage.py cargar_demo            # fechas tal como en el E7 (hoy = 19 oct 2026)
    python manage.py cargar_demo --al-dia   # recorre las fechas para que el «hoy» del demo sea hoy
"""
import hashlib
import json
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.catalogo.models import Cliente, ModeloExtintor, Producto, Proveedor
from apps.compras.models import DetalleOrdenCompra, DetalleRecepcion, OrdenCompra, RecepcionCompra
from apps.core.models import Bitacora
from apps.inventario.models import DetalleInventarioFisico, InventarioFisico, MovimientoInventario
from apps.usuarios.models import Rol, Sucursal, Usuario
from apps.ventas.models import ArqueoCaja, Caja, Comprobante, DetalleVenta, Pago, SesionCaja, Venta

ARCHIVO = Path(__file__).resolve().parents[2] / "demo" / "datos_demo_e7.json"
CENT = Decimal("0.01")
AGENTES = {"PQS ABC": "PQS", "CO₂": "CO2", "Agua": "AGUA", "Acetato de potasio": "ACETATO_POTASIO"}
TIPO_PERSONA = {"PUBLICO_GENERAL": "PUBLICO_GENERAL", "MORAL": "MORAL", "FISICA": "FISICA"}
D = Decimal


def dinero(v):
    return D(str(v)).quantize(CENT, rounding=ROUND_HALF_UP)


class Command(BaseCommand):
    help = "Carga los datos de ejemplo del Entregable 7 (usuarios demo, catálogo, órdenes, ventas y kárdex)."

    def add_arguments(self, parser):
        parser.add_argument("--al-dia", action="store_true", help="Desplaza las fechas para que el último día del demo sea hoy.")

    def handle(self, *args, **opts):
        if Producto.objects.exists() or Venta.objects.exists() or Usuario.objects.filter(nombre_usuario="gerente01").exists():
            raise CommandError("La base ya tiene datos. cargar_demo solo funciona sobre una base recién migrada.")
        datos = json.loads(ARCHIVO.read_text(encoding="utf-8"))
        hoy_demo = date.fromisoformat(datos["HOY"])
        self.desfase = (timezone.localdate() - hoy_demo) if opts["al_dia"] else timedelta(0)
        with transaction.atomic():
            self.cargar(datos)
        self.stdout.write(self.style.SUCCESS(
            f"Datos de ejemplo cargados ({len(datos['VENTAS'])} ventas, {len(datos['ORDENES'])} órdenes de compra). "
            "Usuarios: gerente01, cajero01, almacen01, admin · contraseña demo2026"
        ))

    # ------------------------------------------------------------------ utilidades
    def fecha(self, s):
        return date.fromisoformat(s[:10]) + self.desfase

    def momento(self, s, hora="10:00"):
        """'2026-10-14' o '2026-10-14T10:47' → datetime con zona de México."""
        f = self.fecha(s)
        h = s[11:16] if len(s) > 10 else hora
        return timezone.make_aware(datetime.combine(f, time.fromisoformat(h)))

    # ------------------------------------------------------------------ carga
    def cargar(self, d):
        roles = {r.nombre: r for r in Rol.objects.all()}
        suc = {}
        for a in d["ALMACENES"]:
            suc[a["id"]] = Sucursal.objects.create(nombre=a["nombre"], direccion="Aguascalientes, Ags. (dirección por confirmar)")
        cajas = {i: Caja.objects.create(sucursal=s, codigo=f"CAJA-0{i}", nombre=f"Caja principal {s.corto}") for i, s in suc.items()}

        usuarios = {}
        for u in d["USUARIOS"]:
            usuarios[u["usuario"]] = Usuario.objects.create_user(
                u["usuario"], "demo2026", nombre_completo=u["nombre"], rol=roles[u["rol"]], sucursal=suc[1]
            )
        gerente = usuarios["gerente01"]

        proveedores = {
            p["id"]: Proveedor.objects.create(nombre_razon_social=p["nombre"], rfc=p["rfc"], correo=p.get("correo"))
            for p in d["PROVEEDORES"]
        }
        clientes = {}
        for c in d["CLIENTES"]:
            if c["tipo"] == "PUBLICO_GENERAL":
                clientes[c["id"]] = Cliente.objects.get(tipo_persona="PUBLICO_GENERAL")
            else:
                clientes[c["id"]] = Cliente.objects.create(
                    tipo_persona=TIPO_PERSONA[c["tipo"]], nombre_razon_social=c["nombre"], rfc=c["rfc"],
                    correo=c.get("correo"), descuento_pct=D(c["desc"]),
                )

        prods = {}
        alta = timezone.make_aware(datetime(2026, 1, 15, 11, 30)) + self.desfase
        for p in d["PRODUCTOS"]:
            obj = Producto.objects.create(
                sku=p["sku"], codigo_barras=p["cb"], nombre=p["nombre"], marca=None if p["marca"] == "—" else p["marca"],
                tipo=p["tipo"], unidad_medida="SERVICIO" if p["tipo"] == "SERVICIO" else "PIEZA", categoria=p["cat"],
                proveedor=proveedores.get(p["prov"]), precio_compra=D(p["costo"]), precio_venta=D(p["precio"]),
                stock_minimo=D(p["min"]), activo=p["activo"],
            )
            if p["tipo"] == "EXTINTOR":
                cap = p["ext"]["cap"].split()
                ModeloExtintor.objects.create(
                    producto=obj, tipo_agente=AGENTES.get(p["ext"]["agente"], "OTRO"), capacidad=D(cap[0]),
                    unidad_capacidad="lb" if cap[1] == "lb" else "kg", meses_entre_recargas=p["ext"]["recarga"],
                )
            prods[p["id"]] = obj
            self.historial_producto(obj, p, usuarios, alta)

        # ---- Existencias iniciales: conteo físico de apertura (el E6 exige origen para un AJUSTE)
        movs = []
        apertura = self.momento(d["INICIO_HIST"], "07:30")
        for a_id, s in suc.items():
            conteo = InventarioFisico.objects.create(
                sucursal=s, creado_por=gerente, autorizado_por=gerente, fecha_inicio=apertura,
                fecha_cierre=apertura + timedelta(minutes=20), estado="AJUSTADO", observaciones="Conteo inicial de apertura del sistema",
            )
            for p_id, p in prods.items():
                if p.es_servicio:
                    continue
                cant = D(d["INICIAL"].get(f"{p_id}-{a_id}", 0))
                det = DetalleInventarioFisico.objects.create(inventario_fisico=conteo, producto=p, existencia_sistema=0, existencia_fisica=cant)
                if cant > 0:
                    movs.append(MovimientoInventario(sucursal=s, producto=p, tipo="AJUSTE", cantidad=cant, costo_unitario=p.precio_compra,
                                                     registrado_por=gerente, detalle_inventario=det, fecha_movimiento=apertura + timedelta(minutes=25),
                                                     observaciones="Existencia inicial"))

        # ---- Órdenes de compra
        ordenes, detalles_oc = {}, {}
        for o in d["ORDENES"]:
            oc = OrdenCompra.objects.create(
                proveedor=proveedores[o["prov"]], sucursal=suc[o["alm"]], creado_por=usuarios[o["creado"]], folio=o["folio"],
                fecha_orden=self.momento(o["fecha"], "10:00"), fecha_estimada=self.fecha(o["estimada"]) if o.get("estimada") else None,
                estado=o["estado"], observaciones=o.get("obs") or None,
            )
            ordenes[o["folio"]] = oc
            for l in o["lines"]:
                detalles_oc[(o["folio"], l["prod"])] = DetalleOrdenCompra.objects.create(
                    orden_compra=oc, producto=prods[l["prod"]], cantidad=D(l["cant"]), costo_unitario=D(l["costo"])
                )

        # ---- Recepciones aplicadas + ENTRADA_COMPRA
        for r in d["RECEPCIONES"]:
            confirmado = self.momento(r["confirmado"])
            rec = RecepcionCompra.objects.create(
                orden_compra=ordenes[r["oc"]], recibido_por=usuarios[r["usuario"]], folio_recepcion=r["folio"],
                fecha_recepcion=confirmado, documento_proveedor=r["doc"], estado="APLICADA", observaciones=r.get("obs") or None,
            )
            for l in r["lines"]:
                det = DetalleRecepcion.objects.create(
                    recepcion=rec, detalle_orden=detalles_oc[(r["oc"], l["prod"])], producto=prods[l["prod"]],
                    cantidad_recibida=D(l["recibida"]), costo_unitario_real=D(l["costo"]),
                )
                movs.append(MovimientoInventario(sucursal=suc[r["alm"]], producto=prods[l["prod"]], tipo="ENTRADA_COMPRA",
                                                 cantidad=D(l["recibida"]), costo_unitario=D(l["costo"]), registrado_por=usuarios[r["usuario"]],
                                                 detalle_recepcion=det, fecha_movimiento=confirmado,
                                                 observaciones=f"Recepción {r['folio']} de {r['oc']}"))

        # ---- Ventas con sesión de caja diaria, pagos, comprobantes y SALIDA_VENTA
        por_dia = defaultdict(list)
        for v in d["VENTAS"]:
            por_dia[(v["fecha"], v["alm"])].append(v)
        for (dia, a_id), ventas in sorted(por_dia.items()):
            abre = self.momento(dia, "09:00")
            vendedor = usuarios[ventas[0]["vendedor"]]
            sesion = SesionCaja.objects.create(caja=cajas[a_id], abierto_por=vendedor, fecha_apertura=abre, fondo_inicial=D("500"))
            efectivo = tarjeta = D("0")
            for v in ventas:
                momento = self.momento(f"{dia}T{v['hora']}")
                venta = Venta.objects.create(
                    sucursal=suc[a_id], cliente=clientes[v["cliente"]], sesion_caja=sesion, creado_por=usuarios[v["vendedor"]],
                    folio=v["folio"], fecha_venta=momento, estado="COMPLETADA", subtotal=dinero(v["subtotal"]),
                    descuento_total=dinero(v["descuento"]), iva_total=dinero(v["iva"]), total=dinero(v["total"]),
                )
                desc_restante = dinero(v["descuento"])
                for i, l in enumerate(v["lines"]):
                    imp = dinero(D(l["qty"]) * D(str(l["precio"])))
                    desc = desc_restante if i == len(v["lines"]) - 1 else min(desc_restante, dinero(imp * D(l["desc"]) / 100))
                    desc_restante -= desc
                    p = prods[l["prod"]]
                    det = DetalleVenta.objects.create(venta=venta, producto=p, cantidad=D(l["qty"]), precio_unitario=D(str(l["precio"])),
                                                      descuento=desc, tasa_iva=p.tasa_iva)
                    if not p.es_servicio:
                        movs.append(MovimientoInventario(sucursal=suc[a_id], producto=p, tipo="SALIDA_VENTA", cantidad=D(l["qty"]),
                                                         costo_unitario=p.precio_compra, registrado_por=usuarios[v["vendedor"]],
                                                         detalle_venta=det, fecha_movimiento=momento, observaciones=f"Venta {v['folio']}"))
                ref = None
                if v["metodo"] == "TARJETA":
                    ref = str(int(hashlib.sha1(v["folio"].encode()).hexdigest(), 16))[:6]
                    tarjeta += venta.total
                else:
                    efectivo += venta.total
                Pago.objects.create(venta=venta, sesion_caja=sesion, registrado_por=usuarios[v["vendedor"]], metodo=v["metodo"],
                                    monto=venta.total, fecha_pago=momento, referencia=ref)
                Comprobante.objects.create(venta=venta, tipo="TICKET", serie="A", folio=v["folio"], fecha_emision=momento)
            cierre = self.momento(dia, "19:00")
            SesionCaja.objects.filter(pk=sesion.pk).update(estado="CERRADA", cerrado_por=vendedor, fecha_cierre=cierre)
            ArqueoCaja.objects.create(sesion_caja=sesion, realizado_por=vendedor, efectivo_esperado=efectivo + D("500"),
                                      efectivo_contado=efectivo + D("500"), tarjeta_esperado=tarjeta, tarjeta_reportado=tarjeta, fecha_arqueo=cierre)

        # ---- Ajustes por conteo físico (IF del 30 sep)
        MovimientoInventario.objects.bulk_create(movs)
        movs = []
        for a in d["AJUSTES"]:
            s, p = suc[a["alm"]], prods[a["prod"]]
            momento = self.momento(a["fecha"], "17:45")
            from apps.inventario.services import existencia

            sistema = existencia(s, p, hasta=self.fecha(a["fecha"]))
            conteo = InventarioFisico.objects.create(sucursal=s, creado_por=gerente, autorizado_por=gerente, fecha_inicio=momento - timedelta(hours=1),
                                                     fecha_cierre=momento - timedelta(minutes=10), estado="AJUSTADO", observaciones=a["obs"])
            det = DetalleInventarioFisico.objects.create(inventario_fisico=conteo, producto=p, existencia_sistema=sistema,
                                                         existencia_fisica=sistema + D(a["delta"]), observaciones=a["obs"])
            movs.append(MovimientoInventario(sucursal=s, producto=p, tipo="AJUSTE", cantidad=abs(D(a["delta"])), costo_unitario=p.precio_compra,
                                             registrado_por=gerente, detalle_inventario=det, fecha_movimiento=momento, observaciones=a["obs"]))
        MovimientoInventario.objects.bulk_create(movs)

    def historial_producto(self, obj, p, usuarios, alta):
        """Mismos registros de ejemplo que cambiosDe() del demo (Fig. 9)."""
        if p["tipo"] == "SERVICIO":
            return
        g = usuarios["gerente01"]

        def reg(fecha, campo, antes, despues, usuario, motivo):
            Bitacora.objects.create(fecha=timezone.make_aware(datetime.fromisoformat(fecha)) + self.desfase, usuario=usuario, entidad="PRODUCTO",
                                    registro_id=obj.pk, accion="ALTA" if campo == "Alta en catálogo" else "CAMBIO", campo=campo,
                                    valor_anterior=antes, valor_nuevo=despues, motivo=motivo)

        m = lambda v: f"${v:,.2f}"  # noqa: E731
        reg("2026-01-15T11:30", "Alta en catálogo", "—", p["sku"], usuarios["admin"], "Registro inicial")
        reg("2026-04-01T09:12", "Precio de venta", m(round(p["precio"] * 0.94)), m(p["precio"]), g, "Actualización semestral de precios")
        reg("2026-04-01T09:12", "Precio de compra", m(round(p["costo"] * 0.95)), m(p["costo"]), g, "Nueva lista del proveedor")
        if p["min"] >= 4:
            reg("2026-08-12T16:40", "Stock mínimo", str(p["min"] - 1), str(p["min"]), g, "Ajuste por temporada alta")
        if p["activo"] is False:
            reg("2026-07-03T10:05", "Estado", "Activo", "Descontinuado", g, "El fabricante dejó de surtir el modelo")
