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
    "-sm", "--split-mode", "-mg", "-ts",
    "--device", "-dev",
    "--n-cpu-moe", "-ot",
    "--prio", "--poll",
    "--verbose", "-v", "--log-disable",
    "--defrag-thold", "--n-predict", "-n",
    "--temp", "--top-p", "--top-k",
}

_SERVIDORES_ACTIVOS: set["GestorLlamaServer"] = set()


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
    extra_args: list[str] = field(default_factory=list)

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

        if self.ubatch_size and self.ubatch_size > 0:
            cmd.extend(["-ub", str(self.ubatch_size)])

        if self.flash_attn:
            cmd.append("-fa")

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

        if optima:
            hilos_opt = optima.get("threads") or hilos
            ubatch = optima.get("ubatch_size")
            fa = bool(optima.get("flash_attn", 0))
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
            )

        # Fallback si no hay afinamiento registrado para este hardware
        ngl_por_defecto = 33 if info_hw.tiene_aceleracion_gpu else 0
        return cls(
            modelo_path=modelo_path,
            binario_path=binario_path,
            host=host,
            port=port,
            n_gpu_layers=ngl_por_defecto,
            ctx_size=4096,
            batch_size=512,
            threads=hilos,
            kv_cache_type="f16",
            alias=modelo_id,
            api_key=api_key,
        )


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

    def detener_servidor(self, timeout: float = 5.0) -> bool:
        """Detiene de forma limpia el proceso llama-server y cierra descriptores de log."""
        if not self.esta_activo():
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

        proc = self._proceso
        exito = False
        try:
            proc.terminate()
            try:
                proc.wait(timeout=timeout)
                exito = True
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2.0)
                exito = True
        except Exception:
            exito = False
        finally:
            if exito:
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

        return exito

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
