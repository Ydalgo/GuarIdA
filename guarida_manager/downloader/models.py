import hashlib
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from guarida_manager import DIRECTORIO_MODELOS
from guarida_manager.cache import GestorCache, ModeloRegistro
from guarida_manager.downloader.compliance import (
    EvaluacionCumplimiento,
    GestorCumplimientoNormativo,
    RegionNormativa,
)


@dataclass(frozen=True)
class DefinicionModeloCatalogo:
    id: str
    categoria: str                 # "coder", "embedding", "general"
    repo_hf: str
    filename: str
    tamano_gb: float
    ram_minima_gb: float
    ram_recomendada_gb: float
    licencia: str
    training_summary_url: str
    copyright_compliant: bool
    descripcion: str


class CatalogoModelos:
    """Catálogo centralizado de modelos preconfigurados y auditados para GuarIdA."""

    MODELOS: dict[str, DefinicionModeloCatalogo] = {
        # --- MODELOS DE PROGRAMACIÓN (Fase 1: Agente Coder) ---
        "qwen2.5-coder-7b-q4": DefinicionModeloCatalogo(
            id="qwen2.5-coder-7b-q4",
            categoria="coder",
            repo_hf="Qwen/Qwen2.5-Coder-7B-Instruct-GGUF",
            filename="qwen2.5-coder-7b-instruct-q4_k_m.gguf",
            tamano_gb=4.68,
            ram_minima_gb=8.0,
            ram_recomendada_gb=16.0,
            licencia="apache-2.0",
            training_summary_url="https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct",
            copyright_compliant=True,
            descripcion="Modelo insignia para programación. Soporta contexto 32k, tool calling estructurado y parches diff precisos.",
        ),
        "qwen2.5-coder-1.5b-q4": DefinicionModeloCatalogo(
            id="qwen2.5-coder-1.5b-q4",
            categoria="coder",
            repo_hf="Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF",
            filename="qwen2.5-coder-1.5b-instruct-q4_k_m.gguf",
            tamano_gb=1.10,
            ram_minima_gb=3.5,
            ram_recomendada_gb=8.0,
            licencia="apache-2.0",
            training_summary_url="https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct",
            copyright_compliant=True,
            descripcion="Modelo ultraligero de programación de alto rendimiento para equipos de hardware muy modesto.",
        ),
        "deepseek-coder-1.3b-q4": DefinicionModeloCatalogo(
            id="deepseek-coder-1.3b-q4",
            categoria="coder",
            repo_hf="TheBloke/deepseek-coder-1.3b-instruct-GGUF",
            filename="deepseek-coder-1.3b-instruct.Q4_K_M.gguf",
            tamano_gb=0.87,
            ram_minima_gb=3.0,
            ram_recomendada_gb=6.0,
            licencia="deepseek-license",
            training_summary_url="https://huggingface.co/deepseek-ai/deepseek-coder-1.3b-instruct",
            copyright_compliant=True,
            descripcion="Modelo compacto optimizado para autocompletado y análisis sintáctico rápido de código.",
        ),
        # --- MODELOS DE EMBEDDINGS (Árboles de nodos, bucles iterativos y memoria semántica) ---
        "nomic-embed-text-v1.5": DefinicionModeloCatalogo(
            id="nomic-embed-text-v1.5",
            categoria="embedding",
            repo_hf="nomic-ai/nomic-embed-text-v1.5-GGUF",
            filename="nomic-embed-text-v1.5.Q4_K_M.gguf",
            tamano_gb=0.15,
            ram_minima_gb=1.0,
            ram_recomendada_gb=2.0,
            licencia="apache-2.0",
            training_summary_url="https://huggingface.co/nomic-ai/nomic-embed-text-v1.5",
            copyright_compliant=True,
            descripcion="Vectorizador de texto con contexto 8192. Indispensable para navegación de grafos AST y árboles de nodos.",
        ),
        "bge-small-en-v1.5": DefinicionModeloCatalogo(
            id="bge-small-en-v1.5",
            categoria="embedding",
            repo_hf="CompendiumLabs/bge-small-en-v1.5-gguf",
            filename="bge-small-en-v1.5-q4_k_m.gguf",
            tamano_gb=0.05,
            ram_minima_gb=0.5,
            ram_recomendada_gb=1.0,
            licencia="mit",
            training_summary_url="https://huggingface.co/BAAI/bge-small-en-v1.5",
            copyright_compliant=True,
            descripcion="Embeddings ultracompactos (45 MB) para recuperación semántica veloz en bucles iterativos.",
        ),
        # --- MODELOS GENERALISTAS (Extensión futura) ---
        "qwen2.5-7b-instruct-q4": DefinicionModeloCatalogo(
            id="qwen2.5-7b-instruct-q4",
            categoria="general",
            repo_hf="Qwen/Qwen2.5-7B-Instruct-GGUF",
            filename="qwen2.5-7b-instruct-q4_k_m.gguf",
            tamano_gb=4.68,
            ram_minima_gb=8.0,
            ram_recomendada_gb=16.0,
            licencia="apache-2.0",
            training_summary_url="https://huggingface.co/Qwen/Qwen2.5-7B-Instruct",
            copyright_compliant=True,
            descripcion="Modelo conversacional y de razonamiento general para tareas no restringidas a código.",
        ),
    }

    @classmethod
    def listar_modelos(
        cls,
        categoria: Optional[str] = None,
        region: RegionNormativa = RegionNormativa.ES_EU,
    ) -> list[tuple[DefinicionModeloCatalogo, EvaluacionCumplimiento]]:
        """Devuelve los modelos disponibles junto a su auditoría legal para la región."""
        resultados = []
        for mod in cls.MODELOS.values():
            if categoria and mod.categoria != categoria:
                continue

            evaluacion = GestorCumplimientoNormativo.evaluar_modelo(
                modelo_id=mod.id,
                licencia=mod.licencia,
                training_summary_url=mod.training_summary_url,
                copyright_compliant=mod.copyright_compliant,
                region=region,
            )
            resultados.append((mod, evaluacion))
        return resultados

    @classmethod
    def obtener_modelo(cls, modelo_id: str) -> Optional[DefinicionModeloCatalogo]:
        return cls.MODELOS.get(modelo_id)


class DescargadorModelos:
    """Descarga modelos GGUF con reanudación, cálculo de hash y registro inmutable en SQLite."""

    def __init__(self, directorio_modelos: Optional[Path] = None) -> None:
        self.directorio_modelos = directorio_modelos or DIRECTORIO_MODELOS
        self.directorio_modelos.mkdir(parents=True, exist_ok=True)
        self.cache = GestorCache()

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

        # Comprobar si ya existe completo
        if ruta_archivo_final.exists() and ruta_archivo_final.stat().st_size > 0:
            log(f"El modelo ya está presente en el almacenamiento local: {ruta_archivo_final}", 100.0)
            self._registrar_en_cache(modelo, str(ruta_archivo_final))
            return ruta_archivo_final

        url_hf = f"https://huggingface.co/{modelo.repo_hf}/resolve/main/{modelo.filename}"
        bytes_existentes = ruta_archivo_parcial.stat().st_size if ruta_archivo_parcial.exists() else 0

        encabezados = {"User-Agent": "GuarIdA-Bunker-Downloader/1.0"}
        modo_apertura = "wb"

        if bytes_existentes > 0:
            encabezados["Range"] = f"bytes={bytes_existentes}-"
            modo_apertura = "ab"
            log(f"Reanudando descarga previa desde {bytes_existentes / (1024**2):.1f} MB...", 0.0)
        else:
            log(f"Iniciando descarga de {modelo.filename} desde Hugging Face...", 0.0)

        peticion = urllib.request.Request(url_hf, headers=encabezados)

        try:
            with urllib.request.urlopen(peticion, timeout=30) as respuesta:
                longitud_contenido = respuesta.headers.get("Content-Length")
                tamano_total = (int(longitud_contenido) + bytes_existentes) if longitud_contenido else None

                descargado = bytes_existentes
                chunk_size = 128 * 1024  # Chunks de 128 KB
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
                        else:
                            log(f"Descargando: {descargado / (1024**2):.1f} MB", 0.0)

            # Mover a la ruta final
            if ruta_archivo_final.exists():
                os.remove(ruta_archivo_final)
            ruta_archivo_parcial.rename(ruta_archivo_final)

            log("Descarga completada e integrada en el Búnker.", 100.0)
            self._registrar_en_cache(modelo, str(ruta_archivo_final))
            return ruta_archivo_final

        except Exception as e:
            log(f"Error o interrupción durante la descarga: {e}", 0.0)
            raise

    def archivar_modelo_sin_archivo(self, modelo_id: str) -> bool:
        """Elimina el archivo .gguf para liberar espacio en disco manteniendo el registro en SQLite.

        Conserva intactas las métricas de benchmarks, capas óptimas y motivos de descarte.
        """
        modelo_dict = self.cache.obtener_modelo(modelo_id)
        if not modelo_dict:
            return False

        ruta_local = modelo_dict.get("ruta_local")
        if ruta_local and Path(ruta_local).exists():
            try:
                os.remove(Path(ruta_local))
            except Exception:
                pass

        # Actualizar en la base de datos a estado 'archivado_sin_archivo' manteniendo sus métricas
        registro_actualizado = ModeloRegistro(
            id=modelo_dict["id"],
            repo_hf=modelo_dict["repo_hf"],
            filename=modelo_dict["filename"],
            ruta_local="",  # Se vacía la ruta para reflejar que no ocupa disco
            estado="archivado_sin_archivo",
            motivo_descarte=modelo_dict.get("motivo_descarte"),
            license=modelo_dict.get("license"),
            training_summary_url=modelo_dict.get("training_summary_url"),
        )
        self.cache.guardar_modelo(registro_actualizado)
        return True

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
