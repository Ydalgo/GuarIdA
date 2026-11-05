import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from guarida_manager import DIRECTORIO_BINARIOS_CPU, DIRECTORIO_BINARIOS_GPU


def detectar_gpus_dxgi_windows(
    ram_total_gb: float,
    detectar_soporte_vulkan_fn,
    detectar_soporte_cuda_fn,
    calcular_limites_memoria_gpu_fn,
    clasificar_tipo_gpu_fn,
    dispositivo_gpu_cls,
):
    """Detecta adaptadores gráficos nativos en Windows mediante DXGI."""
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

        gpus = []
        idx = 0
        adapter = ctypes.c_void_p()

        soporte_vulkan = detectar_soporte_vulkan_fn()
        soporte_cuda = detectar_soporte_cuda_fn()

        while enum_adapters1(factory, idx, ctypes.byref(adapter)) == 0:
            desc = DXGI_ADAPTER_DESC1()
            adapter_vtable = ctypes.cast(adapter, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
            get_desc_proto = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(DXGI_ADAPTER_DESC1))
            get_desc1 = get_desc_proto(adapter_vtable[10])

            if get_desc1(adapter, ctypes.byref(desc)) == 0:
                if not (desc.Flags & 2):  # Filtrar adaptadores de software (WARP)
                    vram_dedicada_gb = round(desc.DedicatedVideoMemory / (1024**3), 2)
                    memoria_compartida_gb = round(desc.SharedSystemMemory / (1024**3), 2)
                    nombre = desc.Description

                    tipo, es_integrada = clasificar_tipo_gpu_fn(nombre, vram_dedicada_gb)

                    lim_seguro, lim_extremo, _ = calcular_limites_memoria_gpu_fn(
                        vram_dedicada_gb=vram_dedicada_gb,
                        memoria_compartida_gb=memoria_compartida_gb,
                        ram_total_gb=ram_total_gb,
                        es_integrada=es_integrada,
                        sistema="Windows",
                    )

                    memoria_principal_gb = memoria_compartida_gb if es_integrada else vram_dedicada_gb

                    backend = "Vulkan" if soporte_vulkan else "DirectX"
                    if "nvidia" in nombre.lower() and soporte_cuda:
                        backend = "CUDA"

                    gpus.append(
                        dispositivo_gpu_cls(
                            identificador=f"DXGI-{idx}",
                            nombre=nombre,
                            memoria_mb=round(memoria_principal_gb * 1024.0, 2),
                            memoria_gb=memoria_principal_gb,
                            backend=backend,
                            tipo=tipo,
                            vram_dedicada_gb=vram_dedicada_gb,
                            memoria_compartida_gb=memoria_compartida_gb,
                            limite_seguro_gb=lim_seguro,
                            limite_extremo_gb=lim_extremo,
                        )
                    )

            ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(adapter_vtable[2])(adapter)
            idx += 1

        ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtable[2])(factory)
        return gpus
    except Exception:
        return []


def detectar_gpus_linux(
    ram_total_gb: float,
    detectar_soporte_vulkan_fn,
    calcular_limites_memoria_gpu_fn,
    clasificar_tipo_gpu_fn,
    dispositivo_gpu_cls,
):
    """Detecta GPUs en Linux mediante nvidia-smi y los subsistemas DRM/GTT."""
    if platform.system() != "Linux":
        return []

    gpus = []
    soporte_vulkan = detectar_soporte_vulkan_fn()

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
                    lim_seguro, lim_extremo, _ = calcular_limites_memoria_gpu_fn(
                        vram_dedicada_gb=vram_gb,
                        memoria_compartida_gb=0.0,
                        ram_total_gb=ram_total_gb,
                        es_integrada=False,
                        sistema="Linux",
                    )
                    gpus.append(
                        dispositivo_gpu_cls(
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

    # 2. Linux DRM /sys/class/drm
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
                tipo, es_integrada = clasificar_tipo_gpu_fn(nombre, vram_gb)
                lim_seguro, lim_extremo, _ = calcular_limites_memoria_gpu_fn(
                    vram_dedicada_gb=vram_gb,
                    memoria_compartida_gb=gtt_gb,
                    ram_total_gb=ram_total_gb,
                    es_integrada=es_integrada,
                    sistema="Linux",
                )
                memoria_gb = gtt_gb if es_integrada else vram_gb
                gpus.append(
                    dispositivo_gpu_cls(
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


def detectar_gpus_macos(
    ram_total_gb: float,
    calcular_limites_memoria_gpu_fn,
    dispositivo_gpu_cls,
):
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

        lim_seguro, lim_extremo, _ = calcular_limites_memoria_gpu_fn(
            vram_dedicada_gb=0.0,
            memoria_compartida_gb=ram_total_gb,
            ram_total_gb=ram_total_gb,
            es_integrada=True,
            sistema="Darwin",
        )
        return [
            dispositivo_gpu_cls(
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
    salida_texto: str,
    ram_total_gb: float,
    convertir_cadena_memoria_fn,
    clasificar_tipo_gpu_fn,
    calcular_limites_memoria_gpu_fn,
    dispositivo_gpu_cls,
):
    """Parsea la salida del comando --list-devices de llama.cpp."""
    dispositivos_detectados = []
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
            memoria_mb = convertir_cadena_memoria_fn(
                coincidencia_memoria.group(1), coincidencia_memoria.group(2)
            )

        memoria_gb = round(memoria_mb / 1024.0, 2)
        tipo, es_integrada = clasificar_tipo_gpu_fn(nombre_dispositivo, memoria_gb)
        lim_seguro, lim_extremo, _ = calcular_limites_memoria_gpu_fn(
            vram_dedicada_gb=memoria_gb if not es_integrada else 0.0,
            memoria_compartida_gb=memoria_gb if es_integrada else 0.0,
            ram_total_gb=ram_total_gb,
            es_integrada=es_integrada,
        )

        dispositivos_detectados.append(
            dispositivo_gpu_cls(
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
    """Resuelve la ruta del binario de inferencia unificando con GestorHerramientasBunker (N16)."""
    if ruta_solicitada:
        try:
            ruta_directa = Path(ruta_solicitada)
            if ruta_directa.exists():
                return ruta_directa
        except (OSError, PermissionError):
            pass

    try:
        from guarida_manager.downloader.tools import GestorHerramientasBunker
        return GestorHerramientasBunker.resolver_ruta_ejecutable("llama-server")
    except Exception:
        nombre_ejecutable = "llama-server.exe" if sys.platform == "win32" else "llama-server"
        candidatos = [
            DIRECTORIO_BINARIOS_GPU / nombre_ejecutable,
            DIRECTORIO_BINARIOS_CPU / nombre_ejecutable,
        ]
        for c in candidatos:
            try:
                if c.exists():
                    return c
            except (OSError, PermissionError):
                continue

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
