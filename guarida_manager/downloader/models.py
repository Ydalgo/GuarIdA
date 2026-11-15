import hmac
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

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
from guarida_manager.downloader.core import DescargadorSeguro, calcular_sha256_archivo


def validar_repo_hf(repo: str) -> str:
    """Valida y sanea el identificador del repositorio de Hugging Face."""
    repo = repo.strip()
    partes = repo.split("/")
    if len(partes) != 2 or not partes[0] or not partes[1]:
        raise ValueError(
            f"Identificador de repositorio Hugging Face inválido: '{repo}'. Formato requerido: 'usuario_u_org/nombre_repo'"
        )
    for parte in partes:
        if not re.match(r"^[a-zA-Z0-9_\-\.]+$", parte) or ".." in parte:
            raise ValueError(f"Caracteres no permitidos o path traversal en repositorio Hugging Face: '{repo}'")
    return repo


def validar_filename_hf(filename: str) -> str:
    """Valida y sanea el nombre de archivo del modelo GGUF o Safetensors evitando path traversal."""
    filename = filename.strip()
    if "/" in filename or "\\" in filename or ".." in filename or Path(filename).name != filename:
        raise ValueError(f"Ruta o nombre de archivo sospechoso (intento de path traversal): '{filename}'")
    if not re.match(r"^[a-zA-Z0-9_\-\.]+\.(gguf|safetensors|bin|pt)$", filename, re.IGNORECASE):
        raise ValueError(
            f"Nombre de archivo de modelo no válido. Debe tener extensión .gguf, .safetensors, .bin o .pt: '{filename}'"
        )
    return filename


def validar_revision_hf(revision: Optional[str]) -> str:
    """Valida la revisión, rama o commit SHA de Hugging Face."""
    if not revision or not revision.strip():
        return "main"
    rev = revision.strip()
    if "/" in rev or "\\" in rev or ".." in rev or not re.match(r"^[a-zA-Z0-9_\-\.]+$", rev):
        raise ValueError(f"Identificador de revisión no válido: '{rev}'")
    return rev


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
    sha256_esperado: Optional[str] = None
    revision: str = "main"
    formato: str = "gguf"  # "gguf", "safetensors", "pytorch"


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
        "qwen2.5-coder-0.5b-q4": DefinicionModeloCatalogo(
            id="qwen2.5-coder-0.5b-q4",
            nombre_legible="Qwen2.5-Coder 0.5B (Q4_K_M - Ultraligero CPU)",
            categoria="coder",
            cuantizacion="Q4_K_M",
            idiomas_destacados="código, es, en",
            repo_hf="Qwen/Qwen2.5-Coder-0.5B-Instruct-GGUF",
            filename="qwen2.5-coder-0.5b-instruct-q4_k_m.gguf",
            tamano_gb=0.39,
            ram_minima_gb=1.5,
            ram_recomendada_gb=3.0,
            licencia="apache-2.0",
            training_summary_url="https://huggingface.co/Qwen/Qwen2.5-Coder-0.5B-Instruct",
            copyright_compliant=True,
            es_sin_censura=False,
            descripcion="Modelo de código ultracompacto para hardware muy modesto o ejecución ultra-rápida en CPU.",
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
        "qwen2.5-coder-3b-q4": DefinicionModeloCatalogo(
            id="qwen2.5-coder-3b-q4",
            nombre_legible="Qwen2.5-Coder 3B (Q4_K_M - Paso Intermedio)",
            categoria="coder",
            cuantizacion="Q4_K_M",
            idiomas_destacados="código, es, en",
            repo_hf="Qwen/Qwen2.5-Coder-3B-Instruct-GGUF",
            filename="qwen2.5-coder-3b-instruct-q4_k_m.gguf",
            tamano_gb=1.95,
            ram_minima_gb=4.5,
            ram_recomendada_gb=8.0,
            licencia="apache-2.0",
            training_summary_url="https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct",
            copyright_compliant=True,
            es_sin_censura=False,
            descripcion="Excelente equilibrio intermedio entre 1.5B y 7B para portátiles con memoria moderada.",
        ),
        "qwen3-8b-q4": DefinicionModeloCatalogo(
            id="qwen3-8b-q4",
            nombre_legible="Qwen3 8B (Q4_K_M - Generación Código y Razonamiento)",
            categoria="coder",
            cuantizacion="Q4_K_M",
            idiomas_destacados="código, es, en",
            repo_hf="Qwen/Qwen3-8B-GGUF",
            filename="Qwen3-8B-Q4_K_M.gguf",
            tamano_gb=5.03,
            ram_minima_gb=8.5,
            ram_recomendada_gb=16.0,
            licencia="apache-2.0",
            training_summary_url="https://huggingface.co/Qwen/Qwen3-8B",
            copyright_compliant=True,
            es_sin_censura=False,
            descripcion="Arquitectura Qwen3 de última generación para código, AST y resolución algorítmica.",
        ),
        "qwen3-4b-q4": DefinicionModeloCatalogo(
            id="qwen3-4b-q4",
            nombre_legible="Qwen3 4B (Q4_K_M - Punto Dulce iGPU Intel/AMD)",
            categoria="coder",
            cuantizacion="Q4_K_M",
            idiomas_destacados="código, es, en",
            repo_hf="Qwen/Qwen3-4B-GGUF",
            filename="Qwen3-4B-Q4_K_M.gguf",
            tamano_gb=2.50,
            ram_minima_gb=5.0,
            ram_recomendada_gb=8.0,
            licencia="apache-2.0",
            training_summary_url="https://huggingface.co/Qwen/Qwen3-4B",
            copyright_compliant=True,
            es_sin_censura=False,
            descripcion="Equilibrio ideal velocidad/calidad para gráficas integradas (Iris Xe / Radeon) con contexto amplio.",
        ),
        "qwen3-30b-a3b-q4": DefinicionModeloCatalogo(
            id="qwen3-30b-a3b-q4",
            nombre_legible="Qwen3-30B-A3B MoE (Q4_K_M - 3B Activos con --n-cpu-moe)",
            categoria="coder",
            cuantizacion="Q4_K_M",
            idiomas_destacados="código, es, en",
            repo_hf="Qwen/Qwen3-30B-A3B-GGUF",
            filename="Qwen3-30B-A3B-Q4_K_M.gguf",
            tamano_gb=17.30,
            ram_minima_gb=20.0,
            ram_recomendada_gb=32.0,
            licencia="apache-2.0",
            training_summary_url="https://huggingface.co/Qwen/Qwen3-30B-A3B",
            copyright_compliant=True,
            es_sin_censura=False,
            descripcion="Modelo MoE de 30B que solo activa 3B por token; permite descargar expertos a RAM con --n-cpu-moe.",
        ),
        "qwen2.5-coder-14b-q4": DefinicionModeloCatalogo(
            id="qwen2.5-coder-14b-q4",
            nombre_legible="Qwen2.5-Coder 14B (Q4_K_M - Alta Capacidad y Refactorización)",
            categoria="coder",
            cuantizacion="Q4_K_M",
            idiomas_destacados="código, es, en",
            repo_hf="Qwen/Qwen2.5-Coder-14B-Instruct-GGUF",
            filename="qwen2.5-coder-14b-instruct-q4_k_m.gguf",
            tamano_gb=8.99,
            ram_minima_gb=14.0,
            ram_recomendada_gb=24.0,
            licencia="apache-2.0",
            training_summary_url="https://huggingface.co/Qwen/Qwen2.5-Coder-14B-Instruct",
            copyright_compliant=True,
            es_sin_censura=False,
            descripcion="Rendimiento excepcional en código complejo, arquitectura multi-archivo y refactorizaciones.",
        ),
        "qwen2.5-coder-32b-q4": DefinicionModeloCatalogo(
            id="qwen2.5-coder-32b-q4",
            nombre_legible="Qwen2.5-Coder 32B (Q4_K_M - Buque Insignia Código)",
            categoria="coder",
            cuantizacion="Q4_K_M",
            idiomas_destacados="código, es, en",
            repo_hf="Qwen/Qwen2.5-Coder-32B-Instruct-GGUF",
            filename="qwen2.5-coder-32b-instruct-q4_k_m.gguf",
            tamano_gb=19.85,
            ram_minima_gb=24.0,
            ram_recomendada_gb=36.0,
            licencia="apache-2.0",
            training_summary_url="https://huggingface.co/Qwen/Qwen2.5-Coder-32B-Instruct",
            copyright_compliant=True,
            es_sin_censura=False,
            descripcion="Modelo insignia de programación con nivel competitivo frente a modelos cerrados punteros.",
        ),
        "deepseek-r1-distill-qwen-7b-q4": DefinicionModeloCatalogo(
            id="deepseek-r1-distill-qwen-7b-q4",
            nombre_legible="DeepSeek-R1 Distill Qwen 7B (Q4_K_M - Razonamiento 7B)",
            categoria="coder",
            cuantizacion="Q4_K_M",
            idiomas_destacados="código, razonamiento, es, en",
            repo_hf="bartowski/DeepSeek-R1-Distill-Qwen-7B-GGUF",
            filename="DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf",
            tamano_gb=4.68,
            ram_minima_gb=8.0,
            ram_recomendada_gb=16.0,
            licencia="mit",
            training_summary_url="https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
            copyright_compliant=True,
            es_sin_censura=False,
            descripcion="Modelo de razonamiento 7B con cadena de pensamiento para lógica algorítmica profunda.",
        ),
        "deepseek-r1-distill-qwen-14b-q4": DefinicionModeloCatalogo(
            id="deepseek-r1-distill-qwen-14b-q4",
            nombre_legible="DeepSeek-R1 Distill Qwen 14B (Q4_K_M - Razonamiento Puro 14B)",
            categoria="coder",
            cuantizacion="Q4_K_M",
            idiomas_destacados="código, razonamiento, es, en",
            repo_hf="bartowski/DeepSeek-R1-Distill-Qwen-14B-GGUF",
            filename="DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf",
            tamano_gb=8.98,
            ram_minima_gb=14.0,
            ram_recomendada_gb=24.0,
            licencia="mit",
            training_summary_url="https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Qwen-14B",
            copyright_compliant=True,
            es_sin_censura=False,
            descripcion="Destilación de DeepSeek-R1 para razonamiento exhaustivo, matemáticas y depuración compleja.",
        ),
        "codestral-22b-q4": DefinicionModeloCatalogo(
            id="codestral-22b-q4",
            nombre_legible="Codestral 22B (Q4_K_M - Ventana 32k Mistral)",
            categoria="coder",
            cuantizacion="Q4_K_M",
            idiomas_destacados="código, 80+ lenguajes, es, en",
            repo_hf="bartowski/Codestral-22B-v0.1-GGUF",
            filename="Codestral-22B-v0.1-Q4_K_M.gguf",
            tamano_gb=13.50,
            ram_minima_gb=18.0,
            ram_recomendada_gb=32.0,
            licencia="mnpl",
            training_summary_url="https://huggingface.co/mistralai/Codestral-22B-v0.1",
            copyright_compliant=True,
            es_sin_censura=False,
            descripcion="Modelo de Mistral especializado en programación con soporte nativo de fill-in-the-middle y 32k contexto.",
        ),
        "qwen2.5-coder-32b-q8": DefinicionModeloCatalogo(
            id="qwen2.5-coder-32b-q8",
            nombre_legible="Qwen2.5-Coder 32B (Q8_0 - Máxima Precisión Coder)",
            categoria="coder",
            cuantizacion="Q8_0",
            idiomas_destacados="código, es, en",
            repo_hf="Qwen/Qwen2.5-Coder-32B-Instruct-GGUF",
            filename="qwen2.5-coder-32b-instruct-q8_0.gguf",
            tamano_gb=34.50,
            ram_minima_gb=40.0,
            ram_recomendada_gb=64.0,
            licencia="apache-2.0",
            training_summary_url="https://huggingface.co/Qwen/Qwen2.5-Coder-32B-Instruct",
            copyright_compliant=True,
            es_sin_censura=False,
            descripcion="Insignia Coder sin pérdida de cuantización. Ideal para GPUs de 48-64 GB VRAM.",
        ),
        "llama-3.3-70b-instruct-q4": DefinicionModeloCatalogo(
            id="llama-3.3-70b-instruct-q4",
            nombre_legible="Llama 3.3 70B Instruct (Q4_K_M - Nivel Flagship)",
            categoria="coder",
            cuantizacion="Q4_K_M",
            idiomas_destacados="código, es, en, multilingüe",
            repo_hf="bartowski/Llama-3.3-70B-Instruct-GGUF",
            filename="Llama-3.3-70B-Instruct-Q4_K_M.gguf",
            tamano_gb=42.50,
            ram_minima_gb=48.0,
            ram_recomendada_gb=64.0,
            licencia="llama-3.3-license",
            training_summary_url="https://huggingface.co/meta-llama/Llama-3.3-70B-Instruct",
            copyright_compliant=True,
            es_sin_censura=False,
            descripcion="Modelo de 70B de Meta con rendimiento comparable a GPT-4. Óptimo para VRAM >=48 GB.",
        ),
        "qwen2.5-72b-instruct-q4": DefinicionModeloCatalogo(
            id="qwen2.5-72b-instruct-q4",
            nombre_legible="Qwen2.5 72B Instruct (Q4_K_M - Titán Open Source)",
            categoria="coder",
            cuantizacion="Q4_K_M",
            idiomas_destacados="código, es, en, 29+ idiomas",
            repo_hf="Qwen/Qwen2.5-72B-Instruct-GGUF",
            filename="qwen2.5-72b-instruct-q4_k_m.gguf",
            tamano_gb=43.50,
            ram_minima_gb=50.0,
            ram_recomendada_gb=64.0,
            licencia="qwen-license",
            training_summary_url="https://huggingface.co/Qwen/Qwen2.5-72B-Instruct",
            copyright_compliant=True,
            es_sin_censura=False,
            descripcion="Capacidad de razonamiento y generación de arquitectura de software a gran escala (VRAM >=48 GB).",
        ),
        "deepseek-r1-distill-llama-70b-q4": DefinicionModeloCatalogo(
            id="deepseek-r1-distill-llama-70b-q4",
            nombre_legible="DeepSeek-R1 Distill Llama 70B (Q4_K_M - Razonamiento 70B)",
            categoria="coder",
            cuantizacion="Q4_K_M",
            idiomas_destacados="código, razonamiento matemático, es, en",
            repo_hf="bartowski/DeepSeek-R1-Distill-Llama-70B-GGUF",
            filename="DeepSeek-R1-Distill-Llama-70B-Q4_K_M.gguf",
            tamano_gb=42.50,
            ram_minima_gb=48.0,
            ram_recomendada_gb=64.0,
            licencia="mit",
            training_summary_url="https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Llama-70B",
            copyright_compliant=True,
            es_sin_censura=False,
            descripcion="Razonamiento CoT de frontera sobre arquitectura Llama 70B para problemas algorítmicos complejos.",
        ),
        "qwen2.5-72b-instruct-q8": DefinicionModeloCatalogo(
            id="qwen2.5-72b-instruct-q8",
            nombre_legible="Qwen2.5 72B Instruct (Q8_0 - Monstruo 128 GB VRAM)",
            categoria="coder",
            cuantizacion="Q8_0",
            idiomas_destacados="código, es, en, multilingüe",
            repo_hf="Qwen/Qwen2.5-72B-Instruct-GGUF",
            filename="qwen2.5-72b-instruct-q8_0.gguf",
            tamano_gb=77.00,
            ram_minima_gb=85.0,
            ram_recomendada_gb=128.0,
            licencia="qwen-license",
            training_summary_url="https://huggingface.co/Qwen/Qwen2.5-72B-Instruct",
            copyright_compliant=True,
            es_sin_censura=False,
            descripcion="Máxima fidelidad FP8 para equipos con 96-128 GB VRAM (Mac Ultra, dual A100/H100 o multi-GPU).",
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
        "llama-3.2-1b-chat-q4": DefinicionModeloCatalogo(
            id="llama-3.2-1b-chat-q4",
            nombre_legible="Llama 3.2 1B Instruct (Q4_K_M - Meta Ligero)",
            categoria="chat",
            cuantizacion="Q4_K_M",
            idiomas_destacados="es, en",
            repo_hf="bartowski/Llama-3.2-1B-Instruct-GGUF",
            filename="Llama-3.2-1B-Instruct-Q4_K_M.gguf",
            tamano_gb=0.80,
            ram_minima_gb=2.0,
            ram_recomendada_gb=4.0,
            licencia="llama-3.2-license",
            training_summary_url="https://huggingface.co/meta-llama/Llama-3.2-1B-Instruct",
            copyright_compliant=True,
            es_sin_censura=False,
            descripcion="Modelo conversacional ultracompacto de Meta para bajo consumo de memoria.",
        ),
        "qwen2.5-0.5b-chat-q4": DefinicionModeloCatalogo(
            id="qwen2.5-0.5b-chat-q4",
            nombre_legible="Qwen2.5 0.5B Chat (Q4_K_M - Asistente Ultraligero)",
            categoria="chat",
            cuantizacion="Q4_K_M",
            idiomas_destacados="es, en, multilingüe",
            repo_hf="Qwen/Qwen2.5-0.5B-Instruct-GGUF",
            filename="qwen2.5-0.5b-instruct-q4_k_m.gguf",
            tamano_gb=0.39,
            ram_minima_gb=1.5,
            ram_recomendada_gb=3.0,
            licencia="apache-2.0",
            training_summary_url="https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct",
            copyright_compliant=True,
            es_sin_censura=False,
            descripcion="Asistente ultraligero con excelente entendimiento de español y consumo inferior a 400 MB.",
        ),
        "smollm2-360m-instruct-q8": DefinicionModeloCatalogo(
            id="smollm2-360m-instruct-q8",
            nombre_legible="SmolLM2 360M Instruct (Q8_0 - Micro Agente)",
            categoria="chat",
            cuantizacion="Q8_0",
            idiomas_destacados="es, en",
            repo_hf="HuggingFaceTB/SmolLM2-360M-Instruct-GGUF",
            filename="smollm2-360m-instruct-q8_0.gguf",
            tamano_gb=0.38,
            ram_minima_gb=1.0,
            ram_recomendada_gb=2.0,
            licencia="apache-2.0",
            training_summary_url="https://huggingface.co/HuggingFaceTB/SmolLM2-360M-Instruct",
            copyright_compliant=True,
            es_sin_censura=False,
            descripcion="Micro-modelo de HuggingFace optimizado para interacciones locales inmediatas con CPU modesta.",
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
            repo_hf="gpustack/bge-m3-GGUF",
            filename="bge-m3-Q4_K_M.gguf",
            tamano_gb=0.42,
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
        "jina-embeddings-v2-code-q4": DefinicionModeloCatalogo(
            id="jina-embeddings-v2-code-q4",
            nombre_legible="Jina Embeddings v2 Code (Especializado AST / Código)",
            categoria="embedding",
            cuantizacion="Q4_K_M",
            idiomas_destacados="en, python, js, ts, c++, rust, 30+ lenguajes",
            repo_hf="second-state/jina-embeddings-v2-base-code-GGUF",
            filename="jina-embeddings-v2-base-code-Q4_K_M.gguf",
            tamano_gb=0.10,
            ram_minima_gb=1.0,
            ram_recomendada_gb=1.5,
            licencia="apache-2.0",
            training_summary_url="https://huggingface.co/jinaai/jina-embeddings-v2-base-code",
            copyright_compliant=True,
            es_sin_censura=False,
            descripcion="Entrenado específicamente sobre repositorios de código y árboles sintácticos (8192 ctx, 768 dims).",
        ),
        "snowflake-arctic-embed-m-q4": DefinicionModeloCatalogo(
            id="snowflake-arctic-embed-m-q4",
            nombre_legible="Snowflake Arctic Embed M (Alta Precisión Técnica)",
            categoria="embedding",
            cuantizacion="Q4_K_M",
            idiomas_destacados="en, código técnico",
            repo_hf="mradermacher/snowflake-arctic-embed-m-GGUF",
            filename="snowflake-arctic-embed-m.Q4_K_M.gguf",
            tamano_gb=0.08,
            ram_minima_gb=0.8,
            ram_recomendada_gb=1.5,
            licencia="apache-2.0",
            training_summary_url="https://huggingface.co/Snowflake/snowflake-arctic-embed-m",
            copyright_compliant=True,
            es_sin_censura=False,
            descripcion="Recuperación semántica ultrarrápida de alta precisión para consultas técnicas (768 dims).",
        ),
        "all-minilm-l6-v2-q8": DefinicionModeloCatalogo(
            id="all-minilm-l6-v2-q8",
            nombre_legible="All-MiniLM-L6-v2 Q8 (Ultraligero CPU/iGPU)",
            categoria="embedding",
            cuantizacion="Q8_0",
            idiomas_destacados="en, código",
            repo_hf="second-state/All-MiniLM-L6-v2-Embedding-GGUF",
            filename="all-MiniLM-L6-v2-ggml-model-q8_0.gguf",
            tamano_gb=0.04,
            ram_minima_gb=0.5,
            ram_recomendada_gb=1.0,
            licencia="apache-2.0",
            training_summary_url="https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2",
            copyright_compliant=True,
            es_sin_censura=False,
            descripcion="Vectorizador ultraligero (40 MB, 384 dims) para hardware modesto con >100 emb/s en CPU.",
            formato="gguf",
        ),

        # =========================================================================
        # 5. MODELOS CON TENSORES Y PESOS NATIVOS (SAFETENSORS / PYTORCH)
        # =========================================================================
        "smollm2-135m-safetensors": DefinicionModeloCatalogo(
            id="smollm2-135m-safetensors",
            nombre_legible="SmolLM2 135M (Pesos Safetensors Nativo)",
            categoria="chat",
            cuantizacion="FP16/BF16",
            idiomas_destacados="es, en",
            repo_hf="HuggingFaceTB/SmolLM2-135M-Instruct",
            filename="model.safetensors",
            tamano_gb=0.27,
            ram_minima_gb=1.0,
            ram_recomendada_gb=2.0,
            licencia="apache-2.0",
            training_summary_url="https://huggingface.co/HuggingFaceTB/SmolLM2-135M-Instruct",
            copyright_compliant=True,
            es_sin_censura=False,
            descripcion="Tensores y pesos originales Safetensors ejecutables con transformers/torch.",
            formato="safetensors",
        ),
        "qwen2.5-0.5b-safetensors": DefinicionModeloCatalogo(
            id="qwen2.5-0.5b-safetensors",
            nombre_legible="Qwen2.5 0.5B Instruct (Safetensors Nativo)",
            categoria="chat",
            cuantizacion="FP16/BF16",
            idiomas_destacados="es, en, multilingüe",
            repo_hf="Qwen/Qwen2.5-0.5B-Instruct",
            filename="model.safetensors",
            tamano_gb=0.98,
            ram_minima_gb=2.0,
            ram_recomendada_gb=4.0,
            licencia="apache-2.0",
            training_summary_url="https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct",
            copyright_compliant=True,
            es_sin_censura=False,
            descripcion="Pesos Safetensors de Qwen2.5 0.5B para carga directa en tensores.",
            formato="safetensors",
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
        sha256_esperado: Optional[str] = None,
        revision: str = "main",
    ) -> DefinicionModeloCatalogo:
        """Permite al usuario registrar cualquier modelo GGUF arbitrario de Hugging Face validando entradas."""
        repo_seguro = validar_repo_hf(repo_hf)
        filename_seguro = validar_filename_hf(filename)
        revision_segura = validar_revision_hf(revision)

        formato = "safetensors" if filename_seguro.lower().endswith((".safetensors", ".bin", ".pt")) else "gguf"
        nuevo = DefinicionModeloCatalogo(
            id=id_unico.strip(),
            nombre_legible=nombre_legible.strip(),
            categoria=categoria.strip(),
            cuantizacion=cuantizacion.strip(),
            idiomas_destacados=idiomas.strip(),
            repo_hf=repo_seguro,
            filename=filename_seguro,
            tamano_gb=tamano_gb,
            ram_minima_gb=round(tamano_gb * 1.5, 1),
            ram_recomendada_gb=round(tamano_gb * 2.5, 1),
            licencia=licencia.strip(),
            training_summary_url=training_summary_url.strip() if training_summary_url else None,
            copyright_compliant=True,
            es_sin_censura=es_sin_censura,
            descripcion=descripcion.strip(),
            sha256_esperado=sha256_esperado.strip().lower() if sha256_esperado else None,
            revision=revision_segura,
            formato=formato,
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


def validar_archivo_gguf(ruta: Path, tamano_minimo_gb: float = 0.0) -> tuple[bool, str]:
    """Verifica que el archivo exista, tenga cabecera binaria GGUF válida y no sea una página HTML de error."""
    if not ruta.exists() or not ruta.is_file():
        return False, f"El archivo '{ruta.name}' no existe en disco."
    tamano_bytes = ruta.stat().st_size
    if tamano_bytes < 4:
        return False, f"El archivo '{ruta.name}' está vacío ({tamano_bytes} bytes)."
    try:
        with open(ruta, "rb") as f:
            cabecera = f.read(4)
            if cabecera != b"GGUF":
                f.seek(0)
                muestra = f.read(512).decode("utf-8", errors="replace")
                if "<html" in muestra.lower() or "<!doctype" in muestra.lower():
                    return False, f"El archivo '{ruta.name}' es una página HTML de Hugging Face (modelo restringido/gated o error HTTP 401/403)."
                if "{" in muestra and "error" in muestra.lower():
                    return False, f"El archivo '{ruta.name}' contiene un error JSON de Hugging Face: {muestra.strip()[:100]}"
                return False, f"Cabecera GGUF inválida ({cabecera!r}). El archivo no es un modelo GGUF válido."
    except Exception as e:
        return False, f"No se pudo leer la cabecera de '{ruta.name}': {e}"

    return True, "OK"


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
        modelo: Any,
        region: RegionNormativa = RegionNormativa.ES_EU,
        callback_progreso: Optional[Callable[[str, float], None]] = None,
        permitir_inseguro: bool = False,
    ) -> Path:
        if isinstance(modelo, str):
            def_mod = CatalogoModelos.obtener_modelo(modelo)
            if not def_mod:
                raise ValueError(f"Modelo '{modelo}' no encontrado en el catálogo.")
            modelo = def_mod
        ruta_archivo_final = self.directorio_modelos / modelo.filename

        # Limpiar posibles restos de versiones antiguas (.partial)
        ruta_antigua_partial = self.directorio_modelos / f"{modelo.filename}.partial"
        if ruta_antigua_partial.exists():
            try:
                ruta_antigua_partial.unlink()
            except OSError:
                pass

        def log(msg: str, pct: float = 0.0) -> None:
            if callback_progreso:
                callback_progreso(msg, pct)
            else:
                print(f"[{pct:.1f}%] {msg}")

        if ruta_archivo_final.exists() and ruta_archivo_final.stat().st_size > 0:
            es_val, mot_inval = validar_archivo_gguf(ruta_archivo_final, modelo.tamano_gb)
            if not es_val:
                log(f"Archivo previo descartado por inválido/incompleto ({mot_inval}). Re-descargando...", 0.0)
                try:
                    ruta_archivo_final.unlink()
                except OSError:
                    pass
            elif modelo.sha256_esperado:
                hash_actual = calcular_sha256_archivo(ruta_archivo_final)
                if not hmac.compare_digest(hash_actual.lower(), modelo.sha256_esperado.lower()):
                    raise ValueError(
                        f"Integridad comprometida en modelo existente {ruta_archivo_final.name}: "
                        f"esperado {modelo.sha256_esperado}, actual {hash_actual}"
                    )
                log(f"El modelo ya está presente y verificado con SHA-256 en el Búnker: {ruta_archivo_final.name}", 100.0)
                self._registrar_en_cache(modelo, str(ruta_archivo_final))
                return ruta_archivo_final
            else:
                log(f"El modelo ya está presente y con cabecera GGUF válida: {ruta_archivo_final.name}", 100.0)
                self._registrar_en_cache(modelo, str(ruta_archivo_final))
                return ruta_archivo_final

        url_hf = f"https://huggingface.co/{modelo.repo_hf}/resolve/{modelo.revision}/{modelo.filename}"

        try:
            try:
                DescargadorSeguro.descargar_archivo(
                    url=url_hf,
                    ruta_destino=ruta_archivo_final,
                    sha256_esperado=modelo.sha256_esperado,
                    permitir_reanudacion=True,
                    permitir_inseguro=permitir_inseguro,
                    callback_progreso=callback_progreso,
                    user_agent="GuarIdA-Bunker-Downloader/1.0",
                )
            except Exception as err_primario:
                if "404" in str(err_primario) and not modelo.sha256_esperado:
                    url_alt = self._resolver_url_hf_fallback(modelo)
                    if url_alt and url_alt != url_hf:
                        log(f"Resolviendo espejo/nombre exacto en Hugging Face: {url_alt.split('/')[-1]}...", 5.0)
                        DescargadorSeguro.descargar_archivo(
                            url=url_alt,
                            ruta_destino=ruta_archivo_final,
                            sha256_esperado=None,
                            permitir_reanudacion=True,
                            permitir_inseguro=True,
                            callback_progreso=callback_progreso,
                            user_agent="GuarIdA-Bunker-Downloader/1.0",
                        )
                    else:
                        raise err_primario
                else:
                    raise err_primario

            es_val_desc, mot_desc = validar_archivo_gguf(ruta_archivo_final, modelo.tamano_gb)
            if not es_val_desc:
                try:
                    ruta_archivo_final.unlink()
                except OSError:
                    pass
                raise ValueError(f"Fallo de integridad tras descarga en {modelo.filename}: {mot_desc}")

            if modelo.sha256_esperado:
                log(f"Modelo {modelo.filename} verificado criptográficamente con SHA-256 e integrado.", 100.0)
            else:
                log(f"Modelo {modelo.filename} integrado (aviso: descargado sin hash SHA-256 verificado).", 100.0)
            self._registrar_en_cache(modelo, str(ruta_archivo_final))
            return ruta_archivo_final
        except Exception as e:
            log(f"Interrupción en la descarga de {modelo.filename}: {e}", 0.0)
            raise

    @staticmethod
    def _resolver_url_hf_fallback(modelo: DefinicionModeloCatalogo) -> Optional[str]:
        """Consulta la API de Hugging Face o espejos alternativos si el nombre exacto del .gguf varía."""
        import json
        import urllib.request

        espejos_por_id: dict[str, list[str]] = {
            "bge-m3-q4": ["gpustack/bge-m3-GGUF", "cstr/bge-m3-GGUF", "CompendiumLabs/bge-m3-gguf"],
            "jina-embeddings-v2-code-q4": [
                "second-state/jina-embeddings-v2-base-code-GGUF",
                "gandolfi/jina-embeddings-v2-base-code-Q4_K_M-GGUF",
                "gaianet/jina-embeddings-v2-base-code-GGUF",
            ],
            "snowflake-arctic-embed-m-q4": [
                "mradermacher/snowflake-arctic-embed-m-GGUF",
                "gpustack/snowflake-arctic-embed-m-GGUF",
                "yixuan-chia/snowflake-arctic-embed-m-GGUF",
            ],
            "qwen3-8b-q4": ["Qwen/Qwen3-8B-GGUF", "bartowski/Qwen_Qwen3-8B-GGUF", "unsloth/Qwen3-8B-GGUF"],
            "qwen3-4b-q4": ["Qwen/Qwen3-4B-GGUF", "bartowski/Qwen_Qwen3-4B-GGUF", "unsloth/Qwen3-4B-GGUF"],
        }
        repos_candidatos = [modelo.repo_hf] + [
            r for r in espejos_por_id.get(modelo.id, []) if r != modelo.repo_hf
        ]
        cuant_lower = modelo.cuantizacion.lower().replace("_", "")

        for repo in repos_candidatos:
            api_url = f"https://huggingface.co/api/models/{repo}"
            try:
                req = urllib.request.Request(api_url, headers={"User-Agent": "GuarIdA-Bunker-Downloader/1.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    datos = json.loads(resp.read().decode("utf-8"))
                siblings = datos.get("siblings", [])
                ggufs = [
                    s.get("rfilename", "")
                    for s in siblings
                    if s.get("rfilename", "").lower().endswith(".gguf")
                ]
                if not ggufs:
                    continue
                # Buscar coincidencia por cuantización (ej. q4_k_m, q8_0, f16)
                for g in ggufs:
                    gl = g.lower().replace("_", "").replace("-", "")
                    if cuant_lower in gl:
                        return f"https://huggingface.co/{repo}/resolve/main/{g}"
                # Si no hay Q4_K_M exacto, preferir Q8_0 o el primer .gguf disponible
                for pref in ("q4", "q5", "q8", "f16"):
                    for g in ggufs:
                        if pref in g.lower():
                            return f"https://huggingface.co/{repo}/resolve/main/{g}"
                return f"https://huggingface.co/{repo}/resolve/main/{ggufs[0]}"
            except Exception:
                continue
        return None

    def descargar_cesta(
        self,
        cesta: CestaDescarga,
        region: RegionNormativa = RegionNormativa.ES_EU,
        callback_progreso: Optional[Callable[[str, float], None]] = None,
        permitir_inseguro: bool = False,
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
                permitir_inseguro=permitir_inseguro,
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


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Gestor de descarga y catálogo de modelos GGUF de GuarIdA.")
    parser.add_argument("--descargar", type=str, help="ID del modelo del catálogo a descargar (ej. bge-m3-q4 o nomic-embed-text-v1.5)")
    parser.add_argument("--listar", action="store_true", help="Listar modelos disponibles en el catálogo")
    parser.add_argument("--categoria", type=str, default=None, help="Filtrar por categoría (coder, chat, embedding, etc.)")
    args = parser.parse_args()

    if args.listar:
        print("\nModelos disponibles en catálogo:")
        for m in CatalogoModelos.MODELOS.values():
            if not args.categoria or m.categoria.lower() == args.categoria.lower():
                print(f"  * {m.id:<25} [{m.categoria:<10}] {m.tamano_gb:.2f} GB - {m.nombre_legible}")
    elif args.descargar:
        descargador = DescargadorModelos()
        print(f">> Iniciando descarga de '{args.descargar}'...")
        try:
            ruta = descargador.descargar_modelo(args.descargar, permitir_inseguro=True)
            print(f"[OK] Modelo descargado y registrado en: {ruta}")
        except Exception as e:
            print(f"[ERROR]: {e}")
            raise
