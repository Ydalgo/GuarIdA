import os
import sys
import unittest
from pathlib import Path

from guarida_manager.cache import GestorCache
from guarida_manager.downloader.compliance import GestorCumplimientoNormativo, RegionNormativa
from guarida_manager.downloader.models import CatalogoModelos
from guarida_manager.downloader.provisioning import OrquestadorAprovisionamiento
from guarida_manager.hardware import obtener_informacion_hardware
from guarida_manager.memory_probe import ejecutar_prueba_estres_memoria


def limpiar_pantalla() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def mostrar_banner() -> None:
    print("=" * 50)
    print("           GUARIDA - BÚNKER DE IA LOCAL")
    print("   Entorno de Desarrollo Agéntico Local y Privado")
    print("=" * 50)
    print()


def opcion_hardware() -> None:
    print("\n--- [1] DIAGNÓSTICO DE HARDWARE Y LÍMITES DE MEMORIA ---")
    info = obtener_informacion_hardware()
    print(f"Modelo CPU:                  {info.modelo_cpu}")
    print(f"Núcleos:                     {info.nucleos_fisicos} físicos / {info.nucleos_logicos} lógicos")
    print(f"RAM Total del Sistema:       {info.ram_total_gb:.2f} GB ({info.ram_total_bytes:,} bytes)")
    print(f"Aceleración GPU Activa:      {'SÍ' if info.tiene_aceleracion_gpu else 'NO'}")
    print(f"Dispositivo Principal:       {info.nombre_gpu_principal} ({info.tipo_gpu_principal})")
    print(f"Memoria Compartida / GTT:    {info.gtt_disponible_gb:.2f} GB")
    print(f"Reserva Vital del SO:        {info.reserva_sistema_gb:.2f} GB (margen contra OOM)")
    print(f"LÍMITE EXTREMO FORZABLE:     {info.memoria_extrema_forzable_gb:.2f} GB")
    print(f"Hash Hardware SHA-256:       {info.hash_hardware}")

    if info.gpus:
        print("\nDetalle de Adaptadores Gráficos y Memoria Extrema:")
        for gpu in info.gpus:
            print(f"  * {gpu.identificador}: {gpu.nombre} [{gpu.backend}]")
            print(f"    - Tipo:                     {gpu.tipo}")
            print(f"    - VRAM Dedicada Física:     {gpu.vram_dedicada_gb:.2f} GB")
            print(f"    - Memoria Compartida SO:    {gpu.memoria_compartida_gb:.2f} GB")
            print(f"    - Límite Seguro (85%):      {gpu.limite_seguro_gb:.2f} GB")
            print(f"    - LÍMITE MÁXIMO EXTREMO:    {gpu.limite_extremo_gb:.2f} GB")

    print("\nEstimación de Capacidad al Extremo:")
    if info.memoria_extrema_forzable_gb >= 20.0:
        print("  [+] ¡Hardware preparado para modelos 32B Q4 (~19-20 GB) o 14B Q8 con contexto amplio!")
    elif info.memoria_extrema_forzable_gb >= 10.0:
        print("  [+] Hardware preparado para modelos 14B Q4 (~8-9 GB) o 7B Q8 con 16k-32k contexto.")
    elif info.memoria_extrema_forzable_gb >= 5.0:
        print("  [+] Hardware preparado para modelos 7B Q4 (~4.5 GB) con contexto moderado.")
    else:
        print("  [+] Hardware modesto: óptimo para modelos 1.5B - 3B Q4.")
    print()


def opcion_estres_memoria() -> None:
    ejecutar_prueba_estres_memoria()


def opcion_cache() -> None:
    print("\n--- [2] ESTADO DE CACHÉ Y BASE DE DATOS SQLITE ---")
    gestor = GestorCache()
    print(f"Ruta Base de Datos:          {gestor.ruta_db}")
    modulos = gestor.obtener_modulos_instalados()
    print(f"Módulos registrados:         {len(modulos)}")
    for mod in modulos:
        print(f"  - {mod.get('nombre')} (instalado: {mod.get('fecha')})")
    
    with gestor.sesion() as conn:
        modelos_count = conn.execute("SELECT COUNT(*) FROM modelos;").fetchone()[0]
        benchmarks_count = conn.execute("SELECT COUNT(*) FROM benchmarks;").fetchone()[0]
    print(f"Modelos en catálogo:         {modelos_count}")
    print(f"Benchmarks guardados:        {benchmarks_count}")
    print()


def opcion_tests() -> None:
    print("\n--- [3] EJECUCIÓN DE PRUEBAS UNITARIAS ---")
    loader = unittest.TestLoader()
    suite = loader.discover("tests")
    runner = unittest.TextTestRunner(verbosity=2)
    resultado = runner.run(suite)
    print()
    if resultado.wasSuccessful():
        print(">> Todas las pruebas pasaron satisfactoriamente.")
    else:
        print(f">> Hubo {len(resultado.failures)} fallos y {len(resultado.errors)} errores.")
    print()


def opcion_catalogo_y_bunker() -> None:
    print("\n--- [5] CATÁLOGO DE MODELOS Y GOBERNANZA REGIONAL (EU AI ACT) ---")
    print("Región activa: España / Unión Europea (Reglamento UE 2024/1689)\n")

    modelos = CatalogoModelos.listar_modelos(region=RegionNormativa.ES_EU)
    print("Modelos Disponibles y Auditoría Legal:")
    print("-" * 75)
    for idx, (m, ev) in enumerate(modelos, 1):
        estado_tag = "[CONFORME]" if ev.estado.value == "CONFORME" else "[REVISION]"
        print(f"[{idx}] {m.id} ({m.categoria.upper()}) - {m.tamano_gb:.2f} GB")
        print(f"    Descripción:   {m.descripcion}")
        print(f"    RAM Rec.:      {m.ram_recomendada_gb:.1f} GB | Licencia: {m.licencia}")
        print(f"    {estado_tag} Estado Legal: {ev.estado.value} | {ev.resumen_legal}")
        print(f"    Transparencia: {ev.detalles_transparencia}")
        print()
    print("-" * 75)
    print("Opciones:")
    print("  1. Iniciar Aprovisionamiento Completo del Búnker (One-Shot Offline Setup)")
    print("  0. Volver al menú principal")
    
    sub = input("\nElige una opción [0-1]: ").strip()
    if sub == "1":
        print("\nIniciando asistente de aprovisionamiento único...")
        orquestador = OrquestadorAprovisionamiento()
        cfg = orquestador.ejecutar_aprovisionamiento(
            region=RegionNormativa.ES_EU,
            interfaz="terminal",
            instalar_pdf=True,
            modelo_coder_id="qwen2.5-coder-7b-q4",
            modelo_embedding_id="nomic-embed-text-v1.5",
        )
        print(f"\n[OK] Búnker configurado en modo: {cfg.estado_bunker}")
    print()


def iniciar_menu() -> None:
    while True:
        mostrar_banner()
        print("Menú Principal:")
        print("  1. Diagnóstico de Hardware (CPU, RAM, GPU, Hash)")
        print("  2. Test de Asignación y Estrés Real de Memoria (GPU VRAM + RAM)")
        print("  3. Consultar Base de Datos y Caché Local")
        print("  4. Ejecutar Pruebas Unitarias del Sistema (Tests)")
        print("  5. Catálogo de Modelos y Aprovisionamiento del Búnker")
        print("  0. Salir")
        print("-" * 50)
        
        try:
            opcion = input("Selecciona una opción [0-5]: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\nSaliendo de GuarIdA...")
            sys.exit(0)

        if opcion == "1":
            opcion_hardware()
            input("Presiona [Enter] para volver al menú...")
        elif opcion == "2":
            opcion_estres_memoria()
            input("Presiona [Enter] para volver al menú...")
        elif opcion == "3":
            opcion_cache()
            input("Presiona [Enter] para volver al menú...")
        elif opcion == "4":
            opcion_tests()
            input("Presiona [Enter] para volver al menú...")
        elif opcion == "5":
            opcion_catalogo_y_bunker()
            input("Presiona [Enter] para volver al menú...")
        elif opcion == "0":
            print("\nCerrando GuarIdA. ¡Hasta pronto!\n")
            break
        else:
            print("\n[!] Opción no válida. Intenta de nuevo.\n")
            input("Presiona [Enter] para continuar...")
        
        limpiar_pantalla()


if __name__ == "__main__":
    iniciar_menu()
