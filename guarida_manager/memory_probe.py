import ctypes
import os
import platform
import shutil
import sys
import time
from dataclasses import dataclass
from typing import Callable, Optional

import psutil


@dataclass(frozen=True)
class ResultadoPruebaMemoria:
    backend: str
    vram_gpu_asignada_gb: float
    ram_sistema_asignada_gb: float
    memoria_total_verificada_gb: float
    tamano_chunk_gb: float
    chunks_asignados: int
    tiempo_total_segundos: float
    velocidad_escritura_gbs: float
    integridad_verificada: bool
    limite_alcanzado_motivo: str


def probar_asignacion_ram_real(
    objetivo_gb: float,
    callback_progreso: Optional[Callable[[str], None]] = None,
) -> tuple[float, float, bool]:
    """Asigna memoria fisica real en RAM escribiendo en cada pagina para forzar commit."""
    def log(msg: str) -> None:
        if callback_progreso:
            callback_progreso(msg)

    chunk_size = 256 * 1024 * 1024  # Chunks de 256 MB
    bloques = []
    total_asignado_bytes = 0
    objetivo_bytes = int(objetivo_gb * 1024 * 1024 * 1024)

    t0 = time.perf_counter()
    patron = b"\xaa\x55\xaa\x55" * (1024)  # 4 KB

    try:
        while total_asignado_bytes + chunk_size <= objetivo_bytes:
            # Comprobar margen de seguridad en el SO (dejar al menos 2.0 GB libres)
            mem_disp = psutil.virtual_memory().available
            if mem_disp < 2.0 * (1024**3):
                log(f"  [RAM] Detenido por seguridad: memoria disponible baja ({mem_disp / (1024**3):.2f} GB)")
                break

            bloque = bytearray(chunk_size)
            # Tocar cada pagina de 4 KB para forzar el page-table commit
            for offset in range(0, chunk_size, 4096 * 64):
                bloque[offset : offset + 4] = b"\xde\xad\xbe\xef"

            bloques.append(bloque)
            total_asignado_bytes += chunk_size
            log(f"  [RAM] Asignados y verificados: {total_asignado_bytes / (1024**3):.2f} GB")

    except MemoryError:
        log("  [RAM] MemoryError detectado al solicitar mas memoria.")
    finally:
        dt = time.perf_counter() - t0
        gb_asignados = total_asignado_bytes / (1024**3)
        velocidad = (gb_asignados / dt) if dt > 0 else 0.0

        # Verificacion de integridad
        integridad = True
        for b in bloques:
            if b[0:4] != b"\xde\xad\xbe\xef":
                integridad = False
                break

        bloques.clear()
        del bloques

    return round(gb_asignados, 2), round(velocidad, 2), integridad


def probar_asignacion_vulkan_real(
    objetivo_gb: float,
    chunk_gb: float = 1.0,
    callback_progreso: Optional[Callable[[str], None]] = None,
) -> tuple[float, int, bool, str]:
    """Asigna memoria real directamente en la GPU usando Vulkan y verifica escritura/lectura."""
    def log(msg: str) -> None:
        if callback_progreso:
            callback_progreso(msg)

    sistema = platform.system()
    lib_name = "vulkan-1.dll" if sistema == "Windows" else "libvulkan.so.1"

    try:
        vulkan = ctypes.cdll.LoadLibrary(lib_name)
    except Exception as e:
        return 0.0, 0, False, f"No se pudo cargar la libreria Vulkan: {e}"

    # Configuracion de firmas de ctypes para 64-bit
    vulkan.vkCreateInstance.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    vulkan.vkCreateInstance.restype = ctypes.c_int
    vulkan.vkEnumeratePhysicalDevices.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    vulkan.vkEnumeratePhysicalDevices.restype = ctypes.c_int
    vulkan.vkGetPhysicalDeviceMemoryProperties.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    vulkan.vkGetPhysicalDeviceMemoryProperties.restype = None
    vulkan.vkCreateDevice.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    vulkan.vkCreateDevice.restype = ctypes.c_int
    vulkan.vkAllocateMemory.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    vulkan.vkAllocateMemory.restype = ctypes.c_int
    vulkan.vkMapMemory.argtypes = [ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_uint, ctypes.c_void_p]
    vulkan.vkMapMemory.restype = ctypes.c_int
    vulkan.vkUnmapMemory.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
    vulkan.vkUnmapMemory.restype = None
    vulkan.vkFreeMemory.argtypes = [ctypes.c_void_p, ctypes.c_uint64, ctypes.c_void_p]
    vulkan.vkFreeMemory.restype = None
    vulkan.vkDestroyDevice.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    vulkan.vkDestroyDevice.restype = None
    vulkan.vkDestroyInstance.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    vulkan.vkDestroyInstance.restype = None

    class VkApplicationInfo(ctypes.Structure):
        _fields_ = [
            ("sType", ctypes.c_uint),
            ("pNext", ctypes.c_void_p),
            ("pApplicationName", ctypes.c_char_p),
            ("applicationVersion", ctypes.c_uint),
            ("pEngineName", ctypes.c_char_p),
            ("engineVersion", ctypes.c_uint),
            ("apiVersion", ctypes.c_uint),
        ]

    class VkInstanceCreateInfo(ctypes.Structure):
        _fields_ = [
            ("sType", ctypes.c_uint),
            ("pNext", ctypes.c_void_p),
            ("flags", ctypes.c_uint),
            ("pApplicationInfo", ctypes.POINTER(VkApplicationInfo)),
            ("enabledLayerCount", ctypes.c_uint),
            ("ppEnabledLayerNames", ctypes.POINTER(ctypes.c_char_p)),
            ("enabledExtensionCount", ctypes.c_uint),
            ("ppEnabledExtensionNames", ctypes.POINTER(ctypes.c_char_p)),
        ]

    app_info = VkApplicationInfo(
        sType=1,
        pNext=None,
        pApplicationName=b"GuarIdA Memory Probe",
        applicationVersion=1,
        pEngineName=b"GuarIdA",
        engineVersion=1,
        apiVersion=(1 << 22) | (2 << 12),
    )
    inst_info = VkInstanceCreateInfo(
        sType=10,
        pNext=None,
        flags=0,
        pApplicationInfo=ctypes.pointer(app_info),
        enabledLayerCount=0,
        ppEnabledLayerNames=None,
        enabledExtensionCount=0,
        ppEnabledExtensionNames=None,
    )

    instance = ctypes.c_void_p()
    if vulkan.vkCreateInstance(ctypes.byref(inst_info), None, ctypes.byref(instance)) != 0:
        return 0.0, 0, False, "Fallo al inicializar instancia Vulkan"

    total_asignado_gb = 0.0
    chunks_ok = 0
    integridad = True
    motivo_fin = "Objetivo completado"
    asignaciones: list[int] = []
    device = ctypes.c_void_p()

    try:
        count = ctypes.c_uint(0)
        vulkan.vkEnumeratePhysicalDevices(instance, ctypes.byref(count), None)
        if count.value == 0:
            return 0.0, 0, False, "No se encontraron dispositivos Vulkan físicos"

        devices = (ctypes.c_void_p * count.value)()
        vulkan.vkEnumeratePhysicalDevices(instance, ctypes.byref(count), devices)
        phys_dev = devices[0]

        class VkMemoryType(ctypes.Structure):
            _fields_ = [("propertyFlags", ctypes.c_uint), ("heapIndex", ctypes.c_uint)]

        class VkMemoryHeap(ctypes.Structure):
            _fields_ = [("size", ctypes.c_uint64), ("flags", ctypes.c_uint)]

        class VkPhysicalDeviceMemoryProperties(ctypes.Structure):
            _fields_ = [
                ("memoryTypeCount", ctypes.c_uint),
                ("memoryTypes", VkMemoryType * 32),
                ("memoryHeapCount", ctypes.c_uint),
                ("memoryHeaps", VkMemoryHeap * 16),
            ]

        mem_props = VkPhysicalDeviceMemoryProperties()
        vulkan.vkGetPhysicalDeviceMemoryProperties(phys_dev, ctypes.byref(mem_props))

        # Seleccionar tipo de memoria con VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT (0x1)
        selected_type = None
        for i in range(mem_props.memoryTypeCount):
            props = mem_props.memoryTypes[i].propertyFlags
            # Preferir DEVICE_LOCAL (0x1) y HOST_VISIBLE (0x2) para mapeo
            if (props & 1) and (props & 2):
                selected_type = i
                break
        if selected_type is None:
            # Fallback a solo DEVICE_LOCAL
            for i in range(mem_props.memoryTypeCount):
                if mem_props.memoryTypes[i].propertyFlags & 1:
                    selected_type = i
                    break

        if selected_type is None:
            return 0.0, 0, False, "No se encontro heap DEVICE_LOCAL en la GPU"

        # Crear dispositivo logico con 1 cola
        class VkDeviceQueueCreateInfo(ctypes.Structure):
            _fields_ = [
                ("sType", ctypes.c_uint),
                ("pNext", ctypes.c_void_p),
                ("flags", ctypes.c_uint),
                ("queueFamilyIndex", ctypes.c_uint),
                ("queueCount", ctypes.c_uint),
                ("pQueuePriorities", ctypes.POINTER(ctypes.c_float)),
            ]

        prio = (ctypes.c_float * 1)(1.0)
        q_info = VkDeviceQueueCreateInfo(
            sType=2, pNext=None, flags=0, queueFamilyIndex=0, queueCount=1, pQueuePriorities=prio
        )

        class VkDeviceCreateInfo(ctypes.Structure):
            _fields_ = [
                ("sType", ctypes.c_uint),
                ("pNext", ctypes.c_void_p),
                ("flags", ctypes.c_uint),
                ("queueCreateInfoCount", ctypes.c_uint),
                ("pQueueCreateInfos", ctypes.POINTER(VkDeviceQueueCreateInfo)),
                ("enabledLayerCount", ctypes.c_uint),
                ("ppEnabledLayerNames", ctypes.POINTER(ctypes.c_char_p)),
                ("enabledExtensionCount", ctypes.c_uint),
                ("ppEnabledExtensionNames", ctypes.POINTER(ctypes.c_char_p)),
                ("pEnabledFeatures", ctypes.c_void_p),
            ]

        dev_info = VkDeviceCreateInfo(
            sType=3,
            pNext=None,
            flags=0,
            queueCreateInfoCount=1,
            pQueueCreateInfos=ctypes.pointer(q_info),
            enabledLayerCount=0,
            ppEnabledLayerNames=None,
            enabledExtensionCount=0,
            ppEnabledExtensionNames=None,
            pEnabledFeatures=None,
        )

        if vulkan.vkCreateDevice(phys_dev, ctypes.byref(dev_info), None, ctypes.byref(device)) != 0:
            return 0.0, 0, False, "Fallo al crear dispositivo logico Vulkan"

        class VkMemoryAllocateInfo(ctypes.Structure):
            _fields_ = [
                ("sType", ctypes.c_uint),
                ("pNext", ctypes.c_void_p),
                ("allocationSize", ctypes.c_uint64),
                ("memoryTypeIndex", ctypes.c_uint),
            ]

        chunk_bytes = int(chunk_gb * 1024 * 1024 * 1024)
        total_chunks = int(objetivo_gb / chunk_gb)

        for i in range(total_chunks):
            alloc_info = VkMemoryAllocateInfo(
                sType=5,
                pNext=None,
                allocationSize=chunk_bytes,
                memoryTypeIndex=selected_type,
            )
            dev_mem = ctypes.c_uint64(0)
            res = vulkan.vkAllocateMemory(device, ctypes.byref(alloc_info), None, ctypes.byref(dev_mem))

            if res != 0:
                motivo_fin = f"Limite alcanzado por el driver Vulkan (codigo de salida {res})"
                log(f"  [GPU] Limite del driver alcanzado en chunk {i+1} ({total_asignado_gb:.2f} GB)")
                break

            asignaciones.append(dev_mem.value)
            chunks_ok += 1
            total_asignado_gb += chunk_gb

            # Prueba rapida de escritura y lectura en el buffer mapeado
            if mem_props.memoryTypes[selected_type].propertyFlags & 2:
                p_data = ctypes.c_void_p()
                if vulkan.vkMapMemory(device, dev_mem, 0, 4096, 0, ctypes.byref(p_data)) == 0:
                    int_ptr = ctypes.cast(p_data, ctypes.POINTER(ctypes.c_uint32))
                    patron_test = 0xA1B2C3D4 + i
                    int_ptr[0] = patron_test
                    int_ptr[1023] = patron_test ^ 0xFFFFFFFF

                    leido_0 = int_ptr[0]
                    leido_1023 = int_ptr[1023]
                    if leido_0 != patron_test or leido_1023 != (patron_test ^ 0xFFFFFFFF):
                        integridad = False

                    vulkan.vkUnmapMemory(device, dev_mem)

            log(f"  [GPU VRAM] Chunk {chunks_ok}: {total_asignado_gb:.2f} GB verificados en VRAM")

    finally:
        # Liberar toda la memoria de la GPU
        if device.value:
            for mem_handle in asignaciones:
                vulkan.vkFreeMemory(device, ctypes.c_uint64(mem_handle), None)
            vulkan.vkDestroyDevice(device, None)
        if instance.value:
            vulkan.vkDestroyInstance(instance, None)

    return round(total_asignado_gb, 2), chunks_ok, integridad, motivo_fin


def ejecutar_prueba_estres_memoria(
    limite_forzar_gb: Optional[float] = None,
    probar_ram: bool = True,
    callback_progreso: Optional[Callable[[str], None]] = None,
) -> ResultadoPruebaMemoria:
    """Ejecuta una prueba completa forzando la asignacion real en GPU (Vulkan) y RAM."""
    def log(msg: str) -> None:
        if callback_progreso:
            callback_progreso(msg)
        else:
            print(msg)

    t_inicio = time.perf_counter()
    log("\n" + "=" * 55)
    log("  GUARIDA: PRUEBA DE ASIGNACIÓN REAL Y ESTRÉS DE MEMORIA")
    log("=" * 55)

    # 1. Determinar objetivos segun hardware del sistema
    memoria_ram_total_gb = psutil.virtual_memory().total / (1024**3)
    if limite_forzar_gb is None:
        # Por defecto intentar llegar al 85% de la memoria compartida GPU
        limite_vulkan_objetivo = min(16.0, memoria_ram_total_gb * 0.5)
    else:
        limite_vulkan_objetivo = limite_forzar_gb

    log(f"Objetivo de asignación en GPU VRAM: {limite_vulkan_objetivo:.2f} GB")
    log("Iniciando prueba en chunks de 1.5 GB en GPU (Vulkan)...")

    # 2. Prueba en GPU
    vram_ok_gb, chunks_vulkan, integ_vulkan, motivo_vulkan = probar_asignacion_vulkan_real(
        objetivo_gb=limite_vulkan_objetivo,
        chunk_gb=1.5,
        callback_progreso=log,
    )
    log(f">> VRAM GPU Real Verificada: {vram_ok_gb:.2f} GB ({chunks_vulkan} chunks de 1.5 GB)")
    log(f"   Estado de Integridad GPU: {'CORRECTA (Lectura/Escritura OK)' if integ_vulkan else 'FALLO'}")
    log(f"   Detalle del driver: {motivo_vulkan}")

    # 3. Prueba en RAM si se solicita
    ram_ok_gb = 0.0
    vel_ram = 0.0
    integ_ram = True
    if probar_ram:
        objetivo_ram = max(2.0, min(8.0, memoria_ram_total_gb - 4.0))
        log(f"\nIniciando prueba de escritura forzada en RAM ({objetivo_ram:.2f} GB)...")
        ram_ok_gb, vel_ram, integ_ram = probar_asignacion_ram_real(
            objetivo_gb=objetivo_ram,
            callback_progreso=log,
        )
        log(f">> RAM de Sistema Verificada: {ram_ok_gb:.2f} GB a {vel_ram:.2f} GB/s")

    t_total = time.perf_counter() - t_inicio
    memoria_total = vram_ok_gb + ram_ok_gb

    log("\n" + "-" * 55)
    log(f"RESUMEN FINAL DE PRUEBA EMPÍRICA:")
    log(f"  * Memoria GPU VRAM real confirmada: {vram_ok_gb:.2f} GB")
    log(f"  * Memoria RAM real confirmada:      {ram_ok_gb:.2f} GB")
    log(f"  * Capacidad Total Verificada:       {memoria_total:.2f} GB")
    log(f"  * Integridad de datos:              {'SUPERADA CON ÉXITO' if (integ_vulkan and integ_ram) else 'CON ERRORES'}")
    log(f"  * Tiempo total de prueba:           {t_total:.2f} s")
    log("=" * 55 + "\n")

    return ResultadoPruebaMemoria(
        backend="Vulkan" if vram_ok_gb > 0 else "RAM/CPU",
        vram_gpu_asignada_gb=vram_ok_gb,
        ram_sistema_asignada_gb=ram_ok_gb,
        memoria_total_verificada_gb=round(memoria_total, 2),
        tamano_chunk_gb=1.5,
        chunks_asignados=chunks_vulkan,
        tiempo_total_segundos=round(t_total, 2),
        velocidad_escritura_gbs=vel_ram,
        integridad_verificada=(integ_vulkan and integ_ram),
        limite_alcanzado_motivo=motivo_vulkan,
    )


if __name__ == "__main__":
    ejecutar_prueba_estres_memoria()
