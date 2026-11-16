"""Pruebas unitarias para el módulo de chat interactivo por terminal."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from guarida_manager.cache import GestorCache
from guarida_manager.chat import (
    calcular_metricas_interaccion,
    ejecutar_chat_terminal,
    extraer_hechos_declarativos,
    medir_tokens_mensaje,
    mostrar_metricas_turno,
    mostrar_parejas_recomendadas,
    obtener_parejas_recomendadas,
)
from guarida_manager.engine.client import ClienteLlamaOffline


class TestChatTerminal(unittest.TestCase):
    """Batería de pruebas para la funcionalidad de chat por terminal y métricas."""

    def setUp(self):
        self.mock_cache = MagicMock(spec=GestorCache)
        self.mock_cache.obtener_benchmark.return_value = {
            "tok_s": 25.5,
            "n_gpu_layers": 16,
            "ctx_size": 4096,
        }

    def test_obtener_parejas_recomendadas(self):
        parejas = obtener_parejas_recomendadas(self.mock_cache)
        self.assertIsInstance(parejas, list)
        self.assertGreater(len(parejas), 0)
        p0 = parejas[0]
        self.assertIn("modelo_gen_id", p0)
        self.assertIn("modelo_emb_id", p0)
        self.assertIn("recomendacion_uso", p0)
        self.assertIn("score_conjunto", p0)
        self.assertIn("tok_s", p0)
        self.assertIn("clasificacion_rendimiento", p0)
        self.assertGreater(p0["tok_s"], 0.0)

        # Verificar que cada modelo generativo aparece una sola vez
        modelos_generativos = [p["modelo_gen_id"] for p in parejas]
        self.assertEqual(len(modelos_generativos), len(set(modelos_generativos)))

    def test_mostrar_parejas_recomendadas(self):
        salidas = []
        parejas = [
            {
                "modelo_gen_id": "qwen2.5-3b-chat-q4",
                "modelo_emb_id": "bge-m3-q4",
                "descargado_gen": True,
                "tok_s": 22.4,
                "tok_s_es_real": True,
                "score_conjunto": 95.0,
                "clasificacion_rendimiento": "🚀 ÁGIL",
                "recomendacion_uso": "Pareja para chat interactivo",
            }
        ]
        mostrar_parejas_recomendadas(parejas, modelo_activo="qwen2.5-3b-chat-q4", print_func=salidas.append)
        texto_unido = "\n".join(salidas)
        self.assertIn("PAREJAS RECOMENDADAS", texto_unido)
        self.assertIn("PISTA DE RENDIMIENTO", texto_unido)
        self.assertIn("qwen2.5-3b-chat-q4", texto_unido)
        self.assertIn("bge-m3-q4", texto_unido)

    def test_medir_tokens_mensaje_exitoso(self):
        mock_cli = MagicMock(spec=ClienteLlamaOffline)
        mock_cli.tokenizar.return_value = [101, 2054, 2003, 102]
        total = medir_tokens_mensaje(mock_cli, "¿Cómo estás?")
        self.assertEqual(total, 4)

    def test_medir_tokens_mensaje_fallback(self):
        mock_cli = MagicMock(spec=ClienteLlamaOffline)
        mock_cli.tokenizar.side_effect = Exception("Servidor sin endpoint tokenize")
        total = medir_tokens_mensaje(mock_cli, "Hola mundo")
        self.assertGreaterEqual(total, 1)

    def test_calcular_metricas_interaccion(self):
        resp_api = {
            "choices": [{"message": {"role": "assistant", "content": "Hola, en qué puedo ayudarte"}}],
            "usage": {
                "prompt_tokens": 15,
                "completion_tokens": 8,
                "total_tokens": 23,
            },
            "timings": {
                "prompt_per_second": 120.0,
                "predicted_per_second": 32.0,
            },
        }
        metricas = calcular_metricas_interaccion(
            tokens_mensaje=5,
            respuesta_api=resp_api,
            tiempo_total_s=0.25,
            contenido_salida="Hola, en qué puedo ayudarte",
        )
        self.assertEqual(metricas["tokens_mensaje"], 5)
        self.assertEqual(metricas["tokens_enviados_realmente"], 15)
        self.assertEqual(metricas["tokens_generados"], 8)
        self.assertEqual(metricas["tokens_totales"], 23)
        self.assertEqual(metricas["velocidad_generacion_tok_s"], 32.0)
        self.assertEqual(metricas["velocidad_prompt_tok_s"], 120.0)
        self.assertAlmostEqual(metricas["latencia_ms"], 250.0, delta=1.0)

    def test_chat_salida_inmediata_con_quit(self):
        salidas = []
        entradas = iter(["/quit"])

        mock_srv = MagicMock()
        mock_srv.esta_activo.return_value = True
        mock_srv.obtener_estado.return_value = {"activo": True, "modelo": "qwen2.5-3b-chat-q4"}
        mock_cli = MagicMock()
        mock_cli.esta_disponible.return_value = True

        ejecutar_chat_terminal(
            gestor_cache=self.mock_cache,
            gestor_server=mock_srv,
            cliente=mock_cli,
            modelo_seleccionado="qwen2.5-3b-chat-q4",
            input_func=lambda _: next(entradas),
            print_func=salidas.append,
        )

        texto_unido = "\n".join(salidas)
        # Verifica que se anuncia el comando /quit
        self.assertIn("/quit", texto_unido)
        # Verifica que se reconoció el comando /quit y salió
        self.assertIn("Comando '/quit' recibido", texto_unido)

    def test_chat_flujo_completo_con_metricas_y_quit(self):
        salidas = []
        entradas = iter([
            "Hola, ¿cuál es tu función?",
            "/quit",
        ])

        mock_srv = MagicMock()
        mock_srv.esta_activo.return_value = True
        mock_srv.obtener_estado.return_value = {"activo": True, "modelo": "qwen2.5-3b-chat-q4"}
        mock_cli = MagicMock()
        mock_cli.esta_disponible.return_value = True
        mock_cli.tokenizar.return_value = [1, 2, 3, 4, 5, 6]
        mock_cli.completar_chat.return_value = {
            "choices": [{"message": {"role": "assistant", "content": "Soy un asistente local."}}],
            "usage": {
                "prompt_tokens": 42,
                "completion_tokens": 6,
                "total_tokens": 48,
            },
            "timings": {
                "predicted_per_second": 28.5,
                "prompt_per_second": 150.0,
            },
        }

        ejecutar_chat_terminal(
            gestor_cache=self.mock_cache,
            gestor_server=mock_srv,
            cliente=mock_cli,
            modelo_seleccionado="qwen2.5-3b-chat-q4",
            input_func=lambda _: next(entradas),
            print_func=salidas.append,
        )

        texto_unido = "\n".join(salidas)
        # Anuncio de salida
        self.assertIn("Para salir del chat escribe el comando '/quit'", texto_unido)
        # Respuesta del asistente
        self.assertIn("Soy un asistente local.", texto_unido)
        # Métricas de mensaje y envío
        self.assertIn("Tokens del mensaje introducido:       6 tokens", texto_unido)
        self.assertIn("Tokens realmente enviados al modelo:  42 tokens", texto_unido)
        self.assertIn("Tokens generados en la respuesta:     6 tokens", texto_unido)
        self.assertIn("Velocidad de generación (TG):         28.50 tok/s", texto_unido)
        # Resumen de sesión
        self.assertIn("RESUMEN DE LA SESIÓN DE CHAT", texto_unido)

    def test_chat_seleccion_pareja_recomendada_por_defecto(self):
        salidas = []
        entradas = iter([
            "",       # Enter para seleccionar la recomendada por defecto
            "/quit",  # Salir
        ])

        mock_srv = MagicMock()
        mock_srv.esta_activo.return_value = True
        mock_srv.obtener_estado.return_value = {"activo": True, "modelo": "qwen2.5-3b-chat-q4"}
        mock_cli = MagicMock()
        mock_cli.esta_disponible.return_value = True

        ejecutar_chat_terminal(
            gestor_cache=self.mock_cache,
            gestor_server=mock_srv,
            cliente=mock_cli,
            modelo_seleccionado=None,
            input_func=lambda _: next(entradas),
            print_func=salidas.append,
        )

        texto_unido = "\n".join(salidas)
        self.assertIn("PAREJAS RECOMENDADAS", texto_unido)
        self.assertIn("Comando '/quit' recibido", texto_unido)

    def test_chat_usuario_decide_pareja_recomendada_especifica(self):
        salidas = []
        entradas = iter([
            "1",      # Usuario decide explícitamente la opción #1
            "/quit",
        ])

        mock_srv = MagicMock()
        mock_srv.esta_activo.return_value = True
        mock_srv.obtener_estado.return_value = {"activo": True, "modelo": "qwen2.5-3b-chat-q4"}
        mock_cli = MagicMock()
        mock_cli.esta_disponible.return_value = True

        ejecutar_chat_terminal(
            gestor_cache=self.mock_cache,
            gestor_server=mock_srv,
            cliente=mock_cli,
            modelo_seleccionado=None,
            input_func=lambda _: next(entradas),
            print_func=salidas.append,
        )

        texto_unido = "\n".join(salidas)
        self.assertIn("Pareja activa elegida por el usuario", texto_unido)
        self.assertIn("Comando '/quit' recibido", texto_unido)

    def test_chat_usuario_decide_pareja_manual_personalizada(self):
        salidas = []
        entradas = iter([
            "M",                     # Usuario elige configurar manualmente
            "qwen2.5-coder-7b-q4",   # Modelo generativo elegido
            "bge-m3-q4",             # Motor AST elegido
            "/quit",
        ])

        mock_srv = MagicMock()
        mock_srv.esta_activo.return_value = True
        mock_srv.obtener_estado.return_value = {"activo": True, "modelo": "qwen2.5-coder-7b-q4"}
        mock_cli = MagicMock()
        mock_cli.esta_disponible.return_value = True

        ejecutar_chat_terminal(
            gestor_cache=self.mock_cache,
            gestor_server=mock_srv,
            cliente=mock_cli,
            modelo_seleccionado=None,
            input_func=lambda _: next(entradas),
            print_func=salidas.append,
        )

        texto_unido = "\n".join(salidas)
        self.assertIn("SELECCIÓN MANUAL", texto_unido)
        self.assertIn("Pareja activa elegida por el usuario", texto_unido)
        self.assertIn("qwen2.5-coder-7b-q4", texto_unido)
        self.assertIn("bge-m3-q4", texto_unido)

    @patch("guarida_manager.chat.ClienteTensoresChat")
    def test_chat_modelo_safetensors_usa_motor_tensores(self, mock_cli_tensores_cls):
        mock_inst = MagicMock()
        mock_inst.esta_disponible.return_value = True
        mock_inst.base_url = "tensors://local/smollm2-135m-safetensors"
        mock_inst.tokenizar.return_value = [10, 20, 30]
        mock_inst.completar_chat.return_value = {
            "choices": [{"message": {"role": "assistant", "content": "Hola desde PyTorch."}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17},
            "timings": {"predicted_per_second": 45.0},
        }
        mock_cli_tensores_cls.return_value = mock_inst

        salidas = []
        entradas = iter(["Hola", "/quit"])

        mock_srv = MagicMock()
        mock_srv.esta_activo.return_value = False

        with patch("guarida_manager.menu_actions.obtener_modelos_locales") as mock_loc:
            mock_loc.return_value = [{
                "id": "smollm2-135m-safetensors",
                "filename": "model.safetensors",
                "ruta_local": "C:/dummy/model.safetensors",
                "tamano_mb": 270.0,
            }]

            ejecutar_chat_terminal(
                gestor_cache=self.mock_cache,
                gestor_server=mock_srv,
                modelo_seleccionado="smollm2-135m-safetensors",
                input_func=lambda _: next(entradas),
                print_func=salidas.append,
            )

        mock_inst.cargar.assert_called_once()
        mock_srv.iniciar_servidor.assert_not_called()  # No intenta arrancar llama-server
        texto_unido = "\n".join(salidas)
        self.assertIn("Iniciando motor de tensores nativo", texto_unido)
        self.assertIn("Hola desde PyTorch.", texto_unido)

    @patch("guarida_manager.chat.ClienteTensoresChat")
    def test_chat_modelo_safetensors_error_carga_diagnostico(self, mock_cli_tensores_cls):
        mock_inst = MagicMock()
        mock_inst.cargar.side_effect = RuntimeError("Falta archivo config.json")
        mock_cli_tensores_cls.return_value = mock_inst

        salidas = []
        mock_srv = MagicMock()
        mock_srv.esta_activo.return_value = False

        with patch("guarida_manager.menu_actions.obtener_modelos_locales") as mock_loc:
            mock_loc.return_value = [{
                "id": "smollm2-135m-safetensors",
                "filename": "model.safetensors",
                "ruta_local": "C:/dummy/model.safetensors",
                "tamano_mb": 270.0,
            }]

            ejecutar_chat_terminal(
                gestor_cache=self.mock_cache,
                gestor_server=mock_srv,
                modelo_seleccionado="smollm2-135m-safetensors",
                print_func=salidas.append,
            )

        texto_unido = "\n".join(salidas)
        self.assertIn("Error al abrir el modelo de tensores", texto_unido)
        self.assertIn("config.json", texto_unido)
        mock_srv.iniciar_servidor.assert_not_called()

    @patch("guarida_manager.downloader.tools.GestorHerramientasBunker.resolver_ruta_ejecutable")
    def test_chat_reintento_automatico_cpu_si_gpu_falla(self, mock_resolver):
        mock_resolver.return_value = Path("C:/dummy/llama-server.exe")
        salidas = []
        entradas = iter(["/quit"])

        mock_srv = MagicMock()
        mock_srv.esta_activo.return_value = False
        # Simular que el proceso tiene poll vivo tras el segundo intento
        mock_proc = MagicMock()
        mock_proc.poll.side_effect = [1, None, None, None]
        mock_srv.proceso = mock_proc

        mock_cli = MagicMock()
        # Primer intento falla; segundo intento en CPU responde OK
        mock_cli.esta_disponible.side_effect = [False, True, True]

        with patch("guarida_manager.menu_actions.obtener_modelos_locales") as mock_loc, \
             patch("guarida_manager.engine.server.LlamaServerConfig.desde_afinamiento") as mock_desde:
            mock_loc.return_value = [{
                "id": "deepseek-r1-distill-qwen-14b-q4",
                "filename": "deepseek.gguf",
                "ruta_local": "C:/dummy/deepseek.gguf",
                "tamano_mb": 8900.0,
            }]

            mock_cfg = MagicMock()
            mock_cfg.n_gpu_layers = 16
            mock_cfg.extra_args = []
            mock_cfg.ctx_size = 4096
            mock_desde.return_value = mock_cfg

            ejecutar_chat_terminal(
                gestor_cache=self.mock_cache,
                gestor_server=mock_srv,
                cliente=mock_cli,
                modelo_seleccionado="deepseek-r1-distill-qwen-14b-q4",
                input_func=lambda _: next(entradas),
                print_func=salidas.append,
            )

        texto_unido = "\n".join(salidas)
        self.assertIn("Reintentando en modo CPU seguro", texto_unido)
        self.assertEqual(mock_srv.iniciar_servidor.call_count, 2)

    def test_mostrar_metricas_turno_con_rag_y_hardware(self):
        from guarida_manager.telemetry import MetricasTelemetria

        hw_mock = MetricasTelemetria(
            cpu_pct=25.4,
            ram_usada_gb=12.2,
            ram_total_gb=32.0,
            ram_pct=38.1,
            vram_usada_gb=4.5,
            vram_total_gb=16.0,
            temperatura_c=55.0,
            disco_usado_gb=200.0,
            disco_total_gb=500.0,
            disco_pct=40.0,
            disco_libre_gb=300.0,
            gpu_nombre="Intel Iris Xe",
            gpu_tipo="Integrada / APU",
            nucleos_cpu="4C / 8T",
        )

        metricas_rag = {
            "tiempo_busqueda_ms": 14.8,
            "fragmentos_evaluados": 7468,
            "fragmentos_citados": 5,
            "top_score": 0.88,
            "tiempo_contexto_ms": 3.2,
            "tokens_contexto": 1250,
            "chars_contexto": 5000,
            "ficheros_consultados": ["Manual.pdf", "Doc.odt"],
        }

        metricas = {
            "tokens_mensaje": 25,
            "tokens_enviados_realmente": 1400,
            "tokens_generados": 180,
            "tokens_totales": 1580,
            "tiempo_total_s": 6.5,
            "latencia_ms": 6500.0,
            "velocidad_generacion_tok_s": 27.69,
            "velocidad_prompt_tok_s": 110.5,
            "rag": metricas_rag,
            "hardware": hw_mock,
        }

        salidas = []
        mostrar_metricas_turno(metricas, print_func=salidas.append)
        texto = "\n".join(salidas)

        self.assertIn("[MÉTRICAS DEL MENSAJE E INFERENCIA]", texto)
        self.assertIn("Velocidad de generación (TG):         27.69 tok/s", texto)
        self.assertIn("[TRABAJO CON FICHEROS / RAG LOCAL]", texto)
        self.assertIn("Búsqueda de referencias:              14.8 ms (7468 fragmentos evaluados)", texto)
        self.assertIn("Citas / Fragmentos aplicados:         5 fragmentos (Top-Score: 0.88)", texto)
        self.assertIn("Tiempo aplicación de contexto:        3.2 ms", texto)
        self.assertIn("Tokens de contexto inyectados:        1250 tokens (~5000 caracteres)", texto)
        self.assertIn("Ficheros consultados:                 Manual.pdf, Doc.odt", texto)
        self.assertIn("[CONSUMO DE HARDWARE EN TIEMPO REAL]", texto)
        self.assertIn("CPU:                                  25.4 % (4C / 8T)", texto)
        self.assertIn("RAM:                                  12.2 / 32.0 GB (38.1 %)", texto)
        self.assertIn("VRAM / GTT:                           4.5 / 16.0 GB (Intel Iris Xe)", texto)
        self.assertIn("GPU:                                  Intel Iris Xe [Integrada / APU]", texto)
        self.assertIn("Disco:                                200.0 / 500.0 GB (40.0 %) [300.0 GB libres]", texto)
        self.assertIn("Temperatura Silicio:                  55.0 °C", texto)

    def test_extraer_hechos_declarativos(self):
        hechos_exp = extraer_hechos_declarativos("[HECHO: puerto_api | es | 8083]")
        self.assertEqual(hechos_exp, [("puerto_api", "es", "8083")])

        hechos_nat = extraer_hechos_declarativos("Recuerda que el motor usa SQLite WAL.")
        self.assertEqual(hechos_nat, [("el motor", "usa", "SQLite WAL")])

    def test_chat_comandos_remember_recall_e_inyeccion_superseded(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_real = GestorCache(Path(tmp_dir) / "chat_memoria.db")
            salidas = []
            entradas = iter([
                "/remember puerto_api | es | 8080",
                "/remember puerto_api | es | 9000",
                "/recall",
                "/recall all",
                "¿Qué puerto usamos?",
                "/quit",
            ])

            mock_srv = MagicMock()
            mock_srv.esta_activo.return_value = True
            mock_srv.obtener_estado.return_value = {"activo": True, "modelo": "qwen2.5-3b-chat-q4"}
            mock_cli = MagicMock()
            mock_cli.esta_disponible.return_value = True
            mock_cli.base_url = "http://127.0.0.1:8083"
            mock_cli.tokenizar.return_value = [1, 2, 3, 4]
            mock_cli.completar_chat.return_value = {
                "choices": [{"message": {"role": "assistant", "content": "Usamos el puerto 9000."}}],
                "usage": {"prompt_tokens": 30, "completion_tokens": 5, "total_tokens": 35},
                "timings": {"predicted_per_second": 25.0},
            }

            ejecutar_chat_terminal(
                gestor_cache=cache_real,
                gestor_server=mock_srv,
                cliente=mock_cli,
                modelo_seleccionado="qwen2.5-3b-chat-q4",
                input_func=lambda _: next(entradas),
                print_func=salidas.append,
            )

            texto_salida = "\n".join(salidas)
            self.assertIn("Hecho registrado en memoria inmutable", texto_salida)
            self.assertIn("[MEMORIA DECLARATIVA ACTIVA] (1 hechos):", texto_salida)
            self.assertIn("[AUDITORÍA COMPLETA DE MEMORIA] (2 hechos):", texto_salida)
            self.assertIn("[SUPERSEDED -> #2]", texto_salida)

            mock_cli.completar_chat.assert_called_once()
            mensajes_enviados = mock_cli.completar_chat.call_args.kwargs["mensajes"]
            prompt_usuario = mensajes_enviados[-1]["content"]
            self.assertIn("[Memoria Declarativa Activa (Hechos Verificados)]:", prompt_usuario)
            self.assertIn("puerto_api | es | 9000", prompt_usuario)
            self.assertNotIn("puerto_api | es | 8080", prompt_usuario)

            sesiones = cache_real.listar_sesiones_chat()
            self.assertEqual(len(sesiones), 1)
            msgs_db = cache_real.obtener_mensajes_sesion(sesiones[0]["id"])
            self.assertEqual(msgs_db[0]["contenido"], "¿Qué puerto usamos?")


if __name__ == "__main__":
    unittest.main()
