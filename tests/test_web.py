"""Pruebas unitarias para el servidor web autoalojado de GuarIdA (estilo Antigravity IDE)."""

import json
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock

from guarida_manager.cache import GestorCache
from guarida_manager.web.server import ControladorWebGuarida, crear_servidor_web


class TestServidorWebGuarida(unittest.TestCase):
    """Valida API JSON, estáticos HTML/CSS/JS, RAG AST, memoria declarativa y chat."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.tmp_dir.name)
        self.cache = GestorCache(self.base_path / "db")

        self.mock_srv = MagicMock()
        self.mock_srv.host = "127.0.0.1"
        self.mock_srv.port = 8083
        self.mock_srv.esta_activo.return_value = True
        self.mock_srv.obtener_estado.return_value = {
            "activo": True,
            "pid": 9999,
            "uptime_segundos": 12.5,
            "host": "127.0.0.1",
            "port": 8083,
            "modelo": "qwen2.5-3b-chat-q4",
            "n_gpu_layers": 33,
            "ctx_size": 4096,
        }

        self.mock_cli = MagicMock()
        self.mock_cli.base_url = "http://127.0.0.1:8083"
        self.mock_cli.esta_disponible.return_value = True
        self.mock_cli.tokenizar.return_value = [1, 2, 3, 4, 5]
        self.mock_cli.completar_chat.return_value = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "La función `calcular_indice` está definida en `modulo.py`.",
                    }
                }
            ],
            "usage": {"prompt_tokens": 48, "completion_tokens": 12, "total_tokens": 60},
            "timings": {"predicted_per_second": 41.2, "prompt_per_second": 180.0},
        }

        self.ctrl = ControladorWebGuarida(
            gestor_cache=self.cache,
            gestor_server=self.mock_srv,
            cliente=self.mock_cli,
        )
        self.ctrl.modelo_activo_id = "qwen2.5-3b-chat-q4"

        self.server = crear_servidor_web(host="127.0.0.1", port=0, controlador=self.ctrl)
        self.port = int(self.server.server_address[1])
        self.base_url = f"http://127.0.0.1:{self.port}"
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2.0)
        self.tmp_dir.cleanup()

    def _get(self, path: str) -> tuple[int, str, dict[str, str]]:
        with self._opener.open(f"{self.base_url}{path}", timeout=5.0) as resp:
            return resp.getcode(), resp.read().decode("utf-8"), dict(resp.headers)

    def _post(self, path: str, payload: dict) -> tuple[int, dict]:
        datos = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=datos,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self._opener.open(req, timeout=10.0) as resp:
            return resp.getcode(), json.loads(resp.read().decode("utf-8"))

    def test_estaticos_estilo_antigravity(self):
        code_html, html, headers = self._get("/")
        self.assertEqual(code_html, 200)
        self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")
        self.assertIn("ANTIGRAVITY BUNKER", html)
        self.assertIn("GuarIdA", html)

        code_css, css, _ = self._get("/styles.css")
        self.assertEqual(code_css, 200)
        self.assertIn("--bg-canvas: #090b10", css)

        code_js, js, _ = self._get("/app.js")
        self.assertEqual(code_js, 200)
        self.assertIn("/api/status", js)
        self.assertIn("/api/chat", js)

    def test_estado_sistema_y_catalogo_modelos(self):
        code_st, raw_st, _ = self._get("/api/status")
        self.assertEqual(code_st, 200)
        st = json.loads(raw_st)
        self.assertIn("hardware", st)
        self.assertIn("telemetria", st)
        self.assertIn("parejas_recomendadas", st)
        self.assertGreater(len(st["parejas_recomendadas"]), 0)
        self.assertTrue(st["servidor"]["disponible_http"])

        code_mod, raw_mod, _ = self._get("/api/models")
        self.assertEqual(code_mod, 200)
        mods = json.loads(raw_mod)["modelos"]
        self.assertTrue(any(m["id"] == "qwen2.5-3b-chat-q4" for m in mods))

    def test_proyecto_ast_memoria_privacidad_y_chat_rag(self):
        repo_dir = self.base_path / "repo_demo"
        repo_dir.mkdir()
        (repo_dir / "modulo.py").write_text(
            "def calcular_indice(valor: int) -> int:\n"
            "    return valor * 2\n\n"
            "def ejecutar_flujo() -> int:\n"
            "    return calcular_indice(21)\n",
            encoding="utf-8",
        )

        code_p, res_p = self._post(
            "/api/projects",
            {"nombre": "Demo AST", "ruta_directorio": str(repo_dir), "descripcion": "Test"},
        )
        self.assertEqual(code_p, 201)
        pid = res_p["proyecto"]["id"]
        self.assertGreaterEqual(res_p["indexacion"]["nodos_ast"], 2)

        code_files, raw_files, _ = self._get(
            f"/api/projects/files?proyecto_id={pid}&semilla=ejecutar_flujo"
        )
        self.assertEqual(code_files, 200)
        datos_files = json.loads(raw_files)
        self.assertTrue(any(d["ruta_relativa"] == "modulo.py" for d in datos_files["documentos"]))
        self.assertTrue(any(n["nombre"] == "calcular_indice" for n in datos_files["nodos_ast"]))

        # Memoria declarativa superseded y modo RGPD
        code_m1, _ = self._post(
            "/api/memory",
            {"sujeto": "puerto_web", "predicado": "es", "objeto": "8080", "proyecto_id": pid},
        )
        self.assertEqual(code_m1, 201)
        code_m2, _ = self._post(
            "/api/memory",
            {"sujeto": "puerto_web", "predicado": "es", "objeto": "9090", "proyecto_id": pid},
        )
        self.assertEqual(code_m2, 201)

        _, raw_mem_act, _ = self._get(f"/api/memory?proyecto_id={pid}")
        hechos_act = json.loads(raw_mem_act)["hechos"]
        self.assertEqual(len(hechos_act), 1)
        self.assertEqual(hechos_act[0]["objeto"], "9090")

        _, raw_mem_all, _ = self._get(f"/api/memory?proyecto_id={pid}&incluir_superseded=1")
        hechos_all = json.loads(raw_mem_all)["hechos"]
        self.assertEqual(len(hechos_all), 2)
        self.assertEqual(hechos_all[0]["estado"], "superseded")

        code_priv, res_priv = self._post("/api/privacy", {"modo": "rgpd_estricto"})
        self.assertEqual(code_priv, 200)
        self.assertEqual(res_priv["modo"], "rgpd_estricto")

        # Comandos en chat (/ficheros, /remember, /recall)
        code_c1, res_c1 = self._post("/api/chat", {"mensaje": "/ficheros", "proyecto_id": pid})
        self.assertEqual(code_c1, 200)
        self.assertTrue(res_c1["comando"])
        self.assertIn("modulo.py", res_c1["respuesta"])
        sid = res_c1["sesion_id"]

        _, res_c2 = self._post(
            "/api/chat",
            {"mensaje": "/remember framework | es | GuarIdA Web", "proyecto_id": pid, "sesion_id": sid},
        )
        self.assertEqual(len(res_c2["hechos_detectados"]), 1)

        _, res_c3 = self._post(
            "/api/chat", {"mensaje": "/recall all", "proyecto_id": pid, "sesion_id": sid}
        )
        self.assertIn("SUPERSEDED", res_c3["respuesta"])

        # Turno conversacional RAG citando fuentes y midiendo métricas
        code_rag, res_rag = self._post(
            "/api/chat",
            {
                "mensaje": "¿Dónde está calcular_indice? correo usuario@ejemplo.com",
                "proyecto_id": pid,
                "sesion_id": sid,
            },
        )
        self.assertEqual(code_rag, 200)
        self.assertFalse(res_rag["comando"])
        self.assertIn("calcular_indice", res_rag["respuesta"])
        self.assertTrue(any(f["archivo"] == "modulo.py" for f in res_rag["fuentes"]))
        self.assertGreater(res_rag["redacciones_privacidad"], 0)
        self.assertAlmostEqual(res_rag["metricas"]["velocidad_generacion_tok_s"], 41.2, places=1)

    def test_cierre_automatico_al_cerrar_web(self):
        import time

        code_st, _, _ = self._get("/api/status")
        self.assertEqual(code_st, 200)
        self.assertFalse(self.ctrl.debe_finalizar_por_cierre_web(gracia_beacon_s=0.1))

        # Simular recarga (F5): beacon tab_closed seguido de latido inmediato
        code_b1, res_b1 = self._post("/api/web/close", {"motivo": "tab_closed"})
        self.assertEqual(code_b1, 200)
        self.assertTrue(res_b1["ok"])
        self._get("/api/status")
        time.sleep(0.12)
        self.assertFalse(self.ctrl.debe_finalizar_por_cierre_web(gracia_beacon_s=0.1))

        # Sin latido tras gracia_beacon_s debe marcar finalización
        self._post("/api/web/close", {"motivo": "tab_closed"})
        time.sleep(0.15)
        self.assertTrue(self.ctrl.debe_finalizar_por_cierre_web(gracia_beacon_s=0.1))

        # Reinicio y cierre manual inmediato
        self.ctrl.reiniciar_monitor_cierre()
        self.assertFalse(self.ctrl.debe_finalizar_por_cierre_web())
        self._post("/api/web/close", {"motivo": "manual"})
        self.assertTrue(self.ctrl.debe_finalizar_por_cierre_web())


if __name__ == "__main__":
    unittest.main()
