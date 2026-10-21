"""CP-01 · Iniciar sesión y permisos por rol (SPVCI-01 / PD-00, SPVCI-02 / PD-01)."""
from apps.usuarios.models import Usuario

from .base import ConDatosDemo


class CP01Acceso(ConDatosDemo):
    def textos_menu(self, r):
        return [i["texto"] for g in r.context["nav"] for i in g["items"]]

    def test_cp_01_01_credenciales_validas(self):
        r = self.client.post("/acceso/", {"usuario": "gerente01", "contrasena": "demo2026", "sucursal": self.matriz.pk}, follow=True)
        self.assertEqual(r.redirect_chain[-1][0], "/panel/")
        self.assertIn("Bienvenido(a), Mariana López", " ".join(self.mensajes(r)))
        menu = self.textos_menu(r)
        for modulo in ["Inicio", "Ventas", "Recibo de mercancía", "Abastecimiento", "Inventario", "Valor de inventario"]:
            self.assertIn(modulo, menu)
        self.assertNotIn("Usuarios", menu)

    def test_cp_01_02_contrasena_incorrecta(self):
        r = self.client.post("/acceso/", {"usuario": "gerente01", "contrasena": "clave123", "sucursal": self.matriz.pk})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Usuario o contraseña incorrectos.")
        self.assertContains(r, "Intento 1 de 3; al tercero la cuenta se bloquea.")
        self.assertEqual(Usuario.objects.get(nombre_usuario="gerente01").intentos_fallidos, 1)

    def test_cp_01_03_bloqueo_tres_intentos(self):
        for clave in ("clave123", "clave124", "clave125"):
            r = self.client.post("/acceso/", {"usuario": "gerente01", "contrasena": clave, "sucursal": self.matriz.pk})
        self.assertContains(r, "Cuenta bloqueada")
        u = Usuario.objects.get(nombre_usuario="gerente01")
        self.assertTrue(u.bloqueado)
        # Ya bloqueada, ni la contraseña correcta deja entrar.
        r = self.client.post("/acceso/", {"usuario": "gerente01", "contrasena": "demo2026", "sucursal": self.matriz.pk})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Cuenta bloqueada")
        # El administrador la reactiva.
        self.entrar("admin")
        self.client.post(f"/administracion/usuarios/{u.pk}/reactivar/")
        self.client.post("/salir/")
        self.entrar("gerente01")

    def test_cp_01_04_campos_vacios(self):
        r = self.client.post("/acceso/", {"usuario": "", "contrasena": ""})
        self.assertContains(r, "Escribe tu usuario y tu contraseña.")
        self.assertEqual(Usuario.objects.get(nombre_usuario="gerente01").intentos_fallidos, 0)

    def test_cp_01_05_permisos_cajero(self):
        r = self.client.post("/acceso/", {"usuario": "cajero01", "contrasena": "demo2026", "sucursal": self.matriz.pk}, follow=True)
        self.assertEqual(self.textos_menu(r), ["Inicio", "Ventas", "Inventario"])
        r = self.client.get("/reportes/valor/")
        self.assertEqual(r.status_code, 403)
        self.assertContains(r, "Acceso restringido", status_code=403)

    def test_cajero_no_elige_otra_sucursal(self):
        r = self.client.post("/acceso/", {"usuario": "cajero01", "contrasena": "demo2026", "sucursal": self.norte.pk})
        self.assertContains(r, "Tu usuario está asignado a Almacén Matriz")

    def test_paginas_internas_piden_sesion(self):
        for url in ["/panel/", "/ventas/", "/inventario/", "/reportes/valor/", "/administracion/usuarios/"]:
            r = self.client.get(url)
            self.assertEqual(r.status_code, 302, url)
            self.assertTrue(r["Location"].startswith("/acceso/"), url)

    def test_matriz_de_permisos(self):
        esperado = {
            "admin": {"/administracion/usuarios/": 200, "/reportes/valor/": 200, "/ventas/registradas/": 200},
            "gerente01": {"/administracion/usuarios/": 403, "/reportes/ventas/": 200, "/abastecimiento/pedidos/": 200},
            "almacen01": {"/recepcion/": 200, "/inventario/fisico/": 200, "/ventas/": 403, "/reportes/valor/": 403},
            "cajero01": {"/ventas/registradas/": 200, "/recepcion/": 403, "/abastecimiento/": 403, "/inventario/fisico/": 403},
        }
        for usuario, urls in esperado.items():
            self.client.logout()
            self.entrar(usuario)
            for url, codigo in urls.items():
                self.assertEqual(self.client.get(url).status_code, codigo, f"{usuario} {url}")

    def test_contrasena_guardada_con_hash(self):
        u = Usuario.objects.get(nombre_usuario="cajero01")
        self.assertNotIn("demo2026", u.password)
        self.assertTrue(u.check_password("demo2026"))
