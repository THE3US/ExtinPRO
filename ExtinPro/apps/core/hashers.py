from django.contrib.auth.hashers import PBKDF2PasswordHasher


class PBKDF2RapidoParaPruebas(PBKDF2PasswordHasher):
    """Solo para la suite de pruebas: mismo formato que en producción, una iteración."""

    iterations = 1
