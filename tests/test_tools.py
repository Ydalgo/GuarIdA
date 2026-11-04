import unittest

from guarida_manager.downloader.tools import (
    DefinicionHerramienta,
    EstadoHerramienta,
    GestorHerramientasBunker,
)


class TestTools(unittest.TestCase):
    def test_catalogo_herramientas_definidas(self):
        herramientas = GestorHerramientasBunker.HERRAMIENTAS
        self.assertIn("llama-server", herramientas)
        self.assertIn("git", herramientas)
        self.assertIn("ripgrep", herramientas)

        git_def = herramientas["git"]
        self.assertIsInstance(git_def, DefinicionHerramienta)
        self.assertTrue(git_def.es_critica)

    def test_verificar_todas_herramientas(self):
        estados = GestorHerramientasBunker.verificar_todas_herramientas()
        self.assertGreaterEqual(len(estados), 3)

        ids = [e.id for e in estados]
        self.assertIn("git", ids)
        self.assertIn("llama-server", ids)
        self.assertIn("ripgrep", ids)

        for e in estados:
            self.assertIsInstance(e, EstadoHerramienta)
            self.assertIsInstance(e.instalada, bool)


if __name__ == "__main__":
    unittest.main()
