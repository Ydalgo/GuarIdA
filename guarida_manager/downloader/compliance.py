from dataclasses import dataclass
from enum import Enum
from typing import Optional


class RegionNormativa(str, Enum):
    ES_EU = "ES_EU"      # España y Unión Europea (Reglamento de Inteligencia Artificial - EU AI Act)
    GLOBAL = "GLOBAL"    # Ámbito internacional sin requisitos específicos de la UE


class EstadoCumplimiento(str, Enum):
    CONFORME = "CONFORME"
    REQUIERE_REVISION = "REQUIERE_REVISION"
    EXPERIMENTAL_SIN_CENSURA = "EXPERIMENTAL_SIN_CENSURA"
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
    permite_descarga: bool = True  # Siempre True: la gobernanza es informativa, nunca un bloqueo total


class GestorCumplimientoNormativo:
    """Evalúa el cumplimiento de modelos de IA con respecto al marco legal de la región del usuario.

    Enfoque de GuarIdA:
      - La auditoría legal es rigurosa pero INFORMATIVA. Nunca bloquea arbitrariamente la libertad
        del usuario de descargar modelos experimentales, variantes sin censura (abliterated)
        o pesos personalizados en su propio hardware privado.
      - Advierte claramente de las implicaciones según el Reglamento (UE) 2024/1689 (EU AI Act).
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
        es_sin_censura: bool = False,
        region: RegionNormativa = RegionNormativa.ES_EU,
    ) -> EvaluacionCumplimiento:
        licencia_norm = (licencia or "desconocida").strip().lower()

        if es_sin_censura:
            return EvaluacionCumplimiento(
                region=region,
                estado=EstadoCumplimiento.EXPERIMENTAL_SIN_CENSURA,
                es_apto_para_uso=True,
                resumen_legal=(
                    "Modelo desalineado o sin censura (Abliterated / Uncensored). No apto para despliegues "
                    "públicos regulados bajo el EU AI Act, pero permitido para investigación privada en búnker local."
                ),
                normativa_aplicable="Exención de I+D y uso estrictamente personal/laboratorio",
                detalles_transparencia="Pesos modificados para neutralizar filtros de alineación.",
                detalles_copyright="Dependiente del modelo base de origen.",
                licencia=licencia or "Modificación Comunitaria",
                permite_descarga=True,
            )

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
                permite_descarga=True,
            )

        # Evaluación para España / Unión Europea (EU AI Act)
        normativa = "Reglamento (UE) 2024/1689 (EU AI Act, Art. 53 y 55) y Directiva (UE) 2019/790"

        tiene_resumen_publico = bool(training_summary_url and training_summary_url.startswith("http"))
        es_licencia_abierta = licencia_norm in cls.LICENCIAS_PERMISIVAS_AUDITABLES

        if tiene_resumen_publico and es_licencia_abierta and copyright_compliant:
            estado = EstadoCumplimiento.CONFORME
            resumen = (
                "Cumple con el EU AI Act: Licencia permisiva transparente y resumen de entrenamiento "
                "público disponible para auditoría legal."
            )
        elif es_licencia_abierta and not tiene_resumen_publico:
            estado = EstadoCumplimiento.REQUIERE_REVISION
            resumen = (
                "Licencia permisiva pero el dataset de entrenamiento no cuenta con ficha "
                "técnica pública verificada (Art. 53(1)(d)). Permitido con advertencia."
            )
        elif not copyright_compliant:
            estado = EstadoCumplimiento.NO_CONFORME
            resumen = (
                "Alerta legal: No se garantiza la política de derechos de autor y minería de datos (TDM opt-out) "
                "de la UE. El usuario asume la responsabilidad si se usa en producción."
            )
        else:
            estado = EstadoCumplimiento.REQUIERE_REVISION
            resumen = (
                f"Licencia '{licencia}' con restricciones comerciales o términos específicos. "
                "Uso autorizado en búnker local privado."
            )

        detalles_transp = (
            f"Ficha técnica en: {training_summary_url}"
            if tiene_resumen_publico
            else "Sin URL pública de documentación de entrenamiento."
        )

        detalles_copy = (
            "Cumple con directiva de derechos de autor europea."
            if copyright_compliant
            else "Riesgo de derechos de autor: sin garantía de exclusión de datasets protegidos."
        )

        return EvaluacionCumplimiento(
            region=region,
            estado=estado,
            es_apto_para_uso=True,
            resumen_legal=resumen,
            normativa_aplicable=normativa,
            detalles_transparencia=detalles_transp,
            detalles_copyright=detalles_copy,
            licencia=licencia or "No especificada",
            permite_descarga=True,
        )
