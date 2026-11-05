import getpass
import os
import secrets
import sys
from pathlib import Path
from typing import Optional

from guarida_manager import menu_actions
from guarida_manager.cache import GestorCache
from guarida_manager.comparator import ComparadorModelosHardware
from guarida_manager.engine import ClienteLlamaOffline, GestorLlamaServer, LlamaServerConfig
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
from guarida_manager.logger import inicializar_logging, obtener_logger, obtener_ultimas_lineas_log
from guarida_manager.tuning.bateria import BateriaEstresLlama
from guarida_manager.tuning.buscador import BuscadorAfinamientoEtapas
from guarida_manager.tuning.capacidades import DescubridorCapacidades
from guarida_manager.tuning.informes import GeneradorInformesTuning
from guarida_manager.tuning.perfiles import GestorPerfilesTuning

logger = obtener_logger("menu")


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


def opcion_cache(gestor_cache: Optional[GestorCache] = None) -> None:
    cache = gestor_cache or GestorCache()
    menu_actions.mostrar_estado_cache(cache)


def opcion_tests() -> None:
    print("\n--- [4] EJECUCIÓN DE PRUEBAS UNITARIAS ---")
    import unittest
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


def opcion_catalogo_y_bunker(gestor_cache: Optional[GestorCache] = None) -> None:
    cache = gestor_cache or GestorCache()
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
            revision = input("Revisión/Commit (opcional, [Enter] para 'main'): ").strip() or "main"
            sha256 = input("Hash SHA-256 esperado (opcional para verificación de integridad): ").strip() or None
            if repo and filename:
                tam_str = input("Tamaño aproximado en GB (ej. 4.6): ").strip()
                try:
                    tam = float(tam_str)
                except ValueError:
                    tam = 4.0
                es_cens = input("¿Es un modelo sin censura / abliterated? (s/N): ").strip().lower() == "s"
                cat = input("Categoría [coder/chat/uncensored/embedding]: ").strip().lower() or "coder"
                mid = filename.lower().replace(".gguf", "")

                try:
                    nuevo = CatalogoModelos.agregar_modelo_personalizado(
                        id_unico=mid,
                        nombre_legible=f"Custom: {filename}",
                        repo_hf=repo,
                        filename=filename,
                        tamano_gb=tam,
                        categoria=cat,
                        es_sin_censura=es_cens,
                        sha256_esperado=sha256,
                        revision=revision,
                    )
                    print(f"\n[OK] Modelo '{nuevo.nombre_legible}' añadido con éxito al catálogo disponible.")
                except ValueError as err:
                    print(f"\n[ERROR DE VALIDACIÓN / SEGURIDAD]: {err}")
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
                clave_boveda = getpass.getpass("Contraseña para bóveda criptográfica postcuántica (opcional, Enter para omitir): ") or None
                cfg = menu_actions.aprovisionar_bunker_lote(
                    gestor_cache=cache,
                    modelos_elegidos=modelos_elegidos,
                    clave_boveda=clave_boveda,
                    region=RegionNormativa.ES_EU,
                    interfaz="terminal",
                    instalar_pdf=True,
                )
                print(f"\n[OK] ¡Búnker sellado con éxito! Estado: {cfg.estado_bunker}")
            input("Presiona [Enter] para volver...")

        elif sub == "6":
            hardware = obtener_informacion_hardware()
            menu_actions.listar_perfiles_afinamiento(cache, hardware.hash_hardware)
            input("Presiona [Enter] para continuar...")

        elif sub == "7":
            print("\n--- ARCHIVAR MODELO (LIBERAR DISCO MANTENIENDO AFINAMIENTO) ---")
            filas = menu_actions.obtener_modelos_locales(cache)

            if not filas:
                print("No hay modelos descargados actualmente ocupando espacio en disco.")
            else:
                print("Modelos en disco:")
                for f in filas:
                    print(f"  * {f['id']} ({f['filename']}) - Estado: {f['estado']}")
                mid_borrar = input("\nIntroduce el ID del modelo que deseas archivar/eliminar del disco: ").strip()
                if mid_borrar:
                    if menu_actions.archivar_modelo(cache, mid_borrar):
                        print(f"[OK] Archivo físico eliminado. La mejor configuración y benchmarks de '{mid_borrar}' siguen guardadas en SQLite.")
                    else:
                        print("[!] No se encontró el modelo especificado.")
            input("Presiona [Enter] para continuar...")

        elif sub == "0":
            break


_GESTOR_SERVER: Optional[GestorLlamaServer] = None
_CLIENTE_LLAMA: Optional[ClienteLlamaOffline] = None


def obtener_gestor_servidor(cache: Optional[GestorCache] = None) -> GestorLlamaServer:
    global _GESTOR_SERVER
    if _GESTOR_SERVER is None:
        _GESTOR_SERVER = GestorLlamaServer(gestor_cache=cache)
    return _GESTOR_SERVER


def obtener_cliente_llama(api_key: Optional[str] = None) -> ClienteLlamaOffline:
    global _CLIENTE_LLAMA
    if _CLIENTE_LLAMA is None:
        _CLIENTE_LLAMA = ClienteLlamaOffline(api_key=api_key)
    elif api_key is not None:
        _CLIENTE_LLAMA.api_key = api_key
    return _CLIENTE_LLAMA


def opcion_motor_inferencia(gestor_cache: Optional[GestorCache] = None) -> None:
    cache = gestor_cache or GestorCache()
    gestor_server = obtener_gestor_servidor(cache)
    cliente_llama = obtener_cliente_llama()

    while True:
        limpiar_pantalla()
        print("=" * 65)
        print("    GUARIDA: MOTOR DE INFERENCIA LOCAL Y CONTROL DE PROCESOS")
        print("=" * 65)
        estado = gestor_server.obtener_estado()
        disponible = cliente_llama.esta_disponible(timeout=1.0)
        
        print(f"Estado Proceso Servidor:     {'[ACTIVO]' if estado['activo'] else '[DETENIDO]'}")
        if estado["activo"]:
            print(f"  * PID:                     {estado['pid']}")
            print(f"  * Uptime:                  {estado['uptime_segundos']} s")
            print(f"  * Endpoint:                http://{estado['host']}:{estado['port']}")
            print(f"  * Modelo Cargado:          {estado['modelo']}")
            print(f"  * Capas GPU (-ngl):        {estado['n_gpu_layers']} | Contexto (-c): {estado['ctx_size']}")
        print(f"Conectividad HTTP Local:     {'[DISPONIBLE]' if disponible else '[NO RESPONDE]'}")
        print("-" * 65)
        print("Opciones del Motor:")
        print("  1. Comprobar salud y respuesta del servidor (/health)")
        print("  2. Arrancar llama-server con afinamiento optimo de SQLite")
        print("  3. Detener llama-server")
        print("  4. Consultar ranuras de contexto y memoria (/slots)")
        print("  5. Probar tokenizador interactivo (/tokenize y /detokenize)")
        print("  6. Test de generacion e inferencia local (/v1/chat/completions)")
        print("  0. Volver al menu principal")
        print("-" * 65)

        try:
            sub = input("Selecciona una opcion [0-6]: ").strip()
        except (KeyboardInterrupt, EOFError):
            break

        if sub == "1":
            print("\n--- SALUD DEL SERVIDOR LOCAL ---")
            try:
                salud = cliente_llama.obtener_salud(timeout=3.0)
                print(f"[OK] Respuesta del endpoint /health: {salud}")
            except Exception as e:
                print(f"[!] No se pudo contactar con /health: {e}")
            input("Presiona [Enter] para continuar...")

        elif sub == "2":
            print("\n--- ARRANCAR LLAMA-SERVER ---")
            if gestor_server.esta_activo():
                print("[!] El servidor ya se encuentra en ejecucion.")
            else:
                binario = GestorHerramientasBunker.resolver_ruta_ejecutable("llama-server")
                if not binario:
                    print("[!] No se encontro el ejecutable 'llama-server'. Descargalo primero desde el menu de herramientas (opcion 5.3).")
                else:
                    filas = menu_actions.obtener_modelos_locales(cache)
                    if not filas:
                        print("[!] No hay modelos descargados en la carpeta local. Descarga un modelo primero (opcion 5).")
                    else:
                        print("Modelos disponibles:")
                        for idx, f in enumerate(filas, start=1):
                            print(f"  [{idx}] {f['id']} -> {f['filename']}")
                        sel = input("\nElige el numero del modelo a levantar: ").strip()
                        try:
                            num = int(sel)
                            if 1 <= num <= len(filas):
                                mod_sel = filas[num - 1]
                                clave_api = secrets.token_urlsafe(32)
                                config = LlamaServerConfig.desde_afinamiento(
                                    modelo_path=Path(mod_sel["ruta_local"]),
                                    modelo_id=mod_sel["id"],
                                    binario_path=binario,
                                    gestor_cache=cache,
                                    api_key=clave_api,
                                )
                                cliente_llama.api_key = clave_api
                                print(f"Levantando '{mod_sel['id']}' con {config.n_gpu_layers} capas GPU y contexto de {config.ctx_size}...")
                                res = gestor_server.iniciar_servidor(config)
                                print(f"[OK] Servidor iniciado con PID {res['pid']}. Esperando disponibilidad...")
                            else:
                                print("[!] Opcion fuera de rango.")
                        except ValueError:
                            print("[!] Entrada invalida.")
            input("Presiona [Enter] para continuar...")

        elif sub == "3":
            print("\n--- DETENER LLAMA-SERVER ---")
            if not gestor_server.esta_activo():
                print("El servidor no estaba en ejecucion.")
            else:
                if gestor_server.detener_servidor():
                    print("[OK] Servidor detenido correctamente.")
                else:
                    print("[!] Error al intentar detener el servidor.")
            input("Presiona [Enter] para continuar...")

        elif sub == "4":
            print("\n--- RANURAS DE CONTEXTO Y ESTADO (/slots) ---")
            try:
                slots = cliente_llama.obtener_slots(timeout=3.0)
                print(f"Total de ranuras reportadas: {len(slots)}")
                for s in slots:
                    print(f"  * Slot ID {s.get('id', '?')}: Estado: {s.get('state', '?')}, Contexto procesado: {s.get('n_past', 0)}")
            except Exception as e:
                print(f"[!] Error al consultar /slots: {e}")
            input("Presiona [Enter] para continuar...")

        elif sub == "5":
            print("\n--- TOKENIZADOR INTERACTIVO ---")
            if not cliente_llama.esta_disponible():
                print("[!] El servidor no responde. Inicia el servidor primero.")
            else:
                texto = input("Introduce una frase o codigo para tokenizar: ").strip()
                if texto:
                    try:
                        tokens = cliente_llama.tokenizar(texto)
                        print(f"Total tokens: {len(tokens)}")
                        print(f"IDs de tokens: {tokens}")
                        recuperado = cliente_llama.detokenizar(tokens)
                        print(f"Texto reconstruido: {recuperado}")
                    except Exception as e:
                        print(f"[!] Error con tokenizador: {e}")
            input("Presiona [Enter] para continuar...")

        elif sub == "6":
            print("\n--- TEST DE INFERENCIA LOCAL (/v1/chat/completions) ---")
            if not cliente_llama.esta_disponible():
                print("[!] El servidor no responde. Inicia el servidor primero (opción 2).")
            else:
                estado_srv = gestor_server.obtener_estado()
                print(f"Modelo cargado actualmente: {estado_srv.get('modelo', 'desconocido')}")
                prompt_usr = input("Introduce tu mensaje/pregunta para conversar con el modelo: ").strip()
                if prompt_usr:
                    try:
                        print("Generando respuesta en local...")
                        resp = cliente_llama.completar_chat(
                            mensajes=[{"role": "user", "content": prompt_usr}],
                            temperatura=0.2,
                            max_tokens=256,
                        )
                        elecciones = resp.get("choices", [])
                        if elecciones:
                            contenido = elecciones[0].get("message", {}).get("content", "")
                            print(f"\nRespuesta del modelo:\n{'-'*40}\n{contenido}\n{'-'*40}")
                            uso = resp.get("usage", {})
                            print(f"Uso de tokens: Prompt={uso.get('prompt_tokens', 0)}, Salida={uso.get('completion_tokens', 0)}")
                    except Exception as e:
                        print(f"[!] Error durante la inferencia: {e}")
            input("Presiona [Enter] para continuar...")

        elif sub == "0":
            break


def opcion_afinador_y_benchmark(gestor_cache: Optional[GestorCache] = None) -> None:
    cache = gestor_cache or GestorCache()
    binario = GestorHerramientasBunker.resolver_ruta_ejecutable("llama-server")
    generador_informes = GeneradorInformesTuning(gestor_cache=cache)

    while True:
        limpiar_pantalla()
        print("=" * 70)
        print("      AFINADOR EMPÍRICO Y BENCHMARKING DE MODELOS LOCALES")
        print("=" * 70)
        print(f"Binario detectado: {binario or 'NO DETECTADO'}")
        print("-" * 70)
        print("Opciones:")
        print("  1. Descubrir y validar capacidades del binario llama-server")
        print("  2. Afinar modelo (búsqueda por etapas y batería de estrés)")
        print("  3. Ejecutar batería de estrés sobre servidor actualmente activo")
        print("  4. Consultar historial de benchmarks e informes guardados")
        print("  5. Comparar dos sesiones de benchmark empíricamente")
        print("  0. Volver al menú principal")
        print("-" * 70)

        sub = input("Selecciona una opción [0-5]: ").strip()
        if sub == "1":
            if not binario:
                print("[!] No se encontró llama-server. Descárgalo desde el menú 5.3.")
            else:
                print("\nAnalizando binario...")
                caps = DescubridorCapacidades.descubrir(binario, gestor_cache=cache, forzar_redescubrimiento=True)
                print(f"[OK] Versión build:           {caps.version_build}")
                print(f"[OK] Flags soportados válidos: {len(caps.flags_soportados)}")
                print(f"[OK] Soporte Flash Attention:  {caps.soporta_flash_attn} ({caps.flash_attn_modo})")
                print(f"[OK] Soporte ubatch (-ub):     {caps.soporta_ubatch}")
                print(f"[OK] Soporte llama-bench:      {caps.soporta_llama_bench}")
                print(f"[OK] Dispositivos reportados:  {caps.dispositivos or 'CPU/Vulkan estándar'}")
            input("Presiona [Enter] para continuar...")

        elif sub == "2":
            if not binario:
                print("[!] No se encontró llama-server.")
            else:
                filas = menu_actions.obtener_modelos_locales(cache)
                if not filas:
                    print("[!] No hay modelos descargados localmente.")
                else:
                    print("\nModelos disponibles:")
                    for idx, f in enumerate(filas, start=1):
                        print(f"  [{idx}] {f['id']} ({f['filename']})")
                    s_mod = input("\nElige el número de modelo: ").strip()
                    try:
                        n_m = int(s_mod)
                        if 1 <= n_m <= len(filas):
                            m_sel = filas[n_m - 1]
                            print("\nPerfiles de barrido: [1] Rápido (~10 min)  [2] Estándar (~45 min)  [3] Exhaustivo")
                            s_p = input("Selecciona perfil [1-3] (defecto 2): ").strip()
                            p_nombre = "rapido" if s_p == "1" else ("exhaustivo" if s_p == "3" else "estandar")

                            print("\nObjetivo: [1] Equilibrado  [2] Chat (baja latencia)  [3] Batch  [4] Agente contexto largo")
                            s_o = input("Selecciona objetivo [1-4] (defecto 1): ").strip()
                            map_obj = {"1": "equilibrado", "2": "chat", "3": "batch", "4": "agente_contexto_largo"}
                            obj_elegido = map_obj.get(s_o, "equilibrado")

                            caps = DescubridorCapacidades.descubrir(binario, gestor_cache=cache)
                            p_barrido = GestorPerfilesTuning.obtener_perfil_barrido(p_nombre)
                            p_barrido.objetivo_scoring = obj_elegido
                            p_bateria = GestorPerfilesTuning.obtener_perfil_bateria(p_nombre)

                            print(f"\nIniciando afinamiento para '{m_sel['id']}'...")
                            try:
                                buscador = BuscadorAfinamientoEtapas(
                                    modelo_path=Path(m_sel["ruta_local"]),
                                    modelo_id=m_sel["id"],
                                    capacidades=caps,
                                    perfil_barrido=p_barrido,
                                    perfil_bateria=p_bateria,
                                    gestor_cache=cache,
                                    callback_progreso=lambda msg, pct: print(f"[{pct*100:5.1f}%] {msg}"),
                                )
                                ganador = buscador.ejecutar_barrido_completo()
                                if ganador and ganador.estado == "ok":
                                    print(f"\n[OK] ¡Afinamiento completado! Score ganador: {ganador.score}")
                                else:
                                    print("\n[!] No se encontró configuración estable.")
                            except Exception as e:
                                logger.error(f"Fallo durante afinamiento de {m_sel['id']}: {e}", exc_info=True)
                                print(f"\n[!] Error durante el afinamiento: {e}")
                                print("El detalle técnico se ha guardado en el archivo de log.")
                    except ValueError:
                        print("[!] Entrada inválida.")
            input("Presiona [Enter] para continuar...")

        elif sub == "3":
            cliente = obtener_cliente_llama()
            if not cliente.esta_disponible():
                print("[!] El servidor no responde. Levántalo primero en el menú 6.")
            else:
                try:
                    gestor_srv = obtener_gestor_servidor(cache)
                    estado_srv = gestor_srv.obtener_estado()
                    ctx_actual = estado_srv.get("ctx_size", 4096)
                    print(f"\nEjecutando batería de estrés sobre servidor activo (Contexto: {ctx_actual})...")
                    perfil_bat = GestorPerfilesTuning.obtener_perfil_bateria("estandar")
                    bateria = BateriaEstresLlama(cliente, perfil_bat)
                    res = bateria.ejecutar_bateria_completa(ctx_size=ctx_actual)
                    stats = EvaluadorScoring.extraer_metricas_resumen(res)
                    print(f"[OK] Resultados obtenidos ({len(res)} pruebas):")
                    print(f"  * Generación (TG):  {stats['tg_stats']['mediana']} tok/s (IC 95%: [{stats['tg_stats']['ic_inf']}, {stats['tg_stats']['ic_sup']}])")
                    print(f"  * Prefill (PP):     {stats['pp_stats']['mediana']} tok/s")
                    print(f"  * Primer token:     {stats['ttft_stats']['mediana']} ms")
                    print(f"  * Calidad / Éxito:  {stats['calidad_media']:.1f}%")
                except Exception as e:
                    logger.error(f"Error en batería de estrés: {e}", exc_info=True)
                    print(f"[!] Error durante la ejecución de los tests: {e}")
            input("Presiona [Enter] para continuar...")

        elif sub == "4":
            with cache.sesion() as conn:
                sesiones = conn.execute("SELECT * FROM bench_sesiones ORDER BY inicio DESC LIMIT 10;").fetchall()
            if not sesiones:
                print("\nNo hay sesiones de benchmark registradas aún.")
            else:
                print("\nÚltimas sesiones registradas:")
                for s in sesiones:
                    print(f"  * [{s['id']}] {s['modelo_id']} | Objetivo: {s['objetivo']} | Estado: {s['estado']} | {s['inicio']}")
                sid = input("\nIntroduce ID de sesión para ver tabla detallada (o Enter para volver): ").strip()
                if sid:
                    generador_informes.imprimir_tabla_consola(sid)
                    exp = input("¿Deseas exportar esta sesión a CSV y JSON? (s/N): ").strip().lower()
                    if exp == "s":
                        try:
                            rcsv, rjson = generador_informes.exportar_csv_y_json(sid)
                            print(f"[OK] Exportado a:\n  {rcsv}\n  {rjson}")
                        except Exception as e:
                            print(f"[!] Error al exportar: {e}")
            input("Presiona [Enter] para continuar...")

        elif sub == "5":
            s_a = input("ID de Sesión A: ").strip()
            s_b = input("ID de Sesión B: ").strip()
            if s_a and s_b:
                generador_informes.comparar_sesiones(s_a, s_b)
            else:
                print("[!] IDs incompletos.")
            input("Presiona [Enter] para continuar...")

        elif sub == "0":
            break


def opcion_logs_sistema() -> None:
    print("\n--- [8] REGISTRO Y DIAGNÓSTICO DE ERRORES DEL SISTEMA (LOGS) ---")
    lineas = obtener_ultimas_lineas_log(n_lineas=40)
    for l in lineas:
        print(l, end="" if l.endswith("\n") else "\n")
    print("-" * 75)


def iniciar_menu(gestor_cache: Optional[GestorCache] = None) -> None:
    cache = gestor_cache or GestorCache()
    inicializar_logging()
    while True:
        mostrar_banner()
        print("Menú Principal:")
        print("  1. Diagnóstico de Hardware (CPU, RAM, GPU, Hash)")
        print("  2. Test de Asignación y Estrés Real de Memoria (GPU VRAM + RAM)")
        print("  3. Consultar Base de Datos y Caché Local")
        print("  4. Ejecutar Pruebas Unitarias del Sistema (Tests)")
        print("  5. Catálogo de Modelos y Aprovisionamiento del Búnker")
        print("  6. Motor de Inferencia Local y Control de Procesos (Fase 2)")
        print("  7. Afinador Empírico y Benchmarking Estadístico")
        print("  8. Registro y Diagnóstico de Errores (Logs del Sistema)")
        print("  0. Salir")
        print("-" * 50)
        
        try:
            opcion = input("Selecciona una opción [0-8]: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\nSaliendo de GuarIdA...")
            sys.exit(0)

        try:
            if opcion == "1":
                opcion_hardware()
                input("Presiona [Enter] para volver al menú...")
            elif opcion == "2":
                opcion_estres_memoria()
                input("Presiona [Enter] para volver al menú...")
            elif opcion == "3":
                opcion_cache(cache)
                input("Presiona [Enter] para volver al menú...")
            elif opcion == "4":
                opcion_tests()
                input("Presiona [Enter] para volver al menú...")
            elif opcion == "5":
                opcion_catalogo_y_bunker(cache)
                input("Presiona [Enter] para volver al menú...")
            elif opcion == "6":
                opcion_motor_inferencia(cache)
            elif opcion == "7":
                opcion_afinador_y_benchmark(cache)
            elif opcion == "8":
                opcion_logs_sistema()
                input("Presiona [Enter] para volver al menú...")
            elif opcion == "0":
                print("\nCerrando GuarIdA. ¡Hasta pronto!\n")
                break
            else:
                print("\n[!] Opción no válida. Intenta de nuevo.\n")
                input("Presiona [Enter] para continuar...")
        except Exception as e:
            logger.critical(f"Error imprevisto en menú opción {opcion}: {e}", exc_info=True)
            print(f"\n[!] Se produjo un fallo en la opción {opcion}: {e}")
            print("El error detallado se ha guardado en el archivo de log del sistema.")
            input("Presiona [Enter] para continuar...")
        
        limpiar_pantalla()


if __name__ == "__main__":
    iniciar_menu()
