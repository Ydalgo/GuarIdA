import getpass
import os
import secrets
import sys
from pathlib import Path
from typing import Optional

from guarida_manager import menu_actions
from guarida_manager.cache import GestorCache
from guarida_manager.chat import ejecutar_chat_terminal
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
from guarida_manager.telemetry import MonitorTelemetriaHardware
from guarida_manager.tuning.bateria import BateriaEstresLlama
from guarida_manager.tuning.buscador import BuscadorAfinamientoEtapas
from guarida_manager.tuning.capacidades import DescubridorCapacidades
from guarida_manager.tuning.informes import GeneradorInformesTuning
from guarida_manager.tuning.perfiles import GestorPerfilesTuning, PerfilBateria

logger = obtener_logger("menu")


def limpiar_pantalla() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def mostrar_banner() -> None:
    print("=" * 65)
    print("           GUARIDA - BÚNKER DE IA LOCAL")
    print("   Entorno de Desarrollo Agéntico Local y Privado")
    print("=" * 65)
    print(MonitorTelemetriaHardware.formatear_linea_telemetria())
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


def opcion_modo_automatico(gestor_cache: Optional[GestorCache] = None) -> None:
    """Modo de Ajuste Automático: descarga y afina en 1 paso lo que mejor va con el hardware."""
    cache = gestor_cache or GestorCache()
    limpiar_pantalla()
    print("=" * 75)
    print("      MODO DE AJUSTE AUTOMÁTICO (HARDWARE -> DESCARGA -> AFINAMIENTO)")
    print("=" * 75)
    hw = obtener_informacion_hardware()
    est = menu_actions.estimar_conjunto_modelos_optimo(hw)

    print("Diagnóstico del Equipo Detectado:")
    print(f"  * CPU:                    {hw.modelo_cpu} ({hw.nucleos_fisicos} núcleos / {hw.nucleos_logicos} hilos)")
    print(f"  * RAM Total:              {hw.ram_total_gb:.2f} GB (Límite extremo forzable: {hw.memoria_extrema_forzable_gb:.2f} GB)")
    gpu_txt = f"{hw.nombre_gpu_principal} [{hw.gtt_disponible_gb:.2f} GB VRAM/GTT]" if hw.tiene_aceleracion_gpu else "Sin GPU (Modo CPU puro)"
    print(f"  * Dispositivo Gráfico:    {gpu_txt}")
    print(f"  * Nivel / Tier Asignado:  [{est['tier'].upper()}] - {est['descripcion']}")
    print("-" * 75)
    print("Alineación Automática Estimada:")
    print(f"  [1] Modelo Coder (Código/AST):      {est['coder']}")
    print(f"  [2] Modelo Chat (Asistente/Humano): {est['chat']}")
    print(f"  [3] Motor AST (Embeddings):         {est['embedding']}")
    print(f"  [4] Inferencia Offline:             llama-server")
    print(f"  [5] Auto-Afinamiento:               Ajuste de capas GPU, contexto y batch en SQLite")
    print("-" * 75)

    confirm = input("¿Proceder con la descarga y afinamiento automático de todo el conjunto? (S/n): ").strip().lower()
    if confirm == "n":
        print("[!] Ajuste automático cancelado por el usuario.")
        input("Presiona [Enter] para continuar...")
        return

    # 1. Herramientas
    print("\n[1/3] Verificando binario de inferencia 'llama-server'...")
    binario = GestorHerramientasBunker.resolver_ruta_ejecutable("llama-server")
    if not binario:
        print("  -> Descargando y desplegando llama-server optimizado...")
        try:
            from guarida_manager.downloader.binaries import GestorBinariosLlama
            perfil = GestorBinariosLlama.resolver_perfil_sistema()
            GestorBinariosLlama.descargar_y_desplegar(perfil, gestor_cache=cache)
            binario = GestorHerramientasBunker.resolver_ruta_ejecutable("llama-server")
            print("  -> [OK] llama-server desplegado correctamente.")
        except Exception as e:
            print(f"  -> [!] Advertencia al desplegar llama-server: {e}")
    else:
        print("  -> [OK] llama-server ya está listo en el sistema.")

    # 2. Descarga de modelos estimados
    print("\n[2/3] Descargando modelos seleccionados para el hardware...")
    descargador = DescargadorModelos(gestor_cache=cache)
    for mid in est["modelos"]:
        m_def = CatalogoModelos.obtener_modelo(mid)
        if not m_def:
            continue
        print(f"  -> Verificando/Descargando '{mid}' ({m_def.tamano_gb:.2f} GB)...")
        try:
            ruta_m = descargador.descargar_modelo(m_def, permitir_inseguro=True)
            print(f"     [OK] Disponible en: {ruta_m.name}")
        except Exception as err:
            print(f"     [!] Error descargando '{mid}': {err}")

    # 3. Afinamiento automático de llama-server y modelos
    print("\n[3/3] Aplicando auto-afinamiento a los modelos locales para el hardware...")
    afinados = menu_actions.afinar_todos_automatico(cache, forzar=True)
    for a in afinados:
        print(f"  * [OK] {a.modelo_id}: -ngl {a.n_gpu_layers}, -c {a.ctx_size}, -b {a.batch_size}, kv={a.kv_cache_tipo}, threads={a.threads}")

    print("\n" + "=" * 75)
    print("  ¡AJUSTE Y AFINAMIENTO AUTOMÁTICO COMPLETADO!")
    print("  Todos los modelos y parámetros óptimos están listos para operar.")
    print("=" * 75)
    input("Presiona [Enter] para volver al menú principal...")


def opcion_catalogo_y_bunker(gestor_cache: Optional[GestorCache] = None) -> None:
    cache = gestor_cache or GestorCache()
    filtro_rango = "todos"
    while True:
        limpiar_pantalla()
        locales = {m["id"]: m for m in menu_actions.obtener_modelos_locales(cache)}
        todos_modelos = list(CatalogoModelos.MODELOS.values())

        if filtro_rango == "ultraligero":
            modelos_disp = [m for m in todos_modelos if m.tamano_gb < 2.2 and m.categoria in ("coder", "chat")]
            titulo_filtro = "ULTRALIGEROS (0.3B - 3B, <=2.2 GB)"
        elif filtro_rango == "estandar":
            modelos_disp = [m for m in todos_modelos if 2.2 <= m.tamano_gb < 8.5 and m.categoria in ("coder", "chat", "uncensored")]
            titulo_filtro = "ESTÁNDAR EQUILIBRADOS (4B - 8B, 2.5 - 8 GB)"
        elif filtro_rango == "extremo":
            modelos_disp = [m for m in todos_modelos if m.tamano_gb >= 8.5]
            titulo_filtro = "ALTA CAPACIDAD Y EXTREMOS (14B - 32B+, >=8.5 GB)"
        elif filtro_rango == "embedding":
            modelos_disp = [m for m in todos_modelos if m.categoria == "embedding"]
            titulo_filtro = "EMBEDDINGS Y ÁRBOL DE NODOS AST"
        elif filtro_rango == "chat":
            modelos_disp = [m for m in todos_modelos if m.categoria == "chat"]
            titulo_filtro = "ASISTENTES Y CHAT EN ESPAÑOL"
        elif filtro_rango == "safetensors":
            modelos_disp = [m for m in todos_modelos if getattr(m, "formato", "gguf") in ("safetensors", "pytorch")]
            titulo_filtro = "MODELOS CON TENSORES Y PESOS NATIVOS (SAFETENSORS / PYTORCH)"
        else:
            modelos_disp = todos_modelos
            titulo_filtro = f"TODOS LOS MODELOS ({len(todos_modelos)})"

        hw_actual = obtener_informacion_hardware()
        vram_info = f"{hw_actual.gtt_disponible_gb:.1f} GB VRAM/GTT" if hw_actual.tiene_aceleracion_gpu else "CPU Pura"
        print("=" * 115)
        print(f"  MODO MANUAL: CATÁLOGO DE MODELOS - {titulo_filtro}")
        print(f"  Hardware Activo: {hw_actual.modelo_cpu} | Memoria: {vram_info} (RAM: {hw_actual.ram_total_gb:.1f} GB, Límite Extremo: {hw_actual.memoria_extrema_forzable_gb:.1f} GB)")
        print("  Criterios CanIRun/LLMFit: Coding mín: 8 t/s (rec >=15) | Chat mín: 12 t/s (ágil >=20) | Óptimo: >=35 t/s")
        print("=" * 115)
        for i, m in enumerate(modelos_disp, 1):
            est = f"[INSTALADO: {locales[m.id].get('tamano_mb', '?')} MB]" if m.id in locales else f"[{m.tamano_gb:.2f} GB]"
            rol = m.categoria.upper()
            ev = ComparadorModelosHardware.evaluar_modelo_completo(
                modelo_id=m.id,
                tamano_gb=m.tamano_gb,
                hardware=hw_actual,
                gestor_cache=cache,
            )
            fuente_tag = "*" if ev.es_medido_real else "~"
            fmt_tag = f"[{getattr(m, 'formato', 'gguf').upper()}]"
            tag_clasif = ev.clasificacion_coding if m.categoria == "coder" else ev.clasificacion_chat
            vram_txt = f"~{ev.vram_requerida_4k_gb:.1f}GB VRAM"
            print(f"  [{i:>2}] {m.id:<33} {fmt_tag:<14} {est:<20} {vram_txt:<14} -> {fuente_tag}{ev.tok_s_estimado:>4.1f} t/s | {tag_clasif:<18} | {ev.estrategia_vram}")

        print("-" * 115)
        print("Filtros por margen/rango:")
        print("  [T] Todos  [U] Ultraligeros (<=2GB)  [E] Estándar (4B-8B)  [X] Extremos (14B-72B+)  [B] Embeddings  [D] Chat  [S] Safetensors")
        print("-" * 115)
        print("Acciones:")
        print("  * Escribe número(s) (ej. 1 o 2,5)     -> Descargar modelo(s) directamente")
        print("  * [A] Archivar/Eliminar de disco      | [H] Verificar herramientas del bunker")
        print("  * [C] Añadir GGUF / Safetensors de HF | [0 / Enter] Volver")
        print("-" * 95)

        sub = input("Opción, filtro o número(s): ").strip()
        if not sub or sub == "0":
            break

        if sub.lower() == "t":
            filtro_rango = "todos"
            continue
        elif sub.lower() == "u":
            filtro_rango = "ultraligero"
            continue
        elif sub.lower() == "e":
            filtro_rango = "estandar"
            continue
        elif sub.lower() == "x":
            filtro_rango = "extremo"
            continue
        elif sub.lower() == "b":
            filtro_rango = "embedding"
            continue
        elif sub.lower() == "d":
            filtro_rango = "chat"
            continue
        elif sub.lower() == "s":
            filtro_rango = "safetensors"
            continue

        if sub.lower() == "a":
            filas = list(locales.values())
            if not filas:
                print("\n[!] No hay modelos descargados en disco.")
            else:
                print("\nModelos en disco:")
                for idx, f in enumerate(filas, 1):
                    print(f"  [{idx}] {f['id']} ({f.get('tamano_mb', '?')} MB)")
                s_del = input("Número o ID del modelo a eliminar del disco (Enter = cancelar): ").strip()
                mid_borrar = ""
                if s_del.isdigit() and 1 <= int(s_del) <= len(filas):
                    mid_borrar = filas[int(s_del) - 1]["id"]
                elif s_del:
                    mid_borrar = s_del
                if mid_borrar and menu_actions.archivar_modelo(cache, mid_borrar):
                    print(f"[OK] Archivo físico de '{mid_borrar}' eliminado (métricas conservadas en SQLite).")
            input("Presiona [Enter] para continuar...")

        elif sub.lower() == "h":
            estados = GestorHerramientasBunker.verificar_todas_herramientas()
            for h in estados:
                print(f"  * {h.nombre}: {'INSTALADA' if h.instalada else 'NO DETECTADA'} ({h.ruta or 'pendiente'})")
            faltantes = [h.id for h in estados if not h.instalada]
            if faltantes and input("¿Descargar herramientas faltantes ahora? (S/n): ").strip().lower() != "n":
                for fid in faltantes:
                    try:
                        GestorHerramientasBunker.descargar_y_desplegar(fid)
                    except Exception as e:
                        print(f"[!] Error descargando {fid}: {e}")
            input("Presiona [Enter] para continuar...")

        elif sub.lower() == "c":
            repo = input("Repositorio HF (ej. Qwen/Qwen2.5-0.5B-Instruct o bartowski/model-GGUF): ").strip()
            filename = input("Archivo (.gguf, .safetensors, .bin): ").strip()
            if repo and filename:
                import re
                cat = input("Categoría [coder/chat/embedding] (Enter = coder): ").strip().lower() or "coder"
                mid = re.sub(r"\.(gguf|safetensors|bin|pt)$", "", filename.lower())
                try:
                    nuevo = CatalogoModelos.agregar_modelo_personalizado(
                        id_unico=mid,
                        nombre_legible=f"Custom: {filename}",
                        repo_hf=repo,
                        filename=filename,
                        tamano_gb=4.0,
                        categoria=cat,
                    )
                    print(f"[OK] Añadido '{nuevo.id}'. Descargando ahora...")
                    DescargadorModelos(gestor_cache=cache).descargar_modelo(nuevo.id, permitir_inseguro=True)
                except Exception as err:
                    print(f"[!] Error: {err}")
            input("Presiona [Enter] para continuar...")

        else:
            indices = [int(x.strip()) for x in sub.split(",") if x.strip().isdigit()]
            elegidos = [modelos_disp[idx - 1] for idx in indices if 1 <= idx <= len(modelos_disp)]
            if not elegidos:
                print("[!] Selección no reconocida.")
            else:
                descargador = DescargadorModelos(gestor_cache=cache)
                for mod in elegidos:
                    print(f"\n>>> Descargando '{mod.id}' ({mod.nombre_legible})...")
                    try:
                        ruta = descargador.descargar_modelo(mod, permitir_inseguro=True)
                        print(f"[OK] Modelo listo en: {ruta}")
                        # Auto-afinar inmediatamente el modelo descargado
                        menu_actions.afinar_modelo_automatico(cache, mod.id, ruta)
                    except Exception as e:
                        print(f"[!] Error descargando {mod.id}: {e}")
            input("\nPresiona [Enter] para continuar...")


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
        print("  6. Chat interactivo por terminal con metricas y parejas recomendadas")
        print("  7. Probar vectorización y búsqueda semántica en Árbol de Nodos (AST)")
        print("  8. Inferencia directa con tensores y pesos nativos (Safetensors / PyTorch)")
        print("  0. Volver al menu principal")
        print("-" * 65)

        try:
            sub = input("Selecciona una opcion [0-8]: ").strip()
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
                                ruta_m = Path(mod_sel["ruta_local"])
                                if ruta_m.suffix.lower() in (".safetensors", ".bin", ".pt") or ruta_m.is_dir():
                                    print(f"[!] '{mod_sel['id']}' es un modelo de tensores nativos ({ruta_m.suffix or 'dir'}). "
                                          "Para ejecutarlo con PyTorch/Transformers utiliza la opción 8.")
                                else:
                                    clave_api = secrets.token_urlsafe(32)
                                    config = LlamaServerConfig.desde_afinamiento(
                                        modelo_path=ruta_m,
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
            if not gestor_server.esta_activo() and not cliente_llama.esta_disponible():
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
            ejecutar_chat_terminal(cache, gestor_server, cliente_llama)
            input("Presiona [Enter] para continuar...")

        elif sub == "7":
            print("\n--- PRUEBA DE EMBEDDINGS Y ÁRBOL DE NODOS (AST) ---")
            if not cliente_llama.esta_disponible():
                print("[!] El servidor de inferencia no está activo. Arráncalo primero con la opción 2.")
            else:
                try:
                    from guarida_manager.arbol_nodos import ArbolNodosCodigo

                    print("Vectorizando consulta de prueba con el servidor activo...")
                    texto_test = "def calcular_hash_sha256(archivo: Path) -> str:"
                    vec = cliente_llama.calcular_embedding(texto_test)
                    if vec:
                        print(f"[OK] Inferencia vectorial exitosa: vector generado con {len(vec)} dimensiones.")
                    else:
                        print("[!] El servidor respondió pero no devolvió vector (¿el binario fue arrancado con --embedding?).")

                    print("\nConstruyendo árbol sintáctico (AST) a partir del código del gestor de caché...")
                    arbol = ArbolNodosCodigo()
                    with open(Path(__file__).parent / "cache.py", "r", encoding="utf-8") as f_code:
                        codigo_cache = f_code.read()
                    arbol.construir_desde_codigo_python(codigo_cache, ruta_archivo="cache.py")
                    print(f"[OK] Árbol AST generado: {len(arbol.nodos)} nodos indexados (módulos, clases, métodos y funciones).")

                    consulta_busqueda = "¿Cómo se guardan y consultan las configuraciones óptimas en SQLite?"
                    vocab_cache = ["guardar", "obtener", "configuracion", "optima", "sqlite", "sesion", "modelo", "benchmark", "hash", "tabla"]
                    def _calc_emb_opt7(txt: str) -> list[float]:
                        if vec:
                            try:
                                v = cliente_llama.calcular_embedding(txt)
                                if v:
                                    return v
                            except Exception:
                                pass
                        low = txt.lower()
                        v_lex = [float(low.count(t)) for t in vocab_cache]
                        if sum(v_lex) == 0.0:
                            v_lex[0] = 0.01
                        return v_lex

                    arbol.indexar_embeddings(_calc_emb_opt7)
                    vec_q = _calc_emb_opt7(consulta_busqueda)
                    res_nodos = arbol.buscar_nodos_relevantes(vec_q, top_k=2)
                    print(f"\nBúsqueda semántica para: '{consulta_busqueda}'")
                    for n, score in res_nodos:
                        print(f"  * [{n.tipo.value}] {n.nombre} (líneas {n.linea_inicio}-{n.linea_fin})")

                    msg = arbol.generar_mensaje_inter_modelo(consulta_busqueda, res_nodos)
                    print(f"\nContexto óptimo estructurado generado (MensajeInterModelo: {msg.tipo_accion}):")
                    print(f"{'-'*40}\n{msg.payload['contexto_sintactico'][:400]}...\n{'-'*40}")
                except Exception as e:
                    print(f"[!] Error probando árbol de nodos / embeddings: {e}")
            input("Presiona [Enter] para continuar...")

        elif sub == "8":
            print("\n--- INFERENCIA DIRECTA CON TENSORES Y PESOS NATIVOS ---")
            from guarida_manager.engine.tensors_engine import MotorTensoresLocales
            filas = menu_actions.obtener_modelos_locales(cache)
            candidatos_tensores = [
                f for f in filas if Path(f["ruta_local"]).suffix.lower() in (".safetensors", ".bin", ".pt") or Path(f["ruta_local"]).is_dir()
            ]

            from guarida_manager import DIRECTORIO_MODELOS
            if DIRECTORIO_MODELOS.exists():
                for arch in DIRECTORIO_MODELOS.glob("*.safetensors"):
                    if not any(c.get("ruta_local") == str(arch) for c in candidatos_tensores):
                        candidatos_tensores.append({"id": arch.stem, "filename": arch.name, "ruta_local": str(arch)})

            p_sel = None
            if not candidatos_tensores:
                print("No se encontraron archivos .safetensors o .bin descargados en la carpeta local.")
                ruta_manual = input("Introduce ruta a un archivo .safetensors o carpeta de pesos (Enter = cancelar): ").strip()
                if ruta_manual and Path(ruta_manual).exists():
                    p_sel = Path(ruta_manual)
            else:
                print("Modelos de tensores y pesos disponibles:")
                for idx_t, c_t in enumerate(candidatos_tensores, 1):
                    info_t = MotorTensoresLocales.inspeccionar_tensores(Path(c_t["ruta_local"]))
                    params_txt = f"{info_t['parametros_aprox'] / 1e6:.1f}M params" if info_t["parametros_aprox"] > 0 else info_t["tipo"]
                    print(f"  [{idx_t}] {c_t['id']} -> {c_t['filename']} ({params_txt})")
                sel_t = input("Elige número o introduce ruta manual (Enter = cancelar): ").strip()
                if sel_t.isdigit() and 1 <= int(sel_t) <= len(candidatos_tensores):
                    p_sel = Path(candidatos_tensores[int(sel_t) - 1]["ruta_local"])
                elif sel_t and Path(sel_t).exists():
                    p_sel = Path(sel_t)

            if p_sel:
                info_t = MotorTensoresLocales.inspeccionar_tensores(p_sel)
                print(f"\n[OK] Inspección de tensores:")
                print(f"  * Formato:              {info_t['tipo']}")
                print(f"  * Tamaño en disco:      {info_t['tamano_mb']} MB")
                print(f"  * Parámetros aprox:     {info_t['parametros_aprox']:,}")
                print(f"  * Tensores analizados:  {len(info_t['tensores'])}")

                prompt_usr = input("\nIntroduce prompt de prueba para el motor de tensores: ").strip()
                if prompt_usr:
                    try:
                        print("Ejecutando inferencia en tensores nativos con PyTorch/Transformers...")
                        motor = MotorTensoresLocales(ruta_modelo=p_sel)
                        res_t = motor.completar_texto(prompt_usr, max_tokens=128)
                        print(f"\nRespuesta generada en [{res_t['dispositivo']}]:")
                        print("-" * 50)
                        print(res_t["content"])
                        print("-" * 50)
                        print(f"Velocidad: {res_t['tok_per_second']} tok/s (Tokens generados: {res_t['completion_tokens']}, Latencia: {res_t['latencia_ms']} ms)")
                        motor.liberar_memoria()
                    except Exception as err_t:
                        print(f"[!] Error ejecutando motor de tensores: {err_t}")
            input("\nPresiona [Enter] para continuar...")

        elif sub == "0":
            break


def _etiqueta_puntuacion(modelo_id: str, gestor_cache: GestorCache, hash_hw: str) -> str:
    """Retorna una etiqueta concisa con la puntuación y estado de afinamiento en SQLite."""
    opt = gestor_cache.obtener_configuracion_optima(modelo_id, hash_hw)
    if opt:
        tok_s = opt.get("tok_s_medido")
        score_str = f"{tok_s:.1f} t/s" if tok_s else "Afinado"
        fa_s = "FA:SÍ" if opt.get("flash_attn") else "FA:NO"
        return f"[Afinado: Score {score_str} | ngl={opt.get('n_gpu_layers', 0)}, c={opt.get('ctx_size', 2048)}, {fa_s}]"
    return "[Sin afinar]"


def ejecutar_comparativa_ast_directa(gestor_cache: Optional[GestorCache] = None) -> None:
    """Ejecuta en 1 paso la comparativa Inferencia Directa vs Árbol AST + Cara a Cara entre modelos."""
    import time
    from guarida_manager.tuning.ejecutor import encontrar_puerto_libre

    cache = gestor_cache or GestorCache()
    binario = GestorHerramientasBunker.resolver_ruta_ejecutable("llama-server")
    cliente = obtener_cliente_llama()
    gestor_srv = obtener_gestor_servidor(cache)
    hw_actual = obtener_informacion_hardware()

    filas = menu_actions.obtener_modelos_locales(cache)
    if not filas:
        print("\n[!] No hay modelos descargados en el disco. Usa la opción 1 para descargar uno.")
        input("Presiona [Enter] para continuar...")
        return

    def _es_emb(m_id: str) -> bool:
        ml = m_id.lower()
        return any(k in ml for k in ("embed", "bge", "minilm", "jina", "snowflake"))

    modelos_emb = [m for m in filas if _es_emb(m["id"])]
    if not modelos_emb:
        print("\n" + "=" * 70)
        print("  DESCARGA RÁPIDA DE MOTOR DE EMBEDDINGS AST")
        print("=" * 70)
        print("  [1] nomic-embed-text-v1.5       (Equilibrado, 0.15 GB / 768 dims)")
        print("  [2] jina-embeddings-v2-code-q4  (Especializado AST/Código, 0.10 GB / 8192 ctx)")
        print("  [3] snowflake-arctic-embed-m-q4 (Alta precisión técnica, 0.08 GB / 768 dims)")
        print("  [4] all-minilm-l6-v2-q8         (Ultraligero CPU/iGPU, 0.04 GB / >100 emb/s)")
        print("  [5] bge-m3-q4                   (Multilingüe ES/EN/Código, 0.42 GB)")
        print("-" * 70)
        sel_d = input("Elige motor AST a descargar [1-5] (Enter = 1, n = cancelar): ").strip().lower()
        if sel_d == "n":
            return
        mapa_emb = {
            "1": "nomic-embed-text-v1.5",
            "2": "jina-embeddings-v2-code-q4",
            "3": "snowflake-arctic-embed-m-q4",
            "4": "all-minilm-l6-v2-q8",
            "5": "bge-m3-q4",
        }
        id_desc = mapa_emb.get(sel_d, "nomic-embed-text-v1.5")
        try:
            print(f"\nDescargando '{id_desc}'...")
            DescargadorModelos(gestor_cache=cache).descargar_modelo(id_desc, permitir_inseguro=True)
            filas = menu_actions.obtener_modelos_locales(cache)
            modelos_emb = [m for m in filas if _es_emb(m["id"])]
        except Exception as err_desc:
            print(f"[!] Error descargando '{id_desc}': {err_desc}")
            input("Presiona [Enter] para continuar...")
            return

    lista_emb_a_probar = [modelos_emb[0]]
    if len(modelos_emb) > 1:
        print("\nMotores de Embeddings AST instalados:")
        for i, me in enumerate(modelos_emb, 1):
            tag = _etiqueta_puntuacion(me["id"], cache, hw_actual.hash_hardware)
            print(f"  [{i}] {me['id']} ({me.get('tamano_mb', '?')} MB) {tag}")
        print("  [T] Comparar TODOS los motores AST (Enter = TODOS)")
        s_e = input(f"Elige motor AST [1-{len(modelos_emb)} o Enter = TODOS]: ").strip().lower()
        if s_e.isdigit() and 1 <= int(s_e) <= len(modelos_emb):
            lista_emb_a_probar = [modelos_emb[int(s_e) - 1]]
        elif s_e in ("t", "todos", ""):
            lista_emb_a_probar = list(modelos_emb)

    modelos_gen = [m for m in filas if not _es_emb(m["id"])]
    lista_gen_a_probar = modelos_gen if modelos_gen else [modelos_emb[0]]
    if len(modelos_gen) > 1:
        print("\nModelos Generativos instalados:")
        for i, mg in enumerate(modelos_gen, 1):
            tag = _etiqueta_puntuacion(mg["id"], cache, hw_actual.hash_hardware)
            print(f"  [{i}] {mg['id']} ({mg.get('tamano_mb', '?')} MB) {tag}")
        print("  [T] Comparar TODOS cara a cara (Enter = TODOS)")
        s_g = input(f"Elige opción [1-{len(modelos_gen)} o Enter = TODOS]: ").strip().lower()
        if s_g.isdigit() and 1 <= int(s_g) <= len(modelos_gen):
            lista_gen_a_probar = [modelos_gen[int(s_g) - 1]]
        elif s_g in ("t", "todos", ""):
            lista_gen_a_probar = list(modelos_gen)

    perfil_bat = PerfilBateria(
        nombre="comparativa_ast",
        descripcion="Comparativa AST vs Directo",
        repeticiones_min=2,
        repeticiones_max=3,
        calentamientos_descartados=1,
        enfriamiento_segundos=0.5,
        escenarios_activos=["embedding", "arbol_nodos"],
    )

    resumen_cara_a_cara: list[dict] = []
    gestor_emb = GestorLlamaServer(gestor_cache=cache)

    try:
        for idx_e, mod_emb in enumerate(lista_emb_a_probar, 1):
            opt_emb = cache.obtener_configuracion_optima(mod_emb["id"], hw_actual.hash_hardware) or {}
            hilos_coop_emb = opt_emb.get("threads") or max(1, (hw_actual.nucleos_fisicos or 4) // 2)
            batch_coop_emb = opt_emb.get("batch_size") or 512
            ubatch_coop_emb = opt_emb.get("ubatch_size") or 512

            puerto_emb = encontrar_puerto_libre("127.0.0.1")
            clave_emb = secrets.token_urlsafe(32)
            cfg_emb = LlamaServerConfig(
                modelo_path=Path(mod_emb["ruta_local"]),
                binario_path=binario,
                host="127.0.0.1",
                port=puerto_emb,
                n_gpu_layers=0,
                ctx_size=2048,
                batch_size=batch_coop_emb,
                ubatch_size=ubatch_coop_emb,
                threads=hilos_coop_emb,
                embedding=True,
                api_key=clave_emb,
                alias=mod_emb["id"],
            )
            cliente_emb = ClienteLlamaOffline(host="127.0.0.1", port=puerto_emb, api_key=clave_emb)

            print(
                f"\nIniciando motor AST [{idx_e}/{len(lista_emb_a_probar)}] '{mod_emb['id']}' "
                f"[Modo Cooperativo: ngl=0, hilos={hilos_coop_emb}, batch={batch_coop_emb}] en puerto {puerto_emb}..."
            )
            gestor_emb.iniciar_servidor(cfg_emb)
            for _ in range(30):
                if cliente_emb.esta_disponible():
                    break
                time.sleep(0.5)

            print("\n" + "=" * 75)
            print(f"  COMPARATIVA EMPÍRICA: INFERENCIA DIRECTA VS ÁRBOL AST ({mod_emb['id']})")
            print("=" * 75)

            bateria_emb = BateriaEstresLlama(
                cliente=cliente_emb,
                perfil=perfil_bat,
                cliente_embedding=cliente_emb,
            )
            print(f"\n[Fase 1] Vectorizando Árbol AST con '{mod_emb['id']}' y liberando recursos antes del Coder...")
            res_emb = bateria_emb.ejecutar_escenario_embedding()
            validas_emb = [r for r in res_emb if not r.get("es_calentamiento") and r.get("exito") == 1] or res_emb
            emb_vel = 15.0
            if validas_emb:
                e0 = validas_emb[0]
                emb_vel = float(e0.get("embeddings_por_s") or 15.0)
                print(f"  -> Vectorización: {emb_vel} emb/s (Latencia: {e0.get('ttft_ms', 0)} ms | Dimensiones: {e0.get('dimensiones_vector', 0)})")

            try:
                bateria_emb.precalentar_cache_ast()
            except Exception:
                pass
            gestor_emb.detener_servidor()
            print("  -> [Cooperación Activa] Vectores AST en caché SHA-256; motor de embeddings pausado (100% hardware libre para Coder).")

            for idx_m, mod_gen in enumerate(lista_gen_a_probar, 1):
                if binario:
                    gestor_srv.detener_servidor()
                    time.sleep(0.5)
                    clave_gen = secrets.token_urlsafe(32)
                    cfg_gen = LlamaServerConfig.desde_afinamiento(
                        modelo_path=Path(mod_gen["ruta_local"]),
                        modelo_id=mod_gen["id"],
                        binario_path=binario,
                        gestor_cache=cache,
                        api_key=clave_gen,
                    )
                    opt_db = cache.obtener_configuracion_optima(mod_gen["id"], hw_actual.hash_hardware)
                    etiqueta_cfg = "AFINADO EN SQLITE" if opt_db else "AUTO-HEURÍSTICA (SIN AFINAR AÚN)"
                    cliente = ClienteLlamaOffline(host=cfg_gen.host, port=cfg_gen.port, api_key=clave_gen)
                    print(
                        f"\n[Modelo {idx_m}/{len(lista_gen_a_probar)}] Arrancando '{mod_gen['id']}' [{etiqueta_cfg}]\n"
                        f"  -> Config aplicada: ngl={cfg_gen.n_gpu_layers}, hilos={cfg_gen.threads}, "
                        f"ctx={cfg_gen.ctx_size}, batch={cfg_gen.batch_size}/{cfg_gen.ubatch_size}, "
                        f"kv={cfg_gen.kv_cache_type}, fa={'SÍ' if cfg_gen.flash_attn else 'NO'}"
                    )
                    gestor_srv.iniciar_servidor(cfg_gen)
                    arranco_ok = False
                    for _ in range(80):
                        if not gestor_srv.esta_activo():
                            break
                        if cliente.esta_disponible():
                            arranco_ok = True
                            break
                        time.sleep(0.5)

                    if not arranco_ok:
                        print(f"  [Auto-Recuperación] El servidor para '{mod_gen['id']}' no respondió; reintentando en modo CPU seguro (-ngl 0)...")
                        gestor_srv.detener_servidor()
                        time.sleep(0.8)
                        clave_gen = secrets.token_urlsafe(32)
                        cfg_gen = LlamaServerConfig(
                            modelo_path=Path(mod_gen["ruta_local"]),
                            binario_path=binario,
                            host="127.0.0.1",
                            port=encontrar_puerto_libre("127.0.0.1"),
                            n_gpu_layers=0,
                            ctx_size=min(cfg_gen.ctx_size, 4096),
                            batch_size=256,
                            ubatch_size=128,
                            threads=hw_actual.nucleos_fisicos or 4,
                            kv_cache_type="q8_0" if cfg_gen.kv_cache_type != "f16" else "f16",
                            flash_attn=False,
                            api_key=clave_gen,
                            alias=mod_gen["id"],
                        )
                        cliente = ClienteLlamaOffline(host=cfg_gen.host, port=cfg_gen.port, api_key=clave_gen)
                        gestor_srv.iniciar_servidor(cfg_gen)
                        for _ in range(80):
                            if not gestor_srv.esta_activo():
                                break
                            if cliente.esta_disponible():
                                break
                            time.sleep(0.5)

                bateria = BateriaEstresLlama(
                    cliente=cliente,
                    perfil=perfil_bat,
                    cliente_embedding=cliente_emb,
                )
                print(f"  Evaluando '{mod_gen['id']}' + AST '{mod_emb['id']}'...")
                res_arbol = bateria.ejecutar_escenario_arbol_nodos()
                validas_arbol = [r for r in res_arbol if not r.get("es_calentamiento") and "comparativa" in r] or [r for r in res_arbol if "comparativa" in r]

                # Auto-recuperación si Vulkan/GPU agota memoria o falla conexión
                if not validas_arbol and binario and res_arbol and any(
                    k in str(res_arbol[-1].get("error", "")) for k in ("OutOfDeviceMemory", "allocateMemory", "500", "failed", "10061", "denegó", "refused", "No se pudo conectar")
                ):
                    print(f"  [Auto-Ajuste RAM/CPU] Reintentando '{mod_gen['id']}' en modo CPU puro (--device none -ngl 0)...")
                    gestor_srv.detener_servidor()
                    time.sleep(0.8)
                    clave_cpu = secrets.token_urlsafe(32)
                    cfg_cpu = LlamaServerConfig(
                        modelo_path=Path(mod_gen["ruta_local"]),
                        binario_path=binario,
                        host="127.0.0.1",
                        port=encontrar_puerto_libre("127.0.0.1"),
                        n_gpu_layers=0,
                        ctx_size=1024,
                        batch_size=128,
                        ubatch_size=64,
                        threads=hw_actual.nucleos_fisicos or 4,
                        kv_cache_type="q8_0",
                        api_key=clave_cpu,
                        alias=mod_gen["id"],
                        extra_args=["--device", "none", "-nkvo"],
                    )
                    cliente = ClienteLlamaOffline(host=cfg_cpu.host, port=cfg_cpu.port, api_key=clave_cpu)
                    gestor_srv.iniciar_servidor(cfg_cpu)
                    arranco_cpu = False
                    for _ in range(80):
                        if not gestor_srv.esta_activo():
                            break
                        if cliente.esta_disponible():
                            arranco_cpu = True
                            break
                        time.sleep(0.5)
                    if not arranco_cpu:
                        gestor_srv.detener_servidor()
                        cfg_cpu.extra_args = ["-nkvo"]
                        gestor_srv.iniciar_servidor(cfg_cpu)
                        for _ in range(80):
                            if cliente.esta_disponible():
                                break
                            time.sleep(0.5)

                    bateria = BateriaEstresLlama(cliente=cliente, perfil=perfil_bat, cliente_embedding=cliente_emb)
                    res_arbol = bateria.ejecutar_escenario_arbol_nodos()
                    validas_arbol = [r for r in res_arbol if not r.get("es_calentamiento") and "comparativa" in r] or [r for r in res_arbol if "comparativa" in r]

                if validas_arbol:
                    ca = validas_arbol[0]["comparativa"]
                    tg_efec = ca.get("tg_efectivo_tok_s", ca.get("tg_arbol_tok_s", 0.0))
                    sp_x = ca.get("speedup_x", 1.0)
                    ahorro_tok = ca.get("ahorro_tokens_pct", 0.0)
                    cal_pct = ca.get("calidad_arbol_pct", 100.0)
                    score_conjunto = round((tg_efec * 0.40) + (sp_x * 12.0) + (ahorro_tok * 0.20) + (cal_pct * 0.15) + min(15.0, emb_vel * 0.4), 2)

                    es_c = any(k in mod_gen["id"].lower() for k in ("coder", "code"))
                    es_ch = any(k in mod_gen["id"].lower() for k in ("chat", "instruct"))
                    emb_low = mod_emb["id"].lower()
                    if es_c and "jina" in emb_low:
                        rec_uso = "Óptimo para refactorización AST de código en repositorios grandes (8k ctx)"
                    elif es_c and "bge" in emb_low:
                        rec_uso = "Excelente balance multilingüe para bases de código heterogéneas"
                    elif "minilm" in emb_low:
                        rec_uso = "Ultraligero: máxima velocidad y latencia mínima en recursos ajustados"
                    elif es_ch and ("bge" in emb_low or "nomic" in emb_low):
                        rec_uso = "Ideal para asistente conversacional con base documental RAG"
                    else:
                        rec_uso = "Pareja balanceada para tareas generales de asistencia e inferencia"

                    resumen_cara_a_cara.append({
                        "modelo_id": mod_gen["id"],
                        "ast_id": mod_emb["id"],
                        "score_conjunto": score_conjunto,
                        "recomendacion_uso": rec_uso,
                        **ca,
                    })

                    kv_eval = ca.get("tokens_evaluados_kv", ca["prompt_tokens_arbol"])
                    kv_cache = ca.get("tokens_cache_kv", 0)
                    info_kv = f" (KV Cache: {kv_cache} reutilizados, {kv_eval} evaluados)" if kv_cache > 0 else ""
                    print("\n" + "-" * 75)
                    print(f"  RESULTADOS: {mod_gen['id']} + AST {mod_emb['id']}")
                    print("-" * 75)
                    print(f"  * Score de Conjunto:           {score_conjunto}")
                    print(f"  * Recomendación de Uso:        {rec_uso}")
                    print(f"  * Nodo AST recuperado:         {ca['nodo_recuperado']}")
                    print(f"  * Tokens de Prompt (Entrada):  AST+BPE: {ca['prompt_tokens_arbol']} vs Base: {ca['prompt_tokens_baseline']} tokens{info_kv}")
                    print(f"  * Tokens Generados (Salida):   AST Telegráfico: {ca.get('predicted_tokens_arbol', '?')} vs Base: {ca.get('predicted_tokens_baseline', '?')} tokens")
                    print(f"  * Compresión / Ahorro Tokens:  {ca['ahorro_tokens_pct']}% ({ca.get('ratio_compresion_x', 1.0)}x menos tokens de contexto)")
                    print(f"  * Velocidad Lectura (PP):      AST: {ca.get('pp_arbol_tok_s', 0.0)} tok/s vs Base: {ca.get('pp_baseline_tok_s', 0.0)} tok/s")
                    print(
                        f"  * Velocidad Creación (TG):     AST: {ca.get('tg_arbol_tok_s', 0.0)} tok/s "
                        f"(Efectiva: {ca.get('tg_efectivo_tok_s', ca.get('tg_arbol_tok_s', 0.0))} tok/s) "
                        f"vs Base: {ca.get('tg_baseline_tok_s', 0.0)} tok/s"
                    )
                    print(f"  * Latencia Baseline directa:   {ca['latencia_baseline_ms']} ms")
                    print(f"  * Latencia asistida por AST:   {ca['latencia_arbol_ms']} ms (búsqueda AST: {ca['overhead_recuperacion_ast_ms']} ms)")
                    print(f"  * Aceleración (Speedup):       {ca.get('speedup_x', 1.0)}x más rápido")
                    print(f"  * Calidad de respuesta:        AST: {ca['calidad_arbol_pct']}% vs Base: {ca['calidad_baseline_pct']}%")
                    print("-" * 75)
                elif res_arbol and res_arbol[-1].get("error"):
                    tam_mod_gb = (mod_gen.get("tamano_mb", 0) or 0) / 1024.0
                    print(f"  [!] Fallo en '{mod_gen['id']}': {res_arbol[-1]['error']}")
                    print(f"      Nota técnica: El modelo '{mod_gen['id']}' ({tam_mod_gb:.1f} GB) requiere suficiente memoria libre. Prueba en modo CPU puro (-ngl 0) o con un contexto menor.")

        if len(resumen_cara_a_cara) > 1:
            print("\n" + "=" * 105)
            print("  TABLA COMPARATIVA CARA A CARA ENTRE MODELOS GENERATIVOS (CON Y SIN AST)")
            print("=" * 105)
            print(f"{'Modelo Generativo':<30} {'Motor AST':<22} {'PP Base/AST(t/s)':<18} {'TG Base/AST(t/s)':<18} {'Speedup':<8} {'Calidad':<8}")
            print("-" * 105)
            for rc in resumen_cara_a_cara:
                pp_s = f"{rc.get('pp_baseline_tok_s', 0):.1f} / {rc.get('pp_arbol_tok_s', 0):.1f}"
                tg_s = f"{rc.get('tg_baseline_tok_s', 0):.1f} / {rc.get('tg_arbol_tok_s', 0):.1f}"
                sp_s = f"{rc.get('speedup_x', 1.0)}x"
                cal_s = f"{rc['calidad_arbol_pct']:.0f}%"
                print(f"{rc['modelo_id'][:29]:<30} {rc['ast_id'][:21]:<22} {pp_s:<18} {tg_s:<18} {sp_s:<8} {cal_s:<8}")
            print("=" * 105)

        if resumen_cara_a_cara:
            resumen_cara_a_cara.sort(key=lambda x: x.get("score_conjunto", 0.0), reverse=True)
            print("\n" + "=" * 110)
            print("  RANKING DE PAREJAS COMBINADAS (MODELO GENERATIVO + MOTOR AST) Y RECOMENDACIÓN DE USO")
            print("=" * 110)
            print(f"{'#':<3} {'Modelo Generativo':<26} {'Motor AST':<22} {'Score Conj':<11} {'Speedup':<9} {'Ahorro Tok':<11} {'Recomendación de Uso'}")
            print("-" * 110)
            for idx_rc, rc in enumerate(resumen_cara_a_cara, 1):
                sp_txt = f"{rc.get('speedup_x', 1.0)}x"
                ah_txt = f"{rc.get('ahorro_tokens_pct', 0.0)}%"
                sc_txt = f"{rc.get('score_conjunto', 0.0):.2f}"
                print(f"{idx_rc:<3} {rc['modelo_id'][:25]:<26} {rc['ast_id'][:21]:<22} {sc_txt:<11} {sp_txt:<9} {ah_txt:<11} {rc.get('recomendacion_uso', '')}")
            print("=" * 110)
            mejor_par = resumen_cara_a_cara[0]
            print(f"\n[PAREJA RECOMENDADA PARA ESTE HARDWARE]: '{mejor_par['modelo_id']}' + '{mejor_par['ast_id']}' (Score: {mejor_par['score_conjunto']})")
            print(f"  -> {mejor_par['recomendacion_uso']}")
    except Exception as e:
        logger.error(f"Error en comparativa de árbol de nodos: {e}", exc_info=True)
        print(f"[!] Error durante la ejecución de la prueba: {e}")
    finally:
        gestor_emb.detener_servidor()
        gestor_srv.detener_servidor()
    input("\nPresiona [Enter] para continuar...")


def opcion_afinador_y_benchmark(gestor_cache: Optional[GestorCache] = None) -> None:
    cache = gestor_cache or GestorCache()
    binario = GestorHerramientasBunker.resolver_ruta_ejecutable("llama-server")
    generador_informes = GeneradorInformesTuning(gestor_cache=cache)

    while True:
        limpiar_pantalla()
        print("=" * 75)
        print("      AFINADOR DE PUNTO DULCE Y BENCHMARKING DE LLAMA-SERVER")
        print("=" * 75)
        print("  1. Auto-Afinar automáticamente TODOS los modelos locales (1 clic en SQLite)")
        print("  2. Auto-Afinar un modelo específico (cálculo por hardware en SQLite)")
        print("  3. Búsqueda exhaustiva de Punto Dulce (Benchmark empírico con barrido)")
        print("  4. Comparativa Directa vs Árbol AST y Cara a Cara de Modelos")
        print("  5. Ver Ranking de Punto Dulce e Informes Guardados")
        print("  6. Test rápido de velocidad sobre servidor activo")
        print("  0. Volver al menú principal")
        print("-" * 75)

        sub = input("Selecciona una opción [0-6]: ").strip()
        if sub in ("4",):
            ejecutar_comparativa_ast_directa(cache)

        elif sub == "1":
            print("\n--- AUTO-AFINAMIENTO DE TODOS LOS MODELOS LOCALES ---")
            locales = menu_actions.obtener_modelos_locales(cache)
            if not locales:
                print("[!] No hay modelos descargados en el disco.")
            else:
                afinados = menu_actions.afinar_todos_automatico(cache, forzar=True)
                print(f"[OK] {len(afinados)} modelos afinados automáticamente para este hardware:")
                for a in afinados:
                    print(f"  * {a.modelo_id}: -ngl {a.n_gpu_layers}, -c {a.ctx_size}, -b {a.batch_size}, kv={a.kv_cache_tipo}, threads={a.threads}")

                parejas = menu_actions.obtener_mejores_parejas_combinadas(cache)
                if parejas:
                    print("\n--- AFINAMIENTO COMBINADO DE MODELOS CON EMBEDDINGS AST ---")
                    print(f"{'#':<3} {'Modelo Generativo':<28} {'Motor AST':<26} {'Score':<8} {'Recomendación de Uso'}")
                    print("-" * 95)
                    for idx_p, p in enumerate(parejas[:5], 1):
                        print(f"{idx_p:<3} {p['modelo_gen_id'][:27]:<28} {p['modelo_emb_id'][:25]:<26} {p['score_conjunto']:<8.2f} {p['recomendacion_uso']}")
                    print("=" * 95)
                    p0 = parejas[0]
                    print(f"[RECOMENDACIÓN ÓPTIMA]: Pareja '{p0['modelo_gen_id']}' + '{p0['modelo_emb_id']}' (Score Conjunto: {p0['score_conjunto']})")
                    print(f"  -> {p0['recomendacion_uso']}")
            input("\nPresiona [Enter] para continuar...")

        elif sub == "2":
            print("\n--- AUTO-AFINAR UN MODELO ESPECÍFICO ---")
            locales = menu_actions.obtener_modelos_locales(cache)
            if not locales:
                print("[!] No hay modelos descargados.")
            else:
                hw_act = obtener_informacion_hardware()
                for idx, f in enumerate(locales, 1):
                    tag = _etiqueta_puntuacion(f["id"], cache, hw_act.hash_hardware)
                    print(f"  [{idx}] {f['id']} ({f.get('tamano_mb', '?')} MB) {tag}")
                sel_m = input(f"Elige modelo [1-{len(locales)}] (Enter = 1): ").strip() or "1"
                if sel_m.isdigit() and 1 <= int(sel_m) <= len(locales):
                    m_sel = locales[int(sel_m) - 1]
                    reg = menu_actions.afinar_modelo_automatico(cache, m_sel["id"], Path(m_sel["ruta_local"]), forzar=True)
                    print(f"\n[OK] Modelo '{reg.modelo_id}' afinado en SQLite:")
                    print(f"  * Capas GPU (-ngl): {reg.n_gpu_layers} | Contexto (-c): {reg.ctx_size}")
                    print(f"  * Batch: {reg.batch_size}/{reg.ubatch_size} | Hilos: {reg.threads} | KV: {reg.kv_cache_tipo}")

                    es_emb_sel = any(k in m_sel["id"].lower() for k in ("embed", "bge", "minilm", "jina", "snowflake"))
                    if not es_emb_sel:
                        embs = [m for m in locales if any(k in m["id"].lower() for k in ("embed", "bge", "minilm", "jina", "snowflake"))]
                        if embs:
                            print("\n--- AFINAMIENTO COMBINADO CON MOTORES DE EMBEDDINGS AST ---")
                            for e in embs:
                                comb = menu_actions.calcular_afinamiento_combinado(cache, m_sel["id"], e["id"], Path(m_sel["ruta_local"]), Path(e["ruta_local"]))
                                print(f"  * Con '{e['id']}': Score Conjunto = {comb['score_conjunto']} | Mem: {comb['memoria_conjunta_mb']} MB")
                                print(f"    -> {comb['recomendacion_uso']}")
                    else:
                        gens = [m for m in locales if not any(k in m["id"].lower() for k in ("embed", "bge", "minilm", "jina", "snowflake"))]
                        if gens:
                            print("\n--- AFINAMIENTO COMBINADO CON MODELOS GENERATIVOS ---")
                            for g in gens:
                                comb = menu_actions.calcular_afinamiento_combinado(cache, g["id"], m_sel["id"], Path(g["ruta_local"]), Path(m_sel["ruta_local"]))
                                print(f"  * Con '{g['id']}': Score Conjunto = {comb['score_conjunto']} | Mem: {comb['memoria_conjunta_mb']} MB")
                                print(f"    -> {comb['recomendacion_uso']}")
            input("\nPresiona [Enter] para continuar...")

        elif sub == "3":
            if not binario:
                print("[!] No se encontró llama-server.")
            else:
                filas = menu_actions.obtener_modelos_locales(cache)
                if not filas:
                    print("[!] No hay modelos descargados localmente.")
                else:
                    print("\nModelos disponibles:")
                    for idx, f in enumerate(filas, start=1):
                        print(f"  [{idx}] {f['id']} ({f.get('tamano_mb', '?')} MB)")
                    s_mod = input(f"\nElige modelo [1-{len(filas)}] (Enter = 1): ").strip() or "1"
                    if s_mod.isdigit() and 1 <= int(s_mod) <= len(filas):
                        m_sel = filas[int(s_mod) - 1]
                        s_p = input("Perfil: [1] Rápido (Recomendado)  [2] Estándar  [3] Exhaustivo (Enter = 1): ").strip() or "1"
                        p_nombre = "estandar" if s_p == "2" else ("exhaustivo" if s_p == "3" else "rapido")
                        caps = DescubridorCapacidades.descubrir(binario, gestor_cache=cache)
                        p_barrido = GestorPerfilesTuning.obtener_perfil_barrido(p_nombre)
                        p_barrido.objetivo_scoring = "coder_ast"
                        p_bateria = GestorPerfilesTuning.obtener_perfil_bateria(p_nombre)
                        if "arbol_nodos" not in p_bateria.escenarios_activos:
                            p_bateria.escenarios_activos.append("arbol_nodos")

                        print(f"\nBuscando Punto Dulce para '{m_sel['id']}'...")
                        try:
                            obtener_gestor_servidor(cache).detener_servidor()
                            buscador = BuscadorAfinamientoEtapas(
                                modelo_path=Path(m_sel["ruta_local"]),
                                modelo_id=m_sel["id"],
                                capacidades=caps,
                                perfil_barrido=p_barrido,
                                perfil_bateria=p_bateria,
                                gestor_cache=cache,
                                callback_progreso=lambda msg, pct: print(msg),
                            )
                            ganador = buscador.ejecutar_barrido_completo()
                            if ganador and ganador.estado == "ok":
                                print(f"\n[OK] ¡Punto Dulce encontrado! Score: {ganador.score}")
                            else:
                                print("\n[!] No se encontró configuración estable.")
                        except Exception as e:
                            logger.error(f"Fallo durante afinamiento de {m_sel['id']}: {e}", exc_info=True)
                            print(f"\n[!] Error durante el afinamiento: {e}")
            input("Presiona [Enter] para continuar...")

        elif sub == "5":
            hw_actual = obtener_informacion_hardware()
            locales = menu_actions.obtener_modelos_locales(cache)
            print("\n" + "=" * 98)
            print("  PANEL GENERAL: PUNTO DULCE ÓPTIMO POR MODELO Y PAREJAS COMBINADAS")
            print("=" * 98)
            if locales:
                print(f"{'#':<3} {'Modelo':<34} {'Tipo':<12} {'NGL':<5} {'Ctx':<6} {'KV':<6} {'Hilos':<6} {'Score':<8}")
                print("-" * 98)
                for idx_l, m in enumerate(locales, 1):
                    es_e = any(k in m["id"].lower() for k in ("embed", "bge", "minilm", "jina", "snowflake"))
                    tipo_str = "Embedding" if es_e else "Generativo"
                    opt = cache.obtener_configuracion_optima(m["id"], hw_actual.hash_hardware)
                    if opt:
                        ngl_s = str(opt.get("n_gpu_layers", 0))
                        ctx_s = str(opt.get("ctx_size", 4096))
                        kv_s = str(opt.get("kv_cache_tipo", "f16"))
                        th_s = str(opt.get("threads", 4))
                        sc_s = f"{opt.get('tok_s_medido', 0.0):.2f}"
                    else:
                        ngl_s, ctx_s, kv_s, th_s, sc_s = "-", "-", "-", "-", "Sin afinar"
                    print(f"{idx_l:<3} {m['id'][:33]:<34} {tipo_str:<12} {ngl_s:<5} {ctx_s:<6} {kv_s:<6} {th_s:<6} {sc_s:<8}")
                print("-" * 98)

            parejas = menu_actions.obtener_mejores_parejas_combinadas(cache)
            if parejas:
                print("\nPAREJAS COMBINADAS RECOMENDADAS (GENERATIVO + EMBEDDINGS AST):")
                print(f"{'#':<3} {'Modelo Generativo':<28} {'Motor AST':<26} {'Score Conj':<11} {'Recomendación de Uso'}")
                print("-" * 98)
                for idx_p, p in enumerate(parejas[:5], 1):
                    print(f"{idx_p:<3} {p['modelo_gen_id'][:27]:<28} {p['modelo_emb_id'][:25]:<26} {p['score_conjunto']:<11.2f} {p['recomendacion_uso']}")
                print("=" * 98)

            with cache.sesion() as conn:
                sesiones = conn.execute("SELECT * FROM bench_sesiones ORDER BY inicio DESC LIMIT 10;").fetchall()
            if not sesiones:
                print("\nNo hay sesiones de benchmark individuales registradas aún.")
            else:
                ultima_id = sesiones[0]["id"]
                print("\nSesiones de benchmark individuales para auditar en detalle:")
                for idx_s, s in enumerate(sesiones, 1):
                    print(f"  [{idx_s}] {s['modelo_id']} | {s['estado']} | {s['inicio']} (ID: {s['id']})")
                sel_s = input("\nNúmero de sesión a consultar [1-10], [U] ver última completa, o [E] exportar (Enter = volver): ").strip().lower()
                if sel_s == "e":
                    rcsv, rjson = generador_informes.exportar_csv_y_json(ultima_id)
                    print(f"[OK] Exportado a:\n  {rcsv}\n  {rjson}")
                elif sel_s == "u":
                    generador_informes.imprimir_tabla_consola(ultima_id)
                elif sel_s.isdigit() and 1 <= int(sel_s) <= len(sesiones):
                    generador_informes.imprimir_tabla_consola(sesiones[int(sel_s) - 1]["id"])
            input("Presiona [Enter] para continuar...")

        elif sub == "4":
            cliente = obtener_cliente_llama()
            if not cliente.esta_disponible():
                filas = menu_actions.obtener_modelos_locales(cache)
                if filas and binario:
                    mod_sel = filas[0]
                    gestor_srv = obtener_gestor_servidor(cache)
                    clave_api = secrets.token_urlsafe(32)
                    cfg_levantar = LlamaServerConfig.desde_afinamiento(
                        modelo_path=Path(mod_sel["ruta_local"]),
                        modelo_id=mod_sel["id"],
                        binario_path=binario,
                        gestor_cache=cache,
                        api_key=clave_api,
                    )
                    cliente.api_key = clave_api
                    print(f"Arrancando '{mod_sel['id']}' en puerto {cfg_levantar.port}...")
                    gestor_srv.iniciar_servidor(cfg_levantar)
                    import time
                    time.sleep(2.5)

            if cliente.esta_disponible():
                try:
                    from guarida_manager.tuning.scoring import EvaluadorScoring
                    gestor_srv = obtener_gestor_servidor(cache)
                    ctx_actual = gestor_srv.obtener_estado().get("ctx_size", 4096)
                    print(f"\nEjecutando test rápido de velocidad (Contexto: {ctx_actual})...")
                    perfil_bat = GestorPerfilesTuning.obtener_perfil_bateria("rapido")
                    bateria = BateriaEstresLlama(cliente, perfil_bat)
                    res = bateria.ejecutar_bateria_completa(ctx_size=ctx_actual)
                    stats = EvaluadorScoring.extraer_metricas_resumen(res)
                    print(f"\n[OK] Resultados ({len(res)} pruebas):")
                    print(f"  * Velocidad Lectura (Prefill PP):  {stats['pp_stats']['mediana']} tok/s")
                    print(f"  * Velocidad Creación (Gen TG):     {stats['tg_stats']['mediana']} tok/s")
                    print(f"  * Latencia Primer Token (TTFT):    {stats['ttft_stats']['mediana']} ms")
                    print(f"  * Calidad / Éxito:                 {stats['calidad_media']:.1f}%")
                except Exception as e:
                    print(f"[!] Error: {e}")
            input("Presiona [Enter] para continuar...")

        elif sub in ("0", ""):
            break


def opcion_logs_sistema() -> None:
    print("\n--- [8] REGISTRO Y DIAGNÓSTICO DE ERRORES DEL SISTEMA (LOGS) ---")
    lineas = obtener_ultimas_lineas_log(n_lineas=40)
    for l in lineas:
        print(l, end="" if l.endswith("\n") else "\n")
    print("-" * 75)


def opcion_diagnostico_unificado(cache: GestorCache) -> None:
    while True:
        limpiar_pantalla()
        print("=" * 65)
        print("           DIAGNÓSTICO DEL SISTEMA Y UTILIDADES")
        print("=" * 65)
        print("  1. Hardware, CPU, GPU y Memoria GTT/VRAM")
        print("  2. Estado de Base de Datos SQLite y Perfiles Afinados")
        print("  3. Ejecutar Pruebas Unitarias (Tests)")
        print("  4. Test de Estrés de Memoria RAM/VRAM")
        print("  5. Ver Registro de Errores (Logs)")
        print("  0. Volver")
        print("-" * 65)
        sub = input("Selecciona opción [0-5]: ").strip()
        if sub in ("0", ""):
            break
        elif sub == "1":
            opcion_hardware()
            input("Presiona [Enter] para continuar...")
        elif sub == "2":
            opcion_cache(cache)
            hw = obtener_informacion_hardware()
            menu_actions.listar_perfiles_afinamiento(cache, hw.hash_hardware)
            input("Presiona [Enter] para continuar...")
        elif sub == "3":
            opcion_tests()
            input("Presiona [Enter] para continuar...")
        elif sub == "4":
            opcion_estres_memoria()
            input("Presiona [Enter] para continuar...")
        elif sub == "5":
            opcion_logs_sistema()
            input("Presiona [Enter] para continuar...")


def opcion_asistente_configuracion_llm(gestor_cache: Optional[GestorCache] = None) -> None:
    cache = gestor_cache or GestorCache()
    srv = obtener_gestor_servidor(cache)
    cli = obtener_cliente_llama()
    ejecutar_chat_terminal(cache, gestor_server=srv, cliente=cli)


def iniciar_menu(gestor_cache: Optional[GestorCache] = None) -> None:
    cache = gestor_cache or GestorCache()
    inicializar_logging()

    # Escaneo automático de hardware inmediatamente en el arranque de la aplicación
    info_hw = obtener_informacion_hardware()
    est_hw = menu_actions.estimar_conjunto_modelos_optimo(info_hw)
    logger.info(
        f"Escaneo de hardware automático al arranque: CPU='{info_hw.modelo_cpu}', "
        f"RAM={info_hw.ram_total_gb:.2f}GB, GPU='{info_hw.nombre_gpu_principal}' ({info_hw.tipo_gpu_principal}), "
        f"VRAM/GTT={info_hw.gtt_disponible_gb:.2f}GB, Tier={est_hw['tier']}"
    )

    while True:
        mostrar_banner()

        # Resumen de escaneo de hardware automático
        print("=" * 75)
        print("  ESCANEO AUTOMÁTICO DE HARDWARE Y RECOMENDACIÓN")
        print("=" * 75)
        print(f"  * CPU:              {info_hw.modelo_cpu} ({info_hw.nucleos_fisicos} núcleos / {info_hw.nucleos_logicos} hilos)")
        print(f"  * RAM Total:        {info_hw.ram_total_gb:.2f} GB | Límite Extremo Forzable: {info_hw.memoria_extrema_forzable_gb:.2f} GB")
        gpu_txt = f"{info_hw.nombre_gpu_principal} [{info_hw.gtt_disponible_gb:.2f} GB VRAM/GTT]" if info_hw.tiene_aceleracion_gpu else "Sin GPU (Modo CPU puro)"
        print(f"  * Dispositivo GPU:  {gpu_txt}")
        print(f"  * Nivel Asignado:   [{est_hw['tier'].upper()}] - {est_hw['descripcion']}")
        print(f"  * Hash Hardware:    {info_hw.hash_hardware[:16]}...")
        print("=" * 75)

        filas_inst = menu_actions.obtener_modelos_locales(cache)
        nombres_inst = ", ".join(m["id"] for m in filas_inst) if filas_inst else "Ninguno aún"
        print(f"Modelos en disco ({len(filas_inst)}): {nombres_inst}")
        print("-" * 75)
        print("Menú Principal:")
        print("  [A] MODO AUTOMÁTICO:  Descarga y Afinamiento Óptimo en 1-Paso para este Hardware")
        print("  [1] MODO MANUAL:      Catálogo de Modelos (Ultraligeros, Estándar, Extremos)")
        print("  [2] Comparativa Directa vs Árbol AST y Cara a Cara de Modelos")
        print("  [3] Afinamiento de llama-server y Modelos (Auto 1-clic o Benchmark)")
        print("  [4] Servidor Local e Inferencia (Arrancar / Chat / Estado)")
        print("  [5] Diagnóstico del Sistema (Hardware, Caché, Tests y Logs)")
        print("  [6] Chat por Terminal con Modelo (Parejas Recomendadas / Métricas)")
        print("  [0] Salir")
        print("-" * 75)
        
        try:
            opcion = input("Selecciona una opción [A, 1-6, 0]: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\nSaliendo de GuarIdA...")
            sys.exit(0)

        try:
            if opcion.lower() == "a":
                opcion_modo_automatico(cache)
            elif opcion == "1":
                opcion_catalogo_y_bunker(cache)
            elif opcion == "2":
                ejecutar_comparativa_ast_directa(cache)
            elif opcion in ("3", "7"):
                opcion_afinador_y_benchmark(cache)
            elif opcion in ("4",):
                opcion_motor_inferencia(cache)
            elif opcion == "5":
                opcion_diagnostico_unificado(cache)
            elif opcion in ("6", "c", "C") or opcion.lower() == "chat":
                opcion_asistente_configuracion_llm(cache)
                input("\nPresiona [Enter] para volver al menú...")
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
