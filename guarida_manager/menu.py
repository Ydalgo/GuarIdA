import os
import sys
import unittest
from pathlib import Path

from guarida_manager.cache import GestorCache
from guarida_manager.comparator import ComparadorModelosHardware
from guarida_manager.downloader.compliance import GestorCumplimientoNormativo, RegionNormativa
from guarida_manager.downloader.models import (
    CatalogoModelos,
    CestaDescarga,
    DescargadorModelos,
)
from guarida_manager.downloader.provisioning import OrquestadorAprovisionamiento
from guarida_manager.downloader.tools import GestorHerramientasBunker
from guarida_manager.hardware import obtener_informacion_hardware
from guarida_manager.memory_probe import ejecutar_prueba_estres_memoria
from guarida_manager.roles import AsignacionRoles


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
    while True:
        print("\n" + "=" * 65)
        print("  CATÁLOGO, HERRAMIENTAS Y APROVISIONAMIENTO DEL BÚNKER")
        print("=" * 65)
        print("Submenú de Selección, Herramientas y Afinamiento:")
        print("  1. Explorar Catálogo por Roles (Coder, Chat Español, Sin Censura, Embeddings)")
        print("  2. Comparador de Cuantizaciones (Q3 vs Q4 vs Q5) y Memoria de Contexto")
        print("  3. Estado y Descarga de Herramientas del Búnker (llama-server, git, ripgrep)")
        print("  4. Añadir Modelo Personalizado de Hugging Face (cualquier repo/archivo .gguf)")
        print("  5. Descargar Cesta Multirrol y Aprovisionar Búnker Offline")
        print("  6. Consultar Perfiles de Afinamiento Óptimo Guardados (Memoria SQLite)")
        print("  7. Archivar Modelo (Liberar disco conservando afinamiento y métricas)")
        print("  0. Volver al menú principal")
        print("-" * 65)

        sub = input("Selecciona una opción [0-7]: ").strip()

        if sub == "1":
            print("\nFiltros disponibles: [1] Coder, [2] Chat en Español, [3] Sin Censura (Abliterated), [4] Embeddings, [5] Todos")
            f_opt = input("Elige filtro [1-5]: ").strip()
            cat_map = {"1": "coder", "2": "chat", "3": "uncensored", "4": "embedding"}
            categoria_filtro = cat_map.get(f_opt)

            modelos = CatalogoModelos.listar_modelos(categoria=categoria_filtro, region=RegionNormativa.ES_EU)
            print("\n" + "-" * 75)
            for idx, (m, ev) in enumerate(modelos, 1):
                tag_legal = f"[{ev.estado.value}]"
                tag_censura = " [SIN CENSURA]" if m.es_sin_censura else ""
                print(f"[{idx}] {m.nombre_legible}{tag_censura} - {m.tamano_gb:.2f} GB ({m.cuantizacion})")
                print(f"    Categoría:      {m.categoria.upper()} | Idiomas: {m.idiomas_destacados}")
                print(f"    RAM Rec.:       {m.ram_recomendada_gb:.1f} GB | Licencia: {m.licencia}")
                print(f"    Estado Legal:   {tag_legal} {ev.resumen_legal}")
                print(f"    Descripción:    {m.descripcion}")
                print()
            print("-" * 75)
            input("Presiona [Enter] para continuar...")

        elif sub == "2":
            print("\n--- COMPARADOR DE CUANTIZACIONES Y CONTEXTO (MODELOS 7B) ---")
            analisis = ComparadorModelosHardware.analizar_cuantizaciones_7b()
            hardware = obtener_informacion_hardware()
            vram_gpu = hardware.gtt_disponible_gb if hardware.tiene_aceleracion_gpu else 0.0
            print(f"VRAM / Memoria GTT disponible en tu GPU: {vram_gpu:.2f} GB\n")

            for a in analisis:
                v16k = "SI" if a.es_viable_16k_gpu else "NO (Desborda a RAM)"
                v32k = "SI" if a.es_viable_32k_gpu else "NO (Desborda a RAM)"
                print(f"* Cuantización: {a.cuantizacion} (Pesos: {a.tamano_pesos_gb:.2f} GB | Calidad: ~{a.calidad_relativa_pct:.1f}%)")
                print(f"  - Total con 16k contexto: {a.vram_total_16k_gb:.2f} GB -> Viable en GPU: {v16k}")
                print(f"  - Total con 32k contexto: {a.vram_total_32k_gb:.2f} GB -> Viable en GPU: {v32k}")
                print(f"  - Análisis: {a.recomendacion}")
                print()
            input("Presiona [Enter] para continuar...")

        elif sub == "3":
            print("\n--- HERRAMIENTAS Y BINARIOS DEL BÚNKER ---")
            estados = GestorHerramientasBunker.verificar_todas_herramientas()
            for h in estados:
                estado_str = f"INSTALADA ({h.version})" if h.instalada else "NO DETECTADA"
                critica_str = "[CRÍTICA]" if h.es_critica else "[OPCIONAL]"
                print(f"* {h.nombre} {critica_str}: {estado_str}")
                print(f"  - Ruta: {h.ruta or 'Pendiente de descarga'}")
                print(f"  - Uso:  {h.descripcion}\n")

            faltantes = [h.id for h in estados if not h.instalada]
            if faltantes:
                try:
                    desc = input(f"¿Deseas descargar las herramientas faltantes ({', '.join(faltantes)})? (s/N): ").strip().lower()
                    if desc == "s":
                        for fid in faltantes:
                            try:
                                GestorHerramientasBunker.descargar_y_desplegar(fid)
                            except Exception as e:
                                print(f"[!] Error descargando {fid}: {e}")
                except (KeyboardInterrupt, EOFError):
                    pass
            try:
                input("Presiona [Enter] para continuar...")
            except (KeyboardInterrupt, EOFError):
                pass

        elif sub == "4":
            print("\n--- AÑADIR MODELO PERSONALIZADO DE HUGGING FACE ---")
            repo = input("Repositorio HF (ej. bartowski/Qwen2.5-7B-Instruct-GGUF): ").strip()
            filename = input("Nombre de archivo .gguf (ej. Qwen2.5-7B-Instruct-Q4_K_M.gguf): ").strip()
            if repo and filename:
                tam_str = input("Tamaño aproximado en GB (ej. 4.6): ").strip()
                try:
                    tam = float(tam_str)
                except ValueError:
                    tam = 4.0
                es_cens = input("¿Es un modelo sin censura / abliterated? (s/N): ").strip().lower() == "s"
                cat = input("Categoría [coder/chat/uncensored/embedding]: ").strip().lower() or "coder"
                mid = filename.lower().replace(".gguf", "")

                nuevo = CatalogoModelos.agregar_modelo_personalizado(
                    id_unico=mid,
                    nombre_legible=f"Custom: {filename}",
                    repo_hf=repo,
                    filename=filename,
                    tamano_gb=tam,
                    categoria=cat,
                    es_sin_censura=es_cens,
                )
                print(f"\n[OK] Modelo '{nuevo.nombre_legible}' añadido con éxito al catálogo disponible.")
            else:
                print("[!] Datos incompletos. Operación cancelada.")
            input("Presiona [Enter] para continuar...")

        elif sub == "5":
            print("\n--- APROVISIONAMIENTO MULTIRROL DEL BÚNKER ---")
            print("Selecciona los modelos que deseas descargar en este lote único:")
            modelos_disp = list(CatalogoModelos.MODELOS.values())
            for i, m in enumerate(modelos_disp, 1):
                print(f"  [{i}] {m.id} ({m.categoria.upper()} {m.cuantizacion}) - {m.tamano_gb:.2f} GB")

            seleccion = input("\nIntroduce los números separados por coma (ej. 1,2,6,8) o presiona [Enter] para lote recomendado: ").strip()
            if seleccion:
                indices = [int(x.strip()) for x in seleccion.split(",") if x.strip().isdigit()]
                modelos_elegidos = [modelos_disp[idx - 1].id for idx in indices if 1 <= idx <= len(modelos_disp)]
            else:
                modelos_elegidos = ["qwen2.5-coder-7b-q4", "qwen2.5-3b-chat-q4", "bge-m3-q4"]

            print(f"\nModelos seleccionados para descargar ({len(modelos_elegidos)}):")
            for mid in modelos_elegidos:
                print(f"  - {mid}")

            confirma = input("\n¿Iniciar aprovisionamiento y descarga de componentes ahora? (s/N): ").strip().lower()
            if confirma == "s":
                clave_boveda = input("Contraseña para bóveda criptográfica postcuántica (opcional, Enter para omitir): ").strip() or None
                orquestador = OrquestadorAprovisionamiento()
                cfg = orquestador.ejecutar_aprovisionamiento_lote(
                    region=RegionNormativa.ES_EU,
                    interfaz="terminal",
                    instalar_pdf=True,
                    modelos_ids_lote=modelos_elegidos,
                    clave_maestra_boveda=clave_boveda,
                )
                print(f"\n[OK] ¡Búnker sellado con éxito! Estado: {cfg.estado_bunker}")
            input("Presiona [Enter] para volver...")

        elif sub == "6":
            print("\n--- PERFILES DE AFINAMIENTO ÓPTIMO GUARDADOS EN MEMORIA (SQLITE) ---")
            hardware = obtener_informacion_hardware()
            hash_hw = hardware.hash_hardware
            perfiles = GestorCache().listar_configuraciones_optimas(hash_hw)

            if not perfiles:
                print(f"Aún no hay perfiles afinados para este hardware específico ({hash_hw[:12]}...).")
                print("Cuando ejecutes un benchmark o archives un modelo, su mejor configuración se guardará aquí automáticamente.")
            else:
                print(f"Configuraciones óptimas registradas para este equipo ({len(perfiles)}):")
                print("-" * 75)
                for p in perfiles:
                    rec_str = "[RECOMENDADA]" if p.get("es_recomendada") else ""
                    print(f"* Modelo: {p['modelo_id']} {rec_str}")
                    print(f"  - Capas en GPU (n_gpu_layers): {p['n_gpu_layers']}")
                    print(f"  - Contexto afinado:            {p['ctx_size']} tokens")
                    print(f"  - Batch size / KV Cache:       {p['batch_size']} / {p['kv_cache_tipo']}")
                    print(f"  - Velocidad registrada:        {p['tok_s_medido']} tokens/s")
                    print(f"  - Pico VRAM/GTT medido:        {p['gtt_pico_mb']} MB")
                    print(f"  - Nota / Motivo descarte:      {p.get('motivo_descarte_o_nota') or 'Óptima para uso'}")
                    print()
                print("-" * 75)
            input("Presiona [Enter] para continuar...")

        elif sub == "7":
            print("\n--- ARCHIVAR MODELO (LIBERAR DISCO MANTENIENDO AFINAMIENTO) ---")
            descargador = DescargadorModelos()
            with GestorCache().sesion() as conn:
                filas = conn.execute("SELECT id, filename, estado FROM modelos WHERE ruta_local != '';").fetchall()

            if not filas:
                print("No hay modelos descargados actualmente ocupando espacio en disco.")
            else:
                print("Modelos en disco:")
                for f in filas:
                    print(f"  * {f['id']} ({f['filename']}) - Estado: {f['estado']}")
                mid_borrar = input("\nIntroduce el ID del modelo que deseas archivar/eliminar del disco: ").strip()
                if mid_borrar:
                    if descargador.archivar_modelo_sin_archivo(mid_borrar):
                        print(f"[OK] Archivo físico eliminado. La mejor configuración y benchmarks de '{mid_borrar}' siguen guardadas en SQLite.")
                    else:
                        print("[!] No se encontró el modelo especificado.")
            input("Presiona [Enter] para continuar...")

        elif sub == "0":
            break


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
