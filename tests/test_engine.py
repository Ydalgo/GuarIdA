import io
import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import urllib.error

from guarida_manager.engine.client import ClienteLlamaOffline, ErrorInferenciaOffline
from guarida_manager.engine.server import GestorLlamaServer, LlamaServerConfig


class TestLlamaServer(unittest.TestCase):
    def test_construir_comando_basico(self):
        config = LlamaServerConfig(
            modelo_path=Path("C:/models/qwen.gguf"),
            binario_path=Path("C:/bin/llama-server.exe"),
            host="127.0.0.1",
            port=8083,
            n_gpu_layers=33,
            ctx_size=16384,
            batch_size=512,
            threads=8,
            kv_cache_type="q4_0",
            alias="qwen2.5",
            embedding=False,
            no_webui=True,
        )

        cmd = config.construir_comando()

        self.assertIn("-m", cmd)
        self.assertIn(str(Path("C:/models/qwen.gguf")), cmd)
        self.assertIn("--host", cmd)
        self.assertIn("127.0.0.1", cmd)
        self.assertIn("--port", cmd)
        self.assertIn("8083", cmd)
        self.assertIn("-ngl", cmd)
        self.assertIn("33", cmd)
        self.assertIn("-c", cmd)
        self.assertIn("16384", cmd)
        self.assertIn("-b", cmd)
        self.assertIn("512", cmd)
        self.assertIn("-t", cmd)
        self.assertIn("8", cmd)
        self.assertIn("--cache-type-k", cmd)
        self.assertIn("q4_0", cmd)
        self.assertIn("-a", cmd)
        self.assertIn("qwen2.5", cmd)
        self.assertIn("--no-webui", cmd)

    def test_desde_afinamiento_con_cache_optima(self):
        mock_cache = MagicMock()
        mock_cache.obtener_configuracion_optima.return_value = {
            "n_gpu_layers": 28,
            "ctx_size": 8192,
            "batch_size": 256,
            "kv_cache_tipo": "q8_0",
        }

        with patch("guarida_manager.engine.server.obtener_informacion_hardware") as mock_info_fn:
            mock_perfil = MagicMock()
            mock_perfil.hash_hardware = "dummy_hash"
            mock_perfil.nucleos_fisicos = 4
            mock_perfil.tiene_aceleracion_gpu = True
            mock_info_fn.return_value = mock_perfil

            config = LlamaServerConfig.desde_afinamiento(
                modelo_path=Path("modelo.gguf"),
                modelo_id="qwen2.5-coder-7b",
                gestor_cache=mock_cache,
            )

            self.assertEqual(config.n_gpu_layers, 28)
            self.assertEqual(config.ctx_size, 8192)
            self.assertEqual(config.batch_size, 256)
            self.assertEqual(config.kv_cache_type, "q8_0")
            self.assertEqual(config.threads, 4)

    @patch("guarida_manager.engine.server.subprocess.Popen")
    def test_gestor_servidor_ciclo_de_vida(self, mock_popen):
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.poll.return_value = None  # Indica proceso vivo
        mock_popen.return_value = mock_proc

        mock_cache = MagicMock()
        gestor = GestorLlamaServer(gestor_cache=mock_cache)
        config = LlamaServerConfig(modelo_path=Path("dummy.gguf"))

        self.assertFalse(gestor.esta_activo())
        res = gestor.iniciar_servidor(config)

        self.assertEqual(res["pid"], 12345)
        self.assertTrue(gestor.esta_activo())
        info = gestor.obtener_estado()
        self.assertEqual(info["pid"], 12345)
        self.assertTrue(info["activo"])

        # Intentar iniciar de nuevo debe lanzar RuntimeError
        with self.assertRaises(RuntimeError):
            gestor.iniciar_servidor(config)

        # Detener servidor
        detenido = gestor.detener_servidor()
        self.assertTrue(detenido)
        mock_proc.terminate.assert_called_once()
        self.assertFalse(gestor.esta_activo())


class TestClienteLlamaOffline(unittest.TestCase):
    def setUp(self):
        self.cliente = ClienteLlamaOffline(host="127.0.0.1", port=8083)

    @patch("urllib.request.urlopen")
    def test_salud_y_disponibilidad(self, mock_urlopen):
        # Mock respuesta 200 con status ok
        mock_resp = MagicMock()
        mock_resp.getcode.return_value = 200
        mock_resp.read.return_value = json.dumps({"status": "ok"}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        self.assertTrue(self.cliente.esta_disponible())
        salud = self.cliente.obtener_salud()
        self.assertEqual(salud.get("status"), "ok")

    @patch("urllib.request.urlopen")
    def test_completar_chat(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.getcode.return_value = 200
        payload_salida = {
            "choices": [
                {"message": {"role": "assistant", "content": "print('Hola desde búnker')"}}
            ],
            "usage": {"prompt_tokens": 12, "completion_tokens": 8},
        }
        mock_resp.read.return_value = json.dumps(payload_salida).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        res = self.cliente.completar_chat([{"role": "user", "content": "Hola"}])
        self.assertIn("choices", res)
        self.assertEqual(
            res["choices"][0]["message"]["content"],
            "print('Hola desde búnker')",
        )

    @patch("urllib.request.urlopen")
    def test_tokenizar_y_detokenizar(self, mock_urlopen):
        # 1. Tokenizar
        mock_resp_tok = MagicMock()
        mock_resp_tok.getcode.return_value = 200
        mock_resp_tok.read.return_value = json.dumps({"tokens": [15, 230, 999]}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp_tok

        tokens = self.cliente.tokenizar("hola mundo")
        self.assertEqual(tokens, [15, 230, 999])

        # 2. Detokenizar
        mock_resp_detok = MagicMock()
        mock_resp_detok.getcode.return_value = 200
        mock_resp_detok.read.return_value = json.dumps({"content": "hola mundo"}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp_detok

        texto = self.cliente.detokenizar([15, 230, 999])
        self.assertEqual(texto, "hola mundo")

    @patch("urllib.request.urlopen")
    def test_error_conexion(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("Conexion rechazada")
        self.assertFalse(self.cliente.esta_disponible())

        with self.assertRaises(ErrorInferenciaOffline):
            self.cliente.obtener_salud()

    def test_calcular_embedding_formatos(self):
        # 1. Formato lista de diccionarios (llama-server estándar)
        with patch.object(self.cliente, "_solicitud_http", return_value=[{"embedding": [0.1, 0.2, 0.3]}]) as m:
            vec = self.cliente.calcular_embedding("test")
            self.assertEqual(vec, [0.1, 0.2, 0.3])

        # 2. Formato diccionario nativo
        with patch.object(self.cliente, "_solicitud_http", return_value={"embedding": [0.4, 0.5]}):
            vec = self.cliente.calcular_embedding("test")
            self.assertEqual(vec, [0.4, 0.5])

        # 3. Formato OpenAI data
        with patch.object(self.cliente, "_solicitud_http", return_value={"data": [{"embedding": [0.6, 0.7]}]}):
            vec = self.cliente.calcular_embedding("test")
            self.assertEqual(vec, [0.6, 0.7])

        # 4. Formato lista plana
        with patch.object(self.cliente, "_solicitud_http", return_value=[0.8, 0.9]):
            vec = self.cliente.calcular_embedding("test")
            self.assertEqual(vec, [0.8, 0.9])

        # 5. Formato 2D anidado de llama-server reciente ([{"index": 0, "embedding": [[...]]}])
        with patch.object(self.cliente, "_solicitud_http", return_value=[{"index": 0, "embedding": [[0.11, 0.22, 0.33]]}]):
            vec = self.cliente.calcular_embedding("test")
            self.assertEqual(vec, [0.11, 0.22, 0.33])


if __name__ == "__main__":
    unittest.main()
