"""
Configuración de Django para ExtinPro · SPVCI.

Los valores sensibles o que cambian por entorno se leen de variables de entorno
(archivo .env en desarrollo). Ver .env.example.
"""
import sys
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CSRF_TRUSTED_ORIGINS=(list, []),
    SECURE_SSL_REDIRECT=(bool, False),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Módulos del sistema (agrupados como las figuras del Entregable 6)
    "apps.core",
    "apps.usuarios",
    "apps.catalogo",
    "apps.compras",
    "apps.inventario",
    "apps.ventas",
    "apps.servicio",
    "apps.sitio",
    "apps.reportes",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Almacén (sucursal) activo de la sesión, validado contra el usuario.
    "apps.usuarios.middleware.SucursalActivaMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.usuarios.context_processors.sesion",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Base de datos: PostgreSQL. Todas las tablas viven en el esquema "extinpro"
# (igual que el script del Entregable 6). Ejemplo de DATABASE_URL:
#   postgres://extinpro:contraseña@localhost:5432/extinpro
DB_SCHEMA = env("DB_SCHEMA", default="extinpro")
DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
DATABASES["default"].setdefault("OPTIONS", {})["options"] = f"-c search_path={DB_SCHEMA},public"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "usuarios.Usuario"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

LOGIN_URL = "usuarios:acceso"
LOGIN_REDIRECT_URL = "core:inicio"
LOGOUT_REDIRECT_URL = "usuarios:acceso"

# Internacionalización
LANGUAGE_CODE = "es-mx"
TIME_ZONE = "America/Mexico_City"
USE_I18N = True
USE_TZ = True

# Archivos estáticos (WhiteNoise los sirve en producción)
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}

# Sesiones y cookies
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_AGE = 60 * 60 * 12  # un turno
CSRF_COOKIE_HTTPONLY = False

if not DEBUG:
    SECURE_SSL_REDIRECT = env("SECURE_SSL_REDIRECT")
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=0)
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    X_FRAME_OPTIONS = "DENY"

# Registro: nunca registrar contraseñas, tokens ni datos de tarjeta.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simple": {"format": "{levelname} {asctime} {name}: {message}", "style": "{"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "simple"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {"django.db.backends": {"level": "WARNING"}},
}

# Reglas de negocio configurables (ver README)
SPVCI = {
    "IVA": "0.16",
    "INTENTOS_ACCESO": 3,  # al tercer intento fallido la cuenta se bloquea (CP-01-03)
    "DESCUENTO_MAXIMO": "50",  # % por partida (CP-03-08)
    "DIAS_ENTREGA_PROVEEDOR": 5,  # días hábiles para la fecha prevista de una OC (CP-05-02)
    "INICIO_HISTORICO": "2026-05-01",  # fecha mínima de corte del valor de inventario (CP-07-03)
    "EMPRESA": "ExtinPro",
    "CIUDAD": "Aguascalientes, Ags.",
}

# Suite de pruebas: hash rápido (sigue cumpliendo ck_usuario_contrasena_hash ≥ 60) y sin ruido.
TESTING = len(sys.argv) > 1 and sys.argv[1] == "test"
if TESTING:
    PASSWORD_HASHERS = ["apps.core.hashers.PBKDF2RapidoParaPruebas"]
    LOGGING["loggers"]["django.request"] = {"level": "ERROR"}
    STORAGES["staticfiles"] = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}
    WHITENOISE_AUTOREFRESH = True
