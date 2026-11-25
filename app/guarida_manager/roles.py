import json
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Optional


class RolAgente(str, Enum):
    CONVERSACIONAL = "conversacional"        # Interfaz de usuario: español fluido, empatía técnica y resumen
    CODER = "coder"                          # Programador: generación de parches diff, análisis sintáctico y AST
    EMBEDDING_INDEXER = "embedding_indexer"  # Indexador: embeddings, búsqueda semántica y árboles de nodos
    REVIEWER = "reviewer"                    # Revisor: análisis de seguridad, pruebas y detección de regresiones


@dataclass(frozen=True)
class MensajeInterModelo:
    """Protocolo estructurado para que los modelos se comuniquen entre sí sin desalinearse."""

    emisor_rol: str
    receptor_rol: str
    tipo_accion: str                         # "PLAN_TRABAJO", "SOLICITUD_CODIGO", "RESULTADO_PARCHE", "CONSULTA_NODOS"
    idioma_comunicacion: str                 # "es" o "en"
    payload: dict[str, Any]
    firma_integridad: Optional[str] = None

    def serializar_para_prompt(self) -> str:
        """Convierte el mensaje en un bloque JSON estandarizado para inyectar en el contexto."""
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)

    @classmethod
    def deserializar(cls, raw_json: str) -> "MensajeInterModelo":
        datos = json.loads(raw_json)
        return cls(**datos)


@dataclass
class AsignacionRoles:
    """Mapeo de qué modelo se encargará de cada función en el búnker offline."""

    modelo_conversacional_id: str = "qwen2.5-3b-chat-q4"
    modelo_coder_id: str = "qwen2.5-coder-7b-q4"
    modelo_embedding_id: str = "bge-m3-q4"
    modelo_sin_censura_id: Optional[str] = None
    idioma_preferido_usuario: str = "es"

    def resumen_roles(self) -> dict[str, str]:
        return {
            "Chat / Interfaz con Usuario": self.modelo_conversacional_id,
            "Motor de Código (Coder)": self.modelo_coder_id,
            "Memoria y Árboles de Nodos (Embeddings)": self.modelo_embedding_id,
            "Modelo Sin Censura (Opcional)": self.modelo_sin_censura_id or "No configurado",
        }
