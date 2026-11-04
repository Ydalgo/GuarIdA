import hashlib
import os
import shutil
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from datetime import datetime, timezone

from guarida_manager import DIRECTORIO_MODELOS
from guarida_manager.cache import (
    ConfiguracionOptimaRegistro,
    GestorCache,
    ModeloRegistro,
)
from guarida_manager.downloader.compliance import (
    EvaluacionCumplimiento,
    GestorCumplimientoNormativo,
    RegionNormativa,
)


@dataclass(frozen=True)
class DefinicionModeloCatalogo:
    id: str
    nombre_legible: str
    categoria: str                 # "coder", "chat", "uncensored", "embedding", "general"
    cuantizacion: str              # "Q5_K_M", "Q4_K_M", "Q3_K_M", "Q2_K", etc.
    idiomas_destacados: str        # "es, en", "multilingüe", "código"
    repo_hf: str
    filename: str
    tamano_gb: float
    ram_minima_gb: float
    ram_recomendada_gb: float
    licencia: str
    training_summary_url: Optional[str]
    copyright_compliant: bool
    es_sin_censura: bool
    descripcion: str


class CatalogoModelos:
    """Catálogo flexible y multirrol de modelos auditados y personalizables."""

    MODELOS: dict[str, DefinicionModeloCatalogo] = {
        # =========================================================================
        # 1. ROL CODER (PROGRAMACIÓN Y GENERACIÓN DE PARCHES)
        # =========================================================================
        "qwen2.5-coder-7b-q5": DefinicionModeloCatalogo(
            id="qwen2.5-coder-7b-q5",
            nombre_legible="Qwen2.5-Coder 7B (Q5_K_M - Alta Fidelidad)",
            categoria="coder",
            cuantizacion="Q5_K_M",
            idiomas_destacados="código, en, es",
            repo_hf="Qwen/Qwen2.5-Coder-7B-Instruct-GGUF",
            filename="qwen2.5-coder-7b-instruct-q5_k_m.gguf",
            tamano_gb=5.40,
            ram_minima_gb=10.0,
            ram_recomendada_gb=16.0,
            licencia="apache-2.0",
            training_summary_url="https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct",
            copyright_compliant=True,
            es_sin_censura=False,
            descripcion="Máxima precisión sintáctica para generación de código complejo. Recomendado con >16 GB RAM.",
        ),
        "qwen2.5-coder-7b-q4": DefinicionModeloCatalogo(
            id="qwen2.5-coder-7b-q4",
            nombre_legible="Qwen2.5-Coder 7B (Q4_K_M - Estándar Equilibrado)",
            categoria="coder",
            cuantizacion="Q4_K_M",
            idiomas_destacados="código, en, es",
            repo_hf="Qwen/Qwen2.5-Coder-7B-Instruct-GGUF",
            filename="qwen2.5-coder-7b-instruct-q4_k_m.gguf",
            tamano_gb=4.68,
            ram_minima_gb=8.0,
            ram_recomendada_gb=16.0,
            licencia="apache-2.0",
            training_summary_url="https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct",
            copyright_compliant=True,
            es_sin_censura=False,
            descripcion="Estándar óptimo de inferencia local. Soporta 32k contexto y tool calling estructurado.",
        ),
        "qwen2.5-coder-7b-q3": DefinicionModeloCatalogo(
            id="qwen2.5-coder-7b-q3",
            nombre_legible="Qwen2.5-Coder 7B (Q3_K_M - Ahorro de VRAM)",
            categoria="coder",
            cuantizacion="Q3_K_M",
            idiomas_destacados="código, en, es",
            repo_hf="Qwen/Qwen2.5-Coder-7B-Instruct-GGUF",
            filename="qwen2.5-coder-7b-instruct-q3_k_m.gguf",
            tamano_gb=3.74,
            ram_minima_gb=6.5,
            ram_recomendada_gb=12.0,
            licencia="apache-2.0",
            training_summary_url="https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct",
            copyright_compliant=True,
            es_sin_censura=False,
            descripcion="Reduce consumo de memoria para permitir contextos de 32k tokens en APUs de 16 GB.",
        ),
        "qwen2.5-coder-1.5b-q4": DefinicionModeloCatalogo(
            id="qwen2.5-coder-1.5b-q4",
            nombre_legible="Qwen2.5-Coder 1.5B (Q4_K_M - Ultraligero)",
            categoria="coder",
            cuantizacion="Q4_K_M",
            idiomas_destacados="código, en, es",
            repo_hf="Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF",
            filename="qwen2.5-coder-1.5b-instruct-q4_k_m.gguf",
            tamano_gb=1.10,
            ram_minima_gb=3.5,
            ram_recomendada_gb=8.0,
            licencia="apache-2.0",
            training_summary_url="https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct",
            copyright_compliant=True,
            es_sin_censura=False,
            descripcion="Para PCs muy modestos o tareas de autocompletado rápido sin saturar la GPU.",
        ),
        "deepseek-coder-1.3b-q4": DefinicionModeloCatalogo(
            id="deepseek-coder-1.3b-q4",
            nombre_legible="DeepSeek-Coder 1.3B (Q4_K_M)",
            categoria="coder",
            cuantizacion="Q4_K_M",
            idiomas_destacados="código, en",
            repo_hf="TheBloke/deepseek-coder-1.3b-instruct-GGUF",
            filename="deepseek-coder-1.3b-instruct.Q4_K_M.gguf",
            tamano_gb=0.87,
            ram_minima_gb=3.0,
            ram_recomendada_gb=6.0,
            licencia="deepseek-license",
            training_summary_url="https://huggingface.co/deepseek-ai/deepseek-coder-1.3b-instruct",
            copyright_compliant=True,
            es_sin_censura=False,
            descripcion="Modelo alternativo rápido para pruebas sintácticas unitarias.",
        ),

        # =========================================================================
        # 2. ROL CHAT / CONVERSACIONAL (INTERFAZ HUMANA EN ESPAÑOL Y COORDINADOR)
        # =========================================================================
        "qwen2.5-3b-chat-q4": DefinicionModeloCatalogo(
            id="qwen2.5-3b-chat-q4",
            nombre_legible="Qwen2.5 3B Chat (Q4_K_M - Coordinador Multilingüe)",
            categoria="chat",
            cuantizacion="Q4_K_M",
            idiomas_destacados="es (nativo), en, multilingüe",
            repo_hf="Qwen/Qwen2.5-3B-Instruct-GGUF",
            filename="qwen2.5-3b-instruct-q4_k_m.gguf",
            tamano_gb=2.00,
            ram_minima_gb=4.5,
            ram_recomendada_gb=8.0,
            licencia="apache-2.0",
            training_summary_url="https://huggingface.co/Qwen/Qwen2.5-3B-Instruct",
            copyright_compliant=True,
            es_sin_censura=False,
            descripcion="Ideal como agente conversacional con el usuario en español. Rápido, empático y traduce intenciones a JSON para el Coder.",
        ),
        "llama-3.2-3b-chat-q4": DefinicionModeloCatalogo(
            id="llama-3.2-3b-chat-q4",
            nombre_legible="Llama 3.2 3B Instruct (Q4_K_M)",
            categoria="chat",
            cuantizacion="Q4_K_M",
            idiomas_destacados="es, en",
            repo_hf="bartowski/Llama-3.2-3B-Instruct-GGUF",
            filename="Llama-3.2-3B-Instruct-Q4_K_M.gguf",
            tamano_gb=2.02,
            ram_minima_gb=4.5,
            ram_recomendada_gb=8.0,
            licencia="llama-3.2-license",
            training_summary_url="https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct",
            copyright_compliant=True,
            es_sin_censura=False,
            descripcion="Modelo ligero de Meta con excelente razonamiento lógico y diálogo estructurado.",
        ),

        # =========================================================================
        # 3. ROL SIN CENSURA / ABLITERATED (INVESTIGACIÓN Y CÓDIGO SIN FILTROS)
        # =========================================================================
        "qwen2.5-coder-7b-abliterated-q4": DefinicionModeloCatalogo(
            id="qwen2.5-coder-7b-abliterated-q4",
            nombre_legible="Qwen2.5-Coder 7B Abliterated (Sin Censura Q4)",
            categoria="uncensored",
            cuantizacion="Q4_K_M",
            idiomas_destacados="código, en, es",
            repo_hf="bartowski/Qwen2.5-Coder-7B-Instruct-abliterated-GGUF",
            filename="Qwen2.5-Coder-7B-Instruct-abliterated-Q4_K_M.gguf",
            tamano_gb=4.68,
            ram_minima_gb=8.0,
            ram_recomendada_gb=16.0,
            licencia="comunitaria-abliterated",
            training_summary_url=None,
            copyright_compliant=True,
            es_sin_censura=True,
            descripcion="Filtros de alineación neutralizados. Permite auditar vulnerabilidades, payloads y análisis de seguridad sin bloqueos éticos.",
        ),

        # =========================================================================
        # 4. ROL EMBEDDINGS (ÁRBOLES DE NODOS, GRAFOS AST Y MEMORIA SEMÁNTICA)
        # =========================================================================
        "bge-m3-q4": DefinicionModeloCatalogo(
            id="bge-m3-q4",
            nombre_legible="BGE-M3 (Multilingüe Español/Inglés/Código)",
            categoria="embedding",
            cuantizacion="Q4_K_M",
            idiomas_destacados="es, en, código, 100+ idiomas",
            repo_hf="CompendiumLabs/bge-m3-gguf",
            filename="bge-m3-q4_k_m.gguf",
            tamano_gb=0.35,
            ram_minima_gb=1.5,
            ram_recomendada_gb=3.0,
            licencia="mit",
            training_summary_url="https://huggingface.co/BAAI/bge-m3",
            copyright_compliant=True,
            es_sin_censura=False,
            descripcion="Estándar para indexación de árboles sintácticos y grafos de código con soporte nativo en español y 8192 contexto.",
        ),
        "nomic-embed-text-v1.5": DefinicionModeloCatalogo(
            id="nomic-embed-text-v1.5",
            nombre_legible="Nomic Embed Text v1.5 (Auditable)",
            categoria="embedding",
            cuantizacion="Q4_K_M",
            idiomas_destacados="en, código",
            repo_hf="nomic-ai/nomic-embed-text-v1.5-GGUF",
            filename="nomic-embed-text-v1.5.Q4_K_M.gguf",
            tamano_gb=0.15,
            ram_minima_gb=1.0,
            ram_recomendada_gb=2.0,
            licencia="apache-2.0",
            training_summary_url="https://huggingface.co/nomic-ai/nomic-embed-text-v1.5",
            copyright_compliant=True,
            es_sin_censura=False,
            descripcion="Modelo compacto y auditable para recuperación semántica de funciones y variables.",
        ),
    }

    @classmethod
    def listar_modelos(
        cls,
        categoria: Optional[str] = None,
        region: RegionNormativa = RegionNormativa.ES_EU,
    ) -> list[tuple[DefinicionModeloCatalogo, EvaluacionCumplimiento]]:
        resultados = []
        for mod in cls.MODELOS.values():
            if categoria and mod.categoria != categoria:
                continue

            evaluacion = GestorCumplimientoNormativo.evaluar_modelo(
                modelo_id=mod.id,
                licencia=mod.licencia,
                training_summary_url=mod.training_summary_url,
                copyright_compliant=mod.copyright_compliant,
                es_sin_censura=mod.es_sin_censura,
                region=region,
            )
            resultados.append((mod, evaluacion))
        return resultados

    @classmethod
    def obtener_modelo(cls, modelo_id: str) -> Optional[DefinicionModeloCatalogo]:
        return cls.MODELOS.get(modelo_id)

    @classmethod
    def agregar_modelo_personalizado(
        cls,
        id_unico: str,
        nombre_legible: str,
        repo_hf: str,
        filename: str,
        tamano_gb: float,
        categoria: str = "coder",
        cuantizacion: str = "Q4_K_M",
        idiomas: str = "es, en, código",
        licencia: str = "custom",
        training_summary_url: Optional[str] = None,
        es_sin_censura: bool = False,
        descripcion: str = "Modelo personalizado añadido por el usuario.",
    ) -> DefinicionModeloCatalogo:
        """Permite al usuario registrar cualquier modelo GGUF arbitrario de Hugging Face."""
        nuevo = DefinicionModeloCatalogo(
            id=id_unico,
            nombre_legible=nombre_legible,
            categoria=categoria,
            cuantizacion=cuantizacion,
            idiomas_destacados=idiomas,
            repo_hf=repo_hf.strip(),
            filename=filename.strip(),
            tamano_gb=tamano_gb,
            ram_minima_gb=round(tamano_gb * 1.5, 1),
            ram_recomendada_gb=round(tamano_gb * 2.5, 1),
            licencia=licencia,
            training_summary_url=training_summary_url,
            copyright_compliant=True,
            es_sin_censura=es_sin_censura,
            descripcion=descripcion,
        )
        cls.MODELOS[id_unico] = nuevo
        return nuevo


@dataclass
class CestaDescarga:
    """Cola de modelos seleccionados para ser descargados en lote durante la ventana de conexión."""

    modelos: list[DefinicionModeloCatalogo]

    @property
    def tamano_total_gb(self) -> float:
        return round(sum(m.tamano_gb for m in self.modelos), 2)

    def verificar_espacio_disco(self, ruta_destino: Path) -> tuple[bool, float]:
        """Comprueba si hay suficiente espacio libre en el disco de destino."""
        total, usado, libre = shutil.disk_usage(ruta_destino)
        libre_gb = libre / (1024**3)
        # Margen de seguridad del 10%
        suficiente = libre_gb >= (self.tamano_total_gb * 1.1)
        return suficiente, round(libre_gb, 2)


class DescargadorModelos:
    """Descarga modelos GGUF con reanudación, cálculo de hash y registro inmutable en SQLite."""

    def __init__(
        self,
        directorio_modelos: Optional[Path] = None,
        gestor_cache: Optional[GestorCache] = None,
    ) -> None:
        self.directorio_modelos = directorio_modelos or DIRECTORIO_MODELOS
        self.directorio_modelos.mkdir(parents=True, exist_ok=True)
        self.cache = gestor_cache or GestorCache()

    def descargar_modelo(
        self,
        modelo: DefinicionModeloCatalogo,
        region: RegionNormativa = RegionNormativa.ES_EU,
        callback_progreso: Optional[Callable[[str, float], None]] = None,
    ) -> Path:
        ruta_archivo_final = self.directorio_modelos / modelo.filename
        ruta_archivo_parcial = self.directorio_modelos / f"{modelo.filename}.part"

        def log(msg: str, pct: float = 0.0) -> None:
            if callback_progreso:
                callback_progreso(msg, pct)
            else:
                print(f"[{pct:.1f}%] {msg}")

        if ruta_archivo_final.exists() and ruta_archivo_final.stat().st_size > 0:
            log(f"El modelo ya está presente en el Búnker: {ruta_archivo_final.name}", 100.0)
            self._registrar_en_cache(modelo, str(ruta_archivo_final))
            return ruta_archivo_final

        url_hf = f"https://huggingface.co/{modelo.repo_hf}/resolve/main/{modelo.filename}"
        bytes_existentes = ruta_archivo_parcial.stat().st_size if ruta_archivo_parcial.exists() else 0

        encabezados = {"User-Agent": "GuarIdA-Bunker-Downloader/1.0"}
        modo_apertura = "wb"

        if bytes_existentes > 0:
            encabezados["Range"] = f"bytes={bytes_existentes}-"
            modo_apertura = "ab"
            log(f"Reanudando descarga de {modelo.filename} desde {bytes_existentes / (1024**2):.1f} MB...", 0.0)
        else:
            log(f"Iniciando descarga de {modelo.filename} ({modelo.tamano_gb:.2f} GB)...", 0.0)

        peticion = urllib.request.Request(url_hf, headers=encabezados)

        try:
            with urllib.request.urlopen(peticion, timeout=30) as respuesta:
                longitud_contenido = respuesta.headers.get("Content-Length")
                tamano_total = (int(longitud_contenido) + bytes_existentes) if longitud_contenido else None

                descargado = bytes_existentes
                chunk_size = 128 * 1024
                sha256_hasher = hashlib.sha256()

                with open(ruta_archivo_parcial, modo_apertura) as f_out:
                    while True:
                        fragmento = respuesta.read(chunk_size)
                        if not fragmento:
                            break
                        f_out.write(fragmento)
                        sha256_hasher.update(fragmento)
                        descargado += len(fragmento)

                        if tamano_total:
                            porcentaje = (descargado / tamano_total) * 100.0
                            log(
                                f"Descargando: {descargado / (1024**3):.2f} GB / {tamano_total / (1024**3):.2f} GB",
                                porcentaje,
                            )

            if ruta_archivo_final.exists():
                os.remove(ruta_archivo_final)
            ruta_archivo_parcial.rename(ruta_archivo_final)

            log(f"Modelo {modelo.filename} verificado e integrado.", 100.0)
            self._registrar_en_cache(modelo, str(ruta_archivo_final))
            return ruta_archivo_final

        except Exception as e:
            log(f"Interrupción en la descarga de {modelo.filename}: {e}", 0.0)
            raise

    def descargar_cesta(
        self,
        cesta: CestaDescarga,
        region: RegionNormativa = RegionNormativa.ES_EU,
        callback_progreso: Optional[Callable[[str, float], None]] = None,
    ) -> list[Path]:
        """Descarga todos los modelos de la cesta informando del avance global."""
        rutas_descargadas = []
        total_modelos = len(cesta.modelos)

        for i, mod in enumerate(cesta.modelos, 1):
            if callback_progreso:
                callback_progreso(f"\n[Lote {i}/{total_modelos}] Procesando {mod.nombre_legible}...", 0.0)

            ruta = self.descargar_modelo(
                modelo=mod,
                region=region,
                callback_progreso=callback_progreso,
            )
            rutas_descargadas.append(ruta)

        return rutas_descargadas

    def archivar_modelo_sin_archivo(self, modelo_id: str) -> bool:
        """Elimina el archivo .gguf para liberar espacio en disco manteniendo el registro en SQLite."""
        modelo_dict = self.cache.obtener_modelo(modelo_id)
        if not modelo_dict:
            return False

        ruta_local = modelo_dict.get("ruta_local")
        if ruta_local and Path(ruta_local).exists():
            try:
                os.remove(Path(ruta_local))
            except Exception:
                pass

        # Preservar automáticamente el mejor benchmark en la tabla de configuraciones óptimas si no existe
        benchmarks = self.cache.listar_benchmarks_por_modelo(modelo_id)
        if benchmarks:
            mejor_b = benchmarks[0]
            config_existente = self.cache.obtener_configuracion_optima(modelo_id, mejor_b["hash_hardware"])
            if not config_existente:
                self.cache.guardar_configuracion_optima(
                    ConfiguracionOptimaRegistro(
                        modelo_id=modelo_id,
                        hash_hardware=mejor_b["hash_hardware"],
                        n_gpu_layers=mejor_b["n_gpu_layers"],
                        ctx_size=mejor_b["ctx_size"],
                        batch_size=512,
                        kv_cache_tipo="q4_0",
                        tok_s_medido=mejor_b["tok_s"],
                        gtt_pico_mb=mejor_b["gtt_pico_mb"],
                        fecha_afinamiento=datetime.now(timezone.utc).isoformat(),
                        motivo_descarte_o_nota=f"Afinamiento preservado al archivar: {mejor_b['tok_s']} t/s con {mejor_b['n_gpu_layers']} capas GPU",
                        es_recomendada=True,
                    )
                )

        registro_actualizado = ModeloRegistro(
            id=modelo_dict["id"],
            repo_hf=modelo_dict["repo_hf"],
            filename=modelo_dict["filename"],
            ruta_local="",
            estado="archivado_sin_archivo",
            motivo_descarte=modelo_dict.get("motivo_descarte"),
            license=modelo_dict.get("license"),
            training_summary_url=modelo_dict.get("training_summary_url"),
        )
        self.cache.guardar_modelo(registro_actualizado)
        return True

    def consultar_afinamiento_guardado(
        self, modelo_id: str, hash_hardware: str
    ) -> Optional[dict[str, Any]]:
        """Recupera la mejor configuración afinada guardada en el histórico para este hardware."""
        return self.cache.obtener_configuracion_optima(modelo_id, hash_hardware)

    def _registrar_en_cache(self, modelo: DefinicionModeloCatalogo, ruta_local: str) -> None:
        registro = ModeloRegistro(
            id=modelo.id,
            repo_hf=modelo.repo_hf,
            filename=modelo.filename,
            ruta_local=ruta_local,
            estado="descargado",
            motivo_descarte=None,
            license=modelo.licencia,
            training_summary_url=modelo.training_summary_url,
        )
        self.cache.guardar_modelo(registro)
