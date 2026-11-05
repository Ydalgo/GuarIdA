import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from guarida_manager.cache import GestorCache
from guarida_manager.engine.server import LlamaServerConfig
from guarida_manager.tuning.bateria import (
    calcular_estadisticas_serie,
    calcular_intervalo_confianza_bootstrap,
)
from guarida_manager.tuning.capacidades import (
    CapacidadesBinario,
    DescubridorCapacidades,
    InfoFlag,
)
from guarida_manager.tuning.ejecutor import EjecutorIntentoLlama
from guarida_manager.tuning.perfiles import (
    GestorPerfilesTuning,
    PerfilBarrido,
    PerfilBateria,
    calcular_hash_canonico_dict,
)
from guarida_manager.tuning.scoring import EvaluadorScoring

MOCK_HELP_ANTIGUO = """
usage: llama-server [options]

options:
  -h, --help            show this help message and exit
  -m, --model FNAME     model path
  -c, --ctx-size N      size of the prompt context (default: 4096)
  -b, --batch-size N    batch size for prompt processing (default: 512)
  -ub, --ubatch-size N  physical batch size for prompt processing (default: 512)
  -ngl, --n-gpu-layers N  number of layers to store in VRAM
  -t, --threads N       number of threads to use during generation (default: 4)
  -fa, --flash-attn     enable Flash Attention
  --cache-type-k TYPE   KV cache data type for K (default: f16)
  --cache-type-v TYPE   KV cache data type for V (default: f16)
  --mlock               force system to keep model in RAM
  --no-mmap             do not memory-map model
"""

MOCK_HELP_NUEVO = """
usage: llama-server [options]

options:
  -fa, --flash-attn {on,off,auto}  set Flash Attention mode
  -ub, --ubatch-size N             physical batch size (default: 512)
  -tb, --threads-batch N           threads for batch processing
  --list-devices                   list available compute devices
"""


class TestTuningCapacidades(unittest.TestCase):
    def test_parsear_ayuda_antiguo(self):
        flags = DescubridorCapacidades.parsear_ayuda(MOCK_HELP_ANTIGUO)
        self.assertIn("-fa", flags)
        self.assertIn("--flash-attn", flags)
        self.assertIn("-ngl", flags)
        self.assertIn("-ub", flags)
        self.assertIn("--cache-type-k", flags)

    def test_parsear_ayuda_nuevo_flash_attn_enum(self):
        flags = DescubridorCapacidades.parsear_ayuda(MOCK_HELP_NUEVO)
        self.assertIn("--flash-attn", flags)
        self.assertIn("-tb", flags)

    def test_reglas_compatibilidad(self):
        caps = CapacidadesBinario(
            sha256_binario="dummy_sha",
            version_build="b12017",
            ruta_binario="/fake/bin",
            soporta_flash_attn=True,
            soporta_ubatch=True,
        )

        # 1. ubatch > batch debe ser inválido
        valido, err = DescubridorCapacidades.validar_compatibilidad_config(
            {"batch_size": 256, "ubatch_size": 512}, caps
        )
        self.assertFalse(valido)
        self.assertIn("ubatch", err)

        # 2. KV q4_0 sin flash-attn debe ser inválido
        valido, err = DescubridorCapacidades.validar_compatibilidad_config(
            {"batch_size": 512, "ubatch_size": 512, "kv_cache_tipo_v": "q4_0", "flash_attn": False}, caps
        )
        self.assertFalse(valido)
        self.assertIn("requiere flash attention", err)

        # 3. Configuración válida
        valido, err = DescubridorCapacidades.validar_compatibilidad_config(
            {"batch_size": 512, "ubatch_size": 256, "kv_cache_tipo_v": "q4_0", "flash_attn": True}, caps
        )
        self.assertTrue(valido)


class TestTuningEstadisticaYScoring(unittest.TestCase):
    def test_bootstrap_e_intervalos(self):
        valores = [20.0, 21.0, 19.5, 20.5, 20.2]
        inf, sup = calcular_intervalo_confianza_bootstrap(valores, n_bootstrap=500)
        self.assertGreaterEqual(sup, inf)
        self.assertGreater(inf, 18.0)
        self.assertLess(sup, 23.0)

    def test_estadisticas_serie(self):
        valores = [10.0, 10.0, 10.0, 10.0]
        stats = calcular_estadisticas_serie(valores)
        self.assertEqual(stats["mediana"], 10.0)
        self.assertEqual(stats["cv_pct"], 0.0)

    def test_scoring_objetivos(self):
        ejecs = [
            {"es_calentamiento": False, "exito": 1, "tg_tok_s": 25.0, "pp_tok_s": 150.0, "ttft_ms": 200.0, "calidad_pct": 100.0},
            {"es_calentamiento": False, "exito": 1, "tg_tok_s": 24.5, "pp_tok_s": 145.0, "ttft_ms": 210.0, "calidad_pct": 100.0},
        ]
        score_chat = EvaluadorScoring.calcular_score(ejecs, memoria_mb=2048, ctx_size=4096, objetivo="chat")
        score_batch = EvaluadorScoring.calcular_score(ejecs, memoria_mb=2048, ctx_size=4096, objetivo="batch")
        self.assertGreater(score_chat, 0.0)
        self.assertGreater(score_batch, 0.0)

    def test_frente_pareto(self):
        c1 = {"estado": "ok", "metricas": {"tg_mediana": 30.0}, "mem_total_mb": 4000}
        c2 = {"estado": "ok", "metricas": {"tg_mediana": 20.0}, "mem_total_mb": 5000}  # dominada por c1
        c3 = {"estado": "ok", "metricas": {"tg_mediana": 15.0}, "mem_total_mb": 2000}  # pareto óptima en memoria
        pareto = EvaluadorScoring.calcular_frente_pareto([c1, c2, c3])
        self.assertIn(c1, pareto)
        self.assertIn(c3, pareto)
        self.assertNotIn(c2, pareto)


class TestTuningPersistenciaYPerfiles(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_tuning.db"
        self.cache = GestorCache(ruta_base_datos=self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_migracion_idempotente_tablas_tuning(self):
        with self.cache.sesion() as conn:
            # Comprobar que las nuevas tablas existen
            tables = [
                r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table';"
                ).fetchall()
            ]
            self.assertIn("capacidades_binario", tables)
            self.assertIn("bench_sesiones", tables)
            self.assertIn("bench_configs", tables)
            self.assertIn("bench_ejecuciones", tables)

            # Comprobar columnas añadidas a configuraciones_optimas
            cols = [r[1] for r in conn.execute("PRAGMA table_info(configuraciones_optimas);").fetchall()]
            self.assertIn("threads", cols)
            self.assertIn("ubatch_size", cols)
            self.assertIn("flash_attn", cols)

    def test_perfiles_hash_canonico(self):
        p1 = GestorPerfilesTuning.obtener_perfil_barrido("estandar")
        h1 = p1.hash_sha256
        self.assertTrue(len(h1) == 64)

        # Mismo contenido debe dar el mismo hash
        p2 = GestorPerfilesTuning.obtener_perfil_barrido("estandar")
        self.assertEqual(h1, p2.hash_sha256)

        # Modificación debe variar el hash
        p2.presupuesto_minutos = 999.0
        self.assertNotEqual(h1, p2.hash_sha256)


class TestTuningSeguridadArgs(unittest.TestCase):
    def test_llama_server_config_seguridad(self):
        cfg = LlamaServerConfig(
            modelo_path=Path("dummy.gguf"),
            extra_args=["--flash-attn", "-ub=256", "-tb=4"],
        )
        cmd = cfg.construir_comando()
        self.assertTrue("-fa" in cmd or "--flash-attn" in cmd)

        # Flag peligroso / no autorizado debe disparar ValueError
        cfg_insegura = LlamaServerConfig(
            modelo_path=Path("dummy.gguf"),
            extra_args=["--unauthorized-flag"],
        )
        with self.assertRaises(ValueError):
            cfg_insegura.construir_comando()


class TestLogger(unittest.TestCase):
    def test_logger_escritura_y_lectura(self):
        from guarida_manager.logger import inicializar_logging, obtener_ultimas_lineas_log
        with tempfile.TemporaryDirectory() as td:
            ruta_log = Path(td) / "test.log"
            log = inicializar_logging(
                ruta_log=ruta_log,
                capturar_excepciones_globales=False,
                forzar_reconfiguracion=True,
            )
            log.info("Mensaje de prueba para logger de GuarIdA")
            for h in log.handlers:
                h.flush()
            lineas = obtener_ultimas_lineas_log(n_lineas=5, ruta_log=ruta_log)
            self.assertTrue(any("Mensaje de prueba" in l for l in lineas))
            for h in list(log.handlers):
                h.close()
            log.handlers.clear()


if __name__ == "__main__":
    unittest.main()
