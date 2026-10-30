from dataclasses import dataclass
from enum import Enum
from typing import Optional


class RegionNormativa(str, Enum):
    ES_EU = "ES_EU"      # España y Unión Europea (Reglamento de Inteligencia Artificial - EU AI Act)
    GLOBAL = "GLOBAL"    # Ámbito internacional sin requisitos específicos de la UE


class EstadoCumplimiento(str, Enum):
    CONFORME = "CONFORME"
    REQUIERE_REVISION = "REQUIERE_REVISION"
    NO_CONFORME = "NO_CONFORME"


@dataclass(frozen=True)
class EvaluacionCumplimiento:
    region: RegionNormativa
    estado: EstadoCumplimiento
    es_apto_para_uso: bool
    resumen_legal: str
    normativa_aplicable: str
    detalles_transparencia: str
    detalles_copyright: str
    licencia: str


class GestorCumplimientoNormativo:
    """Evalúa el cumplimiento de modelos de IA con respecto al marco legal de la región del usuario.

    En la Unión Europea (y específicamente España), se aplica el Reglamento de Inteligencia
    Artificial de la UE (EU AI Act - Reglamento 2024/1689), en particular las obligaciones para
    proveedores de Modelos de IA de Uso General (GPAI):
      - Art. 53(1)(c): Cumplimiento de la legislación sobre derechos de autor (Directiva UE 2019/790).
      - Art. 53(1)(d): Publicación de un resumen suficientemente detallado de los contenidos usados para el entrenamiento.
      - Compatibilidad de licencias de código abierto / uso comercial.
    """

    LICENCIAS_PERMISIVAS_AUDITABLES = {
        "apache-2.0",
        "mit",
        "bsd-3-clause",
        "bsd-2-clause",
        "gpl-3.0",
        "agpl-3.0",
    }

    @classmethod
    def evaluar_modelo(
        cls,
        modelo_id: str,
        licencia: Optional[str],
        training_summary_url: Optional[str],
        copyright_compliant: bool = True,
        region: RegionNormativa = RegionNormativa.ES_EU,
    ) -> EvaluacionCumplimiento:
        licencia_norm = (licencia or "desconocida").strip().lower()

        if region == RegionNormativa.GLOBAL:
            return EvaluacionCumplimiento(
                region=region,
                estado=EstadoCumplimiento.CONFORME,
                es_apto_para_uso=True,
                resumen_legal="Uso libre sin restricciones territoriales de la Unión Europea.",
                normativa_aplicable="Términos estándar de licencia internacional",
                detalles_transparencia="No requerida bajo directivas regionales específicas",
                detalles_copyright="Regido por la legislación de la jurisdicción local",
                licencia=licencia or "No especificada",
            )

        # Evaluación para España / Unión Europea (EU AI Act)
        normativa = "Reglamento (UE) 2024/1689 (EU AI Act, Art. 53 y 55) y Directiva (UE) 2019/790"

        tiene_resumen_publico = bool(training_summary_url and training_summary_url.startswith("http"))
        es_licencia_abierta = licencia_norm in cls.LICENCIAS_PERMISIVAS_AUDITABLES

        if tiene_resumen_publico and es_licencia_abierta and copyright_compliant:
            estado = EstadoCumplimiento.CONFORME
            es_apto = True
            resumen = (
                "Cumple con el EU AI Act: Licencia permisiva transparente y resumen de entrenamiento "
                "público disponible para auditoría legal."
            )
        elif es_licencia_abierta and not tiene_resumen_publico:
            estado = EstadoCumplimiento.REQUIERE_REVISION
            es_apto = True
            resumen = (
                "Licencia de uso permisiva pero el dataset de entrenamiento no cuenta con ficha "
                "técnica detallada pública (requiere verificación para uso corporativo regulado)."
            )
        elif not copyright_compliant:
            estado = EstadoCumplimiento.NO_CONFORME
            es_apto = False
            resumen = (
                "No conforme con el marco de propiedad intelectual de la UE: Posible vulneración "
                "de directivas de derechos de autor en el dataset de origen."
            )
        else:
            estado = EstadoCumplimiento.REQUIERE_REVISION
            es_apto = True
            resumen = (
                f"Licencia '{licencia}' con restricciones específicas de uso o términos personalizados. "
                "Se permite su ejecución en búnker local privado pero con supervisión."
            )

        detalles_transp = (
            f"Ficha pública en: {training_summary_url}"
            if tiene_resumen_publico
            else "Falta URL verificada del resumen de entrenamiento de acuerdo con el Art. 53(1)(d)."
        )

        detalles_copy = (
            "Cumple con la política de respeto a derechos de autor y minería de datos (TDM opt-out)."
            if copyright_compliant
            else "Alerta: No se garantiza la exclusión de obras sujetas a reserva de derechos de autor."
        )

        return EvaluacionCumplimiento(
            region=region,
            estado=estado,
            es_apto_para_uso=es_apto,
            resumen_legal=resumen,
            normativa_aplicable=normativa,
            detalles_transparencia=detalles_transp,
            detalles_copyright=detalles_copy,
            licencia=licencia or "No especificada",
        )
