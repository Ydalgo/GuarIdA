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
    tipo: str = "Desconocida"              # "Integrada / APU", "Dedicada", "Software"
    vram_dedicada_gb: float = 0.0          # VRAM fisica en la placa (e.g. 128 MB en APU, 12 GB en dedicada)
    memoria_compartida_gb: float = 0.0     # Memoria compartida asignada por el SO (WDDM GTT / Linux DRM)
    limite_seguro_gb: float = 0.0          # Margen seguro de uso (80-85% del heap)
    limite_extremo_gb: float = 0.0         # Limite maximo forzable al extremo (RAM - reserva SO)


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
    memoria_extrema_forzable_gb: float = 0.0    # Memoria maxima que se puede forzar para inferencia
    tipo_gpu_principal: str = "CPU"
    reserva_sistema_gb: float = 0.0             # Reserva minima vital para que el SO no sufra OOM


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


def clasificar_tipo_gpu(nombre: str, vram_dedicada_gb: float) -> tuple[str, bool]:
    """Determina si la GPU es una integrada/APU o dedicada segun nombre y VRAM."""
    nombre_lower = nombre.lower()
    pistas_integrada = (
        "intel",
        "iris",
        "uhd",
        "hd graphics",
        "radeon graphics",
        "vega",
        "apu",
        "680m",
        "780m",
        "890m",
        "microsoft basic render",
    )
    es_integrada = any(p in nombre_lower for p in pistas_integrada) or vram_dedicada_gb < 1.0
    tipo = "Integrada / APU" if es_integrada else "Dedicada"
    return tipo, es_integrada


def calcular_limites_memoria_gpu(
    vram_dedicada_gb: float,
    memoria_compartida_gb: float,
    ram_total_gb: float,
    es_integrada: bool,
    sistema: Optional[str] = None,
) -> tuple[float, float, float]:
    """Calcula (limite_seguro_gb, limite_extremo_gb, reserva_so_gb).

    El 'limite_extremo_gb' cuantifica cuanta memoria se puede forzar al subsistema
    grafico / GTT al maximo sin provocar un colapso del sistema operativo por OOM.
    """
    if sistema is None:
        sistema = platform.system()

    if sistema == "Windows":
        reserva_so_gb = 3.5
    elif sistema == "Darwin":
        reserva_so_gb = 2.5
    else:
        reserva_so_gb = 1.8

    if es_integrada:
        # En APU / iGPU la memoria real reside en el espacio GTT / RAM compartida
        limite_seguro_gb = round(max(vram_dedicada_gb, memoria_compartida_gb * 0.85), 2)
        # Limite extremo: Forzar toda la RAM disponible menos la reserva minima vital del SO
        limite_extremo_gb = round(max(memoria_compartida_gb, ram_total_gb - reserva_so_gb), 2)
    else:
        # En GPUs dedicadas:
        # Limite seguro: 85% de la VRAM dedicada pura
        limite_seguro_gb = round(max(0.0, vram_dedicada_gb * 0.85), 2)
        # Limite extremo en VRAM fisica: VRAM total menos 0.5 GB para framebuffer del escritorio
        limite_extremo_gb = round(max(0.0, vram_dedicada_gb - 0.5), 2)

    return limite_seguro_gb, limite_extremo_gb, reserva_so_gb


def detectar_soporte_vulkan() -> bool:
    """Verifica si la libreria o entorno Vulkan esta presente en el sistema."""
    if shutil.which("vulkaninfo"):
        return True
    try:
        import ctypes

        sistema = platform.system()
        if sistema == "Windows":
            ctypes.cdll.LoadLibrary("vulkan-1.dll")
            return True
        elif sistema == "Linux":
            ctypes.cdll.LoadLibrary("libvulkan.so.1")
            return True
    except Exception:
        pass
    return False


def detectar_soporte_cuda() -> bool:
    """Verifica si NVIDIA CUDA esta disponible."""
    if shutil.which("nvidia-smi"):
        return True
    try:
        import ctypes

        sistema = platform.system()
        if sistema == "Windows":
            ctypes.cdll.LoadLibrary("nvcuda.dll")
            return True
        elif sistema == "Linux":
            ctypes.cdll.LoadLibrary("libcuda.so.1")
            return True
    except Exception:
        pass
    return False


def detectar_gpus_dxgi_windows(ram_total_gb: float) -> list[DispositivoGPU]:
    """Detecta adaptadores graficos nativos en Windows mediante DXGI."""
    if platform.system() != "Windows":
        return []

    try:
        import ctypes
        from ctypes import wintypes

        class LUID(ctypes.Structure):
            _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]

        class DXGI_ADAPTER_DESC1(ctypes.Structure):
            _fields_ = [
                ("Description", wintypes.WCHAR * 128),
                ("VendorId", wintypes.UINT),
                ("DeviceId", wintypes.UINT),
                ("SubSysId", wintypes.UINT),
                ("Revision", wintypes.UINT),
                ("DedicatedVideoMemory", ctypes.c_size_t),
                ("DedicatedSystemMemory", ctypes.c_size_t),
                ("SharedSystemMemory", ctypes.c_size_t),
                ("AdapterLuid", LUID),
                ("Flags", wintypes.UINT),
            ]

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        dxgi = ctypes.windll.dxgi
        factory = ctypes.c_void_p()
        iid = GUID(
            0x770AAE78,
            0xF26F,
            0x4DBA,
            (ctypes.c_ubyte * 8)(0xA8, 0x29, 0x25, 0x3C, 0x83, 0xD1, 0xB3, 0x87),
        )

        if dxgi.CreateDXGIFactory1(ctypes.byref(iid), ctypes.byref(factory)) != 0:
            return []

        vtable = ctypes.cast(factory, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        enum_proto = ctypes.WINFUNCTYPE(
            ctypes.c_long, ctypes.c_void_p, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p)
        )
        enum_adapters1 = enum_proto(vtable[12])

        gpus: list[DispositivoGPU] = []
        idx = 0
        adapter = ctypes.c_void_p()

        soporte_vulkan = detectar_soporte_vulkan()
        soporte_cuda = detectar_soporte_cuda()

        while enum_adapters1(factory, idx, ctypes.byref(adapter)) == 0:
            adapter_vtable = ctypes.cast(adapter, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
            desc_proto = ctypes.WINFUNCTYPE(
                ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(DXGI_ADAPTER_DESC1)
            )
            get_desc1 = desc_proto(adapter_vtable[10])

            desc = DXGI_ADAPTER_DESC1()
            if get_desc1(adapter, ctypes.byref(desc)) == 0:
                # Omitir adaptadores exclusivamente virtuales de software (DXGI_ADAPTER_FLAG_SOFTWARE = 2)
                if not (desc.Flags & 2):
                    vram_dedicada_gb = round(desc.DedicatedVideoMemory / (1024**3), 2)
                    memoria_compartida_gb = round(desc.SharedSystemMemory / (1024**3), 2)
                    nombre = desc.Description.strip()

                    tipo, es_integrada = clasificar_tipo_gpu(nombre, vram_dedicada_gb)

                    backend = "Vulkan" if soporte_vulkan else "DirectX"
                    if "nvidia" in nombre.lower() and soporte_cuda:
                        backend = "CUDA"

                    limite_seguro, limite_extremo, _ = calcular_limites_memoria_gpu(
                        vram_dedicada_gb=vram_dedicada_gb,
                        memoria_compartida_gb=memoria_compartida_gb,
                        ram_total_gb=ram_total_gb,
                        es_integrada=es_integrada,
                        sistema="Windows",
                    )

                    memoria_total_gb = memoria_compartida_gb if es_integrada else vram_dedicada_gb
                    memoria_total_mb = round(memoria_total_gb * 1024.0, 2)

                    gpus.append(
                        DispositivoGPU(
                            identificador=f"GPU-{idx}",
                            nombre=nombre,
                            memoria_mb=memoria_total_mb,
                            memoria_gb=memoria_total_gb,
                            backend=backend,
                            tipo=tipo,
                            vram_dedicada_gb=vram_dedicada_gb,
                            memoria_compartida_gb=memoria_compartida_gb,
                            limite_seguro_gb=limite_seguro,
                            limite_extremo_gb=limite_extremo,
                        )
                    )

            ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(adapter_vtable[2])(adapter)
            idx += 1

        ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtable[2])(factory)
        return gpus
    except Exception:
        return []


def detectar_gpus_linux(ram_total_gb: float) -> list[DispositivoGPU]:
    """Detecta GPUs en Linux mediante nvidia-smi y los subsistemas DRM/GTT."""
    if platform.system() != "Linux":
        return []

    gpus: list[DispositivoGPU] = []
    soporte_vulkan = detectar_soporte_vulkan()

    # 1. NVIDIA SMI
    if shutil.which("nvidia-smi"):
        try:
            cmd = ["nvidia-smi", "--query-gpu=index,name,memory.total", "--format=csv,noheader,nounits"]
            salida = subprocess.check_output(cmd, text=True, timeout=5)
            for linea in salida.strip().splitlines():
                partes = [p.strip() for p in linea.split(",")]
                if len(partes) >= 3:
                    idx_str, nombre_gpu, mb_str = partes[0], partes[1], partes[2]
                    total_mb = float(mb_str)
                    vram_gb = round(total_mb / 1024.0, 2)
                    lim_seguro, lim_extremo, _ = calcular_limites_memoria_gpu(
                        vram_dedicada_gb=vram_gb,
                        memoria_compartida_gb=0.0,
                        ram_total_gb=ram_total_gb,
                        es_integrada=False,
                        sistema="Linux",
                    )
                    gpus.append(
                        DispositivoGPU(
                            identificador=f"CUDA-{idx_str}",
                            nombre=nombre_gpu,
                            memoria_mb=total_mb,
                            memoria_gb=vram_gb,
                            backend="CUDA",
                            tipo="Dedicada",
                            vram_dedicada_gb=vram_gb,
                            memoria_compartida_gb=0.0,
                            limite_seguro_gb=lim_seguro,
                            limite_extremo_gb=lim_extremo,
                        )
                    )
        except Exception:
            pass

    # 2. Linux DRM /sys/class/drm (APUs AMD Radeon, Intel Iris Xe)
    drm_path = Path("/sys/class/drm")
    if drm_path.exists():
        card_dirs = sorted([d for d in drm_path.iterdir() if d.is_dir() and re.match(r"^card\d+$", d.name)])
        for card in card_dirs:
            device_dir = card / "device"
            if not device_dir.exists():
                continue

            vram_bytes = 0
            gtt_bytes = 0

            vram_file = device_dir / "mem_info_vram_total"
            gtt_file = device_dir / "mem_info_gtt_total"

            if vram_file.exists():
                try:
                    vram_bytes = int(vram_file.read_text().strip())
                except Exception:
                    pass

            if gtt_file.exists():
                try:
                    gtt_bytes = int(gtt_file.read_text().strip())
                except Exception:
                    pass

            vram_gb = round(vram_bytes / (1024**3), 2)
            gtt_gb = round(gtt_bytes / (1024**3), 2)

            if vram_gb > 0 or gtt_gb > 0:
                nombre = f"GPU DRM ({card.name})"
                tipo, es_integrada = clasificar_tipo_gpu(nombre, vram_gb)
                lim_seguro, lim_extremo, _ = calcular_limites_memoria_gpu(
                    vram_dedicada_gb=vram_gb,
                    memoria_compartida_gb=gtt_gb,
                    ram_total_gb=ram_total_gb,
                    es_integrada=es_integrada,
                    sistema="Linux",
                )
                memoria_gb = gtt_gb if es_integrada else vram_gb
                gpus.append(
                    DispositivoGPU(
                        identificador=f"DRM-{card.name}",
                        nombre=nombre,
                        memoria_mb=round(memoria_gb * 1024.0, 2),
                        memoria_gb=memoria_gb,
                        backend="Vulkan" if soporte_vulkan else "ROCm/DRM",
                        tipo=tipo,
                        vram_dedicada_gb=vram_gb,
                        memoria_compartida_gb=gtt_gb,
                        limite_seguro_gb=lim_seguro,
                        limite_extremo_gb=lim_extremo,
                    )
                )

    return gpus


def detectar_gpus_macos(ram_total_gb: float) -> list[DispositivoGPU]:
    """Detecta GPU Apple Silicon o discreta en macOS."""
    if platform.system() != "Darwin":
        return []

    try:
        salida = subprocess.check_output(["system_profiler", "SPDisplaysDataType"], text=True, timeout=5)
        nombre = "Apple Silicon GPU"
        for linea in salida.splitlines():
            if "Chipset Model:" in linea:
                nombre = linea.split(":", 1)[1].strip()
                break

        lim_seguro, lim_extremo, _ = calcular_limites_memoria_gpu(
            vram_dedicada_gb=0.0,
            memoria_compartida_gb=ram_total_gb,
            ram_total_gb=ram_total_gb,
            es_integrada=True,
            sistema="Darwin",
        )
        return [
            DispositivoGPU(
                identificador="Metal0",
                nombre=nombre,
                memoria_mb=round(ram_total_gb * 1024.0, 2),
                memoria_gb=ram_total_gb,
                backend="Metal",
                tipo="Integrada / UMA",
                vram_dedicada_gb=0.0,
                memoria_compartida_gb=ram_total_gb,
                limite_seguro_gb=lim_seguro,
                limite_extremo_gb=lim_extremo,
            )
        ]
    except Exception:
        return []


def parsear_dispositivos_llama(
    salida_texto: str, ram_total_gb: Optional[float] = None
) -> list[DispositivoGPU]:
    """Parsea la salida del comando --list-devices de llama.cpp."""
    if ram_total_gb is None:
        ram_total_gb = round(obtener_memoria_ram_total() / (1024**3), 2)

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
        tipo, es_integrada = clasificar_tipo_gpu(nombre_dispositivo, memoria_gb)
        lim_seguro, lim_extremo, _ = calcular_limites_memoria_gpu(
            vram_dedicada_gb=memoria_gb if not es_integrada else 0.0,
            memoria_compartida_gb=memoria_gb if es_integrada else 0.0,
            ram_total_gb=ram_total_gb,
            es_integrada=es_integrada,
        )

        dispositivos_detectados.append(
            DispositivoGPU(
                identificador=identificador,
                nombre=nombre_dispositivo,
                memoria_mb=memoria_mb,
                memoria_gb=memoria_gb,
                backend=backend_extraido,
                tipo=tipo,
                vram_dedicada_gb=memoria_gb if not es_integrada else 0.0,
                memoria_compartida_gb=memoria_gb if es_integrada else 0.0,
                limite_seguro_gb=lim_seguro,
                limite_extremo_gb=lim_extremo,
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
    ram_total_gb: Optional[float] = None,
) -> tuple[DispositivoGPU, ...]:
    """Detecta GPUs disponibles mediante binarios llama.cpp o deteccion nativa del SO."""
    if ram_total_gb is None:
        ram_total_gb = round(obtener_memoria_ram_total() / (1024**3), 2)

    # 1. Intentar con llama-server si el binario ya existe
    binario_resuelto = resolver_ruta_binario_llama(ruta_binario_llama)
    if binario_resuelto:
        try:
            salida_texto = ejecutar_listado_dispositivos_llama(binario_resuelto)
            dispositivos_llama = parsear_dispositivos_llama(salida_texto, ram_total_gb=ram_total_gb)
            if dispositivos_llama:
                return tuple(dispositivos_llama)
        except Exception:
            pass

    # 2. Deteccion nativa multiplataforma (Windows DXGI, Linux DRM/CUDA, macOS Metal)
    sistema = platform.system()
    gpus_nativas: list[DispositivoGPU] = []
    if sistema == "Windows":
        gpus_nativas = detectar_gpus_dxgi_windows(ram_total_gb)
    elif sistema == "Linux":
        gpus_nativas = detectar_gpus_linux(ram_total_gb)
    elif sistema == "Darwin":
        gpus_nativas = detectar_gpus_macos(ram_total_gb)

    return tuple(gpus_nativas)


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

    gpus_detectadas = detectar_dispositivos_gpu(ruta_binario_llama, ram_total_gb=ram_total_gb)
    tiene_aceleracion = len(gpus_detectadas) > 0

    sistema = platform.system()
    reserva_so_gb = 3.5 if sistema == "Windows" else (2.5 if sistema == "Darwin" else 1.8)

    if tiene_aceleracion:
        gpu_principal = gpus_detectadas[0]
        nombre_gpu_principal = gpu_principal.nombre
        tipo_gpu_principal = gpu_principal.tipo
        gtt_disponible_gb = (
            gpu_principal.memoria_compartida_gb
            if gpu_principal.memoria_compartida_gb > 0
            else gpu_principal.memoria_gb
        )
        memoria_extrema = gpu_principal.limite_extremo_gb
    else:
        nombre_gpu_principal = "CPU"
        tipo_gpu_principal = "CPU"
        gtt_disponible_gb = 0.0
        memoria_extrema = max(0.0, round(ram_total_gb - reserva_so_gb, 2))

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
        memoria_extrema_forzable_gb=memoria_extrema,
        tipo_gpu_principal=tipo_gpu_principal,
        reserva_sistema_gb=reserva_so_gb,
    )


if __name__ == "__main__":
    hardware = obtener_informacion_hardware()
    print("=== GUARIDA: DETECTOR DE HARDWARE Y LIMITES DE MEMORIA ===")
    print(f"Modelo CPU:                  {hardware.modelo_cpu}")
    print(f"Nucleos Fisicos / Logicos:   {hardware.nucleos_fisicos} / {hardware.nucleos_logicos}")
    print(f"RAM Total del Sistema:       {hardware.ram_total_gb} GB ({hardware.ram_total_bytes:,} bytes)")
    print(f"Aceleracion GPU Activa:      {'SI' if hardware.tiene_aceleracion_gpu else 'NO'}")
    print(f"Dispositivo Principal:       {hardware.nombre_gpu_principal} ({hardware.tipo_gpu_principal})")
    print(f"Memoria Compartida / GTT:    {hardware.gtt_disponible_gb} GB")
    print(f"Reserva Minima Sistema SO:   {hardware.reserva_sistema_gb} GB")
    print(f"MEMORIA EXTREMA FORZABLE:    {hardware.memoria_extrema_forzable_gb} GB")
    print(f"Hash Hardware SHA-256:       {hardware.hash_hardware}")

    if hardware.gpus:
        print("\nDetalle de Adaptadores Graficos:")
        for g in hardware.gpus:
            print(f"  * {g.identificador}: {g.nombre} [{g.backend}]")
            print(f"    - Tipo:                   {g.tipo}")
            print(f"    - VRAM Dedicada Fisica:   {g.vram_dedicada_gb} GB")
            print(f"    - Memoria Compartida SO:  {g.memoria_compartida_gb} GB")
            print(f"    - Limite Seguro (85%):    {g.limite_seguro_gb} GB")
            print(f"    - LIMITE MAXIMO EXTREMO:  {g.limite_extremo_gb} GB")
