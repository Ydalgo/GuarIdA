import json
import os
import platform
import shutil
import subprocess
import time
import zlib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import psutil

try:
    import zstandard as zstd

    _TIENE_ZSTD = True
except ImportError:
    zstd = None  # type: ignore
    _TIENE_ZSTD = False

from guarida_manager import DIRECTORIO_TELEMETRIA_LOGS
from guarida_manager.hardware import obtener_informacion_hardware
from guarida_manager.logger import obtener_logger

logger = obtener_logger("telemetry")


@dataclass
class MetricasTelemetria:
    cpu_pct: float
    ram_usada_gb: float
    ram_total_gb: float
    ram_pct: float
    vram_usada_gb: float
    vram_total_gb: float
    temperatura_c: Optional[float] = None
    es_critica: bool = False
    disco_usado_gb: float = 0.0
    disco_total_gb: float = 0.0
    disco_pct: float = 0.0
    disco_libre_gb: float = 0.0
    gpu_nombre: str = ""
    gpu_tipo: str = ""
    nucleos_cpu: str = ""


class MonitorTelemetriaHardware:
    """Monitor en tiempo real de métricas críticas de silicio (RAM, CPU, VRAM/GTT y temperatura)."""

    @classmethod
    def obtener_temperatura_actual(cls) -> Optional[float]:
        """Intenta leer la temperatura de CPU/GPU a través de psutil, nvidia-smi o WMI en Windows/Linux."""
        # 1. psutil sensors (Linux / macOS / algunos sistemas Windows con soporte)
        try:
            if hasattr(psutil, "sensors_temperatures"):
                temps = psutil.sensors_temperatures()
                if temps:
                    for nombre, entradas in temps.items():
                        for entrada in entradas:
                            if entrada.current and entrada.current > 0:
                                return float(entrada.current)
        except Exception:
            pass

        # 2. nvidia-smi para GPU dedicada NVIDIA si está presente
        try:
            p = subprocess.run(
                ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=1,
                check=False,
            )
            salida = p.stdout.strip()
            if salida and salida.isdigit():
                return float(salida)
        except Exception:
            pass

        # 3. WMI en Windows (MSAcpi_ThermalZoneTemperature)
        if platform.system() == "Windows":
            try:
                cmd = ["powershell", "-NoProfile", "-Command", "Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature -ErrorAction SilentlyContinue | Select-Object -ExpandProperty CurrentTemperature"]
                p = subprocess.run(cmd, capture_output=True, text=True, timeout=2, check=False)
                salida = p.stdout.strip()
                if salida and salida.isdigit():
                    kelvin_dec = float(salida)
                    celsius = (kelvin_dec - 2732) / 10.0
                    if 0 < celsius < 120:
                        return round(celsius, 1)
            except Exception:
                pass

        return None

    @classmethod
    def capturar_metricas(cls) -> MetricasTelemetria:
        """Captura una instantánea de las métricas vitales del sistema."""
        cpu = psutil.cpu_percent(interval=None)
        vm = psutil.virtual_memory()
        ram_usada = (vm.total - vm.available) / (1024 ** 3)
        ram_total = vm.total / (1024 ** 3)
        ram_pct = vm.percent

        hw = obtener_informacion_hardware()
        vram_total = hw.gtt_disponible_gb if hw.tiene_aceleracion_gpu else 0.0
        vram_usada = min(vram_total, ram_usada * 0.4) if vram_total > 0 else 0.0

        temp = cls.obtener_temperatura_actual()
        es_critica = temp is not None and temp >= 82.0

        try:
            du = shutil.disk_usage(os.getcwd())
            disco_total = du.total / (1024 ** 3)
            disco_usado = du.used / (1024 ** 3)
            disco_libre = du.free / (1024 ** 3)
            disco_pct = (du.used / du.total * 100.0) if du.total > 0 else 0.0
        except Exception:
            disco_total = disco_usado = disco_libre = disco_pct = 0.0

        nucleos_cpu = f"{hw.nucleos_fisicos}C / {hw.nucleos_logicos}T"
        gpu_nombre = hw.nombre_gpu_principal or "CPU"
        gpu_tipo = hw.tipo_gpu_principal or "CPU"

        return MetricasTelemetria(
            cpu_pct=round(cpu, 1),
            ram_usada_gb=round(ram_usada, 2),
            ram_total_gb=round(ram_total, 2),
            ram_pct=round(ram_pct, 1),
            vram_usada_gb=round(vram_usada, 2),
            vram_total_gb=round(vram_total, 2),
            temperatura_c=temp,
            es_critica=es_critica,
            disco_usado_gb=round(disco_usado, 1),
            disco_total_gb=round(disco_total, 1),
            disco_pct=round(disco_pct, 1),
            disco_libre_gb=round(disco_libre, 1),
            gpu_nombre=gpu_nombre,
            gpu_tipo=gpu_tipo,
            nucleos_cpu=nucleos_cpu,
        )

    @classmethod
    def formatear_linea_telemetria(cls) -> str:
        """Genera una barra compacta con los valores de telemetría actuales."""
        m = cls.capturar_metricas()
        temp_str = f"{m.temperatura_c:.0f}°C" if m.temperatura_c is not None else "N/D"
        alerta = " [! ALERTA TÉRMICA !]" if m.es_critica else ""
        return (
            f"[TELEMETRÍA] CPU: {m.cpu_pct:4.1f}% | RAM: {m.ram_usada_gb:.1f}/{m.ram_total_gb:.1f} GB ({m.ram_pct:.0f}%) | "
            f"VRAM/GTT: {m.vram_total_gb:.1f} GB | Temp: {temp_str}{alerta}"
        )

    @classmethod
    def comprobar_y_aplicar_proteccion_termica(
        cls,
        umbral_critico_c: float = 82.0,
        umbral_recuperacion_c: float = 70.0,
        callback_aviso: Optional[Callable[[str], None]] = None,
    ) -> bool:
        """Si la temperatura excede el umbral crítico, pausa la ejecución hasta enfriarse."""
        temp = cls.obtener_temperatura_actual()
        if temp is None or temp < umbral_critico_c:
            return False

        mensaje = (
            f"\n[!] ALERTA DE SEGURIDAD TÉRMICA: Temperatura alcanzada: {temp:.1f}°C "
            f"(Límite crítico: {umbral_critico_c:.0f}°C).\n"
            f"Pausando inferencia y carga de trabajo para permitir el enfriamiento del silicio..."
        )
        logger.warning(mensaje)
        if callback_aviso:
            callback_aviso(mensaje)
        else:
            print(mensaje)

        segundos_espera = 0
        while True:
            time.sleep(3.0)
            segundos_espera += 3
            temp_actual = cls.obtener_temperatura_actual()
            if temp_actual is None or temp_actual <= umbral_recuperacion_c or segundos_espera >= 60:
                msg_ok = f">> Silicio estabilizado ({temp_actual or 'N/D'}°C). Reanudando ejecución."
                logger.info(msg_ok)
                if callback_aviso:
                    callback_aviso(msg_ok)
                else:
                    print(msg_ok)
                break

        return True


class GestorTelemetriaJSONL:
    """Gestor append-only de eventos de telemetría en JSONL particionado por día con rotación Zstd."""

    def __init__(self, directorio_logs: Optional[Path | str] = None) -> None:
        self.directorio_logs = Path(directorio_logs) if directorio_logs else DIRECTORIO_TELEMETRIA_LOGS
        self.directorio_logs.mkdir(parents=True, exist_ok=True)

    def ruta_particion_fecha(self, fecha_str: str) -> Path:
        """Devuelve la ruta de la partición JSONL correspondiente a una fecha YYYY-MM-DD."""
        return self.directorio_logs / f"telemetria_{fecha_str}.jsonl"

    def registrar_evento(
        self,
        tipo_evento: str,
        datos: dict[str, Any],
        timestamp_utc: Optional[datetime] = None,
        auto_rotar: bool = True,
    ) -> Path:
        """Registra un evento estructurado en la partición JSONL diaria sin contención de base de datos."""
        ts = timestamp_utc or datetime.now(timezone.utc)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        else:
            ts = ts.astimezone(timezone.utc)

        fecha_str = ts.strftime("%Y-%m-%d")
        if auto_rotar:
            self.rotar_y_comprimir_particiones_antiguas(fecha_activa=fecha_str)

        ruta = self.ruta_particion_fecha(fecha_str)
        evento = {
            "timestamp_utc": ts.isoformat(),
            "tipo_evento": tipo_evento,
            "datos": datos,
        }
        linea = json.dumps(evento, ensure_ascii=False, separators=(",", ":")) + "\n"
        with open(ruta, "a", encoding="utf-8") as archivo:
            archivo.write(linea)
        return ruta

    def registrar_metricas_hardware(
        self,
        metricas: Optional[MetricasTelemetria] = None,
        timestamp_utc: Optional[datetime] = None,
    ) -> Path:
        """Captura y registra una instantánea de métricas de hardware en JSONL."""
        m = metricas or MonitorTelemetriaHardware.capturar_metricas()
        return self.registrar_evento("metricas_hardware", asdict(m), timestamp_utc=timestamp_utc)

    def rotar_y_comprimir_particiones_antiguas(
        self, fecha_activa: Optional[str] = None
    ) -> list[Path]:
        """Comprime con zstd (o zlib) particiones JSONL de días distintos al activo y elimina el origen."""
        activa = fecha_activa or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        comprimidos: list[Path] = []
        for ruta in sorted(self.directorio_logs.glob("telemetria_*.jsonl")):
            nombre = ruta.name
            if not (nombre.startswith("telemetria_") and nombre.endswith(".jsonl")):
                continue
            fecha_archivo = nombre[len("telemetria_"):-len(".jsonl")]
            if fecha_archivo == activa:
                continue

            raw = ruta.read_bytes()
            if _TIENE_ZSTD and zstd is not None:
                destino = ruta.with_name(f"{nombre}.zst")
                if destino.exists():
                    raw = zstd.ZstdDecompressor().decompress(destino.read_bytes()) + raw
                destino.write_bytes(zstd.ZstdCompressor(level=3).compress(raw))
            else:
                destino = ruta.with_name(f"{nombre}.zlib")
                if destino.exists():
                    raw = zlib.decompress(destino.read_bytes()) + raw
                destino.write_bytes(zlib.compress(raw, level=6))

            ruta.unlink()
            comprimidos.append(destino)

        return comprimidos

    def leer_eventos(self, fecha_str: Optional[str] = None) -> list[dict[str, Any]]:
        """Lee eventos desde particiones JSONL activas y comprimidas (.zst / .zlib)."""
        patron = f"telemetria_{fecha_str}.jsonl*" if fecha_str else "telemetria_*.jsonl*"
        eventos: list[dict[str, Any]] = []

        for ruta in sorted(self.directorio_logs.glob(patron)):
            nombre = ruta.name
            if nombre.endswith(".jsonl"):
                texto = ruta.read_text(encoding="utf-8")
            elif nombre.endswith(".jsonl.zst"):
                if not _TIENE_ZSTD or zstd is None:
                    raise RuntimeError("Se requiere el paquete 'zstandard' para leer telemetría .zst.")
                texto = zstd.ZstdDecompressor().decompress(ruta.read_bytes()).decode("utf-8")
            elif nombre.endswith(".jsonl.zlib"):
                texto = zlib.decompress(ruta.read_bytes()).decode("utf-8")
            else:
                continue

            for linea in texto.splitlines():
                linea_limpia = linea.strip()
                if linea_limpia:
                    eventos.append(json.loads(linea_limpia))

        return eventos
