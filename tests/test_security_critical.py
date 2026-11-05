import io
import json
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from guarida_manager.cache import GestorCache
from guarida_manager.downloader.binaries import (
    GestorBinariosLlama,
    PerfilBinarioLlama,
    extraer_tar_seguro,
    extraer_zip_seguro,
)
from guarida_manager.downloader.models import (
    CatalogoModelos,
    DefinicionModeloCatalogo,
    DescargadorModelos,
)
from guarida_manager.downloader.provisioning import OrquestadorAprovisionamiento
from guarida_manager.downloader.tools import GestorHerramientasBunker


class TestSecurityCritical(unittest.TestCase):
    def test_zip_slip_prevencion(self):
        """S4: Verificar que extraer_zip_seguro rechaza rutas con path traversal."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            dest_dir = Path(tmp_dir) / "extract"
            dest_dir.mkdir()
            malicious_zip = Path(tmp_dir) / "malicious.zip"

            with zipfile.ZipFile(malicious_zip, "w") as zf:
                zf.writestr("../../pwned.txt", "contenido malicioso")

            with self.assertRaises(ValueError) as ctx:
                extraer_zip_seguro(malicious_zip, dest_dir)
            self.assertIn("Zip Slip", str(ctx.exception))
            self.assertFalse((Path(tmp_dir) / "pwned.txt").exists())

    def test_tar_slip_prevencion(self):
        """S4: Verificar que extraer_tar_seguro rechaza rutas con path traversal."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            dest_dir = Path(tmp_dir) / "extract"
            dest_dir.mkdir()
            malicious_tar = Path(tmp_dir) / "malicious.tar"

            with tarfile.open(malicious_tar, "w") as tf:
                tarinfo = tarfile.TarInfo(name="../../pwned.txt")
                data = b"contenido malicioso"
                tarinfo.size = len(data)
                tf.addfile(tarinfo, io.BytesIO(data))

            # En Python 3.12+ filter="data" bloquea o lanza FilterError/ValueError; si no, nuestra validación lanza ValueError
            with self.assertRaises((ValueError, tarfile.FilterError)):
                extraer_tar_seguro(malicious_tar, dest_dir)
            self.assertFalse((Path(tmp_dir) / "pwned.txt").exists())

    def test_verificacion_sha256_binario_llama_falla_si_adulterado(self):
        """S3: Verificar que un binario adulterado es rechazado por hash SHA-256."""
        perfil = PerfilBinarioLlama(
            build_tag="b12017",
            nombre_archivo="llama-test.zip",
            url_descarga="https://example.com/fake.zip",
            directorio_destino=Path("fake_dir"),
            es_vulkan=False,
            sistema_operativo="Windows",
            sha256_esperado="a" * 64,  # Hash esperado ficticio
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            perfil_tmp = PerfilBinarioLlama(
                build_tag="b12017",
                nombre_archivo="llama-test.zip",
                url_descarga="https://example.com/fake.zip",
                directorio_destino=Path(tmp_dir) / "bin",
                es_vulkan=False,
                sistema_operativo="Windows",
                sha256_esperado="a" * 64,
            )

            # Mock urlopen para simular contenido adulterado
            mock_resp = MagicMock()
            mock_resp.headers.get.return_value = "10"
            mock_resp.read.side_effect = [b"datos_falsos", b""]
            mock_resp.__enter__.return_value = mock_resp

            with patch("guarida_manager.downloader.core.urllib.request.urlopen", return_value=mock_resp):
                with self.assertRaises(ValueError) as ctx:
                    GestorBinariosLlama.descargar_y_desplegar(perfil=perfil_tmp)
                self.assertIn("Fallo de integridad SHA-256", str(ctx.exception))

    def test_verificacion_sha256_modelo_gguf_falla_si_adulterado(self):
        """S5: Verificar que un modelo GGUF adulterado es rechazado tras descarga."""
        modelo = DefinicionModeloCatalogo(
            id="modelo-test-seguro",
            nombre_legible="Modelo Test Seguro",
            categoria="coder",
            cuantizacion="Q4_K_M",
            idiomas_destacados="es",
            repo_hf="fake/repo",
            filename="fake-model.gguf",
            tamano_gb=0.01,
            ram_minima_gb=1.0,
            ram_recomendada_gb=2.0,
            licencia="apache-2.0",
            training_summary_url=None,
            copyright_compliant=True,
            es_sin_censura=False,
            descripcion="Test",
            sha256_esperado="b" * 64,
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            test_db = Path(tmp_dir) / "test.db"
            cache = GestorCache(test_db)
            descargador = DescargadorModelos(directorio_modelos=Path(tmp_dir) / "models", gestor_cache=cache)

            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.headers.get.return_value = "12"
            mock_resp.read.side_effect = [b"bytes_modelo", b""]
            mock_resp.__enter__.return_value = mock_resp

            with patch("guarida_manager.downloader.core.urllib.request.urlopen", return_value=mock_resp):
                with self.assertRaises(ValueError) as ctx:
                    descargador.descargar_modelo(modelo)
                self.assertIn("Fallo de integridad SHA-256", str(ctx.exception))

    def test_provisioning_no_escribe_en_claro_si_hay_clave(self):
        """S2: Comprobar que no se escribe la configuración en claro si se usa clave maestra."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            ruta_cfg = tmp_path / "bunker_config.json"
            cache = GestorCache(tmp_path / "test_prov.db")
            models_dir = tmp_path / "models"
            models_dir.mkdir()
            orquestador = OrquestadorAprovisionamiento(
                ruta_config=ruta_cfg,
                gestor_cache=cache,
                directorio_modelos=models_dir,
            )

            with patch.object(GestorBinariosLlama, "descargar_y_desplegar"), \
                 patch.object(GestorHerramientasBunker, "verificar_todas_herramientas", return_value=[]), \
                 patch.object(GestorHerramientasBunker, "descargar_y_desplegar"), \
                 patch.object(DescargadorModelos, "descargar_cesta", return_value=[]), \
                 patch.object(OrquestadorAprovisionamiento, "instalar_paquete_pip", return_value=True):

                orquestador.ejecutar_aprovisionamiento_lote(
                    clave_maestra_boveda="ContrasenaMuyFuerte2026!",
                    instalar_pdf=False,
                )

                ruta_cifrada = ruta_cfg.with_suffix(".pqc.json")
                self.assertTrue(ruta_cifrada.exists(), "El archivo cifrado .pqc.json debe existir")
                self.assertFalse(ruta_cfg.exists(), "El archivo en claro bunker_config.json NO debe existir")

                with open(ruta_cifrada, "r", encoding="utf-8") as f:
                    datos = json.load(f)
                self.assertIn("mac_autenticacion_hex", datos)
                self.assertIn("salt_hex", datos)
                self.assertIn("datos_cifrados_b64", datos)

    def test_s6_validacion_repo_y_filename_hf(self):
        """S6: Validación de HuggingFace repo y filename contra path traversal."""
        from guarida_manager.downloader.models import (
            validar_filename_hf,
            validar_repo_hf,
            validar_revision_hf,
        )

        # Repos inválidos o con traversal
        with self.assertRaises(ValueError):
            validar_repo_hf("malicious/../../evil")
        with self.assertRaises(ValueError):
            validar_repo_hf("singlepart")
        with self.assertRaises(ValueError):
            validar_repo_hf("org/repo/subpath")

        # Repos válidos
        self.assertEqual(validar_repo_hf("Qwen/Qwen2.5-7B"), "Qwen/Qwen2.5-7B")

        # Filenames con path traversal o extensión indebida
        with self.assertRaises(ValueError):
            validar_filename_hf("../../evil.gguf")
        with self.assertRaises(ValueError):
            validar_filename_hf("subfolder/model.gguf")
        with self.assertRaises(ValueError):
            validar_filename_hf("script.sh")

        # Filename válido
        self.assertEqual(validar_filename_hf("model-q4.gguf"), "model-q4.gguf")

        # Revision
        with self.assertRaises(ValueError):
            validar_revision_hf("../escape")
        self.assertEqual(validar_revision_hf("commit123"), "commit123")
        self.assertEqual(validar_revision_hf(None), "main")

    def test_s7_pip_install_whitelist_y_no_deps(self):
        """S7: Verificación de lista blanca y restricción en pip install."""
        # Intento de instalar paquete arbitrario debe fallar
        with self.assertRaises(ValueError) as ctx:
            OrquestadorAprovisionamiento.instalar_paquete_pip("malicious-package")
        self.assertIn("no autorizado", str(ctx.exception))

        # Intento con permitir_pip_runtime=False debe retornar False
        res = OrquestadorAprovisionamiento.instalar_paquete_pip("reportlab", permitir_pip_runtime=False)
        self.assertFalse(res)

    def test_s8_llama_server_seguridad(self):
        """S8: Comprobar --api-key, advertencia de host no-loopback y bloqueo de inyección en extra_args."""
        from guarida_manager.engine.server import LlamaServerConfig
        import warnings

        # 1. API Key no expuesta en argv de línea de comandos (N3)
        config = LlamaServerConfig(
            modelo_path=Path("model.gguf"),
            api_key="bunker-secret-key-12345",
        )
        cmd = config.construir_comando()
        self.assertNotIn("--api-key", cmd)
        self.assertNotIn("bunker-secret-key-12345", cmd)

        # 2. Host inseguro (0.0.0.0) emite warning
        config_insegura = LlamaServerConfig(
            modelo_path=Path("model.gguf"),
            host="0.0.0.0",
        )
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            config_insegura.construir_comando()
            self.assertTrue(any("ADVERTENCIA DE SEGURIDAD" in str(item.message) for item in w))

        # 3. extra_args con caracteres prohibidos de shell
        config_inyeccion = LlamaServerConfig(
            modelo_path=Path("model.gguf"),
            extra_args=["--valid-flag", "; rm -rf /"],
        )
        with self.assertRaises(ValueError) as ctx:
            config_inyeccion.construir_comando()
        self.assertIn("Argumento extra no seguro detectado", str(ctx.exception))

    def test_motor_descargas_bunker_unificado_con_inyeccion_cache(self):
        """Fase 3: Motor centralizado de descargas con inyección de dependencias de caché."""
        from guarida_manager.downloader.core import MotorDescargasBunker
        from guarida_manager.downloader.models import DefinicionModeloCatalogo

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            cache_custom = GestorCache(tmp_path / "custom.db")
            models_dir = tmp_path / "models"
            motor = MotorDescargasBunker(
                gestor_cache=cache_custom,
                directorio_modelos=models_dir,
            )
            self.assertEqual(motor.cache.ruta_db, tmp_path / "custom.db")
            self.assertEqual(motor.directorio_modelos, models_dir)

    def test_descargador_seguro_reintento_exitoso_tras_fallo_transitorio(self):
        """Fase 3: DescargadorSeguro reintenta y supera un fallo transitorio de red."""
        from guarida_manager.downloader.core import DescargadorSeguro
        import urllib.error

        with tempfile.TemporaryDirectory() as tmp_dir:
            dest = Path(tmp_dir) / "output.bin"
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.headers.get.return_value = "5"
            mock_resp.read.side_effect = [b"hello", b""]
            mock_resp.__enter__.return_value = mock_resp

            intentos = [0]
            def side_effect_urlopen(req, timeout=30):
                intentos[0] += 1
                if intentos[0] == 1:
                    raise urllib.error.URLError("Fallo transitorio de socket")
                return mock_resp

            # Verificar política fail-closed (S-C1): sin hash ni permitir_inseguro falla
            with self.assertRaises(ValueError):
                DescargadorSeguro.descargar_archivo(
                    url="https://example.com/file.bin",
                    ruta_destino=dest,
                )

            with patch("guarida_manager.downloader.core.urllib.request.urlopen", side_effect=side_effect_urlopen):
                with patch("guarida_manager.downloader.core.time.sleep") as mock_sleep:
                    res = DescargadorSeguro.descargar_archivo(
                        url="https://example.com/file.bin",
                        ruta_destino=dest,
                        permitir_inseguro=True,
                        max_reintentos=3,
                        reintento_backoff=0.01,
                    )
                    self.assertTrue(res.exists())
                    self.assertEqual(intentos[0], 2)
                    mock_sleep.assert_called_once()

    def test_config_store_atomico_y_cifrado(self):
        """Fase 3: Verificación de persistencia atómica y cifrado/descifrado en config_store."""
        from guarida_manager.downloader.config_store import (
            ConfiguracionBunker,
            guardar_configuracion_bunker,
            cargar_configuracion_bunker,
            escribir_archivo_atomico,
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            cfg_path = tmp_path / "bunker.json"

            # 1. Escritura atómica simple
            test_file = tmp_path / "atomic.txt"
            escribir_archivo_atomico(test_file, "contenido seguro")
            self.assertEqual(test_file.read_text(encoding="utf-8"), "contenido seguro")

            # 2. Guardar en claro
            cfg = ConfiguracionBunker(
                region="ES_EU",
                interfaz_preferida="terminal",
                soporte_informes_pdf=False,
                roles={"coder": "qwen2.5-coder"},
                modelos_instalados=["qwen2.5-coder"],
                herramientas_instaladas=["llama-server"],
                binario_inferencia_instalado=True,
                cifrado_postcuantico_activo=False,
                estado_bunker="OFFLINE_COMPLETO",
            )
            ruta_ret = guardar_configuracion_bunker(cfg, cfg_path)
            self.assertEqual(ruta_ret, cfg_path)
            self.assertTrue(cfg_path.exists())

            cargada = cargar_configuracion_bunker(cfg_path)
            self.assertEqual(cargada.region, "ES_EU")
            self.assertFalse(cargada.cifrado_postcuantico_activo)

            # 3. Guardar con cifrado
            cfg.cifrado_postcuantico_activo = True
            ruta_cifrada = guardar_configuracion_bunker(cfg, cfg_path, clave_maestra_boveda="ClaveBunker123!")
            self.assertTrue(ruta_cifrada.exists())
            self.assertEqual(ruta_cifrada.suffix, ".json")
            self.assertTrue(str(ruta_cifrada).endswith(".pqc.json"))
            self.assertFalse(cfg_path.exists())  # Plaintext eliminado (S2)

            # Carga sin clave debe fallar
            with self.assertRaises(PermissionError):
                cargar_configuracion_bunker(cfg_path)

            # Carga con clave correcta descifra íntegramente
            cfg_descifrada = cargar_configuracion_bunker(cfg_path, clave_maestra_boveda="ClaveBunker123!")
            self.assertEqual(cfg_descifrada.region, "ES_EU")
            self.assertTrue(cfg_descifrada.cifrado_postcuantico_activo)

    def test_packages_gestor(self):
        """Fase 3: Verificación de GestorPaquetesPython y versiones pineadas."""
        from guarida_manager.downloader.packages import GestorPaquetesPython

        self.assertTrue(GestorPaquetesPython.verificar_paquete("json"))
        self.assertFalse(GestorPaquetesPython.verificar_paquete("paquete_totalmente_ficticio_xyz_123"))

        for pkg, specs in GestorPaquetesPython.PAQUETES_PINNED.items():
            for spec in specs:
                self.assertTrue("==" in spec or ">=" in spec, f"El paquete {pkg} debe estar versionado: {spec}")

    def test_menu_actions_desacopladas(self):
        """Fase 3: Verificación de acciones desacopladas de menú con inyección de caché."""
        from guarida_manager import menu_actions

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            db_path = tmp_path / "test_menu.db"
            cache = GestorCache(db_path)

            # Probar listado de modelos locales en caché vacía
            locales = menu_actions.obtener_modelos_locales(cache)
            self.assertEqual(len(locales), 0)

            # Probar listado de perfiles de afinamiento sin excepción
            menu_actions.listar_perfiles_afinamiento(cache, "dummy_hardware_hash")

            # Probar estado de caché sin excepción
            menu_actions.mostrar_estado_cache(cache)


if __name__ == "__main__":
    unittest.main()
