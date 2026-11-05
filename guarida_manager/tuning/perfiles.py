import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from guarida_manager import DIRECTORIO_RAIZ_GUARIDA

DIRECTORIO_PERFILES = DIRECTORIO_RAIZ_GUARIDA / "perfiles"


def calcular_hash_canonico_dict(datos: dict[str, Any]) -> str:
    """Calcula el hash SHA-256 canónico serializando el diccionario con claves ordenadas."""
    payload = json.dumps(datos, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class RestriccionesBarrido:
    ctx_minimo: int = 2048
    margen_vram_pct: float = 15.0  # Conservar al menos 15% de margen de seguridad
    ttft_max_ms: float = 3000.0  # Máximo tiempo aceptable a primer token
    calidad_minima_pct: float = 95.0  # Coincidencia mínima requerida con baseline f16


@dataclass
class PerfilBarrido:
    nombre: str
    descripcion: str
    presupuesto_minutos: float
    objetivo_scoring: str = "equilibrado"  # "chat", "batch", "agente_contexto_largo", "equilibrado"
    restricciones: RestriccionesBarrido = field(default_factory=RestriccionesBarrido)
    batch_sizes: list[int] = field(default_factory=lambda: [512, 2048])
    ubatch_sizes: list[int] = field(default_factory=lambda: [128, 512])
    kv_cache_tipos: list[str] = field(default_factory=lambda: ["f16", "q8_0", "q4_0"])
    probar_flash_attn: bool = True
    ctx_escalones: list[int] = field(default_factory=lambda: [2048, 4096, 8192, 16384])
    umbral_poda_pct: float = 0.85
    top_k_refinado: int = 3
    usar_llama_bench_si_disponible: bool = True

    def a_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def hash_sha256(self) -> str:
        return calcular_hash_canonico_dict(self.a_dict())


@dataclass
class PerfilBateria:
    nombre: str
    descripcion: str
    repeticiones_min: int = 3
    repeticiones_max: int = 6
    umbral_cv_pct: float = 5.0
    calentamientos_descartados: int = 1
    enfriamiento_segundos: float = 1.0
    seed: int = 42
    timeout_por_peticion_s: float = 90.0
    escenarios_activos: list[str] = field(
        default_factory=lambda: ["pp", "tg", "ttft", "mixto", "calidad"]
    )
    pp_tokens_lista: list[int] = field(default_factory=lambda: [512, 2048])
    tg_predict_lista: list[int] = field(default_factory=lambda: [256, 512])

    def a_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def hash_sha256(self) -> str:
        return calcular_hash_canonico_dict(self.a_dict())


class GestorPerfilesTuning:
    """Gestiona, serializa y provee los perfiles de barrido y batería versionados."""

    @classmethod
    def obtener_perfil_barrido(cls, nombre: str = "estandar") -> PerfilBarrido:
        predefinidos = {
            "rapido": PerfilBarrido(
                nombre="rapido",
                descripcion="Barrido acelerado (~10 min) enfocado en encontrar ngl y batch óptimos rápidamente.",
                presupuesto_minutos=10.0,
                batch_sizes=[512, 1024],
                ubatch_sizes=[256, 512],
                kv_cache_tipos=["f16", "q8_0"],
                ctx_escalones=[2048, 4096],
                top_k_refinado=2,
                umbral_poda_pct=0.80,
            ),
            "estandar": PerfilBarrido(
                nombre="estandar",
                descripcion="Barrido equilibrado (~30-45 min) con exploración exhaustiva de etapas.",
                presupuesto_minutos=45.0,
                batch_sizes=[256, 512, 1024, 2048],
                ubatch_sizes=[128, 256, 512],
                kv_cache_tipos=["f16", "q8_0", "q4_0"],
                ctx_escalones=[2048, 4096, 8192, 16384],
                top_k_refinado=3,
                umbral_poda_pct=0.85,
            ),
            "exhaustivo": PerfilBarrido(
                nombre="exhaustivo",
                descripcion="Barrido profundo sin límite de tiempo estricto para máxima precisión de laboratorio.",
                presupuesto_minutos=180.0,
                batch_sizes=[256, 512, 1024, 2048, 4096],
                ubatch_sizes=[128, 256, 512, 1024],
                kv_cache_tipos=["f16", "q8_0", "q4_0"],
                ctx_escalones=[2048, 4096, 8192, 16384, 32768],
                top_k_refinado=5,
                umbral_poda_pct=0.90,
            ),
        }
        return predefinidos.get(nombre.lower()) or predefinidos["estandar"]

    @classmethod
    def obtener_perfil_bateria(cls, nombre: str = "estandar") -> PerfilBateria:
        nombre_norm = nombre.lower().rstrip("aos") + "a" if nombre.lower() in ("rapido", "exhaustivo") else nombre.lower()
        predefinidos = {
            "rapida": PerfilBateria(
                nombre="rapida",
                descripcion="Batería corta con repeticiones mínimas y escenarios clave.",
                repeticiones_min=1,
                repeticiones_max=2,
                umbral_cv_pct=10.0,
                calentamientos_descartados=0,
                enfriamiento_segundos=0.3,
                escenarios_activos=["pp", "tg"],
                pp_tokens_lista=[256],
                tg_predict_lista=[64],
            ),
            "estandar": PerfilBateria(
                nombre="estandar",
                descripcion="Batería estadísticamente robusta con repeticiones adaptativas y bootstrap.",
                repeticiones_min=3,
                repeticiones_max=5,
                umbral_cv_pct=5.0,
                calentamientos_descartados=1,
                enfriamiento_segundos=1.0,
                pp_tokens_lista=[512, 2048],
                tg_predict_lista=[256, 512],
            ),
            "exhaustiva": PerfilBateria(
                nombre="exhaustiva",
                descripcion="Batería de alta precisión para comparación estricta entre modelos.",
                repeticiones_min=5,
                repeticiones_max=8,
                umbral_cv_pct=3.0,
                calentamientos_descartados=2,
                enfriamiento_segundos=2.0,
                pp_tokens_lista=[512, 2048, 4096],
                tg_predict_lista=[256, 512, 1024],
            ),
        }
        return predefinidos.get(nombre.lower()) or predefinidos["estandar"]
