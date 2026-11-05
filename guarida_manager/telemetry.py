import os
import platform
import subprocess
import time
from dataclasses import dataclass
from typing import Callable, Optional

import psutil

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

        return MetricasTelemetria(
            cpu_pct=round(cpu, 1),
            ram_usada_gb=round(ram_usada, 2),
            ram_total_gb=round(ram_total, 2),
            ram_pct=round(ram_pct, 1),
            vram_usada_gb=round(vram_usada, 2),
            vram_total_gb=round(vram_total, 2),
            temperatura_c=temp,
            es_critica=es_critica,
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
