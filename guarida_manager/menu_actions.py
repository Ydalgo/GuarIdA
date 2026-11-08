import os
from pathlib import Path
from typing import Optional

from guarida_manager.cache import GestorCache
from guarida_manager.downloader.compliance import RegionNormativa
from guarida_manager.downloader.models import DescargadorModelos
from guarida_manager.downloader.provisioning import OrquestadorAprovisionamiento
from guarida_manager.downloader.tools import GestorHerramientasBunker
from guarida_manager.engine.server import LlamaServerConfig, GestorLlamaServer


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
