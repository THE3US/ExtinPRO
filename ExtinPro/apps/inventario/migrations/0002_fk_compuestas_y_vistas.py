"""
Completa el modelo del Entregable 6 con lo que el ORM de Django no declara por sí solo:

1. Las cuatro llaves foráneas compuestas (garantizan que la serie / partida corresponda al producto).
2. Vistas de consulta del kárdex: v_kardex (cantidad con signo) y v_existencia (existencia actual).
"""
from django.db import migrations

FKS = [
    ("detalle_recepcion", "fk_det_recepcion_det_orden", "detalle_orden_id, producto_id",
     "detalle_orden_compra", "detalle_orden_id, producto_id"),
    ("extintor", "fk_extintor_det_recepcion", "detalle_recepcion_id, producto_id",
     "detalle_recepcion", "detalle_recepcion_id, producto_id"),
    ("movimiento_inventario", "fk_movimiento_extintor", "extintor_id, producto_id",
     "extintor", "extintor_id, producto_id"),
    ("detalle_inventario_fisico", "fk_det_inventario_extintor", "extintor_id, producto_id",
     "extintor", "extintor_id, producto_id"),
]

VISTAS = """
CREATE OR REPLACE VIEW v_kardex AS
SELECT m.movimiento_id,
       m.sucursal_id,
       m.producto_id,
       m.extintor_id,
       m.tipo,
       m.fecha_movimiento,
       m.cantidad,
       CASE
           WHEN m.tipo = 'ENTRADA_COMPRA' THEN m.cantidad
           WHEN m.tipo IN ('SALIDA_VENTA', 'CONSUMO_SERVICIO') THEN -m.cantidad
           WHEN m.tipo = 'AJUSTE' THEN SIGN(d.diferencia) * m.cantidad
           WHEN m.detalle_recepcion_id IS NOT NULL THEN -m.cantidad                 -- reversa de una entrada
           WHEN m.detalle_inventario_id IS NOT NULL THEN -SIGN(d.diferencia) * m.cantidad
           ELSE m.cantidad                                                          -- reversa de venta o consumo
       END AS cantidad_con_signo,
       m.costo_unitario,
       m.registrado_por,
       m.detalle_recepcion_id,
       m.detalle_venta_id,
       m.material_servicio_id,
       m.detalle_inventario_id,
       m.observaciones
  FROM movimiento_inventario m
  LEFT JOIN detalle_inventario_fisico d ON d.detalle_inventario_id = m.detalle_inventario_id;

COMMENT ON VIEW v_kardex IS 'Kárdex con la cantidad con signo (+ entra, − sale) según el tipo y el origen del movimiento.';

CREATE OR REPLACE VIEW v_existencia AS
SELECT sucursal_id, producto_id, SUM(cantidad_con_signo) AS existencia
  FROM v_kardex
 GROUP BY sucursal_id, producto_id;

COMMENT ON VIEW v_existencia IS 'Existencia actual por sucursal y producto, calculada desde el kárdex.';
"""


def sql_fks():
    return [
        f"ALTER TABLE {tabla} ADD CONSTRAINT {nombre} FOREIGN KEY ({cols}) "
        f"REFERENCES {ref} ({ref_cols}) ON UPDATE CASCADE ON DELETE RESTRICT"
        for tabla, nombre, cols, ref, ref_cols in FKS
    ]


class Migration(migrations.Migration):
    dependencies = [
        ("inventario", "0001_initial"),
        ("catalogo", "0003_publico_general"),
        ("compras", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql=sql_fks(),
            reverse_sql=[f"ALTER TABLE {t} DROP CONSTRAINT {n}" for t, n, *_ in FKS],
        ),
        migrations.RunSQL(sql=VISTAS, reverse_sql="DROP VIEW IF EXISTS v_existencia; DROP VIEW IF EXISTS v_kardex;"),
    ]
