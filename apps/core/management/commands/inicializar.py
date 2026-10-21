"""
Primer arranque con base vacía: crea la primera sucursal, su caja y el usuario Administrador.

    python manage.py inicializar
    python manage.py inicializar --sucursal "Almacén Matriz" --usuario admin --nombre "Administrador del sistema"
"""
import getpass

from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.usuarios.models import Rol, Sucursal, Usuario
from apps.ventas.models import Caja


class Command(BaseCommand):
    help = "Crea la primera sucursal, una caja y el usuario Administrador."

    def add_arguments(self, parser):
        parser.add_argument("--sucursal", default="Almacén Matriz")
        parser.add_argument("--direccion", default="Aguascalientes, Ags.")
        parser.add_argument("--usuario", default="admin")
        parser.add_argument("--nombre", default="Administrador del sistema")
        parser.add_argument("--password", help="Si no se indica, se pide en la terminal.")

    def handle(self, *args, **o):
        if Usuario.objects.exists():
            raise CommandError("Ya existen usuarios. Administra usuarios y sucursales desde el sistema (Administración).")
        password = o["password"]
        while not password:
            p1 = getpass.getpass("Contraseña para el administrador: ")
            p2 = getpass.getpass("Repite la contraseña: ")
            if p1 != p2:
                self.stderr.write("No coinciden, intenta de nuevo.")
                continue
            password = p1
        try:
            password_validation.validate_password(password)
        except ValidationError as e:
            raise CommandError(" ".join(e.messages))
        with transaction.atomic():
            sucursal, _ = Sucursal.objects.get_or_create(nombre=o["sucursal"], defaults={"direccion": o["direccion"]})
            Caja.objects.get_or_create(sucursal=sucursal, codigo="CAJA-01", defaults={"nombre": "Caja principal"})
            Usuario.objects.create_user(
                o["usuario"], password, nombre_completo=o["nombre"], sucursal=sucursal, rol=Rol.objects.get(nombre="Administrador")
            )
        self.stdout.write(self.style.SUCCESS(f"Listo. Entra con el usuario «{o['usuario']}» en http://127.0.0.1:8000/acceso/"))
