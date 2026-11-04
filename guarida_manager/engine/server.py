import os
import platform
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from guarida_manager.cache import GestorCache
from guarida_manager.downloader.tools import GestorHerramientasBunker
from guarida_manager.hardware import obtener_informacion_hardware


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
    extra_args: list[str] = field(default_factory=list)

    def construir_comando(self) -> list[str]:
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
    ) -> "LlamaServerConfig":
        """Construye la configuracion cargando los parametros optimos afinados en SQLite si existen."""
        cache = gestor_cache or GestorCache()
        info_hw = obtener_informacion_hardware()
        hash_hw = info_hw.hash_hardware

        optima = cache.obtener_configuracion_optima(modelo_id=modelo_id, hash_hardware=hash_hw)

        # Hilos por defecto: nucleos fisicos si estan disponibles
        hilos = info_hw.nucleos_fisicos if info_hw.nucleos_fisicos > 0 else 4

        if optima:
            return cls(
                modelo_path=modelo_path,
                binario_path=binario_path,
                host=host,
                port=port,
                n_gpu_layers=optima.get("n_gpu_layers", 0),
                ctx_size=optima.get("ctx_size", 4096),
                batch_size=optima.get("batch_size", 512),
                threads=hilos,
                kv_cache_type=optima.get("kv_cache_tipo", "f16"),
                alias=modelo_id,
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
        )


class GestorLlamaServer:
    """Gestiona el ciclo de vida (arranque, estado y parada) de la instancia local de llama-server."""

    def __init__(self, gestor_cache: Optional[GestorCache] = None):
        self.gestor_cache = gestor_cache or GestorCache()
        self._proceso: Optional[subprocess.Popen] = None
        self._config_activa: Optional[LlamaServerConfig] = None
        self._timestamp_inicio: Optional[float] = None

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
        stdout: Any = subprocess.DEVNULL,
        stderr: Any = subprocess.DEVNULL,
    ) -> dict[str, Any]:
        """Inicia el proceso llama-server de forma asincrona en segundo plano."""
        if self.esta_activo():
            raise RuntimeError(
                f"El servidor ya esta en ejecucion (PID: {self._proceso.pid}, Puerto: {self._config_activa.port})"
            )

        cmd = config.construir_comando()

        # En Windows evitamos ventana emergente de consola
        creationflags = 0
        if platform.system() == "Windows":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

        proceso = subprocess.Popen(
            cmd,
            stdout=stdout,
            stderr=stderr,
            creationflags=creationflags,
        )

        self._proceso = proceso
        self._config_activa = config
        self._timestamp_inicio = time.time()

        return {
            "pid": proceso.pid,
            "host": config.host,
            "port": config.port,
            "modelo": str(config.modelo_path),
            "comando": cmd,
        }

    def detener_servidor(self, timeout: float = 5.0) -> bool:
        """Detiene de forma limpia el proceso llama-server."""
        if not self.esta_activo():
            self._proceso = None
            self._config_activa = None
            self._timestamp_inicio = None
            return True

        proc = self._proceso
        try:
            proc.terminate()
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2.0)
        except Exception:
            return False
        finally:
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
