"""Tests unitarios para el motor de búsqueda híbrida HNSW/Matricial + BM25 con RRF y extractores ofimáticos/comprimidos."""

import math
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

from guarida_manager.indice_hibrido import (
    IndiceBM25,
    IndiceVectorial,
    MotorBusquedaHibrida,
    ejecutar_benchmark_indices,
    tokenizar_texto,
)
from guarida_manager.proyectos import (
    extraer_archivos_comprimidos,
    extraer_contenido_archivo,
    extraer_texto_ods,
    extraer_texto_ole,
    extraer_texto_xlsx,
)


class TestIndiceHibrido(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_tokenizar_texto(self):
        tokens = tokenizar_texto("Procedimiento de Expedición de la TIE (2026)")
        self.assertIn("procedimiento", tokens)
        self.assertIn("expedición", tokens)
        self.assertIn("tie", tokens)
        self.assertIn("2026", tokens)

    def test_indice_bm25_consultas(self):
        corpus = [
            "Manual oficial para la expedicion de tarjeta de identidad de extranjero TIE",
            "Instrucciones de cita previa para huella dactilar y tasas 790",
            "Gestion de filiaciones y cambio de domicilio en comisaria",
        ]
        bm25 = IndiceBM25(corpus)
        res = bm25.consultar("expedicion tarjeta TIE", top_k=2)
        self.assertTrue(len(res) > 0)
        self.assertEqual(res[0][0], 0)  # El primer documento es el más relevante

        res_huella = bm25.consultar("huella dactilar", top_k=2)
        self.assertTrue(len(res_huella) > 0)
        self.assertEqual(res_huella[0][0], 1)

    def test_indice_vectorial_y_mmap(self):
        ids = ["c0", "c1", "c2"]
        vectores = [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
        ]
        idx_vec = IndiceVectorial(dimensiones=4)
        idx_vec.construir(ids, vectores)

        # Consulta alineada con c0
        res = idx_vec.consultar([1.0, 0.0, 0.0, 0.0], top_k=2)
        self.assertTrue(len(res) > 0)
        self.assertEqual(res[0][0], 0)
        self.assertAlmostEqual(res[0][1], 1.0, places=4)

        # Guardar y cargar mmap
        ruta_mmap = Path(self.temp_dir) / "vectores_test"
        idx_vec.guardar_mmap(ruta_mmap)
        idx_mmap = IndiceVectorial()
        ok = idx_mmap.cargar_mmap(ruta_mmap, ids)
        self.assertTrue(ok)
        res_mmap = idx_mmap.consultar([0.0, 1.0, 0.0, 0.0], top_k=1)
        self.assertEqual(res_mmap[0][0], 1)

    def test_motor_busqueda_hibrida_rrf(self):
        elementos = [
            {"id": "doc1", "texto": "Formulario 790 y pago de tasas oficiales de extranjeria", "vec": [1.0, 0.2, 0.0]},
            {"id": "doc2", "texto": "Toma de huellas dactilares y expedicion de la TIE", "vec": [0.1, 0.9, 0.1]},
            {"id": "doc3", "texto": "Caducidad de tarjeta y renovacion de autorizacion", "vec": [0.0, 0.1, 0.9]},
        ]
        motor = MotorBusquedaHibrida(k_rrf=60)
        motor.indexar_elementos(
            elementos=elementos,
            obtener_texto=lambda e: e["texto"],
            obtener_vector=lambda e: e["vec"],
            obtener_id=lambda e: e["id"],
        )

        res = motor.buscar_hibrido(
            consulta="tasas 790 extranjeria",
            vector_consulta=[1.0, 0.1, 0.0],
            top_k=2,
        )
        self.assertTrue(len(res) > 0)
        self.assertEqual(res[0][0]["id"], "doc1")

    def test_ejecutar_benchmark_indices(self):
        textos = [f"Documento de prueba sobre manuales y normativas {i}" for i in range(50)]
        vectores = [[float(i % 5), float((i + 1) % 5), 0.5, 0.8] for i in range(50)]
        consultas = ["manuales", "normativas 3"]
        bench = ejecutar_benchmark_indices(textos, vectores, consultas, n_repeticiones=2)
        self.assertIn("latencia_secuencial_ms", bench)
        self.assertIn("latencia_hibrida_ms", bench)
        self.assertIn("aceleracion_factor", bench)
        self.assertGreater(bench["consultas_por_segundo"], 0)

    def test_extraccion_xlsx_y_ods(self):
        # 1. Test XLSX
        ruta_xlsx = Path(self.temp_dir) / "datos.xlsx"
        ss_xml = (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            b'<si><t>Tasa 790-012</t></si>'
            b'<si><t>Importe: 21.87 euros</t></si>'
            b'</sst>'
        )
        sheet_xml = (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            b'<sheetData>'
            b'<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>'
            b'</sheetData></worksheet>'
        )
        with zipfile.ZipFile(ruta_xlsx, "w") as z:
            z.writestr("xl/sharedStrings.xml", ss_xml)
            z.writestr("xl/worksheets/sheet1.xml", sheet_xml)

        txt_xlsx = extraer_texto_xlsx(ruta_xlsx)
        self.assertIn("Tasa 790-012", txt_xlsx)
        self.assertIn("21.87 euros", txt_xlsx)

        # 2. Test ODS
        ruta_ods = Path(self.temp_dir) / "calculo.ods"
        ods_xml = (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
            b'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
            b'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
            b'<office:body><office:spreadsheet>'
            b'<table:table table:name="Resumen">'
            b'<table:table-row>'
            b'<table:table-cell><text:p>Total Dias: 90</text:p></table:table-cell>'
            b'</table:table-row>'
            b'</table:table></office:spreadsheet></office:body></office:document-content>'
        )
        with zipfile.ZipFile(ruta_ods, "w") as z:
            z.writestr("content.xml", ods_xml)

        txt_ods = extraer_texto_ods(ruta_ods)
        self.assertIn("Resumen", txt_ods)
        self.assertIn("Total Dias: 90", txt_ods)

    def test_extraccion_ole_doc(self):
        ruta_doc = Path(self.temp_dir) / "oficial.doc"
        # Simular OLE con cadenas UTF-16LE legibles
        cuerpo_u16 = "Ministerio del Interior - Comisaria General de Extranjeria".encode("utf-16le")
        datos_bin = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64 + cuerpo_u16 + b"\x00" * 32
        ruta_doc.write_bytes(datos_bin)

        txt_doc = extraer_texto_ole(ruta_doc)
        self.assertIn("Ministerio del Interior", txt_doc)

    def test_extraccion_archivos_comprimidos_zip(self):
        ruta_zip = Path(self.temp_dir) / "paquete.zip"
        with zipfile.ZipFile(ruta_zip, "w") as z:
            z.writestr("instrucciones.txt", "Paso 1: Solicitar cita en sede electronica.")
            z.writestr("script.ps1", "Write-Output 'Validando certificado digital'")

        archivos = extraer_archivos_comprimidos(ruta_zip)
        self.assertEqual(len(archivos), 2)
        nombres = [a[0] for a in archivos]
        self.assertIn("instrucciones.txt", nombres)
        self.assertIn("script.ps1", nombres)
        txt_map = dict(archivos)
        self.assertIn("Solicitar cita", txt_map["instrucciones.txt"])


if __name__ == "__main__":
    unittest.main()
