import atexit
import os
import platform
import secrets
import subprocess
import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from guarida_manager.cache import GestorCache
from guarida_manager.downloader.tools import GestorHerramientasBunker
from guarida_manager.hardware import obtener_informacion_hardware

FLAGS_PERMITIDOS_EXTRA_ARGS = {
    "--threads", "-t", "--threads-http",
    "-tb", "--threads-batch",
    "-ub", "--ubatch-size",
    "-np", "--parallel",
    "--metrics", "--embedding", "--cont-batching",
    "--flash-attn", "-fa", "--mlock", "--no-mmap",
    "-nkvo", "--no-kv-offload",
    "-lm", "--load-mode",
    "-sm", "--split-mode", "-mg", "-ts",
    "--device", "-dev",
    "--n-cpu-moe", "-ot",
    "--prio", "--poll",
    "--verbose", "-v", "--log-disable",
    "--defrag-thold", "--n-predict", "-n",
    "--temp", "--top-p", "--top-k",
    "--ctx-shift", "--cache-reuse",
    "--lookup-cache", "--lookup",
    "-md", "--model-draft",
    "--draft", "--draft-min", "--draft-max", "--draft-p-min",
    "--slot-save-path", "--slots",
    "-ctk", "--cache-type-k", "-ctv", "--cache-type-v",
    "--cpu-strict",
}

_SERVIDORES_ACTIVOS: set["GestorLlamaServer"] = set()
_CACHE_AYUDA_BINARIO: dict[str, str] = {}


def obtener_ayuda_binario(binario: Optional[Path]) -> str:
    """Devuelve la salida de `--help` del binario (cacheada por ruta y mtime). Cadena vacía si no es ejecutable."""
    if not binario:
        return ""
    try:
        if not Path(binario).is_file():
            return ""
        clave = f"{binario}:{Path(binario).stat().st_mtime_ns}"
        if clave in _CACHE_AYUDA_BINARIO:
            return _CACHE_AYUDA_BINARIO[clave]
        proc = subprocess.run(
            [str(binario), "--help"], capture_output=True, text=True, timeout=15, check=False
        )
        texto = (proc.stdout or "") + "\n" + (proc.stderr or "")
        _CACHE_AYUDA_BINARIO[clave] = texto
        return texto
    except Exception:
        return ""


def _limpiar_servidores_activos() -> None:
    for srv in list(_SERVIDORES_ACTIVOS):
        try:
            srv.detener_servidor(timeout=2.0)
        except Exception:
            pass


atexit.register(_limpiar_servidores_activos)


@dataclass
class LlamaServerConfig:
    modelo_path: Path
    binario_path: Optional[Path] = None
    host: str = "127.0.0.1"
    port: int = 8083
    n_gpu_layers: int = 0
    ctx_size: int = 4096
    batch_size: int = 512
    threads: Optional[int] = None
    kv_cache_type: str = "f16"
    alias: Optional[str] = None
    embedding: bool = False
    no_webui: bool = True
    api_key: Optional[str] = None
    ubatch_size: Optional[int] = None
    flash_attn: bool = False
    threads_batch: Optional[int] = None
    ctx_shift: bool = False
    cache_reuse: Optional[int] = None
    lookup_cache: Optional[int] = None
    model_draft_path: Optional[Path] = None
    draft_max: Optional[int] = None
    mlock: bool = False
    no_mmap: bool = False
    extra_args: list[str] = field(default_factory=list)

    def aplicar_optimizaciones_seguras(self, hilos_logicos: Optional[int] = None) -> "LlamaServerConfig":
        """Activa optimizaciones de bajo riesgo solo si el binario las anuncia en `--help`.

        - `--cache-reuse 256`: reutiliza fragmentos de KV entre turnos (prefijos estables).
        - `-tb`: hilos dedicados al prefill (PP).
        Las opciones de mayor riesgo (`-md`, `--lookup-cache`, `--ctx-shift`) quedan solo bajo petición explícita.
        """
        if self.embedding:
            return self
        binario = self.binario_path or GestorHerramientasBunker.resolver_ruta_ejecutable("llama-server")
        ayuda = obtener_ayuda_binario(Path(binario) if binario else None)
        if not ayuda:
            return self
        if self.cache_reuse is None and "--cache-reuse" in ayuda:
            self.cache_reuse = 256
        if self.threads_batch is None and isinstance(hilos_logicos, int) and hilos_logicos > 0 and (
            "--threads-batch" in ayuda or "-tb," in ayuda or "-tb " in ayuda
        ):
            self.threads_batch = hilos_logicos
        return self

    def construir_comando(self) -> list[str]:
        if self.host not in ("127.0.0.1", "localhost", "::1"):
            warnings.warn(
                f"ADVERTENCIA DE SEGURIDAD (S8): llama-server configurado en interfaz no local '{self.host}'. "
                "Cualquier dispositivo en la red podrá acceder al servidor de inferencia.",
                UserWarning,
                stacklevel=2,
            )

        binario = self.binario_path or GestorHerramientasBunker.resolver_ruta_ejecutable("llama-server")
        if not binario:
            binario_nombre = "llama-server.exe" if platform.system() == "Windows" else "llama-server"
            binario = Path(binario_nombre)

        cmd = [
            str(binario),
            "-m", str(self.modelo_path),
            "--host", str(self.host),
            "--port", str(self.port),
            "-ngl", str(self.n_gpu_layers),
            "-c", str(self.ctx_size),
            "-b", str(self.batch_size),
        ]

        if self.threads and self.threads > 0:
            cmd.extend(["-t", str(self.threads)])

        if self.threads_batch and self.threads_batch > 0:
            cmd.extend(["-tb", str(self.threads_batch)])

        if self.ubatch_size and self.ubatch_size > 0:
            cmd.extend(["-ub", str(self.ubatch_size)])

        if self.flash_attn:
            cmd.append("-fa")

        if self.ctx_shift:
            cmd.append("--ctx-shift")

        if self.cache_reuse and self.cache_reuse > 0:
            cmd.extend(["--cache-reuse", str(self.cache_reuse)])

        if self.lookup_cache and self.lookup_cache > 0:
            cmd.extend(["--lookup-cache", str(self.lookup_cache)])

        if self.model_draft_path:
            cmd.extend(["-md", str(self.model_draft_path)])
            if self.draft_max and self.draft_max > 0:
                cmd.extend(["--draft-max", str(self.draft_max)])

        if self.mlock:
            cmd.append("--mlock")

        if self.no_mmap:
            cmd.append("--no-mmap")

        if self.kv_cache_type and self.kv_cache_type != "f16":
            # Formatos de kv cache soportados en llama.cpp: q8_0, q4_0, etc.
            cmd.extend(["--cache-type-k", self.kv_cache_type, "--cache-type-v", self.kv_cache_type])

        if self.alias:
            cmd.extend(["-a", str(self.alias)])

        if self.embedding:
            cmd.append("--embedding")

        if self.no_webui:
            cmd.append("--no-webui")

        if self.extra_args:
            for arg in self.extra_args:
                if arg.startswith("-"):
                    flag = arg.split("=")[0].strip()
                    if flag not in FLAGS_PERMITIDOS_EXTRA_ARGS:
                        raise ValueError(
                            f"Argumento extra no seguro detectado en extra_args (S-A1): '{arg}'. "
                            f"Solo se autorizan banderas de la lista blanca: {sorted(FLAGS_PERMITIDOS_EXTRA_ARGS)}"
                        )
                elif any(c in arg for c in (";", "&", "|", "`", "$", "\n", "\r", ">", "<")):
                    raise ValueError(f"Argumento extra no seguro detectado: '{arg}'")
            cmd.extend(self.extra_args)

        return cmd

    @classmethod
    def desde_afinamiento(
        cls,
        modelo_path: Path,
        modelo_id: str,
        gestor_cache: Optional[GestorCache] = None,
        binario_path: Optional[Path] = None,
        port: int = 8083,
        host: str = "127.0.0.1",
        api_key: Optional[str] = None,
    ) -> "LlamaServerConfig":
        """Construye la configuracion cargando los parametros optimos afinados en SQLite si existen."""
        cache = gestor_cache or GestorCache()
        info_hw = obtener_informacion_hardware()
        hash_hw = info_hw.hash_hardware

        optima = cache.obtener_configuracion_optima(modelo_id=modelo_id, hash_hardware=hash_hw)

        # Hilos por defecto: nucleos fisicos si estan disponibles
        hilos = info_hw.nucleos_fisicos if info_hw.nucleos_fisicos > 0 else 4

        # Calcular tamaño físico del modelo para proteger contra OOM en Vulkan/iGPU
        tamano_gb = 0.0
        try:
            if modelo_path.exists() and modelo_path.is_file():
                tamano_gb = modelo_path.stat().st_size / (1024**3)
        except OSError:
            tamano_gb = 0.0

        es_igpu = info_hw.tipo_gpu_principal in ("Intel", "CPU") or not info_hw.tiene_aceleracion_gpu or (
            bool(info_hw.gpus) and all(g.tipo == "Integrada" or g.vram_dedicada_gb == 0 for g in info_hw.gpus)
        )
        excede_vram_gpu = tamano_gb > 0 and tamano_gb > info_hw.gtt_disponible_gb
        debe_forzar_cpu = excede_vram_gpu or (es_igpu and tamano_gb >= 6.0)

        if optima and not debe_forzar_cpu:
            hilos_opt = optima.get("threads") or hilos
            ubatch = optima.get("ubatch_size")
            fa = bool(optima.get("flash_attn", 0))
            if info_hw.tipo_gpu_principal != "NVIDIA" or not info_hw.tiene_aceleracion_gpu:
                fa = False
            extra = []
            if optima.get("extra_args_json"):
                try:
                    import json
                    parsed_extra = json.loads(optima["extra_args_json"])
                    if isinstance(parsed_extra, list):
                        extra = parsed_extra
                except Exception:
                    pass
            return cls(
                modelo_path=modelo_path,
                binario_path=binario_path,
                host=host,
                port=port,
                n_gpu_layers=optima.get("n_gpu_layers", 0),
                ctx_size=optima.get("ctx_size", 4096),
                batch_size=optima.get("batch_size", 512),
                threads=hilos_opt,
                kv_cache_type=optima.get("kv_cache_tipo", "f16"),
                alias=modelo_id,
                api_key=api_key,
                ubatch_size=ubatch,
                flash_attn=fa,
                extra_args=extra,
            ).aplicar_optimizaciones_seguras(getattr(info_hw, "nucleos_logicos", None))

        vram_util_gb = max(0.0, info_hw.gtt_disponible_gb - 1.5)
        extra_fallback: list[str] = []
        if not info_hw.tiene_aceleracion_gpu:
            ngl_por_defecto = 0
            ctx_def, batch_def, ubatch_def, kv_def = 2048, 256, 256, "q8_0"
        elif debe_forzar_cpu:
            # Modelo que excede VRAM o grande en iGPU (ej. 14B de 9 GB en Intel Iris Xe):
            # forzar CPU puro (-ngl 0 -nkvo) para evitar vk::Device::allocateMemory: ErrorOutOfDeviceMemory
            ngl_por_defecto = 0
            ctx_def, batch_def, ubatch_def, kv_def = 2048, 256, 128, "q8_0"
            extra_fallback = ["-nkvo"]
        elif tamano_gb > 0 and tamano_gb > vram_util_gb:
            proporcion = max(0.15, min(0.85, vram_util_gb / tamano_gb))
            ngl_por_defecto = max(4, int(32 * proporcion))
            ctx_def, batch_def, ubatch_def, kv_def = 2048, 256, 256, "q8_0"
        else:
            ngl_por_defecto = 33
            ctx_def, batch_def, ubatch_def, kv_def = 4096, 512, 512, "f16"

        return cls(
            modelo_path=modelo_path,
            binario_path=binario_path,
            host=host,
            port=port,
            n_gpu_layers=ngl_por_defecto,
            ctx_size=ctx_def,
            batch_size=batch_def,
            ubatch_size=ubatch_def,
            threads=hilos,
            kv_cache_type=kv_def,
            alias=modelo_id,
            api_key=api_key,
            extra_args=extra_fallback,
        ).aplicar_optimizaciones_seguras(getattr(info_hw, "nucleos_logicos", None))


class GestorLlamaServer:
    """Gestiona el ciclo de vida (arranque, estado y parada) de la instancia local de llama-server."""

    def __init__(self, gestor_cache: Optional[GestorCache] = None):
        self.gestor_cache = gestor_cache or GestorCache()
        self._proceso: Optional[subprocess.Popen] = None
        self._config_activa: Optional[LlamaServerConfig] = None
        self._timestamp_inicio: Optional[float] = None
        self._archivo_log: Any = None

    @property
    def proceso(self) -> Optional[subprocess.Popen]:
        return self._proceso

    @property
    def config_activa(self) -> Optional[LlamaServerConfig]:
        return self._config_activa

    @property
    def host(self) -> str:
        return self._config_activa.host if self._config_activa else "127.0.0.1"

    @property
    def port(self) -> int:
        return self._config_activa.port if self._config_activa else 8083

    def esta_activo(self) -> bool:
        if self._proceso is None:
            return False
        ret = self._proceso.poll()
        return ret is None

    def iniciar_servidor(
        self,
        config: LlamaServerConfig,
        stdout: Any = None,
        stderr: Any = None,
        ruta_log: Optional[Path] = None,
    ) -> dict[str, Any]:
        """Inicia el proceso llama-server de forma asincrona en segundo plano con soporte de log de diagnóstico."""
        if self.esta_activo():
            raise RuntimeError(
                f"El servidor ya esta en ejecucion (PID: {self._proceso.pid}, Puerto: {self._config_activa.port})"
            )

        cmd = config.construir_comando()

        # En Windows evitamos ventana emergente de consola
        creationflags = 0
        if platform.system() == "Windows":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

        if ruta_log is not None:
            ruta_log.parent.mkdir(parents=True, exist_ok=True)
            self._archivo_log = open(ruta_log, "a", encoding="utf-8")
            stdout_stream = self._archivo_log
            stderr_stream = self._archivo_log
        else:
            stdout_stream = stdout if stdout is not None else subprocess.DEVNULL
            stderr_stream = stderr if stderr is not None else subprocess.DEVNULL

        # Filtrar variables LLAMA_ARG_* previas del entorno para evitar esquivar la lista blanca (N9)
        env = {k: v for k, v in os.environ.items() if not k.startswith("LLAMA_ARG_")}
        if config.api_key:
            env["LLAMA_ARG_API_KEY"] = config.api_key
            env["LLAMA_API_KEY"] = config.api_key

        try:
            proceso = subprocess.Popen(
                cmd,
                stdout=stdout_stream,
                stderr=stderr_stream,
                creationflags=creationflags,
                env=env,
            )
        except Exception:
            if self._archivo_log:
                try:
                    self._archivo_log.close()
                except Exception:
                    pass
                self._archivo_log = None
            raise

        self._proceso = proceso
        self._config_activa = config
        self._timestamp_inicio = time.time()
        _SERVIDORES_ACTIVOS.add(self)

        return {
            "pid": proceso.pid,
            "host": config.host,
            "port": config.port,
            "modelo": str(config.modelo_path),
            "comando": cmd,
            "api_key_configurada": bool(config.api_key),
        }

    @staticmethod
    def terminar_procesos_huerfanos(nombre: str = "llama-server") -> int:
        """Localiza y termina procesos llama-server huérfanos en segundo plano."""
        try:
            import psutil
        except ImportError:
            return 0
        terminados = 0
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                nombre_p = proc.info.get("name") or ""
                if nombre.lower() in nombre_p.lower():
                    proc.kill()
                    proc.wait(timeout=2.0)
                    terminados += 1
            except Exception:
                pass
        return terminados

    def detener_servidor(self, timeout: float = 5.0) -> bool:
        """Detiene de forma limpia el proceso llama-server y limpia procesos huérfanos."""
        if self._proceso:
            proc = self._proceso
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=2.0)
            except Exception:
                pass
        self.terminar_procesos_huerfanos("llama-server")

        _SERVIDORES_ACTIVOS.discard(self)
        if self._archivo_log:
            try:
                self._archivo_log.close()
            except Exception:
                pass
            self._archivo_log = None
        self._proceso = None
        self._config_activa = None
        self._timestamp_inicio = None
        return True

    def obtener_estado(self) -> dict[str, Any]:
        """Retorna un resumen del estado del proceso del servidor."""
        activo = self.esta_activo()
        uptime = (time.time() - self._timestamp_inicio) if (activo and self._timestamp_inicio) else 0.0

        return {
            "activo": activo,
            "pid": self._proceso.pid if activo else None,
            "uptime_segundos": round(uptime, 2),
            "host": self._config_activa.host if self._config_activa else None,
            "port": self._config_activa.port if self._config_activa else None,
            "modelo": str(self._config_activa.modelo_path) if self._config_activa else None,
            "n_gpu_layers": self._config_activa.n_gpu_layers if self._config_activa else None,
            "ctx_size": self._config_activa.ctx_size if self._config_activa else None,
        }
