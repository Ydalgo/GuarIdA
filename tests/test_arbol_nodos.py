import unittest
from unittest.mock import MagicMock

from guarida_manager.arbol_nodos import (
    ArbolNodosCodigo,
    NodoAST,
    TipoNodoAST,
    minificar_codigo_bpe,
    similitud_coseno,
)
from guarida_manager.roles import RolAgente

CODIGO_TEST_COMPLETO = """
'''Módulo de criptografía para el Búnker GuarIdA.'''

class CriptoBunker:
    '''Clase responsable de la gestión de claves y firmas.'''

    def __init__(self, algoritmo: str = "SHAKE-256"):
        self.algoritmo = algoritmo
        self.activo = True

    def generar_salt(self, longitud: int = 32) -> bytes:
        '''Genera un salt criptográfico seguro.'''
        import os
        return os.urandom(longitud)

    def firmar_bloque(self, datos: bytes, clave: bytes) -> str:
        '''Genera firma HMAC para verificar integridad.'''
        import hmac, hashlib
        return hmac.new(clave, datos, hashlib.sha256).hexdigest()

def validar_integridad_sha256(archivo_path: str, hash_esperado: str) -> bool:
    '''Calcula el hash del archivo y valida coincidencia.'''
    import hmac
    return hmac.compare_digest("abc", hash_esperado)
"""


class TestArbolNodosCodigo(unittest.TestCase):
    def test_construccion_ast_jerarquico(self):
        arbol = ArbolNodosCodigo()
        arbol.construir_desde_codigo_python(CODIGO_TEST_COMPLETO, ruta_archivo="cripto.py")

        # Verificar nodo raíz (módulo)
        raiz = arbol.obtener_nodo("cripto.py::raiz")
        self.assertIsNotNone(raiz)
        self.assertEqual(raiz.tipo, TipoNodoAST.MODULO)
        self.assertIn("Búnker GuarIdA", raiz.docstring)

        # Verificar nodo clase
        id_clase = "cripto.py::raiz::clase::CriptoBunker"
        clase_nodo = arbol.obtener_nodo(id_clase)
        self.assertIsNotNone(clase_nodo)
        self.assertEqual(clase_nodo.tipo, TipoNodoAST.CLASE)
        self.assertEqual(clase_nodo.nombre, "CriptoBunker")
        self.assertEqual(clase_nodo.padre_id, raiz.id_nodo)

        # Verificar métodos de la clase
        id_metodo = f"{id_clase}::metodo::generar_salt"
        metodo_nodo = arbol.obtener_nodo(id_metodo)
        self.assertIsNotNone(metodo_nodo)
        self.assertEqual(metodo_nodo.tipo, TipoNodoAST.METODO)
        self.assertEqual(metodo_nodo.padre_id, id_clase)

        # Verificar función independiente a nivel de módulo
        id_func = "cripto.py::raiz::funcion::validar_integridad_sha256"
        func_nodo = arbol.obtener_nodo(id_func)
        self.assertIsNotNone(func_nodo)
        self.assertEqual(func_nodo.tipo, TipoNodoAST.FUNCION)
        self.assertEqual(func_nodo.padre_id, raiz.id_nodo)

    def test_similitud_coseno(self):
        # Vectores idénticos
        v1 = [1.0, 0.0, 0.0]
        v2 = [1.0, 0.0, 0.0]
        self.assertAlmostEqual(similitud_coseno(v1, v2), 1.0)

        # Vectores ortogonales
        v3 = [0.0, 1.0, 0.0]
        self.assertAlmostEqual(similitud_coseno(v1, v3), 0.0)

        # Vectores opuestos
        v4 = [-1.0, 0.0, 0.0]
        self.assertAlmostEqual(similitud_coseno(v1, v4), -1.0)

        # Vector nulo / vacío
        self.assertEqual(similitud_coseno([], [1.0]), 0.0)
        self.assertEqual(similitud_coseno([0.0, 0.0], [1.0, 2.0]), 0.0)

    def test_indexacion_y_busqueda_semantica(self):
        arbol = ArbolNodosCodigo()
        arbol.construir_desde_codigo_python(CODIGO_TEST_COMPLETO, ruta_archivo="cripto.py")

        def mock_embed(texto: str) -> list[float]:
            texto_lower = texto.lower()
            if "salt" in texto_lower:
                return [1.0, 0.1, 0.0]
            elif "firmar" in texto_lower or "hmac" in texto_lower:
                return [0.0, 1.0, 0.2]
            elif "sha256" in texto_lower or "integridad" in texto_lower:
                return [0.1, 0.1, 0.9]
            return [0.2, 0.2, 0.2]

        total_indexados = arbol.indexar_embeddings(mock_embed)
        self.assertGreaterEqual(total_indexados, 4)

        # Buscar "generar salt seguro"
        query_vec = [0.95, 0.1, 0.0]
        resultados = arbol.buscar_nodos_relevantes(query_vec, top_k=2)
        self.assertGreater(len(resultados), 0)
        nodo_top, score = resultados[0]
        self.assertEqual(nodo_top.nombre, "generar_salt")
        self.assertGreater(score, 0.9)

    def test_construccion_contexto_y_mensaje_inter_modelo(self):
        arbol = ArbolNodosCodigo()
        arbol.construir_desde_codigo_python(CODIGO_TEST_COMPLETO, ruta_archivo="cripto.py")

        nodo_metodo = arbol.obtener_nodo("cripto.py::raiz::clase::CriptoBunker::metodo::firmar_bloque")
        self.assertIsNotNone(nodo_metodo)

        contexto = arbol.construir_contexto_optimo([(nodo_metodo, 0.95)], incluir_padre=True)
        self.assertIn("CriptoBunker", contexto)
        self.assertIn("firmar_bloque", contexto)

        msg = arbol.generar_mensaje_inter_modelo("¿Cómo se firma un bloque?", [(nodo_metodo, 0.95)])
        self.assertEqual(msg.emisor_rol, RolAgente.EMBEDDING_INDEXER.value)
        self.assertEqual(msg.receptor_rol, RolAgente.CODER.value)
        self.assertEqual(msg.tipo_accion, "CONSULTA_NODOS")
        self.assertIn("contexto_sintactico", msg.payload)
        self.assertEqual(msg.payload["total_nodos_encontrados"], 1)

    def test_compresion_bpe_y_esqueleto_ast(self):
        arbol = ArbolNodosCodigo()
        arbol.construir_desde_codigo_python(CODIGO_TEST_COMPLETO, ruta_archivo="cripto.py")
        nodo_metodo = arbol.obtener_nodo("cripto.py::raiz::clase::CriptoBunker::metodo::firmar_bloque")
        self.assertIsNotNone(nodo_metodo)

        ctx_comprimido = arbol.construir_contexto_optimo([(nodo_metodo, 0.95)], incluir_padre=True, comprimir_bpe=True)
        ctx_sin_comprimir = arbol.construir_contexto_optimo([(nodo_metodo, 0.95)], incluir_padre=True, comprimir_bpe=False)

        self.assertLess(len(ctx_comprimido), len(ctx_sin_comprimir))
        self.assertLess(len(ctx_comprimido), len(CODIGO_TEST_COMPLETO))
        self.assertIn("def generar_salt", ctx_comprimido)  # Esqueleto de método hermano
        self.assertIn("hmac.new", ctx_comprimido)          # Cuerpo del método objetivo


if __name__ == "__main__":
    unittest.main()
