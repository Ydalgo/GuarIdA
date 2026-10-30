import hashlib
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import psutil

from guarida_manager import DIRECTORIO_BINARIOS_CPU, DIRECTORIO_BINARIOS_GPU


@dataclass(frozen=True)
class DispositivoGPU:
    identificador: str
    nombre: str
    memoria_mb: float
    memoria_gb: float
    backend: str


@dataclass(frozen=True)
class InformacionHardware:
    modelo_cpu: str
    nucleos_fisicos: int
    nucleos_logicos: int
    ram_total_bytes: int
    ram_total_gb: float
    gpus: tuple[DispositivoGPU, ...]
    nombre_gpu_principal: str
    tiene_aceleracion_gpu: bool
    gtt_disponible_gb: float
    hash_hardware: str


def obtener_modelo_cpu() -> str:
    sistema = platform.system()

    if sistema == "Windows":
        try:
            import winreg

            clave_registro = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            )
            valor_cpu, _ = winreg.QueryValueEx(clave_registro, "ProcessorNameString")
            winreg.CloseKey(clave_registro)
            if valor_cpu and str(valor_cpu).strip():
                return str(valor_cpu).strip()
        except Exception:
            pass

    elif sistema == "Linux":
        ruta_cpuinfo = Path("/proc/cpuinfo")
        if ruta_cpuinfo.exists():
            try:
                with open(ruta_cpuinfo, "r", encoding="utf-8") as archivo:
                    for linea in archivo:
                        if "model name" in linea:
                            return linea.split(":", 1)[1].strip()
            except Exception:
                pass

    elif sistema == "Darwin":
        try:
            resultado = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True,
                text=True,
                check=True,
            )
            if resultado.stdout.strip():
                return resultado.stdout.strip()
        except Exception:
            pass

    return platform.processor().strip() or platform.machine().strip() or "CPU Desconocida"


def obtener_nucleos_cpu() -> tuple[int, int]:
    nucleos_fisicos = psutil.cpu_count(logical=False) or 1
    nucleos_logicos = psutil.cpu_count(logical=True) or nucleos_fisicos
    return nucleos_fisicos, nucleos_logicos


def obtener_memoria_ram_total() -> int:
    return int(psutil.virtual_memory().total)


def convertir_cadena_memoria_a_megabytes(cantidad_texto: str, unidad_texto: str) -> float:
    cantidad = float(cantidad_texto)
    unidad = unidad_texto.upper()

    if unidad in ("GB", "GIB"):
        return round(cantidad * 1024.0, 2)
    elif unidad in ("MB", "MIB"):
        return round(cantidad, 2)
    elif unidad in ("KB", "KIB"):
        return round(cantidad / 1024.0, 2)
    return round(cantidad, 2)


def parsear_dispositivos_llama(salida_texto: str) -> list[DispositivoGPU]:
    dispositivos_detectados: list[DispositivoGPU] = []
    patron_dispositivo = re.compile(
        r"^\s*(?P<id>(?:Vulkan|CUDA|ROCm|Metal|OpenCL|Device)\s*\d*):\s*(?P<nombre>[^(]+?)(?:\s*\((?P<detalles>[^)]+)\))?\s*$",
        re.MULTILINE,
    )
    patron_memoria = re.compile(
        r"(\d+(?:\.\d+)?)\s*(GB|GiB|MB|MiB)",
        re.IGNORECASE,
    )

    for coincidencia in patron_dispositivo.finditer(salida_texto):
        identificador = coincidencia.group("id").strip()
        nombre_dispositivo = coincidencia.group("nombre").strip()
        detalles = coincidencia.group("detalles") or ""

        if nombre_dispositivo.upper() == "CPU" and not identificador.lower().startswith("vulkan"):
            continue

        backend_extraido = "CPU"
        for backend_candidato in ("Vulkan", "CUDA", "ROCm", "Metal", "OpenCL"):
            if backend_candidato.lower() in identificador.lower():
                backend_extraido = backend_candidato
                break

        memoria_mb = 0.0
        coincidencia_memoria = patron_memoria.search(detalles)
        if coincidencia_memoria:
            memoria_mb = convertir_cadena_memoria_a_megabytes(
                coincidencia_memoria.group(1), coincidencia_memoria.group(2)
            )

        memoria_gb = round(memoria_mb / 1024.0, 2)

        dispositivos_detectados.append(
            DispositivoGPU(
                identificador=identificador,
                nombre=nombre_dispositivo,
                memoria_mb=memoria_mb,
                memoria_gb=memoria_gb,
                backend=backend_extraido,
            )
        )

    return dispositivos_detectados


def resolver_ruta_binario_llama(ruta_solicitada: Optional[Path | str] = None) -> Optional[Path]:
    if ruta_solicitada:
        ruta_directa = Path(ruta_solicitada)
        if ruta_directa.exists():
            return ruta_directa

    nombre_ejecutable = "llama-server.exe" if sys.platform == "win32" else "llama-server"

    candidato_gpu = DIRECTORIO_BINARIOS_GPU / nombre_ejecutable
    if candidato_gpu.exists():
        return candidato_gpu

    candidato_cpu = DIRECTORIO_BINARIOS_CPU / nombre_ejecutable
    if candidato_cpu.exists():
        return candidato_cpu

    busqueda_en_path = shutil.which("llama-server")
    if busqueda_en_path:
        return Path(busqueda_en_path)

    return None


def ejecutar_listado_dispositivos_llama(ruta_binario: Path) -> str:
    ejecutable = str(ruta_binario.resolve())
    proceso = subprocess.run(
        [ejecutable, "--list-devices"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    salida_combinada = f"{proceso.stdout}\n{proceso.stderr}".strip()
    return salida_combinada


def detectar_dispositivos_gpu(
    ruta_binario_llama: Optional[Path | str] = None,
) -> tuple[DispositivoGPU, ...]:
    binario_resuelto = resolver_ruta_binario_llama(ruta_binario_llama)
    if not binario_resuelto:
        return ()

    try:
        salida_texto = ejecutar_listado_dispositivos_llama(binario_resuelto)
        dispositivos = parsear_dispositivos_llama(salida_texto)
        return tuple(dispositivos)
    except Exception:
        return ()


def calcular_hash_hardware(
    modelo_cpu: str,
    ram_total_bytes: int,
    nombre_gpu: str,
) -> str:
    huella_cruda = f"{modelo_cpu.strip()}|{ram_total_bytes}|{nombre_gpu.strip()}"
    return hashlib.sha256(huella_cruda.encode("utf-8")).hexdigest()


def obtener_informacion_hardware(
    ruta_binario_llama: Optional[Path | str] = None,
) -> InformacionHardware:
    modelo_cpu = obtener_modelo_cpu()
    nucleos_fisicos, nucleos_logicos = obtener_nucleos_cpu()
    ram_total_bytes = obtener_memoria_ram_total()
    ram_total_gb = round(ram_total_bytes / (1024**3), 2)

    gpus_detectadas = detectar_dispositivos_gpu(ruta_binario_llama)
    tiene_aceleracion = len(gpus_detectadas) > 0

    if tiene_aceleracion:
        gpu_principal = gpus_detectadas[0]
        nombre_gpu_principal = gpu_principal.nombre
        gtt_disponible_gb = gpu_principal.memoria_gb
    else:
        nombre_gpu_principal = "CPU"
        gtt_disponible_gb = 0.0

    hash_hardware = calcular_hash_hardware(
        modelo_cpu=modelo_cpu,
        ram_total_bytes=ram_total_bytes,
        nombre_gpu=nombre_gpu_principal,
    )

    return InformacionHardware(
        modelo_cpu=modelo_cpu,
        nucleos_fisicos=nucleos_fisicos,
        nucleos_logicos=nucleos_logicos,
        ram_total_bytes=ram_total_bytes,
        ram_total_gb=ram_total_gb,
        gpus=gpus_detectadas,
        nombre_gpu_principal=nombre_gpu_principal,
        tiene_aceleracion_gpu=tiene_aceleracion,
        gtt_disponible_gb=gtt_disponible_gb,
        hash_hardware=hash_hardware,
    )


if __name__ == "__main__":
    hardware = obtener_informacion_hardware()
    print("=== GUARIDA: DETECTOR DE HARDWARE ===")
    print(f"Modelo CPU: {hardware.modelo_cpu}")
    print(f"Nucleos Fisicos: {hardware.nucleos_fisicos}")
    print(f"Nucleos Logicos: {hardware.nucleos_logicos}")
    print(f"RAM Total: {hardware.ram_total_gb} GB ({hardware.ram_total_bytes} bytes)")
    print(f"Aceleracion GPU: {'SI' if hardware.tiene_aceleracion_gpu else 'NO'}")
    print(f"Dispositivo Principal: {hardware.nombre_gpu_principal}")
    print(f"Memoria GTT/VRAM Disponible: {hardware.gtt_disponible_gb} GB")
    print(f"Hash Hardware SHA-256: {hardware.hash_hardware}")

