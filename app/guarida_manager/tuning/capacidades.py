import datetime
import hashlib
import json
import os
import platform
import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from guarida_manager.cache import GestorCache

# Catálogo cerrado de flags candidatos seguros que GuarIdA permite explorar
FLAGS_CANDIDATOS_EXPLORABLES = {
    "-ngl", "--n-gpu-layers",
    "-t", "--threads",
    "-tb", "--threads-batch",
    "-c", "--ctx-size",
    "-b", "--batch-size",
    "-ub", "--ubatch-size",
    "--cache-type-k", "--cache-type-v",
    "-fa", "--flash-attn",
    "--mlock", "--no-mmap",
    "-lm", "--load-mode",
    "-np", "--parallel",
    "--cont-batching",
    "-nkvo", "--no-kv-offload",
    "-sm", "--split-mode",
    "-mg", "-ts",
    "--device",
    "--n-cpu-moe", "-ot",
    "--prio", "--poll",
    "-dev",
}


@dataclass
class InfoFlag:
    flag: str
    alias: list[str] = field(default_factory=list)
    acepta_valor: bool = False
    valores_posibles: list[str] = field(default_factory=list)
    descripcion: str = ""


@dataclass
class CapacidadesBinario:
    sha256_binario: str
    version_build: str
    ruta_binario: str
    flags_soportados: dict[str, dict[str, Any]] = field(default_factory=dict)
    dispositivos: list[str] = field(default_factory=list)
    soporta_llama_bench: bool = False
    ruta_llama_bench: Optional[str] = None
    soporta_flash_attn: bool = False
    flash_attn_modo: str = "ninguno"  # "bool", "enum_on_off_auto", "ninguno"
    tipos_kv_cache_k: list[str] = field(default_factory=lambda: ["f16", "q8_0", "q4_0"])
    tipos_kv_cache_v: list[str] = field(default_factory=lambda: ["f16", "q8_0", "q4_0"])
    soporta_ubatch: bool = False
    soporta_threads_batch: bool = False
    soporta_list_devices: bool = False
    fecha_descubrimiento: str = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())

    def tiene_flag(self, flag: str) -> bool:
        return flag in self.flags_soportados

    def a_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    @classmethod
    def desde_dict(cls, datos: dict[str, Any]) -> "CapacidadesBinario":
        return cls(**datos)


class DescubridorCapacidades:
    """Descubre, parsea y valida empíricamente las capacidades de llama-server y llama-bench."""

    @staticmethod
    def calcular_sha256_archivo(ruta: Path) -> str:
        h = hashlib.sha256()
        with open(ruta, "rb") as f:
            while chunk := f.read(1024 * 1024):
                h.update(chunk)
        return h.hexdigest()

    @classmethod
    def extraer_version(cls, ruta_binario: Path) -> str:
        try:
            p = subprocess.run(
                [str(ruta_binario), "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            salida = (p.stdout or "") + (p.stderr or "")
            coincidencia = re.search(r"version:\s*([^\s]+)", salida, re.IGNORECASE)
            if coincidencia:
                return coincidencia.group(1).strip()
            coincidencia_build = re.search(r"\b(b\d{4,6}|[0-9a-f]{7,40})\b", salida)
            if coincidencia_build:
                return coincidencia_build.group(1).strip()
            lineas = salida.strip().splitlines()
            if lineas:
                return lineas[0][:50].strip()
        except Exception:
            pass
        return "desconocida"

    @classmethod
    def parsear_ayuda(cls, texto_ayuda: str) -> dict[str, InfoFlag]:
        resultado: dict[str, InfoFlag] = {}
        lineas = texto_ayuda.splitlines()

        for linea in lineas:
            linea_str = linea.strip()
            if not linea_str.startswith("-"):
                continue

            partes_flags = []
            parte_desc = ""

            tokens = linea_str.split("  ", 1)
            flags_token = tokens[0].strip()
            if len(tokens) > 1:
                parte_desc = tokens[1].strip()

            tokens_raw = [t.strip().rstrip(",") for t in flags_token.split() if t.strip()]
            flags_encontrados = []
            acepta_valor = False
            valores_enum = []

            for t in tokens_raw:
                if t.startswith("-"):
                    flag_limpio = t.split("=")[0].split("[")[0].strip()
                    if flag_limpio:
                        flags_encontrados.append(flag_limpio)
                else:
                    acepta_valor = True
                    if "|" in t:
                        valores_enum = [v.strip("{()}[] \t") for v in t.split("|") if v.strip("{()}[] \t")]

            if flags_encontrados:
                flag_ppal = flags_encontrados[0]
                aliases = flags_encontrados[1:]
                info = InfoFlag(
                    flag=flag_ppal,
                    alias=aliases,
                    acepta_valor=acepta_valor,
                    valores_posibles=valores_enum,
                    descripcion=parte_desc,
                )
                resultado[flag_ppal] = info
                for a in aliases:
                    resultado[a] = info

        return resultado

    @classmethod
    def descubrir_dispositivos(cls, ruta_binario: Path) -> list[str]:
        dispositivos: list[str] = []
        try:
            p = subprocess.run(
                [str(ruta_binario), "--list-devices"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            salida = (p.stdout or "") + (p.stderr or "")
            for linea in salida.splitlines():
                linea_limpia = linea.strip()
                if linea_limpia and not linea_limpia.lower().startswith("available") and not linea_limpia.startswith("-"):
                    dispositivos.append(linea_limpia)
        except Exception:
            pass
        return dispositivos

    @classmethod
    def descubrir(
        cls,
        ruta_server: Path,
        ruta_bench: Optional[Path] = None,
        gestor_cache: Optional[GestorCache] = None,
        forzar_redescubrimiento: bool = False,
    ) -> CapacidadesBinario:
        if not ruta_server.exists():
            raise FileNotFoundError(f"No existe el binario de llama-server en {ruta_server}")

        sha = cls.calcular_sha256_archivo(ruta_server)
        cache = gestor_cache or GestorCache()

        if not forzar_redescubrimiento:
            cached = cls.obtener_de_cache(cache, sha)
            if cached:
                return cached

        version = cls.extraer_version(ruta_server)

        # Extraer ayuda de llama-server
        ayuda_texto = ""
        try:
            p = subprocess.run(
                [str(ruta_server), "--help"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            ayuda_texto = (p.stdout or "") + "\n" + (p.stderr or "")
        except Exception:
            pass

        flags_parseados = cls.parsear_ayuda(ayuda_texto)

        # Filtrar únicamente flags que están en el catálogo seguro FLAGS_CANDIDATOS_EXPLORABLES
        flags_soportados_dict: dict[str, dict[str, Any]] = {}
        for f, info in flags_parseados.items():
            if f in FLAGS_CANDIDATOS_EXPLORABLES:
                flags_soportados_dict[f] = {
                    "flag": info.flag,
                    "alias": info.alias,
                    "acepta_valor": info.acepta_valor,
                    "valores_posibles": info.valores_posibles,
                    "descripcion": info.descripcion,
                }

        # Detección específica de flash-attn
        soporta_fa = ("-fa" in flags_parseados) or ("--flash-attn" in flags_parseados)
        fa_modo = "ninguno"
        if soporta_fa:
            info_fa = flags_parseados.get("--flash-attn") or flags_parseados.get("-fa")
            if info_fa and any("on" in v or "off" in v or "auto" in v for v in info_fa.valores_posibles):
                fa_modo = "enum_on_off_auto"
            elif "--flash-attn" in ayuda_texto and ("on|off|auto" in ayuda_texto or "{0,1,2}" in ayuda_texto):
                fa_modo = "enum_on_off_auto"
            else:
                fa_modo = "bool"

        dispositivos = cls.descubrir_dispositivos(ruta_server)
        soporta_list_dev = bool(dispositivos or "--list-devices" in ayuda_texto)

        # Comprobar llama-bench
        soporta_bench = False
        ruta_bench_str = None
        if ruta_bench and ruta_bench.exists():
            soporta_bench = True
            ruta_bench_str = str(ruta_bench)
        else:
            # Buscar llama-bench al lado de llama-server
            nombre_bench = "llama-bench.exe" if platform.system() == "Windows" else "llama-bench"
            posible_bench = ruta_server.parent / nombre_bench
            if posible_bench.exists():
                soporta_bench = True
                ruta_bench_str = str(posible_bench)

        capacidades = CapacidadesBinario(
            sha256_binario=sha,
            version_build=version,
            ruta_binario=str(ruta_server),
            flags_soportados=flags_soportados_dict,
            dispositivos=dispositivos,
            soporta_llama_bench=soporta_bench,
            ruta_llama_bench=ruta_bench_str,
            soporta_flash_attn=soporta_fa,
            flash_attn_modo=fa_modo,
            soporta_ubatch=("-ub" in flags_parseados or "--ubatch-size" in flags_parseados),
            soporta_threads_batch=("-tb" in flags_parseados or "--threads-batch" in flags_parseados),
            soporta_list_devices=soporta_list_dev,
        )

        cls.guardar_en_cache(cache, capacidades)
        return capacidades

    @classmethod
    def validar_compatibilidad_config(
        cls,
        config: dict[str, Any],
        capacidades: CapacidadesBinario,
    ) -> tuple[bool, Optional[str]]:
        """Valida reglas de compatibilidad conocidas antes de intentar arrancar."""
        b = config.get("batch_size", 512)
        ub = config.get("ubatch_size", b)
        if ub > b:
            return False, f"Incompatibilidad: ubatch ({ub}) no puede ser mayor que batch ({b})"

        fa = config.get("flash_attn", False)
        kv_v = config.get("kv_cache_tipo_v", config.get("kv_cache_tipo", "f16"))

        if kv_v in ("q8_0", "q4_0") and not fa:
            return False, f"Incompatibilidad: kv_cache cuantizado ({kv_v}) requiere flash attention activo (-fa)"

        if platform.system() == "Windows" and config.get("mlock", False):
            return False, "Incompatibilidad: --mlock suele fallar sin privilegios elevados en Windows"

        if platform.system() == "Windows" and config.get("numa", False):
            return False, "Incompatibilidad: --numa no es aplicable en Windows"

        return True, None

    @classmethod
    def guardar_en_cache(cls, gestor_cache: GestorCache, caps: CapacidadesBinario) -> None:
        with gestor_cache.sesion() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS capacidades_binario (
                    sha256_binario TEXT PRIMARY KEY,
                    version_build TEXT NOT NULL,
                    flags_json TEXT NOT NULL,
                    dispositivos_json TEXT NOT NULL,
                    capacidades_completas_json TEXT NOT NULL,
                    fecha TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                INSERT INTO capacidades_binario (
                    sha256_binario, version_build, flags_json,
                    dispositivos_json, capacidades_completas_json, fecha
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(sha256_binario) DO UPDATE SET
                    version_build = excluded.version_build,
                    flags_json = excluded.flags_json,
                    dispositivos_json = excluded.dispositivos_json,
                    capacidades_completas_json = excluded.capacidades_completas_json,
                    fecha = excluded.fecha;
                """,
                (
                    caps.sha256_binario,
                    caps.version_build,
                    json.dumps(caps.flags_soportados, ensure_ascii=False),
                    json.dumps(caps.dispositivos, ensure_ascii=False),
                    caps.a_json(),
                    caps.fecha_descubrimiento,
                ),
            )

    @classmethod
    def obtener_de_cache(cls, gestor_cache: GestorCache, sha256_binario: str) -> Optional[CapacidadesBinario]:
        try:
            with gestor_cache.sesion() as conn:
                fila = conn.execute(
                    "SELECT capacidades_completas_json FROM capacidades_binario WHERE sha256_binario = ?;",
                    (sha256_binario,),
                ).fetchone()
                if fila and fila[0]:
                    datos = json.loads(fila[0])
                    return CapacidadesBinario.desde_dict(datos)
        except Exception:
            pass
        return None
