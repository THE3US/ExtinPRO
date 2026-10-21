-- =====================================================================
-- ExtinPro · SPVCI — Crea el usuario, la base de datos y el esquema.
-- Ejecutar UNA vez como administrador de PostgreSQL (usuario postgres):
--
--   psql -U postgres -f scripts/crear_bd.sql
--
-- psql te pedirá la contraseña nueva del usuario "extinpro" (\password);
-- usa esa misma contraseña en DATABASE_URL del archivo .env.
-- Las tablas, restricciones y vistas del Entregable 6 las crea Django con:
--   python manage.py migrate
-- =====================================================================

CREATE ROLE extinpro LOGIN CREATEDB;   -- CREATEDB: permite crear la base temporal de las pruebas
\password extinpro

CREATE DATABASE extinpro OWNER extinpro ENCODING 'UTF8' TEMPLATE template0;

\connect extinpro
CREATE SCHEMA IF NOT EXISTS extinpro AUTHORIZATION extinpro;
ALTER ROLE extinpro IN DATABASE extinpro SET search_path = extinpro, public;
