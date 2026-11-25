import hashlib
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from guarida_manager.cache import (
    BenchmarkRegistro,
    ConfiguracionOptimaRegistro,
    GestorCache,
    HechoMemoriaRegistro,
    MensajeChatRegistro,
    ModeloRegistro,
    ProyectoRegistro,
    SesionChatRegistro,
)
from guarida_manager.telemetry import GestorTelemetriaJSONL


class TestCache(unittest.TestCase):
    def setUp(self):
        self.directorio_temporal = tempfile.TemporaryDirectory()
        self.ruta_db = Path(self.directorio_temporal.name) / "test_guarida.db"
        self.cache = GestorCache(self.ruta_db)

    def tearDown(self):
        self.directorio_temporal.cleanup()

    def test_inicializacion_tablas(self):
        self.assertTrue(self.ruta_db.exists())
        with self.cache.sesion() as conexion:
            cursor = conexion.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
            )
            tablas = [fila[0] for fila in cursor.fetchall()]
            self.assertIn("modelos", tablas)
            self.assertIn("benchmarks", tablas)
            self.assertIn("modulos_instalados", tablas)

    def test_guardar_y_obtener_modelo(self):
        modelo = ModeloRegistro(
            id="qwen-2.5-0.5b",
            repo_hf="Qwen/Qwen2.5-0.5B-Instruct-GGUF",
            filename="qwen2.5-0.5b-instruct-q4_k_m.gguf",
            ruta_local="/fake/path/qwen2.5-0.5b-instruct-q4_k_m.gguf",
            estado="optimo",
            motivo_descarte=None,
            license="apache-2.0",
            training_summary_url="https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct",
        )
        self.cache.guardar_modelo(modelo)

        recuperado = self.cache.obtener_modelo("qwen-2.5-0.5b")
        self.assertIsNotNone(recuperado)
        self.assertEqual(recuperado["repo_hf"], "Qwen/Qwen2.5-0.5B-Instruct-GGUF")
        self.assertEqual(recuperado["estado"], "optimo")

    def test_actualizar_estado_modelo(self):
        modelo = ModeloRegistro(
            id="test-model",
            repo_hf="user/repo",
            filename="model.gguf",
            ruta_local="/path/model.gguf",
            estado="optimo",
        )
        self.cache.guardar_modelo(modelo)

        self.cache.actualizar_estado_modelo(
            modelo_id="test-model",
            estado="descartado",
            motivo_descarte="Fallo en tool calling estructurado",
        )

        actualizado = self.cache.obtener_modelo("test-model")
        self.assertEqual(actualizado["estado"], "descartado")
        self.assertEqual(
            actualizado["motivo_descarte"], "Fallo en tool calling estructurado"
        )

    def test_benchmark_cache_flujo(self):
        modelo = ModeloRegistro(
            id="qwen-0.5b",
            repo_hf="Qwen/Qwen2.5-0.5B-Instruct-GGUF",
            filename="qwen0.5b.gguf",
            ruta_local="/models/qwen0.5b.gguf",
            estado="optimo",
        )
        self.cache.guardar_modelo(modelo)

        hash_hw = "a1b2c3d4e5f67890abcdef1234567890abcdef1234567890abcdef1234567890"

        inexistente = self.cache.obtener_benchmark("qwen-0.5b", hash_hw)
        self.assertIsNone(inexistente)

        benchmark = BenchmarkRegistro(
            modelo_id="qwen-0.5b",
            hash_hardware=hash_hw,
            binario_usado="gpu",
            n_gpu_layers=99,
            ctx_size=8192,
            tok_s=45.8,
            gtt_pico_mb=1450.0,
            exito_tool_calling=True,
        )
        id_benchmark = self.cache.guardar_benchmark(benchmark)
        self.assertGreater(id_benchmark, 0)

        existente = self.cache.obtener_benchmark("qwen-0.5b", hash_hw)
        self.assertIsNotNone(existente)
        self.assertEqual(existente["binario_usado"], "gpu")
        self.assertEqual(existente["tok_s"], 45.8)
        self.assertTrue(existente["exito_tool_calling"])

    def test_modulos_instalados(self):
        self.assertFalse(self.cache.verificar_modulo_instalado("core"))

        self.cache.registrar_modulo_instalado("core")
        self.assertTrue(self.cache.verificar_modulo_instalado("core"))

        modulos = self.cache.obtener_modulos_instalados()
        self.assertEqual(len(modulos), 1)
        self.assertEqual(modulos[0]["nombre"], "core")

    def test_configuracion_optima_persistencia(self):
        modelo = ModeloRegistro(
            id="qwen-coder-optimo",
            repo_hf="Qwen/test",
            filename="qwen.gguf",
            ruta_local="/fake/path",
            estado="archivado_sin_archivo",
            motivo_descarte="Demasiado lento para chat interactivo, pero afinado para background batch",
        )
        self.cache.guardar_modelo(modelo)

        hash_hw = "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
        config_optima = ConfiguracionOptimaRegistro(
            modelo_id="qwen-coder-optimo",
            hash_hardware=hash_hw,
            n_gpu_layers=33,
            ctx_size=16384,
            batch_size=512,
            kv_cache_tipo="q4_0",
            tok_s_medido=13.2,
            gtt_pico_mb=8450.0,
            fecha_afinamiento="2026-11-04T18:00:00Z",
            motivo_descarte_o_nota="Configuración óptima: 33 capas GPU, 16k contexto, KV q4_0",
            es_recomendada=True,
        )

        self.cache.guardar_configuracion_optima(config_optima)

        recuperada = self.cache.obtener_configuracion_optima("qwen-coder-optimo", hash_hw)
        self.assertIsNotNone(recuperada)
        self.assertEqual(recuperada["n_gpu_layers"], 33)
        self.assertEqual(recuperada["ctx_size"], 16384)
        self.assertEqual(recuperada["kv_cache_tipo"], "q4_0")
        self.assertEqual(recuperada["tok_s_medido"], 13.2)
        self.assertTrue(recuperada["es_recomendada"])

        lista = self.cache.listar_configuraciones_optimas(hash_hw)
        self.assertEqual(len(lista), 1)
        self.assertEqual(lista[0]["modelo_id"], "qwen-coder-optimo")

    def test_segregacion_bases_de_datos_sqlite(self):
        dir_seg = Path(self.directorio_temporal.name) / "segregado"
        cache_seg = GestorCache(dir_seg)

        self.assertEqual(cache_seg.ruta_db_config, dir_seg / "config.db")
        self.assertEqual(cache_seg.ruta_db_sesiones, dir_seg / "sesiones_chat.db")
        self.assertEqual(cache_seg.ruta_db_proyectos, dir_seg / "proyecto_grafo.db")
        self.assertTrue(cache_seg.ruta_db_config.exists())
        self.assertTrue(cache_seg.ruta_db_sesiones.exists())
        self.assertTrue(cache_seg.ruta_db_proyectos.exists())

        def _tablas(ctx):
            with ctx() as conn:
                rows = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table';"
                ).fetchall()
                return {r[0] for r in rows}

        tablas_cfg = _tablas(cache_seg.sesion_config)
        tablas_proy = _tablas(cache_seg.sesion_proyectos)
        tablas_chat = _tablas(cache_seg.sesion_chat)

        self.assertIn("modelos", tablas_cfg)
        self.assertNotIn("proyectos", tablas_cfg)
        self.assertNotIn("sesiones_chat", tablas_cfg)

        self.assertEqual({"proyectos", "documentos_proyecto", "embeddings_cache"}.issubset(tablas_proy), True)
        self.assertNotIn("modelos", tablas_proy)
        self.assertNotIn("sesiones_chat", tablas_proy)

        self.assertEqual({"sesiones_chat", "mensajes_chat", "contenido_mensajes"}.issubset(tablas_chat), True)
        self.assertNotIn("modelos", tablas_chat)
        self.assertNotIn("proyectos", tablas_chat)

    def test_mensajes_normalizados_compactos_y_limpieza_proyecto(self):
        proy = ProyectoRegistro(
            id="proy-1",
            nombre="Proyecto Test",
            descripcion="Desc",
            ruta_directorio="/tmp/proy",
            fecha_creacion="2026-11-16T10:00:00+00:00",
        )
        self.cache.guardar_proyecto(proy)

        sesion = SesionChatRegistro(
            id="ses-1",
            proyecto_id="proy-1",
            modelo_id="qwen2.5",
            titulo="Sesión segregada",
            fecha_creacion="2026-11-16T10:01:00+00:00",
            fecha_actualizacion="2026-11-16T10:01:00+00:00",
        )
        self.cache.guardar_sesion_chat(sesion)

        texto_largo = "Contenido detallado de análisis AST y arquitectura GuarIdA. " * 20
        msg_id = self.cache.guardar_mensaje_chat(
            MensajeChatRegistro(
                id=None,
                sesion_id="ses-1",
                rol="assistant",
                contenido=texto_largo,
                tokens_prompt=50,
                tokens_generados=120,
                fuentes_ast_json='[{"archivo":"cache.py"}]',
                fecha="2026-11-16T10:02:00+00:00",
            )
        )
        self.assertGreater(msg_id, 0)

        with self.cache.sesion_chat() as conn:
            fila_meta = conn.execute(
                "SELECT contenido FROM mensajes_chat WHERE id = ?;", (msg_id,)
            ).fetchone()
            self.assertEqual(fila_meta["contenido"], "")
            fila_blob = conn.execute(
                "SELECT hash_sha256, compresion, datos_contenido FROM contenido_mensajes WHERE mensaje_id = ?;",
                (msg_id,),
            ).fetchone()
            self.assertEqual(
                fila_blob["hash_sha256"],
                hashlib.sha256(texto_largo.encode("utf-8")).hexdigest(),
            )
            self.assertIn(fila_blob["compresion"], ("zstd", "zlib"))

        rehidratados = self.cache.obtener_mensajes_sesion("ses-1")
        self.assertEqual(len(rehidratados), 1)
        self.assertEqual(rehidratados[0]["contenido"], texto_largo)
        self.assertNotIn("datos_contenido", rehidratados[0])
        self.assertEqual(rehidratados[0]["hash_sha256"], fila_blob["hash_sha256"])

        metadatos = self.cache.obtener_metadatos_mensajes_sesion("ses-1")
        self.assertEqual(len(metadatos), 1)
        self.assertNotIn("contenido", metadatos[0])
        self.assertEqual(metadatos[0]["tokens_generados"], 120)

        eliminado = self.cache.eliminar_proyecto("proy-1")
        self.assertTrue(eliminado)
        sesion_tras_borrado = self.cache.obtener_sesion_chat("ses-1")
        self.assertIsNotNone(sesion_tras_borrado)
        self.assertIsNone(sesion_tras_borrado["proyecto_id"])

    def test_telemetria_jsonl_particion_rotacion_y_lectura(self):
        dir_telemetria = Path(self.directorio_temporal.name) / "telemetria"
        gestor = GestorTelemetriaJSONL(dir_telemetria)

        dt_dia1 = datetime(2026, 11, 14, 12, 0, 0, tzinfo=timezone.utc)
        dt_dia2 = datetime(2026, 11, 15, 8, 30, 0, tzinfo=timezone.utc)

        ruta_d1 = gestor.registrar_evento(
            "inferencia_inicio", {"modelo": "qwen-7b", "ctx": 4096}, timestamp_utc=dt_dia1
        )
        self.assertTrue(ruta_d1.exists())
        self.assertEqual(ruta_d1.name, "telemetria_2026-11-14.jsonl")

        ruta_d2 = gestor.registrar_evento(
            "inferencia_fin", {"tok_s": 28.4}, timestamp_utc=dt_dia2
        )
        self.assertTrue(ruta_d2.exists())
        self.assertEqual(ruta_d2.name, "telemetria_2026-11-15.jsonl")
        self.assertFalse(ruta_d1.exists())

        archivo_rotado = dir_telemetria / "telemetria_2026-11-14.jsonl.zst"
        if not archivo_rotado.exists():
            archivo_rotado = dir_telemetria / "telemetria_2026-11-14.jsonl.zlib"
        self.assertTrue(archivo_rotado.exists())

        eventos_d1 = gestor.leer_eventos("2026-11-14")
        self.assertEqual(len(eventos_d1), 1)
        self.assertEqual(eventos_d1[0]["tipo_evento"], "inferencia_inicio")
        self.assertEqual(eventos_d1[0]["datos"]["modelo"], "qwen-7b")

        todos = gestor.leer_eventos()
        self.assertEqual(len(todos), 2)
        self.assertEqual([e["tipo_evento"] for e in todos], ["inferencia_inicio", "inferencia_fin"])

    def test_memoria_declarativa_inmutable_y_superseded(self):
        id_1 = self.cache.registrar_hecho_memoria(
            HechoMemoriaRegistro(
                sujeto="puerto_servidor",
                predicado="es",
                objeto="8080",
                proyecto_id="p1",
                origen_tipo="chat",
            )
        )
        self.assertGreater(id_1, 0)

        # Idempotencia si el objeto no cambia
        id_1_rep = self.cache.registrar_hecho_memoria(
            HechoMemoriaRegistro(
                sujeto="puerto_servidor",
                predicado="es",
                objeto="8080",
                proyecto_id="p1",
            )
        )
        self.assertEqual(id_1_rep, id_1)

        activos_inicial = self.cache.listar_hechos_memoria(proyecto_id="p1", incluir_superseded=False)
        self.assertEqual(len(activos_inicial), 1)
        self.assertEqual(activos_inicial[0]["estado"], "activo")
        self.assertEqual(activos_inicial[0]["objeto"], "8080")

        # Contradicción/actualización: debe crear hecho nuevo y marcar el anterior como superseded
        id_2 = self.cache.registrar_hecho_memoria(
            HechoMemoriaRegistro(
                sujeto="puerto_servidor",
                predicado="es",
                objeto="9000",
                proyecto_id="p1",
                origen_tipo="comando",
            )
        )
        self.assertGreater(id_2, id_1)

        activos_final = self.cache.listar_hechos_memoria(proyecto_id="p1", incluir_superseded=False)
        self.assertEqual(len(activos_final), 1)
        self.assertEqual(activos_final[0]["id"], id_2)
        self.assertEqual(activos_final[0]["estado"], "activo")
        self.assertEqual(activos_final[0]["objeto"], "9000")

        historial = self.cache.obtener_historial_hecho("puerto_servidor", proyecto_id="p1")
        self.assertEqual(len(historial), 2)
        self.assertEqual(historial[0]["id"], id_1)
        self.assertEqual(historial[0]["estado"], "superseded")
        self.assertEqual(historial[0]["sustituido_por_id"], id_2)
        self.assertIsNotNone(historial[0]["fecha_superseded"])
        self.assertEqual(historial[1]["id"], id_2)
        self.assertEqual(historial[1]["estado"], "activo")
        self.assertIsNone(historial[1]["sustituido_por_id"])

    def test_migracion_automatica_desde_guarida_db_legacy(self):
        dir_mig = Path(self.directorio_temporal.name) / "migracion"
        dir_mig.mkdir(parents=True)
        ruta_legacy = dir_mig / "guarida.db"

        conn = sqlite3.connect(str(ruta_legacy))
        try:
            conn.execute(
                """
                CREATE TABLE modelos (
                    id TEXT PRIMARY KEY,
                    repo_hf TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    ruta_local TEXT NOT NULL,
                    estado TEXT NOT NULL,
                    motivo_descarte TEXT,
                    license TEXT,
                    training_summary_url TEXT
                );
                """
            )
            conn.execute(
                """
                INSERT INTO modelos (id, repo_hf, filename, ruta_local, estado)
                VALUES ('qwen2.5-3b-chat-q4', 'Qwen/Qwen2.5-3B-Instruct-GGUF', 'qwen2.5-3b-instruct-q4_k_m.gguf', '/models/qwen2.5-3b-instruct-q4_k_m.gguf', 'descargado');
                """
            )
            conn.execute(
                """
                CREATE TABLE proyectos (
                    id TEXT PRIMARY KEY,
                    nombre TEXT NOT NULL,
                    descripcion TEXT NOT NULL,
                    ruta_directorio TEXT NOT NULL,
                    fecha_creacion TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                INSERT INTO proyectos (id, nombre, descripcion, ruta_directorio, fecha_creacion)
                VALUES ('proy-legacy', 'TIES', 'Manual', '/docs/ties', '2026-11-10T10:00:00+00:00');
                """
            )
            conn.commit()
        finally:
            conn.close()

        cache_migrado = GestorCache(dir_mig / "config.db")
        modelo = cache_migrado.obtener_modelo("qwen2.5-3b-chat-q4")
        self.assertIsNotNone(modelo)
        self.assertEqual(modelo["estado"], "descargado")
        self.assertEqual(modelo["ruta_local"], "/models/qwen2.5-3b-instruct-q4_k_m.gguf")

        proyecto = cache_migrado.obtener_proyecto("proy-legacy")
        self.assertIsNotNone(proyecto)
        self.assertEqual(proyecto["nombre"], "TIES")


if __name__ == "__main__":
    unittest.main()
