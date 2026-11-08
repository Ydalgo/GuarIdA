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


def opcion_catalogo_y_bunker(gestor_cache: Optional[GestorCache] = None) -> None:
    cache = gestor_cache or GestorCache()
    while True:
        limpiar_pantalla()
        locales = {m["id"]: m for m in menu_actions.obtener_modelos_locales(cache)}
        modelos_disp = list(CatalogoModelos.MODELOS.values())

        print("=" * 75)
        print("  GESTOR RÁPIDO DE MODELOS Y DESCARGAS (1-PASO)")
        print("=" * 75)
        for i, m in enumerate(modelos_disp, 1):
            est = f"[INSTALADO: {locales[m.id].get('tamano_mb', '?')} MB]" if m.id in locales else f"[{m.tamano_gb:.2f} GB]"
            rol = m.categoria.upper()
            print(f"  [{i:>2}] {m.id:<32} ({rol:<10} {m.cuantizacion}) {est}")

        print("-" * 75)
        print("Acciones rápidas:")
        print("  * Escribe número(s) (ej. 5 o 11,12) -> Descargar modelo(s) directamente")
        print("  * [A] Eliminar/Archivar modelo del disco   | [H] Verificar llama-server")
        print("  * [C] Añadir GGUF personalizado de HF      | [0 / Enter] Volver")
        print("-" * 75)

        sub = input("Opción o número(s) a descargar: ").strip()
        if not sub or sub == "0":
            break

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
            repo = input("Repositorio HF (ej. Qwen/Qwen3-8B-GGUF): ").strip()
            filename = input("Archivo .gguf (ej. Qwen3-8B-Q4_K_M.gguf): ").strip()
            if repo and filename:
                cat = input("Categoría [coder/chat/embedding] (Enter = coder): ").strip().lower() or "coder"
                mid = filename.lower().replace(".gguf", "")
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
        print("  6. Test de generacion e inferencia local (/v1/chat/completions)")
        print("  7. Probar vectorización y búsqueda semántica en Árbol de Nodos (AST)")
        print("  0. Volver al menu principal")
        print("-" * 65)

        try:
            sub = input("Selecciona una opcion [0-7]: ").strip()
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

        elif sub == "0":
            break


def ejecutar_comparativa_ast_directa(gestor_cache: Optional[GestorCache] = None) -> None:
    """Ejecuta en 1 paso la comparativa Inferencia Directa vs Árbol AST + Cara a Cara entre modelos."""
    import time
    from guarida_manager.tuning.ejecutor import encontrar_puerto_libre

    cache = gestor_cache or GestorCache()
    binario = GestorHerramientasBunker.resolver_ruta_ejecutable("llama-server")
    cliente = obtener_cliente_llama()
    gestor_srv = obtener_gestor_servidor(cache)

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

    mod_emb = modelos_emb[0]
    if len(modelos_emb) > 1:
        print("\nMotores de Embeddings AST instalados:")
        for i, me in enumerate(modelos_emb, 1):
            print(f"  [{i}] {me['id']} ({me.get('tamano_mb', '?')} MB)")
        s_e = input(f"Elige motor AST [1-{len(modelos_emb)}] (Enter = 1): ").strip()
        if s_e.isdigit() and 1 <= int(s_e) <= len(modelos_emb):
            mod_emb = modelos_emb[int(s_e) - 1]

    modelos_gen = [m for m in filas if not _es_emb(m["id"])]
    lista_gen_a_probar = modelos_gen if modelos_gen else [mod_emb]
    if len(modelos_gen) > 1:
        print("\nModelos Generativos instalados:")
        for i, mg in enumerate(modelos_gen, 1):
            print(f"  [{i}] {mg['id']} ({mg.get('tamano_mb', '?')} MB)")
        print("  [T] Comparar TODOS cara a cara (por defecto al pulsar Enter)")
        s_g = input(f"Elige opción [1-{len(modelos_gen)} o Enter = TODOS]: ").strip().lower()
        if s_g.isdigit() and 1 <= int(s_g) <= len(modelos_gen):
            lista_gen_a_probar = [modelos_gen[int(s_g) - 1]]

    gestor_emb = GestorLlamaServer(gestor_cache=cache)
    puerto_emb = encontrar_puerto_libre("127.0.0.1")
    clave_emb = secrets.token_urlsafe(32)
    cfg_emb = LlamaServerConfig(
        modelo_path=Path(mod_emb["ruta_local"]),
        binario_path=binario,
        host="127.0.0.1",
        port=puerto_emb,
        n_gpu_layers=0,
        ctx_size=2048,
        batch_size=512,
        ubatch_size=512,
        threads=4,
        embedding=True,
        api_key=clave_emb,
        alias=mod_emb["id"],
    )
    cliente_emb = ClienteLlamaOffline(host="127.0.0.1", port=puerto_emb, api_key=clave_emb)
    resumen_cara_a_cara: list[dict] = []

    try:
        print(f"\nIniciando motor AST '{mod_emb['id']}' en puerto {puerto_emb}...")
        gestor_emb.iniciar_servidor(cfg_emb)
        for _ in range(30):
            if cliente_emb.esta_disponible():
                break
            time.sleep(0.5)

        print("\n" + "=" * 75)
        print("  COMPARATIVA EMPÍRICA: INFERENCIA DIRECTA VS ÁRBOL DE NODOS AST + EMBEDDINGS")
        print("=" * 75)
        perfil_bat = PerfilBateria(
            nombre="comparativa_ast",
            descripcion="Comparativa AST vs Directo",
            repeticiones_min=2,
            repeticiones_max=3,
            calentamientos_descartados=1,
            enfriamiento_segundos=0.5,
            escenarios_activos=["embedding", "arbol_nodos"],
        )

        bateria_emb = BateriaEstresLlama(
            cliente=cliente_emb,
            perfil=perfil_bat,
            cliente_embedding=cliente_emb,
        )
        print(f"\n[Fase 1] Midiendo throughput de vectorización (/embedding) con '{mod_emb['id']}'...")
        res_emb = bateria_emb.ejecutar_escenario_embedding()
        validas_emb = [r for r in res_emb if not r.get("es_calentamiento") and r.get("exito") == 1] or res_emb
        if validas_emb:
            e0 = validas_emb[0]
            print(f"  -> Vectorización: {e0.get('embeddings_por_s', 0)} emb/s (Latencia: {e0.get('ttft_ms', 0)} ms | Dimensiones: {e0.get('dimensiones_vector', 0)})")

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
                hw_actual = obtener_informacion_hardware()
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
                for _ in range(90):
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

            # Auto-recuperación si Vulkan/GPU agota memoria (ej. Qwen3-30B-A3B en iGPU integrada)
            if not validas_arbol and binario and res_arbol and any(
                k in str(res_arbol[-1].get("error", "")) for k in ("OutOfDeviceMemory", "allocateMemory", "500", "failed")
            ):
                print(f"  [Auto-Ajuste RAM/CPU] '{mod_gen['id']}' excede la memoria de vídeo Vulkan; reintentando en modo CPU puro (--device none -ngl 0)...")
                gestor_srv.detener_servidor()
                time.sleep(0.8)
                clave_cpu = secrets.token_urlsafe(32)
                cfg_cpu = LlamaServerConfig(
                    modelo_path=Path(mod_gen["ruta_local"]),
                    binario_path=binario,
                    host="127.0.0.1",
                    port=8083,
                    n_gpu_layers=0,
                    ctx_size=1024,
                    batch_size=128,
                    ubatch_size=64,
                    threads=obtener_informacion_hardware().nucleos_fisicos or 4,
                    kv_cache_type="q8_0",
                    api_key=clave_cpu,
                    alias=mod_gen["id"],
                    extra_args=["--device", "none", "-nkvo"],
                )
                cliente = ClienteLlamaOffline(host=cfg_cpu.host, port=cfg_cpu.port, api_key=clave_cpu)
                gestor_srv.iniciar_servidor(cfg_cpu)
                arranco_cpu = False
                for _ in range(90):
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
                    for _ in range(90):
                        if cliente.esta_disponible():
                            break
                        time.sleep(0.5)

                bateria = BateriaEstresLlama(cliente=cliente, perfil=perfil_bat, cliente_embedding=cliente_emb)
                res_arbol = bateria.ejecutar_escenario_arbol_nodos()
                validas_arbol = [r for r in res_arbol if not r.get("es_calentamiento") and "comparativa" in r] or [r for r in res_arbol if "comparativa" in r]

            if validas_arbol:
                ca = validas_arbol[0]["comparativa"]
                resumen_cara_a_cara.append({"modelo_id": mod_gen["id"], "ast_id": mod_emb["id"], **ca})
                kv_eval = ca.get("tokens_evaluados_kv", ca["prompt_tokens_arbol"])
                kv_cache = ca.get("tokens_cache_kv", 0)
                info_kv = f" (KV Cache: {kv_cache} reutilizados, {kv_eval} evaluados)" if kv_cache > 0 else ""
                print("\n" + "-" * 75)
                print(f"  RESULTADOS: {mod_gen['id']} + AST {mod_emb['id']}")
                print("-" * 75)
                print(f"  * Nodo AST recuperado:         {ca['nodo_recuperado']}")
                print(f"  * Tokens de Prompt (Baseline): {ca['prompt_tokens_baseline']} tokens")
                print(f"  * Tokens de Prompt (AST+BPE):  {ca['prompt_tokens_arbol']} tokens{info_kv}")
                print(f"  * Compresión / Ahorro Tokens:  {ca['ahorro_tokens_pct']}% ({ca.get('ratio_compresion_x', 1.0)}x menos tokens)")
                print(f"  * Velocidad Lectura (PP):      AST: {ca.get('pp_arbol_tok_s', 0.0)} tok/s vs Base: {ca.get('pp_baseline_tok_s', 0.0)} tok/s")
                print(f"  * Velocidad Creación (TG):     AST: {ca.get('tg_arbol_tok_s', 0.0)} tok/s vs Base: {ca.get('tg_baseline_tok_s', 0.0)} tok/s")
                print(f"  * Latencia Baseline directa:   {ca['latencia_baseline_ms']} ms")
                print(f"  * Latencia asistida por AST:   {ca['latencia_arbol_ms']} ms (búsqueda AST: {ca['overhead_recuperacion_ast_ms']} ms)")
                print(f"  * Aceleración (Speedup):       {ca.get('speedup_x', 1.0)}x más rápido")
                print(f"  * Calidad de respuesta:        AST: {ca['calidad_arbol_pct']}% vs Base: {ca['calidad_baseline_pct']}%")
                print("-" * 75)
            elif res_arbol and res_arbol[-1].get("error"):
                print(f"  [!] Fallo en '{mod_gen['id']}': {res_arbol[-1]['error']}")
                print("      Nota: Un modelo de 17.7 GB requiere >18 GB de RAM libre. Prueba con 'qwen3-8b-q4' o 'qwen3-4b-q4'.")

        if len(resumen_cara_a_cara) > 1:
            print("\n" + "=" * 95)
            print("  TABLA COMPARATIVA CARA A CARA ENTRE MODELOS GENERATIVOS (CON Y SIN AST)")
            print("=" * 95)
            print(f"{'Modelo Generativo':<34} {'PP Base/AST(t/s)':<18} {'TG Base/AST(t/s)':<18} {'Lat Base/AST(ms)':<18} {'Speedup':<8} {'Calidad':<8}")
            print("-" * 95)
            for rc in resumen_cara_a_cara:
                pp_s = f"{rc.get('pp_baseline_tok_s', 0):.1f} / {rc.get('pp_arbol_tok_s', 0):.1f}"
                tg_s = f"{rc.get('tg_baseline_tok_s', 0):.1f} / {rc.get('tg_arbol_tok_s', 0):.1f}"
                lat_s = f"{rc['latencia_baseline_ms']:.0f} / {rc['latencia_arbol_ms']:.0f}"
                sp_s = f"{rc.get('speedup_x', 1.0)}x"
                cal_s = f"{rc['calidad_arbol_pct']:.0f}%"
                print(f"{rc['modelo_id'][:33]:<34} {pp_s:<18} {tg_s:<18} {lat_s:<18} {sp_s:<8} {cal_s:<8}")
            print("=" * 95)
    except Exception as e:
        logger.error(f"Error en comparativa de árbol de nodos: {e}", exc_info=True)
        print(f"[!] Error durante la ejecución de la prueba: {e}")
    finally:
        gestor_emb.detener_servidor()
    input("\nPresiona [Enter] para continuar...")


def opcion_afinador_y_benchmark(gestor_cache: Optional[GestorCache] = None) -> None:
    cache = gestor_cache or GestorCache()
    binario = GestorHerramientasBunker.resolver_ruta_ejecutable("llama-server")
    generador_informes = GeneradorInformesTuning(gestor_cache=cache)

    while True:
        limpiar_pantalla()
        print("=" * 70)
        print("      AFINADOR DE PUNTO DULCE Y BENCHMARKING (SIMPLIFICADO)")
        print("=" * 70)
        print("  1. Auto-Afinar Punto Dulce de un modelo (1 paso, valores óptimos)")
        print("  2. Comparativa Directa vs Árbol AST + Cara a Cara (Qwen2.5 vs Qwen3)")
        print("  3. Ver Ranking de Punto Dulce e Informes Guardados")
        print("  4. Test rápido de velocidad sobre servidor activo")
        print("  0. Volver al menú principal")
        print("-" * 70)

        sub = input("Selecciona una opción [0-4]: ").strip()
        if sub in ("2", "6"):
            ejecutar_comparativa_ast_directa(cache)

        elif sub == "1":
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

        elif sub == "3":
            with cache.sesion() as conn:
                sesiones = conn.execute("SELECT * FROM bench_sesiones ORDER BY inicio DESC LIMIT 10;").fetchall()
            if not sesiones:
                print("\nNo hay sesiones de benchmark registradas aún.")
            else:
                # Mostrar directamente la sesión más reciente sin obligar a copiar IDs
                ultima_id = sesiones[0]["id"]
                generador_informes.imprimir_tabla_consola(ultima_id)
                resumen = generador_informes.obtener_resumen_sesion(ultima_id)
                if resumen and resumen.get("configs"):
                    ok_configs = [c for c in resumen["configs"] if c["estado"] == "ok"]
                    if ok_configs:
                        mejor = ok_configs[0]
                        args = mejor["args"]
                        st_m = mejor.get("stats", {})
                        pp_m = st_m.get("pp_stats", {}).get("mediana", 0.0)
                        tg_m = st_m.get("tg_stats", {}).get("mediana", 0.0)
                        print(f"[PUNTO DULCE ÓPTIMO]: Score {mejor['score']:.2f} | Ctx Máx: {args.get('ctx_size', 4096)} tokens")
                        print(f"  Velocidad Lectura (Prefill PP): {pp_m:.1f} tok/s | Velocidad Creación (Gen TG): {tg_m:.1f} tok/s")
                        print(f"  Parámetros: ngl={args.get('n_gpu_layers', 0)}, hilos={args.get('threads', 4)}, batch={args.get('batch_size', 512)}/{args.get('ubatch_size', 512)}, kv={args.get('kv_cache_tipo', 'f16')}.")
                        print("-" * 75)
                if len(sesiones) > 1:
                    print("\nOtras sesiones disponibles:")
                    for idx_s, s in enumerate(sesiones, 1):
                        print(f"  [{idx_s}] {s['modelo_id']} | {s['estado']} | {s['inicio']} (ID: {s['id']})")
                    sel_s = input("Número de sesión a consultar o [E] exportar última a CSV/JSON (Enter = volver): ").strip().lower()
                    if sel_s == "e":
                        rcsv, rjson = generador_informes.exportar_csv_y_json(ultima_id)
                        print(f"[OK] Exportado a:\n  {rcsv}\n  {rjson}")
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


def iniciar_menu(gestor_cache: Optional[GestorCache] = None) -> None:
    cache = gestor_cache or GestorCache()
    inicializar_logging()
    while True:
        mostrar_banner()
        filas_inst = menu_actions.obtener_modelos_locales(cache)
        nombres_inst = ", ".join(m["id"] for m in filas_inst) if filas_inst else "Ninguno aún"
        print(f"Modelos en disco ({len(filas_inst)}): {nombres_inst}")
        print("-" * 65)
        print("Menú Principal Simplificado:")
        print("  1. Modelos y Descargas (Instalar / Eliminar modelos en 1 paso)")
        print("  2. Comparativa Directa vs Árbol AST y Cara a Cara (Qwen2.5 vs Qwen3)")
        print("  3. Afinador de Punto Dulce y Rankings de Velocidad (PP / TG)")
        print("  4. Servidor Local e Inferencia (Arrancar / Chat / Estado)")
        print("  5. Diagnóstico del Sistema (Hardware, Caché, Tests y Logs)")
        print("  0. Salir")
        print("-" * 65)
        
        try:
            opcion = input("Selecciona una opción [0-5]: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\nSaliendo de GuarIdA...")
            sys.exit(0)

        try:
            if opcion == "1":
                opcion_catalogo_y_bunker(cache)
            elif opcion == "2":
                ejecutar_comparativa_ast_directa(cache)
            elif opcion in ("3", "7"):
                opcion_afinador_y_benchmark(cache)
            elif opcion in ("4", "6"):
                opcion_motor_inferencia(cache)
            elif opcion == "5":
                opcion_diagnostico_unificado(cache)
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
