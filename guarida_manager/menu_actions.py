import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from guarida_manager.cache import ConfiguracionOptimaRegistro, GestorCache, ModeloRegistro
from guarida_manager.downloader.compliance import RegionNormativa
from guarida_manager.downloader.models import CatalogoModelos, DescargadorModelos
from guarida_manager.downloader.provisioning import OrquestadorAprovisionamiento
from guarida_manager.downloader.tools import GestorHerramientasBunker
from guarida_manager.engine.server import LlamaServerConfig, GestorLlamaServer
from guarida_manager.hardware import InformacionHardware, obtener_informacion_hardware


def mostrar_estado_cache(gestor_cache: GestorCache) -> None:
    """Muestra el estado de la base de datos de caché SQLite."""
    print("\n--- [2] ESTADO DE CACHÉ Y BASE DE DATOS SQLITE ---")
    print(f"Ruta Base de Datos:          {gestor_cache.ruta_db}")
    modulos = gestor_cache.obtener_modulos_instalados()
    print(f"Módulos registrados:         {len(modulos)}")
    for mod in modulos:
        print(f"  - {mod.get('nombre')} (instalado: {mod.get('fecha')})")

    with gestor_cache.sesion() as conn:
        modelos_count = conn.execute("SELECT COUNT(*) FROM modelos;").fetchone()[0]
        benchmarks_count = conn.execute("SELECT COUNT(*) FROM benchmarks;").fetchone()[0]
    print(f"Modelos en catálogo:         {modelos_count}")
    print(f"Benchmarks guardados:        {benchmarks_count}")
    print()


def listar_perfiles_afinamiento(gestor_cache: GestorCache, hash_hw: str) -> None:
    """Imprime los perfiles de afinamiento guardados para el hash de hardware actual."""
    print("\n--- PERFILES DE AFINAMIENTO ÓPTIMO GUARDADOS EN MEMORIA (SQLITE) ---")
    perfiles = gestor_cache.listar_configuraciones_optimas(hash_hw)

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


def obtener_modelos_locales(gestor_cache: GestorCache) -> list[dict]:
    """Obtiene la lista de modelos con archivo descargado y existente en disco."""
    with gestor_cache.sesion() as conn:
        filas = conn.execute(
            "SELECT id, filename, ruta_local, estado FROM modelos WHERE ruta_local != '';"
        ).fetchall()
    resultado = []
    for f in filas:
        d = dict(f)
        ruta = Path(d["ruta_local"])
        if ruta.exists() and ruta.is_file() and ruta.stat().st_size > 0:
            d["tamano_mb"] = round(ruta.stat().st_size / (1024 * 1024), 1)
            resultado.append(d)
    return resultado


def archivar_modelo(gestor_cache: GestorCache, mid_borrar: str) -> bool:
    """Archiva un modelo borrando su archivo físico pero manteniendo métricas en SQLite."""
    descargador = DescargadorModelos(gestor_cache=gestor_cache)
    return descargador.archivar_modelo_sin_archivo(mid_borrar)


def aprovisionar_bunker_lote(
    gestor_cache: GestorCache,
    modelos_elegidos: list[str],
    clave_boveda: Optional[str] = None,
    region: RegionNormativa = RegionNormativa.ES_EU,
    interfaz: str = "terminal",
    instalar_pdf: bool = True,
    permitir_pip_runtime: bool = True,
):
    """Ejecuta el aprovisionamiento por lotes del búnker con inyección de caché."""
    orquestador = OrquestadorAprovisionamiento(gestor_cache=gestor_cache)
    return orquestador.ejecutar_aprovisionamiento_lote(
        region=region,
        interfaz=interfaz,
        instalar_pdf=instalar_pdf,
        modelos_ids_lote=modelos_elegidos,
        clave_maestra_boveda=clave_boveda,
        permitir_pip_runtime=permitir_pip_runtime,
    )


def estimar_conjunto_modelos_optimo(hardware: Optional[InformacionHardware] = None) -> dict:
    """Estima y selecciona el trío óptimo de modelos (Coder, Chat, Embedding) según el hardware."""
    hw = hardware or obtener_informacion_hardware()
    ram = hw.ram_total_gb
    limite = hw.memoria_extrema_forzable_gb
    vram = hw.gtt_disponible_gb if hw.tiene_aceleracion_gpu else 0.0

    if limite >= 80.0 or vram >= 80.0 or ram >= 120.0:
        tier = "ultra_128gb"
        coder = "qwen2.5-72b-instruct-q4"
        chat = "deepseek-r1-distill-llama-70b-q4"
        embedding = "bge-m3-q4"
        desc = "Ultra 128 GB VRAM (70B-72B Full GPU, razonamiento masivo y arquitectura completa)"
    elif limite >= 40.0 or vram >= 40.0 or ram >= 60.0:
        tier = "workstation_pro_64gb"
        coder = "qwen2.5-coder-32b-q4"
        chat = "llama-3.3-70b-instruct-q4"
        embedding = "bge-m3-q4"
        desc = "Workstation Pro 48-64 GB VRAM (32B Coder Q4 + 70B Chat en GPU)"
    elif limite >= 20.0 or ram >= 32.0 or vram >= 16.0:
        tier = "workstation"
        coder = "qwen2.5-coder-14b-q4"
        chat = "qwen2.5-3b-chat-q4"
        embedding = "bge-m3-q4"
        desc = "Alta Capacidad / Workstation (14B Coder + BGE-M3 + 3B Chat)"
    elif limite >= 12.0 or ram >= 16.0 or vram >= 6.0:
        tier = "estandar_alto"
        coder = "qwen2.5-coder-7b-q4"
        chat = "qwen2.5-3b-chat-q4"
        embedding = "bge-m3-q4"
        desc = "Equilibrado Alto (7B Coder + BGE-M3 + 3B Chat)"
    elif limite >= 6.0 or ram >= 8.0:
        tier = "igpu_equilibrado"
        coder = "qwen3-4b-q4"
        chat = "qwen2.5-3b-chat-q4"
        embedding = "nomic-embed-text-v1.5"
        desc = "Punto Dulce iGPU/APU (4B Coder + Nomic Embed + 3B Chat)"
    else:
        tier = "ultraligero"
        coder = "qwen2.5-coder-0.5b-q4"
        chat = "qwen2.5-0.5b-chat-q4"
        embedding = "all-minilm-l6-v2-q8"
        desc = "Ultraligero CPU/Bajo Consumo (0.5B Coder + MiniLM + 0.5B Chat)"

    return {
        "tier": tier,
        "descripcion": desc,
        "coder": coder,
        "chat": chat,
        "embedding": embedding,
        "modelos": [coder, chat, embedding],
    }


def afinar_modelo_automatico(
    gestor_cache: GestorCache,
    modelo_id: str,
    ruta_local: Optional[Path] = None,
    forzar: bool = False,
) -> ConfiguracionOptimaRegistro:
    """Calcula y persiste en SQLite los parámetros de afinamiento óptimo para llama-server según el hardware."""
    hw = obtener_informacion_hardware()
    hash_hw = hw.hash_hardware

    if not forzar:
        optima = gestor_cache.obtener_configuracion_optima(modelo_id=modelo_id, hash_hardware=hash_hw)
        if optima:
            return ConfiguracionOptimaRegistro(
                modelo_id=modelo_id,
                hash_hardware=hash_hw,
                n_gpu_layers=optima.get("n_gpu_layers", 0),
                ctx_size=optima.get("ctx_size", 4096),
                batch_size=optima.get("batch_size", 512),
                kv_cache_tipo=optima.get("kv_cache_tipo", "f16"),
                tok_s_medido=optima.get("tok_s_medido", 25.0),
                gtt_pico_mb=optima.get("gtt_pico_mb", 1024.0),
                fecha_afinamiento=optima.get("fecha_afinamiento", datetime.now(timezone.utc).isoformat()),
                motivo_descarte_o_nota=optima.get("motivo_descarte_o_nota", "Configuración óptima existente"),
                es_recomendada=True,
                threads=optima.get("threads"),
                ubatch_size=optima.get("ubatch_size"),
                flash_attn=optima.get("flash_attn"),
                extra_args_json=optima.get("extra_args_json"),
            )

    tamano_gb = 0.0
    if ruta_local and ruta_local.exists() and ruta_local.is_file():
        tamano_gb = ruta_local.stat().st_size / (1024**3)
    else:
        def_m = CatalogoModelos.obtener_modelo(modelo_id)
        if def_m:
            tamano_gb = def_m.tamano_gb

    # Garantizar que el modelo existe en la tabla 'modelos' para cumplir con la FK de SQLite
    if not gestor_cache.obtener_modelo(modelo_id):
        m_def = CatalogoModelos.obtener_modelo(modelo_id)
        gestor_cache.guardar_modelo(
            ModeloRegistro(
                id=modelo_id,
                repo_hf=m_def.repo_hf if m_def else "custom/repo",
                filename=m_def.filename if m_def else f"{modelo_id}.gguf",
                ruta_local=str(ruta_local or ""),
                estado="disponible" if (ruta_local and ruta_local.exists()) else "registrado",
                license=m_def.licencia if m_def else None,
                training_summary_url=m_def.training_summary_url if m_def else None,
            )
        )

    hilos = max(1, hw.nucleos_fisicos) if hw.nucleos_fisicos > 0 else 4
    vram_util = max(0.0, hw.gtt_disponible_gb - 1.5) if hw.tiene_aceleracion_gpu else 0.0
    es_igpu = hw.tipo_gpu_principal in ("Intel", "CPU") or not hw.tiene_aceleracion_gpu or (
        bool(hw.gpus) and all(g.tipo == "Integrada" or g.vram_dedicada_gb == 0 for g in hw.gpus)
    )
    excede_vram = (tamano_gb > hw.gtt_disponible_gb) if hw.tiene_aceleracion_gpu else True
    es_embedding = "embed" in modelo_id.lower() or "bge" in modelo_id.lower() or "minilm" in modelo_id.lower()

    if not hw.tiene_aceleracion_gpu:
        ngl = 0
        ctx = 2048 if hw.ram_total_gb < 8.0 else 4096
        batch = 256
        ubatch = 128
        kv = "q8_0"
        fa = 0
        extra: list[str] = []
        tok_s = 14.0
    elif excede_vram or (es_igpu and tamano_gb >= 6.0):
        # En iGPU (Intel Iris Xe / APU), modelos >= 6 GB saturan buffers Vulkan; forzar CPU puro (-ngl 0 -nkvo)
        ngl = 0
        ctx = 2048
        batch = 256
        ubatch = 128
        kv = "q8_0"
        fa = 0
        extra = ["-nkvo"]
        tok_s = 8.5
    elif tamano_gb <= vram_util or tamano_gb <= 1.0:
        ngl = 33
        ctx = 8192 if hw.gtt_disponible_gb >= 12.0 else 4096
        batch = 512
        ubatch = 512
        kv = "f16" if hw.gtt_disponible_gb >= 8.0 else "q8_0"
        fa = 1 if (hw.tipo_gpu_principal == "NVIDIA" and hw.tiene_aceleracion_gpu) else 0
        extra = []
        tok_s = 38.0
    else:
        proporcion = max(0.20, min(0.85, vram_util / max(tamano_gb, 1.0)))
        ngl = max(4, int(33 * proporcion))
        ctx = 2048 if hw.gtt_disponible_gb < 8.0 else 4096
        batch = 256
        ubatch = 256
        kv = "q8_0"
        fa = 0
        extra = []
        tok_s = 22.0

    if es_embedding:
        ctx = 2048
        batch = 512
        ubatch = 512
        ngl = 0 if not hw.tiene_aceleracion_gpu else min(ngl, 16)

    registro = ConfiguracionOptimaRegistro(
        modelo_id=modelo_id,
        hash_hardware=hash_hw,
        n_gpu_layers=ngl,
        ctx_size=ctx,
        batch_size=batch,
        kv_cache_tipo=kv,
        tok_s_medido=tok_s,
        gtt_pico_mb=round(tamano_gb * 1024, 1),
        fecha_afinamiento=datetime.now(timezone.utc).isoformat(),
        motivo_descarte_o_nota=f"Auto-Afinado automático para hardware {hash_hw[:8]}",
        es_recomendada=True,
        threads=hilos,
        ubatch_size=ubatch,
        flash_attn=fa,
        extra_args_json=json.dumps(extra),
    )
    gestor_cache.guardar_configuracion_optima(registro)
    return registro


def afinar_todos_automatico(gestor_cache: GestorCache, forzar: bool = False) -> list[ConfiguracionOptimaRegistro]:
    """Auto-afina todos los modelos descargados en el disco para el hardware actual."""
    locales = obtener_modelos_locales(gestor_cache)
    resultados = []
    for mod in locales:
        reg = afinar_modelo_automatico(
            gestor_cache=gestor_cache,
            modelo_id=mod["id"],
            ruta_local=Path(mod["ruta_local"]),
            forzar=forzar,
        )
        resultados.append(reg)
    return resultados


def calcular_afinamiento_combinado(
    gestor_cache: GestorCache,
    modelo_gen_id: str,
    modelo_emb_id: str,
    ruta_gen: Optional[Path] = None,
    ruta_emb: Optional[Path] = None,
) -> dict[str, Any]:
    """Calcula el afinamiento combinado y la asignación armónica de recursos entre un motor de embeddings y un LLM."""
    hw = obtener_informacion_hardware()
    hash_hw = hw.hash_hardware

    cfg_gen = gestor_cache.obtener_configuracion_optima(modelo_gen_id, hash_hw)
    if not cfg_gen:
        afinar_modelo_automatico(gestor_cache, modelo_gen_id, ruta_gen)
        cfg_gen = gestor_cache.obtener_configuracion_optima(modelo_gen_id, hash_hw) or {}

    cfg_emb = gestor_cache.obtener_configuracion_optima(modelo_emb_id, hash_hw)
    if not cfg_emb:
        afinar_modelo_automatico(gestor_cache, modelo_emb_id, ruta_emb)
        cfg_emb = gestor_cache.obtener_configuracion_optima(modelo_emb_id, hash_hw) or {}

    # Memoria conjunta requerida (MB)
    mem_gen = cfg_gen.get("gtt_pico_mb", 4000.0)
    mem_emb = cfg_emb.get("gtt_pico_mb", 300.0)
    mem_total_estimada = round(mem_gen + mem_emb, 1)

    # Reparto de hilos: cooperativo vs concurrente
    hilos_totales = max(1, hw.nucleos_fisicos) if hw.nucleos_fisicos > 0 else 4
    hilos_emb = max(1, min(4, hilos_totales // 2))
    hilos_gen = hilos_totales

    # Puntuación base individual
    score_gen = cfg_gen.get("tok_s_medido", 20.0)
    score_emb = cfg_emb.get("tok_s_medido", 25.0)

    # Bonificación de sinergia
    bono_sinergia = 0.0
    es_coder = "coder" in modelo_gen_id.lower() or "code" in modelo_gen_id.lower()
    es_chat = "chat" in modelo_gen_id.lower() or "instruct" in modelo_gen_id.lower()
    emb_lower = modelo_emb_id.lower()

    if es_coder:
        if "jina" in emb_lower and "code" in emb_lower:
            bono_sinergia += 8.5
            rec = "Óptimo para refactorización AST profunda y contexto amplio de código (8k)"
        elif "bge" in emb_lower:
            bono_sinergia += 7.0
            rec = "Excelente equilibrio multilingüe y comprensión sintáctica densa"
        elif "minilm" in emb_lower:
            bono_sinergia += 6.0
            rec = "Ultraligero: latencia mínima de vectorización en CPU/iGPU limitada"
        else:
            bono_sinergia += 5.0
            rec = "Adecuado para asistencia de programación y búsqueda semántica"
    elif es_chat:
        if "bge" in emb_lower:
            bono_sinergia += 8.0
            rec = "Máxima precisión en diálogo contextual y recuperación RAG multilingüe"
        elif "nomic" in emb_lower or "snowflake" in emb_lower:
            bono_sinergia += 7.5
            rec = "Alta fidelidad semántica en razonamiento y documentación técnica"
        elif "minilm" in emb_lower:
            bono_sinergia += 6.5
            rec = "Respuesta instantánea para chat interactivo con bajo consumo de RAM"
        else:
            bono_sinergia += 5.0
            rec = "Uso general equilibrado"
    else:
        bono_sinergia += 5.0
        rec = "Pareja balanceada para tareas mixtas de inferencia y embeddings"

    # Score de conjunto normalizado
    score_conjunto = round((0.60 * score_gen) + (0.25 * score_emb) + bono_sinergia, 2)

    return {
        "modelo_gen_id": modelo_gen_id,
        "modelo_emb_id": modelo_emb_id,
        "score_conjunto": score_conjunto,
        "score_gen": score_gen,
        "score_emb": score_emb,
        "memoria_conjunta_mb": mem_total_estimada,
        "estrategia_cooperacion": "Secuencial (Caché SHA-256 AST + 100% Coder)",
        "hilos_emb": hilos_emb,
        "hilos_gen": hilos_gen,
        "ctx_emb": cfg_emb.get("ctx_size", 2048),
        "ctx_gen": cfg_gen.get("ctx_size", 4096),
        "ngl_emb": cfg_emb.get("n_gpu_layers", 0),
        "ngl_gen": cfg_gen.get("n_gpu_layers", 0),
        "recomendacion_uso": rec,
    }


def obtener_mejores_parejas_combinadas(gestor_cache: GestorCache) -> list[dict[str, Any]]:
    """Calcula y ordena el ranking de todas las combinaciones generativo + embedding locales."""
    locales = obtener_modelos_locales(gestor_cache)
    def _es_emb(m_id: str) -> bool:
        ml = m_id.lower()
        return any(k in ml for k in ("embed", "bge", "minilm", "jina", "snowflake"))

    embs = [m for m in locales if _es_emb(m["id"])]
    gens = [m for m in locales if not _es_emb(m["id"])]
    if not embs or not gens:
        return []

    parejas = []
    for g in gens:
        for e in embs:
            p = calcular_afinamiento_combinado(
                gestor_cache,
                g["id"],
                e["id"],
                Path(g["ruta_local"]),
                Path(e["ruta_local"]),
            )
            parejas.append(p)

    parejas.sort(key=lambda x: x["score_conjunto"], reverse=True)
    return parejas

