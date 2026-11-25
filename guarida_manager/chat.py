"""Módulo de chat interactivo por terminal con medición de métricas en tiempo real.

Permite probar modelos manualmente tras seleccionar entre parejas recomendadas según el hardware
y los datos de afinamiento y benchmark disponibles en el sistema.
"""

import hashlib
import re
import secrets
import time
from pathlib import Path
from typing import Any, Callable, Optional

from guarida_manager.cache import GestorCache
from guarida_manager.comparator import ComparadorModelosHardware
from guarida_manager.downloader.models import CatalogoModelos, DefinicionModeloCatalogo, DescargadorModelos
from guarida_manager.downloader.tools import GestorHerramientasBunker
from guarida_manager.engine import ClienteLlamaOffline, GestorLlamaServer, LlamaServerConfig
from guarida_manager.engine.server import asegurar_puerto_disponible, puerto_esta_disponible
from guarida_manager.hardware import InformacionHardware, obtener_informacion_hardware
from guarida_manager.logger import obtener_logger
from guarida_manager.proyectos import GestorProyectos
from guarida_manager import DIRECTORIO_LOGS, menu_actions

logger = obtener_logger("chat")

_RE_HECHO_EXPLICITO = re.compile(
    r"(?:\[\s*)?HECHO\s*:\s*([^|\r\n]+?)\s*\|\s*([^|\r\n]+?)\s*\|\s*([^\]\r\n]+?)\s*(?:\]|$)",
    re.IGNORECASE | re.MULTILINE,
)
_RE_HECHO_NATURAL = re.compile(
    r"(?i)\brecuerda\s+que\s+(.+?)\s+"
    r"(es|usa|utiliza|requiere|vale|est[aá]\s+en|apunta\s+a|depende\s+de)\s+"
    r"([^.\r\n;]+)",
)


def _tamano_archivo_seguro(ruta: Path) -> int:
    """Devuelve el tamaño en bytes de `ruta`, o 0 si no existe o no es accesible."""
    try:
        return ruta.stat().st_size if ruta.exists() else 0
    except OSError:
        return 0


def _leer_log_desde(ruta: Path, offset: int) -> str:
    """Lee las últimas líneas no vacías escritas en `ruta` a partir de `offset`."""
    try:
        if not ruta.exists() or ruta.stat().st_size <= offset:
            return ""
        with open(ruta, "rb") as f_log:
            f_log.seek(max(0, offset))
            contenido = f_log.read().decode("utf-8", errors="replace")
        lineas = [l.strip() for l in contenido.splitlines() if l.strip()]
        return "\n    ".join(lineas[-6:])
    except Exception:
        return ""


def _es_error_bind_puerto(detalle_log: str) -> bool:
    """Detecta si el fallo de llama-server se debe a un puerto bloqueado u ocupado."""
    low = detalle_log.lower()
    return any(
        patron in low
        for patron in (
            "couldn't bind",
            "address already in use",
            "bind http server socket",
            "error 10048",
            "error 10013",
        )
    )


def _sincronizar_puerto(cfg: Any, cli: Any, host: str, port: int) -> None:
    """Mantiene alineados puerto y base_url entre la configuración y el cliente HTTP."""
    cfg.port = port
    cli.port = port
    cli.base_url = f"http://{host}:{port}"


def _esperar_servidor_chat(srv: Any, cli: Any, intentos: int = 40, pausa_s: float = 0.5) -> bool:
    """Espera hasta que llama-server responda /health o el proceso termine."""
    for _ in range(intentos):
        if cli.esta_disponible():
            return True
        if srv.proceso and srv.proceso.poll() is not None:
            return False
        time.sleep(pausa_s)
    return False


def extraer_hechos_declarativos(texto: str) -> list[tuple[str, str, str]]:
    """Extrae tripletas (sujeto, predicado, objeto) desde marcadores explícitos o fraseo declarativo."""
    if not texto or not texto.strip():
        return []

    hechos: list[tuple[str, str, str]] = []
    vistos: set[tuple[str, str, str]] = set()

    for patron in (_RE_HECHO_EXPLICITO, _RE_HECHO_NATURAL):
        for match in patron.finditer(texto):
            sujeto = " ".join(match.group(1).split()).strip(" .,:;")
            predicado = " ".join(match.group(2).split()).strip(" .,:;")
            objeto = " ".join(match.group(3).split()).strip(" .,:;")
            if not sujeto or not predicado or not objeto:
                continue
            clave = (sujeto.lower(), predicado.lower(), objeto)
            if clave not in vistos:
                vistos.add(clave)
                hechos.append((sujeto, predicado, objeto))

    return hechos


class ClienteTensoresChat:
    """Adaptador de chat para modelos de tensores nativos (PyTorch / Safetensors)."""

    def __init__(self, ruta_modelo: Path, modelo_id: str):
        self.ruta_modelo = ruta_modelo
        self.modelo_id = modelo_id
        from guarida_manager.engine.tensors_engine import MotorTensoresLocales
        self.motor = MotorTensoresLocales(ruta_modelo=ruta_modelo)
        self.base_url = f"tensors://local/{modelo_id}"
        self.api_key = None

    def esta_disponible(self) -> bool:
        return self.motor._modelo is not None

    def cargar(self) -> bool:
        return self.motor.cargar_modelo()

    def tokenizar(self, texto: str) -> list[int]:
        if self.motor._tokenizador:
            try:
                return self.motor._tokenizador.encode(texto)
            except Exception:
                pass
        return [1] * max(1, len(texto) // 4)

    def completar_chat(
        self,
        mensajes: list[dict[str, str]],
        temperatura: float = 0.2,
        max_tokens: int = 512,
        **kwargs: Any,
    ) -> dict[str, Any]:
        prompt = self._formatear_mensajes(mensajes)
        res = self.motor.completar_texto(prompt, max_tokens=max_tokens, temperatura=temperatura)
        return {
            "choices": [{"message": {"role": "assistant", "content": res["content"]}}],
            "usage": {
                "prompt_tokens": res["prompt_tokens"],
                "completion_tokens": res["completion_tokens"],
                "total_tokens": res["prompt_tokens"] + res["completion_tokens"],
            },
            "timings": {
                "predicted_per_second": res["tok_per_second"],
            },
        }

    def _formatear_mensajes(self, mensajes: list[dict[str, str]]) -> str:
        tok = self.motor._tokenizador
        if tok and hasattr(tok, "apply_chat_template") and getattr(tok, "chat_template", None):
            try:
                return tok.apply_chat_template(mensajes, tokenize=False, add_generation_prompt=True)
            except Exception:
                pass
        partes = []
        for m in mensajes:
            rol = m.get("role", "user")
            contenido = m.get("content", "")
            if rol == "system":
                partes.append(f"System: {contenido}\n")
            elif rol == "user":
                partes.append(f"User: {contenido}\n")
            elif rol == "assistant":
                partes.append(f"Assistant: {contenido}\n")
        partes.append("Assistant: ")
        return "\n".join(partes)

    def liberar_memoria(self) -> None:
        self.motor.liberar_memoria()


def iniciar_servidor_embeddings(
    cache: GestorCache,
    motor_emb_id: Optional[str],
    print_func: Callable[..., Any] = print,
) -> tuple[Optional[GestorLlamaServer], Optional[ClienteLlamaOffline]]:
    """Levanta `llama-server --embedding` (CPU, modo cooperativo, puerto libre, api_key aleatoria).

    Devuelve (gestor, cliente) o (None, None) avisando explícitamente si no es posible.
    """
    if not motor_emb_id:
        print_func("[!] No hay motor de embeddings asignado: la búsqueda del repositorio será solo léxica.")
        return None, None

    locales = {m["id"]: m for m in menu_actions.obtener_modelos_locales(cache)}
    mod = locales.get(motor_emb_id)
    if not mod:
        print_func(f"[!] El motor de embeddings '{motor_emb_id}' no está descargado: búsqueda solo léxica.")
        return None, None

    binario = GestorHerramientasBunker.resolver_ruta_ejecutable("llama-server")
    if not binario:
        print_func("[!] No se encontró 'llama-server': búsqueda solo léxica.")
        return None, None

    from guarida_manager.tuning.ejecutor import encontrar_puerto_libre

    info_hw = obtener_informacion_hardware()
    puerto = encontrar_puerto_libre("127.0.0.1")
    clave = secrets.token_urlsafe(32)
    cfg = LlamaServerConfig(
        modelo_path=Path(mod["ruta_local"]),
        binario_path=binario,
        host="127.0.0.1",
        port=puerto,
        n_gpu_layers=0,
        ctx_size=4096,
        batch_size=2048,
        ubatch_size=2048,
        threads=max(1, (info_hw.nucleos_fisicos or 4) // 2),
        embedding=True,
        api_key=clave,
        alias=motor_emb_id,
    )
    gestor = GestorLlamaServer(gestor_cache=cache)
    cliente = ClienteLlamaOffline(host="127.0.0.1", port=puerto, api_key=clave)
    try:
        gestor.iniciar_servidor(cfg, ruta_log=DIRECTORIO_LOGS / "llama-embeddings.log")
        for _ in range(60):
            if cliente.esta_disponible():
                return gestor, cliente
            if gestor.proceso and gestor.proceso.poll() is not None:
                break
            time.sleep(0.5)
    except Exception as e_emb:
        logger.error(f"Fallo al iniciar servidor de embeddings '{motor_emb_id}': {e_emb}", exc_info=True)
    try:
        gestor.detener_servidor()
    except Exception:
        pass
    print_func(f"[!] No se pudo iniciar el servidor de embeddings '{motor_emb_id}': búsqueda solo léxica.")
    return None, None


def clasificar_tok_s_chat(tok_s: float) -> str:
    """Clasifica la fluidez para chat según las directrices CanIRun/LLMFit."""
    if tok_s >= 35.0:
        return "⚡ INSTANTÁNEO"
    if tok_s >= 20.0:
        return "🚀 ÁGIL"
    if tok_s >= 12.0:
        return "🟢 FLUIDO"
    if tok_s >= 6.0:
        return "🟠 MODERADO"
    return "🔴 LENTO"


def estimar_tok_s_modelo(
    modelo_id: str,
    ruta_local: Optional[str],
    hw: InformacionHardware,
    cache: GestorCache,
) -> tuple[float, str, bool]:
    """Estima o recupera los tokens/segundo de un modelo generativo en este hardware."""
    # 1. Ground truth en benchmarks o afinamiento previo
    bm = cache.obtener_benchmark(modelo_id, hw.hash_hardware)
    if bm and bm.get("tok_s", 0) > 0:
        t = round(float(bm["tok_s"]), 1)
        return t, clasificar_tok_s_chat(t), True

    opt = cache.obtener_configuracion_optima(modelo_id, hw.hash_hardware)
    if opt and opt.get("tok_s_medido", 0) > 0:
        t = round(float(opt["tok_s_medido"]), 1)
        return t, clasificar_tok_s_chat(t), True

    # 2. Catálogo oficial
    m_def = CatalogoModelos.obtener_modelo(modelo_id)
    if m_def:
        ev = ComparadorModelosHardware.evaluar_modelo_completo(m_def.id, m_def.tamano_gb, hw, cache)
        return ev.tok_s_estimado, ev.clasificacion_chat, False

    # 3. Estimación analítica por tamaño de fichero
    tam_gb = 4.0
    if ruta_local:
        try:
            p = Path(ruta_local)
            if p.exists() and p.is_file():
                tam_gb = round(p.stat().st_size / (1024 ** 3), 2)
        except Exception:
            pass

    m_temp = DefinicionModeloCatalogo(
        id=modelo_id,
        nombre=modelo_id,
        categoria="chat",
        tamano_gb=tam_gb,
        ram_minima_gb=tam_gb * 1.3,
        vram_recomendada_gb=tam_gb * 1.1,
        repo_hf="local/custom",
        filename=Path(ruta_local).name if ruta_local else f"{modelo_id}.gguf",
    )
    ev = ComparadorModelosHardware.evaluar_modelo_completo(m_temp.id, m_temp.tamano_gb, hw, cache)
    return ev.tok_s_estimado, ev.clasificacion_chat, False


def obtener_parejas_recomendadas(gestor_cache: GestorCache) -> list[dict[str, Any]]:
    """Recopila las parejas recomendadas garantizando que cada modelo de chat aparezca

    EXCLUSIVAMENTE UNA VEZ con su pareja AST/Embedding más eficiente, ordenadas de mayor a menor rendimiento.
    """
    hw = obtener_informacion_hardware()
    est = menu_actions.estimar_conjunto_modelos_optimo(hw)
    locales = {m["id"]: m for m in menu_actions.obtener_modelos_locales(gestor_cache)}
    parejas_calculadas = menu_actions.obtener_mejores_parejas_combinadas(gestor_cache)

    # 1. Seleccionar para cada modelo generativo únicamente su pareja más eficiente (mayor score/speedup)
    mejores_por_gen: dict[str, dict[str, Any]] = {}
    for p in parejas_calculadas:
        gen_id = p["modelo_gen_id"]
        score = p.get("score_conjunto", 0.0)
        actual = mejores_por_gen.get(gen_id)
        if actual is None or score > actual.get("score_conjunto", 0.0):
            mejores_por_gen[gen_id] = p

    # 2. Asegurar que los modelos clave recomendados para este hardware también tengan su pareja óptima
    parejas_tier = [
        (est["chat"], est["embedding"], "Pareja recomendada para Chat y Asistente interactivo"),
        (est["coder"], est["embedding"], "Pareja recomendada para Código y Asistencia técnica AST"),
    ]
    for gen_id, emb_id, rec_desc in parejas_tier:
        if gen_id not in mejores_por_gen:
            des_g = gen_id in locales
            des_e = emb_id in locales
            mejores_por_gen[gen_id] = {
                "modelo_gen_id": gen_id,
                "modelo_emb_id": emb_id,
                "score_conjunto": 88.0 if des_g and des_e else 75.0,
                "speedup_x": 1.25,
                "ahorro_tokens_pct": 25.0,
                "ngl_gen": "Auto",
                "ngl_emb": "Auto",
                "recomendacion_uso": rec_desc,
                "descargado_gen": des_g,
                "descargado_emb": des_e,
                "origen": f"Recomendación para Hardware [{est['tier'].upper()}]",
            }

    # 3. Enriquecer con métricas de rendimiento y clasificaciones predictivas
    resultado: list[dict[str, Any]] = []
    for gen_id, p in mejores_por_gen.items():
        reg_local = locales.get(gen_id, {})
        ruta_loc = reg_local.get("ruta_local")
        tok_s, clasif_rend, es_real = estimar_tok_s_modelo(gen_id, ruta_loc, hw, gestor_cache)

        if p.get("tok_s") and p["tok_s"] > 0:
            tok_s = float(p["tok_s"])
            clasif_rend = clasificar_tok_s_chat(tok_s)
            es_real = True

        p_copia = dict(p)
        es_st = any(k in gen_id.lower() for k in ("safetensors", "safetensor")) or (
            ruta_loc and Path(ruta_loc).suffix.lower() in (".safetensors", ".bin", ".pt")
        )
        p_copia["formato"] = "Safetensors" if es_st else "GGUF"
        p_copia["tok_s"] = tok_s
        p_copia["tok_s_es_real"] = es_real
        p_copia["clasificacion_rendimiento"] = clasif_rend
        p_copia["descargado_gen"] = gen_id in locales
        p_copia["descargado_emb"] = p.get("modelo_emb_id") in locales
        resultado.append(p_copia)

    # 4. Ordenar de mayor a menor rendimiento (priorizando GGUF para llama-server y score conjunto)
    resultado.sort(
        key=lambda x: (
            1 if x.get("formato") == "GGUF" else 0,
            1 if x.get("descargado_gen") else 0,
            x.get("score_conjunto", 0.0),
            x.get("tok_s", 0.0),
        ),
        reverse=True,
    )

    return resultado


def mostrar_parejas_recomendadas(
    parejas: list[dict[str, Any]],
    modelo_activo: Optional[str] = None,
    print_func: Callable[..., Any] = print,
) -> None:
    """Imprime el listado de parejas únicas más eficientes con pistas claras de rendimiento."""
    print_func("\n" + "=" * 120)
    print_func("     PAREJAS RECOMENDADAS PARA CHAT (MÁXIMA EFICIENCIA POR MODELO EN ESTE HARDWARE)")
    print_func("=" * 120)

    if parejas:
        top = parejas[0]
        tok_top = f"{top['tok_s']:.1f} t/s" if top.get("tok_s") else "Alta velocidad"
        tag_real = "medido" if top.get("tok_s_es_real") else "estimado"
        print_func(
            f"  [PISTA DE RENDIMIENTO]: La opción #1 ('{top['modelo_gen_id']}' + '{top['modelo_emb_id']}') [{top.get('formato', 'GGUF')}] "
            f"es la pareja más eficiente para tu hardware ({tok_top} {tag_real}, {top.get('clasificacion_rendimiento', '')})."
        )
        print_func("  Cada modelo conversacional aparece una sola vez con su mejor motor AST.")
        print_func("-" * 120)

    if modelo_activo:
        print_func(f"  [*] Modelo actualmente cargado en el servidor: {modelo_activo}")
        print_func("-" * 120)

    encabezado = f"{'#':<4} {'Modelo Generativo':<25} {'Motor AST/Emb':<22} {'Formato':<12} {'Estado':<10} {'Velocidad':<13} {'Rendimiento':<15} {'Score':<7} {'Recomendación'}"
    print_func(encabezado)
    print_func("-" * 120)

    for idx, p in enumerate(parejas, start=1):
        num_str = f"{idx}⭐" if idx == 1 else f"{idx}"
        estado_gen = "En disco" if p.get("descargado_gen") else "Catálogo"
        formato = p.get("formato", "GGUF")

        tag_t = f"{p['tok_s']:.1f} t/s" if p.get("tok_s") else "-"
        if not p.get("tok_s_es_real") and p.get("tok_s"):
            tag_t += "*"

        rend = p.get("clasificacion_rendimiento", "MODERADO")[:14]
        sc_txt = f"{p.get('score_conjunto', 0.0):.1f}"
        rec_corta = p.get("recomendacion_uso", "")[:28]

        fila = f"{num_str:<4} {p['modelo_gen_id'][:24]:<25} {p['modelo_emb_id'][:21]:<22} {formato:<12} {estado_gen:<10} {tag_t:<13} {rend:<15} {sc_txt:<7} {rec_corta}"
        print_func(fila)

    print_func("-" * 120)
    print_func("  (* = velocidad estimada según ancho de banda de GPU/RAM; sin asterisco = benchmark real)")
    print_func("=" * 120)


def seleccionar_pareja_chat(
    parejas_recomendadas: list[dict[str, Any]],
    gestor_cache: GestorCache,
    modelo_activo: Optional[str] = None,
    input_func: Callable[[str], str] = input,
    print_func: Callable[..., Any] = print,
) -> tuple[Optional[str], Optional[str]]:
    """Permite al usuario decidir soberanamente con qué pareja chatear, destacando la sugerencia óptima."""
    mostrar_parejas_recomendadas(parejas_recomendadas, modelo_activo=modelo_activo, print_func=print_func)
    
    top = parejas_recomendadas[0] if parejas_recomendadas else None
    if top:
        tok_top = f"{top['tok_s']:.1f} tok/s" if top.get("tok_s") else "Alta velocidad"
        tag_real = "medido en benchmark" if top.get("tok_s_es_real") else "estimado por hardware"
        precision_top = f"Score Calidad/Afinamiento: {top.get('score_conjunto', 0.0):.1f}/100"
        print_func("\n" + "=" * 80)
        print_func("  MODELO SUGERIDO AUTOMÁTICAMENTE (MEJOR RELACIÓN VELOCIDAD Y PRECISIÓN):")
        print_func(f"    * Modelo:     {top['modelo_gen_id']} (Motor AST: {top['modelo_emb_id']})")
        print_func(f"    * Velocidad:  {tok_top} ({tag_real})")
        print_func(f"    * Precisión:  {precision_top} | {top.get('clasificacion_rendimiento', '')}")
        print_func(f"    * Estado:     {'Disponible en disco' if top.get('descargado_gen') else 'En catálogo (descarga 1-clic)'}")
        print_func("=" * 80)

    print_func("\nOpciones de selección:")
    if top:
        print_func(f"  [Enter] o [1] Usar el sugerido ({top['modelo_gen_id']})")
    print_func(f"  [2-{len(parejas_recomendadas)}]    Elegir cualquiera de las otras opciones de la tabla")
    print_func("  [M]          Selección manual libre (elegir cualquier modelo generativo y motor AST)")
    if modelo_activo:
        print_func(f"  [A]          Mantener modelo actualmente cargado en el servidor ('{modelo_activo}')")

    try:
        sel = input_func("\nSelecciona tu opción (Enter = sugerido #1): ").strip()
    except (KeyboardInterrupt, EOFError):
        return None, None

    if sel.lower() in ("m", "manual"):
        return _seleccionar_pareja_manual(gestor_cache, input_func=input_func, print_func=print_func)

    if modelo_activo and sel.lower() in ("a", "activo"):
        emb_def = parejas_recomendadas[0]["modelo_emb_id"] if parejas_recomendadas else "bge-m3-q4"
        return modelo_activo, emb_def

    if sel.isdigit():
        num = int(sel)
        if 1 <= num <= len(parejas_recomendadas):
            p = parejas_recomendadas[num - 1]
            return p["modelo_gen_id"], p["modelo_emb_id"]
        print_func("[!] Opción fuera de rango. Seleccionando la pareja recomendada #1.")
        if parejas_recomendadas:
            return parejas_recomendadas[0]["modelo_gen_id"], parejas_recomendadas[0]["modelo_emb_id"]

    if not sel:
        if modelo_activo:
            emb_def = parejas_recomendadas[0]["modelo_emb_id"] if parejas_recomendadas else "bge-m3-q4"
            return modelo_activo, emb_def
        if parejas_recomendadas:
            return parejas_recomendadas[0]["modelo_gen_id"], parejas_recomendadas[0]["modelo_emb_id"]

    # Si escribió un ID directamente
    emb_def = parejas_recomendadas[0]["modelo_emb_id"] if parejas_recomendadas else "bge-m3-q4"
    return sel, emb_def


def _seleccionar_pareja_manual(
    gestor_cache: GestorCache,
    input_func: Callable[[str], str] = input,
    print_func: Callable[..., Any] = print,
) -> tuple[Optional[str], Optional[str]]:
    """Permite al usuario elegir libremente el modelo generativo y el de embeddings/AST."""
    locales = {m["id"]: m for m in menu_actions.obtener_modelos_locales(gestor_cache)}
    todos_modelos = CatalogoModelos.MODELOS

    gens = [m_id for m_id, m in todos_modelos.items() if m.categoria in ("chat", "coder", "uncensored", "reasoning")]
    embs = [m_id for m_id, m in todos_modelos.items() if m.categoria == "embedding"]

    print_func("\n--- SELECCIÓN MANUAL: 1. MODELO GENERATIVO (CHAT / CÓDIGO) ---")
    for idx, g_id in enumerate(gens, start=1):
        est = "[En disco]" if g_id in locales else "[Catálogo]"
        m_def = todos_modelos.get(g_id)
        desc = m_def.descripcion if m_def else ""
        print_func(f"  [{idx}] {g_id:<28} {est:<10} {desc[:40]}")

    try:
        sel_g = input_func("Elige el número o ID del modelo generativo (Enter = 1): ").strip()
    except (KeyboardInterrupt, EOFError):
        return None, None

    if sel_g.isdigit() and 1 <= int(sel_g) <= len(gens):
        gen_elegido = gens[int(sel_g) - 1]
    elif sel_g and sel_g in todos_modelos:
        gen_elegido = sel_g
    elif not sel_g and gens:
        gen_elegido = gens[0]
    else:
        gen_elegido = sel_g or (gens[0] if gens else "qwen2.5-3b-chat-q4")

    print_func("\n--- SELECCIÓN MANUAL: 2. MOTOR AST / EMBEDDING AUXILIAR ---")
    for idx, e_id in enumerate(embs, start=1):
        est = "[En disco]" if e_id in locales else "[Catálogo]"
        m_def = todos_modelos.get(e_id)
        desc = m_def.descripcion if m_def else ""
        print_func(f"  [{idx}] {e_id:<28} {est:<10} {desc[:40]}")

    try:
        sel_e = input_func("Elige el número o ID del motor AST/Embedding (Enter = 1): ").strip()
    except (KeyboardInterrupt, EOFError):
        return None, None

    if sel_e.isdigit() and 1 <= int(sel_e) <= len(embs):
        emb_elegido = embs[int(sel_e) - 1]
    elif sel_e and sel_e in todos_modelos:
        emb_elegido = sel_e
    elif not sel_e and embs:
        emb_elegido = embs[0]
    else:
        emb_elegido = sel_e or (embs[0] if embs else "bge-m3-q4")

    print_func(f"\n[OK] Pareja personalizada elegida por el usuario: '{gen_elegido}' + '{emb_elegido}'")
    return gen_elegido, emb_elegido


def medir_tokens_mensaje(cliente: ClienteLlamaOffline, texto: str) -> int:
    """Calcula con exactitud los tokens del mensaje mediante el endpoint /tokenize o aproximación."""
    try:
        tokens = cliente.tokenizar(texto)
        if tokens:
            return len(tokens)
    except Exception as e:
        logger.debug(f"Fallo al tokenizar mediante endpoint: {e}")
    # Aproximación conservadora si el endpoint no responde
    return max(1, len(texto) // 4)


def calcular_metricas_interaccion(
    tokens_mensaje: int,
    respuesta_api: dict[str, Any],
    tiempo_total_s: float,
    cliente: Optional[ClienteLlamaOffline] = None,
    contenido_salida: str = "",
    metricas_rag: Optional[dict[str, Any]] = None,
    metricas_hw: Optional[Any] = None,
) -> dict[str, Any]:
    """Extrae y calcula las métricas de velocidad y uso de tokens de un turno conversacional."""
    usage = respuesta_api.get("usage", {})
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")

    if prompt_tokens is None or prompt_tokens <= 0:
        prompt_tokens = tokens_mensaje
    if completion_tokens is None or completion_tokens <= 0:
        if cliente and contenido_salida:
            completion_tokens = medir_tokens_mensaje(cliente, contenido_salida)
        else:
            completion_tokens = max(1, len(contenido_salida) // 4) if contenido_salida else 0

    total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)
    latencia_s = max(0.001, tiempo_total_s)
    vel_generacion_tok_s = completion_tokens / latencia_s

    # Datos de timings reportados directamente por llama.cpp si están presentes
    timings = respuesta_api.get("timings", {})
    vel_prompt_tok_s = timings.get("prompt_per_second")
    vel_pred_timings = timings.get("predicted_per_second")

    hw = metricas_hw
    if hw is None:
        try:
            from guarida_manager.telemetry import MonitorTelemetriaHardware
            hw = MonitorTelemetriaHardware.capturar_metricas()
        except Exception:
            hw = None

    return {
        "tokens_mensaje": tokens_mensaje,
        "tokens_enviados_realmente": prompt_tokens,
        "tokens_generados": completion_tokens,
        "tokens_totales": total_tokens,
        "tiempo_total_s": latencia_s,
        "latencia_ms": latencia_s * 1000.0,
        "velocidad_generacion_tok_s": vel_pred_timings or vel_generacion_tok_s,
        "velocidad_prompt_tok_s": vel_prompt_tok_s,
        "prompt_ms": timings.get("prompt_ms"),
        "predicted_ms": timings.get("predicted_ms"),
        "rag": metricas_rag,
        "hardware": hw,
    }


def mostrar_metricas_turno(
    metricas: dict[str, Any],
    print_func: Callable[..., Any] = print,
) -> None:
    """Muestra el panel de métricas formateado para el turno actual."""
    print_func("\n" + "-" * 75)
    print_func("  [MÉTRICAS DEL MENSAJE E INFERENCIA]")
    print_func(f"  * Tokens del mensaje introducido:       {metricas['tokens_mensaje']} tokens")
    print_func(f"  * Tokens realmente enviados al modelo:  {metricas['tokens_enviados_realmente']} tokens (prompt + historial)")
    print_func(f"  * Tokens generados en la respuesta:     {metricas['tokens_generados']} tokens")
    print_func(f"  * Tokens totales del intercambio:       {metricas['tokens_totales']} tokens")
    print_func(f"  * Tiempo de respuesta / latencia:       {metricas['tiempo_total_s']:.3f} s ({metricas['latencia_ms']:.1f} ms)")
    print_func(f"  * Velocidad de generación (TG):         {metricas['velocidad_generacion_tok_s']:.2f} tok/s")
    if metricas.get("velocidad_prompt_tok_s"):
        print_func(f"  * Velocidad procesamiento prompt (PP):  {metricas['velocidad_prompt_tok_s']:.2f} tok/s")

    rag = metricas.get("rag")
    if rag:
        print_func("\n  [TRABAJO CON FICHEROS / RAG LOCAL]")
        t_busq = rag.get("tiempo_busqueda_ms", 0.0)
        n_eval = rag.get("fragmentos_evaluados", 0)
        eval_str = f" ({n_eval} fragmentos evaluados)" if n_eval else ""
        print_func(f"  * Búsqueda de referencias:              {t_busq:.1f} ms{eval_str}")

        n_cit = rag.get("fragmentos_citados", 0)
        top_sc = rag.get("top_score")
        sc_str = f" (Top-Score: {top_sc:.2f})" if top_sc is not None else ""
        print_func(f"  * Citas / Fragmentos aplicados:         {n_cit} fragmentos{sc_str}")

        t_ctx = rag.get("tiempo_contexto_ms", 0.0)
        print_func(f"  * Tiempo aplicación de contexto:        {t_ctx:.1f} ms")

        tok_ctx = rag.get("tokens_contexto", 0)
        chars_ctx = rag.get("chars_contexto", 0)
        print_func(f"  * Tokens de contexto inyectados:        {tok_ctx} tokens (~{chars_ctx} caracteres)")

        ficheros = rag.get("ficheros_consultados", [])
        if ficheros:
            fich_str = ", ".join(ficheros[:3]) + (f" (+{len(ficheros)-3} más)" if len(ficheros) > 3 else "")
            print_func(f"  * Ficheros consultados:                 {fich_str}")

    hw = metricas.get("hardware")
    if hw:
        print_func("\n  [CONSUMO DE HARDWARE EN TIEMPO REAL]")
        cores_str = f" ({hw.nucleos_cpu})" if getattr(hw, "nucleos_cpu", "") else ""
        print_func(f"  * CPU:                                  {hw.cpu_pct:.1f} %{cores_str}")
        print_func(f"  * RAM:                                  {hw.ram_usada_gb:.1f} / {hw.ram_total_gb:.1f} GB ({hw.ram_pct:.1f} %)")
        gpu_nom = getattr(hw, "gpu_nombre", "") or "GPU"
        gpu_tip = getattr(hw, "gpu_tipo", "")
        tip_str = f" [{gpu_tip}]" if gpu_tip else ""
        print_func(f"  * VRAM / GTT:                           {hw.vram_usada_gb:.1f} / {hw.vram_total_gb:.1f} GB ({gpu_nom})")
        print_func(f"  * GPU:                                  {gpu_nom}{tip_str}")
        du_lib = getattr(hw, "disco_libre_gb", 0.0)
        print_func(f"  * Disco:                                {hw.disco_usado_gb:.1f} / {hw.disco_total_gb:.1f} GB ({hw.disco_pct:.1f} %) [{du_lib:.1f} GB libres]")
        if getattr(hw, "temperatura_c", None) is not None:
            alerta = " [! ALERTA TÉRMICA !]" if hw.es_critica else ""
            print_func(f"  * Temperatura Silicio:                  {hw.temperatura_c:.1f} °C{alerta}")

    print_func("-" * 75)


def ejecutar_chat_terminal(
    gestor_cache: Optional[GestorCache] = None,
    gestor_server: Optional[GestorLlamaServer] = None,
    cliente: Optional[ClienteLlamaOffline] = None,
    modelo_seleccionado: Optional[str] = None,
    proyecto_id: Optional[str] = None,
    sesion_id: Optional[str] = None,
    input_func: Callable[[str], str] = input,
    print_func: Callable[..., Any] = print,
) -> None:
    """Inicia el chat interactivo por terminal con soporte para parejas recomendadas, métricas y comando /quit."""
    cache = gestor_cache or GestorCache()
    srv = gestor_server or GestorLlamaServer(gestor_cache=cache)
    host = getattr(srv, "host", None) or (srv.obtener_estado().get("host") if hasattr(srv, "obtener_estado") else None) or "127.0.0.1"
    port = getattr(srv, "port", None) or (srv.obtener_estado().get("port") if hasattr(srv, "obtener_estado") else None) or 8083
    cli = cliente or ClienteLlamaOffline(host=host, port=port, timeout=300.0)

    # 1. Obtener y ofrecer parejas recomendadas con los datos disponibles, permitiendo al usuario decidir
    parejas = obtener_parejas_recomendadas(cache)
    estado_srv = srv.obtener_estado()
    modelo_activo = estado_srv.get("modelo") if estado_srv.get("activo") else None

    if modelo_seleccionado:
        modelo_elegido_id = modelo_seleccionado
        motor_emb_id = parejas[0]["modelo_emb_id"] if parejas else "bge-m3-q4"
    else:
        modelo_elegido_id, motor_emb_id = seleccionar_pareja_chat(
            parejas,
            gestor_cache=cache,
            modelo_activo=modelo_activo,
            input_func=input_func,
            print_func=print_func,
        )

    if not modelo_elegido_id:
        print_func("[!] No se seleccionó ningún modelo para el chat.")
        return

    # 2. Asegurar que el servidor está levantado con el modelo seleccionado
    servidor_arrancado_por_chat = False
    necesita_arrancar = False

    if not srv.esta_activo() or not cli.esta_disponible():
        necesita_arrancar = True
    elif modelo_activo and modelo_activo != modelo_elegido_id:
        print_func(f"\nEl servidor tiene '{modelo_activo}', pero se eligió '{modelo_elegido_id}'.")
        necesita_arrancar = True

    if necesita_arrancar:
        locales = {m["id"]: m for m in menu_actions.obtener_modelos_locales(cache)}
        if modelo_elegido_id not in locales:
            print_func(f"\n[!] El modelo '{modelo_elegido_id}' no está descargado en disco.")
            print_func("¿Deseas descargarlo ahora automáticamente del catálogo? [S/n]: ")
            try:
                resp_desc = input_func("").strip().lower()
            except (KeyboardInterrupt, EOFError):
                return
            if resp_desc not in ("", "s", "si", "y", "yes"):
                print_func("[!] Inferencia abortada: modelo no presente localmente.")
                return
            print_func(f"Descargando '{modelo_elegido_id}'...")
            try:
                DescargadorModelos(gestor_cache=cache).descargar_modelo(modelo_elegido_id, permitir_inseguro=True)
                locales = {m["id"]: m for m in menu_actions.obtener_modelos_locales(cache)}
            except Exception as err_d:
                print_func(f"[!] Error al descargar modelo: {err_d}")
                return

        mod_reg = locales.get(modelo_elegido_id)
        if not mod_reg:
            print_func(f"[!] Modelo '{modelo_elegido_id}' no disponible.")
            return

        ruta_m = Path(mod_reg["ruta_local"])
        es_tensores = (
            ruta_m.suffix.lower() in (".safetensors", ".bin", ".pt")
            or ruta_m.is_dir()
            or "safetensors" in modelo_elegido_id.lower()
        )

        if es_tensores:
            print_func(f"\nIniciando motor de tensores nativo (PyTorch/Transformers) para '{modelo_elegido_id}'...")
            try:
                cli_tensores = ClienteTensoresChat(ruta_m, modelo_elegido_id)
                cli_tensores.cargar()
                cli = cli_tensores
            except Exception as e_ten:
                logger.error(
                    f"Fallo al abrir chat con modelo de tensores '{modelo_elegido_id}' en '{ruta_m}': {e_ten}",
                    exc_info=True,
                )
                print_func(f"\n[!] Error al abrir el modelo de tensores '{modelo_elegido_id}': {e_ten}")
                print_func("    Detalle técnico: Los modelos en formato Safetensors (.safetensors) son pesos nativos de PyTorch")
                print_func("    y no son compatibles con el motor llama-server (que requiere archivos .gguf).")
                print_func("    Para ejecutarlos con Transformers se requiere config.json y tokenizer.json en su carpeta.")
                print_func("    Se recomienda seleccionar un modelo en formato GGUF para la experiencia completa en GuarIdA.")
                return
        else:
            binario = GestorHerramientasBunker.resolver_ruta_ejecutable("llama-server")
            if not binario:
                print_func("[!] No se encontró el binario 'llama-server'. Descárgalo desde el menú de herramientas.")
                return

            print_func(f"\nIniciando llama-server con el modelo '{modelo_elegido_id}'...")
            if srv.esta_activo():
                srv.detener_servidor()
                time.sleep(0.5)

            menu_actions.afinar_modelo_automatico(cache, modelo_elegido_id, ruta_m)
            clave_api = secrets.token_urlsafe(32)
            cfg = LlamaServerConfig.desde_afinamiento(
                modelo_path=ruta_m,
                modelo_id=modelo_elegido_id,
                binario_path=binario,
                gestor_cache=cache,
                api_key=clave_api,
            )
            host_cfg = cfg.host if isinstance(getattr(cfg, "host", None), str) else "127.0.0.1"
            port_cfg = (
                cfg.port
                if isinstance(getattr(cfg, "port", None), int) and not isinstance(cfg.port, bool)
                else 8083
            )
            if not puerto_esta_disponible(host_cfg, port_cfg):
                srv.terminar_procesos_huerfanos("llama-server")
                time.sleep(0.3)
                port_cfg = asegurar_puerto_disponible(host_cfg, port_cfg)
            _sincronizar_puerto(cfg, cli, host_cfg, port_cfg)

            ruta_log_srv = DIRECTORIO_LOGS / "llama-server.log"
            cli.api_key = clave_api
            offset_log = _tamano_archivo_seguro(ruta_log_srv)
            srv.iniciar_servidor(cfg, ruta_log=ruta_log_srv)
            servidor_arrancado_por_chat = True

            arranco_ok = _esperar_servidor_chat(srv, cli)

            if not arranco_ok:
                detalle_intento = _leer_log_desde(ruta_log_srv, offset_log)
                if _es_error_bind_puerto(detalle_intento):
                    print_func(
                        f"[!] Puerto {port_cfg} ocupado o reservado en el sistema. Reasignando a un puerto libre..."
                    )
                    logger.warning(
                        f"Fallo de bind en puerto {port_cfg} para '{modelo_elegido_id}'. Reasignando puerto..."
                    )
                    srv.detener_servidor()
                    time.sleep(0.3)
                    port_cfg = asegurar_puerto_disponible(
                        host_cfg, port_cfg + 1, excluir={port_cfg}
                    )
                    _sincronizar_puerto(cfg, cli, host_cfg, port_cfg)
                    offset_log = _tamano_archivo_seguro(ruta_log_srv)
                    srv.iniciar_servidor(cfg, ruta_log=ruta_log_srv)
                    arranco_ok = _esperar_servidor_chat(srv, cli)

            # Si falló y tenía capas GPU activas, reintentar automáticamente en modo CPU seguro
            if (
                not arranco_ok
                and isinstance(getattr(cfg, "n_gpu_layers", None), int)
                and not isinstance(cfg.n_gpu_layers, bool)
                and cfg.n_gpu_layers > 0
            ):
                print_func("[!] Inestabilidad o falta de VRAM en GPU. Reintentando en modo CPU seguro (-ngl 0 -nkvo)...")
                logger.warning(
                    f"Fallo al arrancar '{modelo_elegido_id}' con {cfg.n_gpu_layers} capas GPU. "
                    "Reintentando en modo CPU puro (-ngl 0 -nkvo)..."
                )
                srv.detener_servidor()
                time.sleep(0.5)
                port_cfg = asegurar_puerto_disponible(host_cfg, port_cfg)
                _sincronizar_puerto(cfg, cli, host_cfg, port_cfg)
                cfg.n_gpu_layers = 0
                cfg.ctx_size = min(cfg.ctx_size, 2048)
                cfg.batch_size = 256
                cfg.ubatch_size = 128
                cfg.kv_cache_type = "q8_0"
                if "-nkvo" not in cfg.extra_args:
                    cfg.extra_args.append("-nkvo")
                offset_log = _tamano_archivo_seguro(ruta_log_srv)
                srv.iniciar_servidor(cfg, ruta_log=ruta_log_srv)
                arranco_ok = _esperar_servidor_chat(srv, cli)

            if not arranco_ok:
                detalle_err = _leer_log_desde(ruta_log_srv, offset_log) or _leer_log_desde(ruta_log_srv, 0)
                code = srv.proceso.poll() if srv.proceso else "Timeout"
                logger.error(
                    f"llama-server no pudo inicializar '{modelo_elegido_id}' (código {code}). Detalle:\n{detalle_err}"
                )
                print_func(f"\n[!] No se pudo iniciar el servidor para '{modelo_elegido_id}' (código {code}).")
                if detalle_err:
                    print_func(f"    Último registro del motor:\n    {detalle_err}")
                print_func("    Para modelos grandes (ej. 14B), verifica disponer de suficiente memoria RAM libre.")
                srv.detener_servidor()
                return

    # 3. Interfaz de Chat con Soporte de Proyecto/Repositorio y Sesiones Persistentes
    gestor_proy = GestorProyectos(gestor_cache=cache)
    proy_activo = gestor_proy.obtener_proyecto(proyecto_id) if proyecto_id else None

    # Si hay sesión previa solicitada, cargar su historial
    sesion_activa = None
    if sesion_id:
        sesion_activa = gestor_proy.obtener_sesion(sesion_id)

    if not sesion_activa:
        titulo_sesion = f"Chat con {modelo_elegido_id}"
        if proy_activo:
            titulo_sesion += f" [{proy_activo['nombre']}]"
        sesion_reg = gestor_proy.crear_sesion(
            modelo_id=modelo_elegido_id,
            titulo=titulo_sesion,
            proyecto_id=proyecto_id,
        )
        sesion_id_activa = sesion_reg.id
    else:
        sesion_id_activa = sesion_id

    print_func("\n" + "=" * 80)
    print_func("                       CHAT POR TERMINAL - GUARIDA")
    print_func("=" * 80)
    print_func("  Pareja activa elegida por el usuario:")
    print_func(f"    * Modelo Generativo (Chat):   {modelo_elegido_id}")
    print_func(f"    * Motor AST / Embedding:      {motor_emb_id or 'No asignado'}")
    if proy_activo:
        print_func(f"    * Proyecto / Repositorio:     {proy_activo['nombre']} ({proy_activo['ruta_directorio']})")
    print_func(f"    * ID de Sesión Persistente:   {sesion_id_activa}")
    print_func(f"  Servidor HTTP Local:            {cli.base_url}")
    print_func("  " + "-" * 76)
    print_func("  [AVISO]: Para salir del chat escribe el comando '/quit'. Usa '/ficheros' para ver los archivos.")
    print_func("           Memoria y privacidad: '/remember sujeto | predicado | objeto' | '/recall [all]' | '/rgpd [on|off|status]'")
    print_func("=" * 80)

    prompt_sistema = (
        "Eres un asistente de inteligencia artificial preciso y técnico que corre 100% en local "
        "dentro del entorno bunkerizado GuarIdA. Responde en perfecto español de forma concisa y útil."
    )
    historial: list[dict[str, str]] = [{"role": "system", "content": prompt_sistema}]

    # Si hay mensajes previos en la sesión, cargarlos
    if sesion_activa:
        msgs_previos = gestor_proy.obtener_historial_sesion(sesion_id_activa)
        for m in msgs_previos:
            historial.append({"role": m["rol"], "content": m["contenido"]})

    # Contadores de sesión
    total_turnos = 0
    total_tokens_usuario = 0
    total_tokens_enviados = 0
    total_tokens_generados = 0
    tiempo_total_inferencia = 0.0

    # Indexación incremental del proyecto (embeddings reutilizados desde SQLite)
    gestor_emb: Optional[GestorLlamaServer] = None
    fn_emb: Optional[Callable[[str], list[float]]] = None
    if proy_activo:
        gestor_emb, cli_emb = iniciar_servidor_embeddings(cache, motor_emb_id, print_func)
        if cli_emb is not None:
            fn_emb = cli_emb.calcular_embedding
        try:
            print_func(f"\nIndexando proyecto '{proy_activo['nombre']}'...")

            def callback_progreso_chat(mensaje: str, pct: float) -> None:
                print_func(f"  [{pct:5.1f}%] {mensaje}")

            res_idx = gestor_proy.escanear_e_indexar_proyecto(
                proy_activo["id"],
                funcion_embedding=fn_emb,
                modelo_emb_id=motor_emb_id or "",
                callback_progreso=callback_progreso_chat,
            )
            if res_idx.get("snapshot_reutilizado"):
                print_func("  [Caché Snapshot] Repositorio sin cambios: carga instantánea desde disco completada.")
            print_func(
                f"  Archivos: {res_idx.get('archivos_procesados', res_idx.get('total_archivos', 0))} ({res_idx['archivos_sin_cambios']} sin cambios) | "
                f"Nodos AST: {res_idx['nodos_ast']} | Fragmentos: {res_idx['chunks_texto']} | "
                f"Embeddings nuevos/reutilizados: {res_idx.get('embeddings_calculados', 0)}/"
                f"{res_idx.get('embeddings_reutilizados', 0)} | "
                f"Omitidos por seguridad: {res_idx['omitidos_seguridad']}"
            )
            if res_idx.get("errores_embedding"):
                print_func(
                    f"  [!] {res_idx['errores_embedding']} elementos sin vector: se usará ranking léxico para ellos."
                )
            docs_idx = cache.listar_documentos_proyecto(proy_activo["id"])
            if docs_idx:
                prompt_sistema += (
                    f"\n\n[PROYECTO ACTIVO]: '{proy_activo['nombre']}' ({len(docs_idx)} archivos indexados).\n"
                    "DIRECTIVAS ESTRICTAS DE RESPUESTA Y FIDELIDAD DOCUMENTAL:\n"
                    "1. Responde ÚNICAMENTE basándote en la información explícita de los fragmentos en [Contexto del Repositorio/Documentación].\n"
                    "2. Si la información no aparece en los fragmentos citados, responde con total sinceridad: "
                    "'No consta en los fragmentos disponibles del documento consultado'.\n"
                    "3. NUNCA inventes requisitos, normativas, excepciones ni nombres de documentos o archivos que no se indiquen explícitamente en el contexto.\n"
                    "4. Cita con precisión las páginas, artículos o secciones que sustentan tu respuesta.\n"
                    "5. Para listar los archivos indexados del proyecto, indícale al usuario que use el comando '/ficheros'."
                )
                historial[0]["content"] = prompt_sistema
        except Exception as e_idx:
            logger.error(f"Fallo al indexar proyecto: {e_idx}", exc_info=True)
            print_func(f"[!] No se pudo indexar el proyecto: {e_idx}")

    try:
        while True:
            try:
                msg = input_func("\nUsuario > ").strip()
            except (KeyboardInterrupt, EOFError):
                print_func("\n\nSaliendo del chat por terminal...")
                break

            if not msg:
                continue

            # Verificación del comando de salida /quit anunciado
            if msg.lower() in ("/quit", "quit"):
                print_func("\n[OK] Comando '/quit' recibido. Saliendo del chat...")
                break

            # Comando interactivo para listar ficheros del proyecto
            if msg.lower() in ("/ficheros", "/archivos", "/files"):
                if proy_activo:
                    docs_cmd = cache.listar_documentos_proyecto(proy_activo["id"])
                    if docs_cmd:
                        print_func(f"\n[Ficheros indexados en el proyecto '{proy_activo['nombre']}'] ({len(docs_cmd)} archivos):")
                        for d in docs_cmd:
                            print_func(f"  * {d['ruta_relativa']:<50} [{d['tipo_documento']}] ({d['nodos_ast_count']} fragmentos)")
                    else:
                        print_func(f"\n[!] No hay archivos indexados en el proyecto '{proy_activo['nombre']}'.")
                else:
                    print_func("\n[!] No hay ningún proyecto activo asociado a esta sesión de chat.")
                continue

            msg_lower = msg.lower()
            if msg_lower.startswith("/remember") or msg_lower.startswith("/recordar"):
                cuerpo = msg.split(None, 1)[1].strip() if len(msg.split(None, 1)) > 1 else ""
                partes = [p.strip() for p in cuerpo.split("|")]
                if len(partes) == 3 and all(partes):
                    try:
                        hecho_id = gestor_proy.registrar_hecho(
                            partes[0],
                            partes[1],
                            partes[2],
                            proyecto_id=proyecto_id,
                            sesion_id=sesion_id_activa,
                            origen_tipo="comando",
                        )
                        print_func(
                            f"\n[OK] Hecho registrado en memoria inmutable (#{hecho_id}): "
                            f"{partes[0]} | {partes[1]} | {partes[2]}"
                        )
                    except Exception as e_mem:
                        print_func(f"\n[!] Error al registrar hecho en memoria: {e_mem}")
                else:
                    print_func("\n[!] Uso: /remember <sujeto> | <predicado> | <objeto>")
                continue

            if (
                msg_lower == "/recall"
                or msg_lower.startswith("/recall ")
                or msg_lower == "/memoria"
                or msg_lower.startswith("/memoria ")
            ):
                tokens_cmd = msg_lower.split()
                incluir_todo = len(tokens_cmd) > 1 and tokens_cmd[1] in (
                    "all",
                    "todo",
                    "historico",
                    "histórico",
                )
                hechos = (
                    gestor_proy.obtener_auditoria_hechos(
                        proyecto_id=proyecto_id, sesion_id=sesion_id_activa
                    )
                    if incluir_todo
                    else gestor_proy.obtener_hechos_activos(
                        proyecto_id=proyecto_id, sesion_id=sesion_id_activa
                    )
                )
                if not hechos:
                    print_func("\n[!] No hay hechos registrados en la memoria de esta sesión/proyecto.")
                else:
                    titulo_mem = (
                        "AUDITORÍA COMPLETA DE MEMORIA"
                        if incluir_todo
                        else "MEMORIA DECLARATIVA ACTIVA"
                    )
                    print_func(f"\n[{titulo_mem}] ({len(hechos)} hechos):")
                    for h in hechos:
                        estado_h = h.get("estado", "activo")
                        if estado_h == "superseded":
                            etiqueta = f"[SUPERSEDED -> #{h.get('sustituido_por_id')}]"
                        else:
                            etiqueta = "[ACTIVO]"
                        sha_corta = str(h.get("sha_origen", ""))[:8]
                        print_func(
                            f"  #{h['id']} {etiqueta:<22} {h['sujeto']} | {h['predicado']} | {h['objeto']} (sha:{sha_corta})"
                        )
                continue

            if msg_lower == "/rgpd" or msg_lower.startswith("/rgpd "):
                arg_rgpd = msg_lower.split(None, 1)[1].strip() if len(msg_lower.split(None, 1)) > 1 else "status"
                if arg_rgpd in ("on", "estricto", "rgpd_estricto", "1", "true"):
                    gestor_proy.configurar_modo_privacidad("rgpd_estricto")
                    print_func("\n[OK] Modo de privacidad: 'rgpd_estricto' (anonimización irreversible + auditoría HMAC).")
                elif arg_rgpd in ("off", "estandar", "estándar", "0", "false"):
                    gestor_proy.configurar_modo_privacidad("estandar")
                    print_func("\n[OK] Modo de privacidad: 'estandar' (bloques <private> y secretos explícitos).")
                else:
                    n_ev = len(gestor_proy.sanitizador.historial_auditoria)
                    print_func(
                        f"\n[Privacidad] Modo activo: '{gestor_proy.sanitizador.modo}' | "
                        f"Eventos HMAC registrados en sesión: {n_ev}"
                    )
                continue

            if gestor_proy.sanitizador.necesita_sanitizacion(msg):
                res_san_msg = gestor_proy.sanitizador.sanitizar_texto(
                    msg, origen=f"chat:{sesion_id_activa}"
                )
                if res_san_msg.total_redacciones > 0:
                    msg = res_san_msg.texto_sanitizado
                    print_func(
                        f"\n[Privacidad ({res_san_msg.modo})]: "
                        f"{res_san_msg.total_redacciones} dato(s) redactado(s) con log HMAC."
                    )

            # Búsqueda semántica híbrida si hay proyecto activo (RAG Local)
            fuentes_turno: list[dict[str, Any]] = []
            prompt_usuario_final = msg
            datos_rag_turno: Optional[dict[str, Any]] = None

            if proy_activo:
                try:
                    consulta_rag = msg
                    # Expansión conversacional: si es repregunta corta, incorporar términos del turno anterior
                    if len(historial) >= 3 and len(msg.split()) < 15:
                        previos_usr = [m["content"] for m in historial if m["role"] == "user"]
                        if previos_usr:
                            consulta_rag = f"{previos_usr[-1]} {msg}"

                    t_busq_0 = time.perf_counter()
                    ctx_doc, fuentes_turno = gestor_proy.buscar_contexto_hibrido(
                        proyecto_id=proy_activo["id"],
                        consulta=consulta_rag,
                        top_k=5,
                        funcion_embedding=fn_emb,
                    )
                    t_busq_1 = time.perf_counter()

                    t_ctx_0 = time.perf_counter()
                    tokens_ctx = 0
                    if ctx_doc:
                        prompt_usuario_final = (
                            f"{msg}\n\n[Contexto del Repositorio/Documentación]:\n{ctx_doc}"
                        )
                        tokens_ctx = medir_tokens_mensaje(cli, ctx_doc)
                    t_ctx_1 = time.perf_counter()

                    n_fragmentos_totales = len(gestor_proy._chunks_texto.get(proy_activo["id"], []))
                    ficheros_consultados = list(dict.fromkeys(f.get("archivo", "") for f in fuentes_turno if f.get("archivo")))
                    top_score = fuentes_turno[0].get("relevancia") if fuentes_turno else None

                    datos_rag_turno = {
                        "tiempo_busqueda_ms": (t_busq_1 - t_busq_0) * 1000.0,
                        "fragmentos_evaluados": n_fragmentos_totales,
                        "fragmentos_citados": len(fuentes_turno),
                        "top_score": top_score,
                        "tiempo_contexto_ms": (t_ctx_1 - t_ctx_0) * 1000.0,
                        "tokens_contexto": tokens_ctx,
                        "chars_contexto": len(ctx_doc) if ctx_doc else 0,
                        "ficheros_consultados": ficheros_consultados,
                    }
                except Exception as e_rag:
                    logger.warning(f"Fallo al recuperar contexto RAG: {e_rag}", exc_info=True)
                    print_func(f"[!] No se pudo recuperar contexto del repositorio: {e_rag}")

            # Captura e inyección de memoria declarativa inmutable (hechos activos)
            try:
                hechos_detectados = extraer_hechos_declarativos(msg)
                if hechos_detectados:
                    sha_msg = hashlib.sha256(msg.encode("utf-8")).hexdigest()
                    for subj, pred, obj in hechos_detectados:
                        gestor_proy.registrar_hecho(
                            subj,
                            pred,
                            obj,
                            proyecto_id=proyecto_id,
                            sesion_id=sesion_id_activa,
                            origen_tipo="chat",
                            sha_origen=sha_msg,
                        )
                ctx_memoria = gestor_proy.formatear_contexto_memoria_canonica(
                    proyecto_id=proyecto_id, sesion_id=sesion_id_activa
                )
                if ctx_memoria:
                    prompt_usuario_final = f"{prompt_usuario_final}\n\n{ctx_memoria}"
            except Exception as e_mem_ctx:
                logger.debug(f"Fallo al procesar memoria declarativa en turno: {e_mem_ctx}")

            # Medición de tokens del mensaje escrito por el usuario (sin el contexto recuperado)
            tokens_msg = medir_tokens_mensaje(cli, msg)
            # El contexto RAG solo viaja en este turno: el historial conserva el mensaje limpio
            # para que las citas anteriores no inflen la ventana de contexto en turnos sucesivos.
            mensajes_envio = historial + [{"role": "user", "content": prompt_usuario_final}]

            t_inicio = time.perf_counter()
            try:
                print_func("\n[Generando respuesta...]")
                resp = cli.completar_chat(
                    mensajes=mensajes_envio,
                    temperatura=0.2,
                    max_tokens=1024,
                    timeout=300.0,
                )
                t_fin = time.perf_counter()
                tiempo_transcurrido = t_fin - t_inicio

                elecciones = resp.get("choices", [])
                contenido_asistente = elecciones[0].get("message", {}).get("content", "") if elecciones else ""
                print_func(f"\nAsistente > {contenido_asistente}")

                if fuentes_turno:
                    print_func("\n  [Fuentes citadas del repositorio/documentación]:")
                    for f in fuentes_turno:
                        orig = f.get("archivo", "desconocido")
                        lineas = f.get("lineas", "")
                        nom = f.get("nombre") or f.get("seccion", "")
                        rel = f.get("relevancia", 0.0)
                        print_func(f"   * {orig}:{lineas} ({nom}) - Score: {rel:.2f}")

                historial.append({"role": "user", "content": msg})
                historial.append({"role": "assistant", "content": contenido_asistente})

                # Cálculo y presentación de mediciones de tokens y velocidad
                metricas = calcular_metricas_interaccion(
                    tokens_mensaje=tokens_msg,
                    respuesta_api=resp,
                    tiempo_total_s=tiempo_transcurrido,
                    cliente=cli,
                    contenido_salida=contenido_asistente,
                    metricas_rag=datos_rag_turno,
                )
                mostrar_metricas_turno(metricas, print_func=print_func)

                # Persistencia en base de datos
                try:
                    gestor_proy.registrar_mensaje(
                        sesion_id=sesion_id_activa,
                        rol="user",
                        contenido=msg,
                        tokens_prompt=metricas["tokens_mensaje"],
                    )
                    gestor_proy.registrar_mensaje(
                        sesion_id=sesion_id_activa,
                        rol="assistant",
                        contenido=contenido_asistente,
                        fuentes=fuentes_turno if fuentes_turno else None,
                        tokens_generados=metricas["tokens_generados"],
                    )
                except Exception as e_pers:
                    logger.debug(f"Fallo al persistir mensaje: {e_pers}")

                # Acumulación de estadísticas de sesión
                total_turnos += 1
                total_tokens_usuario += metricas["tokens_mensaje"]
                total_tokens_enviados += metricas["tokens_enviados_realmente"]
                total_tokens_generados += metricas["tokens_generados"]
                tiempo_total_inferencia += metricas["tiempo_total_s"]

            except Exception as err:
                print_func(f"\n[!] Error durante la inferencia del modelo: {err}")

    finally:
        if gestor_emb is not None:
            try:
                gestor_emb.detener_servidor()
            except Exception:
                pass
        if hasattr(cli, "liberar_memoria"):
            try:
                cli.liberar_memoria()
            except Exception:
                pass

        if total_turnos > 0:
            vel_media = (total_tokens_generados / tiempo_total_inferencia) if tiempo_total_inferencia > 0 else 0.0
            print_func("\n" + "=" * 80)
            print_func("                    RESUMEN DE LA SESIÓN DE CHAT")
            print_func("=" * 80)
            print_func(f"  * Turnos completados:                  {total_turnos}")
            print_func(f"  * Tokens de mensajes de usuario:       {total_tokens_usuario} tokens")
            print_func(f"  * Tokens realmente enviados al modelo: {total_tokens_enviados} tokens")
            print_func(f"  * Tokens generados totales:            {total_tokens_generados} tokens")
            print_func(f"  * Tiempo total de inferencia:          {tiempo_total_inferencia:.2f} s")
            print_func(f"  * Velocidad promedio de generación:    {vel_media:.2f} tok/s")
            print_func("=" * 80)

        if servidor_arrancado_por_chat and srv.esta_activo():
            try:
                opc_detener = input_func("\n¿Deseas detener el servidor llama-server ahora? [s/N]: ").strip().lower()
                if opc_detener in ("s", "si", "y", "yes"):
                    srv.detener_servidor()
                    print_func("[OK] Servidor llama-server detenido.")
                else:
                    print_func("[*] Servidor mantenido en segundo plano.")
            except (KeyboardInterrupt, EOFError):
                pass
