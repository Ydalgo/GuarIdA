import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator, Optional

from guarida_manager import RUTA_BASE_DATOS_PREDETERMINADA


@dataclass(frozen=True)
class ModeloRegistro:
    id: str
    repo_hf: str
    filename: str
    ruta_local: str
    estado: str
    motivo_descarte: Optional[str] = None
    license: Optional[str] = None
    training_summary_url: Optional[str] = None


@dataclass(frozen=True)
class BenchmarkRegistro:
    modelo_id: str
    hash_hardware: str
    binario_usado: str
    n_gpu_layers: int
    ctx_size: int
    tok_s: float
    gtt_pico_mb: float
    exito_tool_calling: bool
    id: Optional[int] = None


@dataclass(frozen=True)
class ModuloRegistro:
    nombre: str
    fecha: str


@dataclass(frozen=True)
class ProyectoRegistro:
    id: str
    nombre: str
    descripcion: str
    ruta_directorio: str
    fecha_creacion: str


@dataclass(frozen=True)
class DocumentoProyectoRegistro:
    id: Optional[int]
    proyecto_id: str
    ruta_relativa: str
    ruta_absoluta: str
    tipo_documento: str
    sha256: str
    nodos_ast_count: int
    n_tokens_est: int
    fecha_indexacion: str


@dataclass(frozen=True)
class SesionChatRegistro:
    id: str
    proyecto_id: Optional[str]
    modelo_id: str
    titulo: str
    fecha_creacion: str
    fecha_actualizacion: str


@dataclass(frozen=True)
class MensajeChatRegistro:
    id: Optional[int]
    sesion_id: str
    rol: str
    contenido: str
    tokens_prompt: int
    tokens_generados: int
    fuentes_ast_json: Optional[str]
    fecha: str


@dataclass(frozen=True)
class ConfiguracionOptimaRegistro:
    modelo_id: str
    hash_hardware: str
    n_gpu_layers: int
    ctx_size: int
    batch_size: int
    kv_cache_tipo: str
    tok_s_medido: float
    gtt_pico_mb: float
    fecha_afinamiento: str
    motivo_descarte_o_nota: Optional[str] = None
    es_recomendada: bool = True
    threads: Optional[int] = None
    ubatch_size: Optional[int] = None
    flash_attn: Optional[int] = None
    extra_args_json: Optional[str] = None


class GestorCache:
    def __init__(self, ruta_base_datos: Optional[Path | str] = None) -> None:
        if ruta_base_datos is None:
            self.ruta_db = RUTA_BASE_DATOS_PREDETERMINADA
        else:
            self.ruta_db = Path(ruta_base_datos)

        self.ruta_db.parent.mkdir(parents=True, exist_ok=True)
        self.inicializar_tablas()

    @contextmanager
    def sesion(self) -> Generator[sqlite3.Connection, None, None]:
        conexion = sqlite3.connect(str(self.ruta_db), timeout=30.0)
        conexion.row_factory = sqlite3.Row
        conexion.execute("PRAGMA foreign_keys = ON;")
        conexion.execute("PRAGMA journal_mode = WAL;")
        try:
            yield conexion
            conexion.commit()
        finally:
            conexion.close()

    def inicializar_tablas(self) -> None:
        with self.sesion() as conexion:
            conexion.execute(
                """
                CREATE TABLE IF NOT EXISTS modelos (
                    id TEXT PRIMARY KEY,
                    repo_hf TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    ruta_local TEXT NOT NULL,
                    estado TEXT NOT NULL,
                    motivo_descarte TEXT,
                    license TEXT,
                    training_summary_url TEXT
                );
                """
            )
            conexion.execute(
                """
                CREATE TABLE IF NOT EXISTS benchmarks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    modelo_id TEXT NOT NULL,
                    hash_hardware TEXT NOT NULL,
                    binario_usado TEXT NOT NULL,
                    n_gpu_layers INTEGER NOT NULL,
                    ctx_size INTEGER NOT NULL,
                    tok_s REAL NOT NULL,
                    gtt_pico_mb REAL NOT NULL,
                    exito_tool_calling INTEGER NOT NULL,
                    FOREIGN KEY (modelo_id) REFERENCES modelos(id) ON DELETE CASCADE
                );
                """
            )
            conexion.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_benchmarks_lookup
                ON benchmarks(modelo_id, hash_hardware);
                """
            )
            conexion.execute(
                """
                CREATE TABLE IF NOT EXISTS modulos_instalados (
                    nombre TEXT PRIMARY KEY,
                    fecha TEXT NOT NULL
                );
                """
            )
            conexion.execute(
                """
                CREATE TABLE IF NOT EXISTS configuraciones_optimas (
                    modelo_id TEXT NOT NULL,
                    hash_hardware TEXT NOT NULL,
                    n_gpu_layers INTEGER NOT NULL,
                    ctx_size INTEGER NOT NULL,
                    batch_size INTEGER NOT NULL,
                    kv_cache_tipo TEXT NOT NULL,
                    tok_s_medido REAL NOT NULL,
                    gtt_pico_mb REAL NOT NULL,
                    fecha_afinamiento TEXT NOT NULL,
                    motivo_descarte_o_nota TEXT,
                    es_recomendada INTEGER NOT NULL DEFAULT 1,
                    PRIMARY KEY (modelo_id, hash_hardware),
                    FOREIGN KEY (modelo_id) REFERENCES modelos(id) ON DELETE CASCADE
                );
                """
            )
            conexion.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_config_optima_lookup
                ON configuraciones_optimas(modelo_id, hash_hardware);
                """
            )
            conexion.execute(
                """
                CREATE TABLE IF NOT EXISTS capacidades_binario (
                    sha256_binario TEXT PRIMARY KEY,
                    version_build TEXT NOT NULL,
                    flags_json TEXT NOT NULL,
                    dispositivos_json TEXT NOT NULL,
                    capacidades_completas_json TEXT NOT NULL,
                    fecha TEXT NOT NULL
                );
                """
            )
            conexion.execute(
                """
                CREATE TABLE IF NOT EXISTS bench_sesiones (
                    id TEXT PRIMARY KEY,
                    modelo_id TEXT NOT NULL,
                    sha256_modelo TEXT NOT NULL,
                    hash_hardware TEXT NOT NULL,
                    sha256_binario TEXT NOT NULL,
                    version_build TEXT NOT NULL,
                    hash_perfil_barrido TEXT NOT NULL,
                    hash_perfil_bateria TEXT NOT NULL,
                    objetivo TEXT NOT NULL,
                    estado TEXT NOT NULL,
                    inicio TEXT NOT NULL,
                    fin TEXT,
                    FOREIGN KEY (modelo_id) REFERENCES modelos(id) ON DELETE CASCADE
                );
                """
            )
            conexion.execute(
                """
                CREATE TABLE IF NOT EXISTS bench_configs (
                    id TEXT PRIMARY KEY,
                    sesion_id TEXT NOT NULL,
                    hash_config TEXT NOT NULL,
                    args_json TEXT NOT NULL,
                    etapa TEXT NOT NULL,
                    estado TEXT NOT NULL,
                    error_resumen TEXT,
                    mem_modelo_mb REAL DEFAULT 0.0,
                    mem_kv_mb REAL DEFAULT 0.0,
                    mem_compute_mb REAL DEFAULT 0.0,
                    ram_pico_mb REAL DEFAULT 0.0,
                    vram_pico_mb REAL DEFAULT 0.0,
                    gtt_pico_mb REAL DEFAULT 0.0,
                    score REAL DEFAULT 0.0,
                    FOREIGN KEY (sesion_id) REFERENCES bench_sesiones(id) ON DELETE CASCADE
                );
                """
            )
            conexion.execute(
                """
                CREATE TABLE IF NOT EXISTS bench_ejecuciones (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    config_id TEXT NOT NULL,
                    escenario TEXT NOT NULL,
                    rep INTEGER NOT NULL,
                    es_calentamiento INTEGER NOT NULL DEFAULT 0,
                    prompt_n INTEGER NOT NULL DEFAULT 0,
                    predicted_n INTEGER NOT NULL DEFAULT 0,
                    pp_tok_s REAL NOT NULL DEFAULT 0.0,
                    tg_tok_s REAL NOT NULL DEFAULT 0.0,
                    ttft_ms REAL NOT NULL DEFAULT 0.0,
                    latencia_total_ms REAL NOT NULL DEFAULT 0.0,
                    exito INTEGER NOT NULL DEFAULT 1,
                    calidad_pct REAL DEFAULT 100.0,
                    FOREIGN KEY (config_id) REFERENCES bench_configs(id) ON DELETE CASCADE
                );
                """
            )
            # Migración idempotente de columnas para configuraciones_optimas
            try:
                cols = [row[1] for row in conexion.execute("PRAGMA table_info(configuraciones_optimas);").fetchall()]
                if "threads" not in cols:
                    conexion.execute("ALTER TABLE configuraciones_optimas ADD COLUMN threads INTEGER;")
                if "ubatch_size" not in cols:
                    conexion.execute("ALTER TABLE configuraciones_optimas ADD COLUMN ubatch_size INTEGER;")
                if "flash_attn" not in cols:
                    conexion.execute("ALTER TABLE configuraciones_optimas ADD COLUMN flash_attn INTEGER;")
                if "extra_args_json" not in cols:
                    conexion.execute("ALTER TABLE configuraciones_optimas ADD COLUMN extra_args_json TEXT;")
            except Exception:
                pass

            conexion.execute(
                """
                CREATE TABLE IF NOT EXISTS proyectos (
                    id TEXT PRIMARY KEY,
                    nombre TEXT NOT NULL,
                    descripcion TEXT NOT NULL,
                    ruta_directorio TEXT NOT NULL,
                    fecha_creacion TEXT NOT NULL
                );
                """
            )
            conexion.execute(
                """
                CREATE TABLE IF NOT EXISTS documentos_proyecto (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    proyecto_id TEXT NOT NULL,
                    ruta_relativa TEXT NOT NULL,
                    ruta_absoluta TEXT NOT NULL,
                    tipo_documento TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    nodos_ast_count INTEGER DEFAULT 0,
                    n_tokens_est INTEGER DEFAULT 0,
                    fecha_indexacion TEXT NOT NULL,
                    FOREIGN KEY (proyecto_id) REFERENCES proyectos(id) ON DELETE CASCADE
                );
                """
            )
            conexion.execute(
                """
                CREATE TABLE IF NOT EXISTS sesiones_chat (
                    id TEXT PRIMARY KEY,
                    proyecto_id TEXT,
                    modelo_id TEXT NOT NULL,
                    titulo TEXT NOT NULL,
                    fecha_creacion TEXT NOT NULL,
                    fecha_actualizacion TEXT NOT NULL,
                    FOREIGN KEY (proyecto_id) REFERENCES proyectos(id) ON DELETE SET NULL
                );
                """
            )
            conexion.execute(
                """
                CREATE TABLE IF NOT EXISTS mensajes_chat (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sesion_id TEXT NOT NULL,
                    rol TEXT NOT NULL,
                    contenido TEXT NOT NULL,
                    tokens_prompt INTEGER DEFAULT 0,
                    tokens_generados INTEGER DEFAULT 0,
                    fuentes_ast_json TEXT,
                    fecha TEXT NOT NULL,
                    FOREIGN KEY (sesion_id) REFERENCES sesiones_chat(id) ON DELETE CASCADE
                );
                """
            )

    def guardar_modelo(self, modelo: ModeloRegistro) -> None:
        with self.sesion() as conexion:
            conexion.execute(
                """
                INSERT INTO modelos (
                    id, repo_hf, filename, ruta_local,
                    estado, motivo_descarte, license, training_summary_url
                )
                VALUES (:id, :repo_hf, :filename, :ruta_local, :estado, :motivo_descarte, :license, :training_summary_url)
                ON CONFLICT(id) DO UPDATE SET
                    repo_hf = excluded.repo_hf,
                    filename = excluded.filename,
                    ruta_local = excluded.ruta_local,
                    estado = excluded.estado,
                    motivo_descarte = excluded.motivo_descarte,
                    license = excluded.license,
                    training_summary_url = excluded.training_summary_url;
                """,
                asdict(modelo),
            )

    def obtener_modelo(self, modelo_id: str) -> Optional[dict[str, Any]]:
        with self.sesion() as conexion:
            cursor = conexion.execute(
                "SELECT * FROM modelos WHERE id = ?;",
                (modelo_id,),
            )
            fila = cursor.fetchone()
            if fila:
                return dict(fila)
            return None

    def listar_modelos(self, estado: Optional[str] = None) -> list[dict[str, Any]]:
        with self.sesion() as conexion:
            if estado:
                cursor = conexion.execute(
                    "SELECT * FROM modelos WHERE estado = ? ORDER BY id ASC;",
                    (estado,),
                )
            else:
                cursor = conexion.execute(
                    "SELECT * FROM modelos ORDER BY id ASC;"
                )
            return [dict(fila) for fila in cursor.fetchall()]

    def actualizar_estado_modelo(
        self, modelo_id: str, estado: str, motivo_descarte: Optional[str] = None
    ) -> None:
        with self.sesion() as conexion:
            conexion.execute(
                """
                UPDATE modelos
                SET estado = ?, motivo_descarte = ?
                WHERE id = ?;
                """,
                (estado, motivo_descarte, modelo_id),
            )

    def guardar_benchmark(self, benchmark: BenchmarkRegistro) -> int:
        with self.sesion() as conexion:
            cursor = conexion.execute(
                """
                INSERT INTO benchmarks (
                    modelo_id, hash_hardware, binario_usado,
                    n_gpu_layers, ctx_size, tok_s, gtt_pico_mb, exito_tool_calling
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    benchmark.modelo_id,
                    benchmark.hash_hardware,
                    benchmark.binario_usado,
                    benchmark.n_gpu_layers,
                    benchmark.ctx_size,
                    benchmark.tok_s,
                    benchmark.gtt_pico_mb,
                    1 if benchmark.exito_tool_calling else 0,
                ),
            )
            return int(cursor.lastrowid)

    def obtener_benchmark(
        self, modelo_id: str, hash_hardware: str
    ) -> Optional[dict[str, Any]]:
        with self.sesion() as conexion:
            cursor = conexion.execute(
                """
                SELECT * FROM benchmarks
                WHERE modelo_id = ? AND hash_hardware = ?
                ORDER BY exito_tool_calling DESC, tok_s DESC
                LIMIT 1;
                """,
                (modelo_id, hash_hardware),
            )
            fila = cursor.fetchone()
            if fila:
                resultado = dict(fila)
                resultado["exito_tool_calling"] = bool(resultado["exito_tool_calling"])
                return resultado
            return None

    def listar_benchmarks_por_modelo(
        self, modelo_id: str, hash_hardware: Optional[str] = None
    ) -> list[dict[str, Any]]:
        with self.sesion() as conexion:
            if hash_hardware:
                cursor = conexion.execute(
                    """
                    SELECT * FROM benchmarks
                    WHERE modelo_id = ? AND hash_hardware = ?
                    ORDER BY id DESC;
                    """,
                    (modelo_id, hash_hardware),
                )
            else:
                cursor = conexion.execute(
                    """
                    SELECT * FROM benchmarks
                    WHERE modelo_id = ?
                    ORDER BY id DESC;
                    """,
                    (modelo_id,),
                )
            resultados = []
            for fila in cursor.fetchall():
                elemento = dict(fila)
                elemento["exito_tool_calling"] = bool(elemento["exito_tool_calling"])
                resultados.append(elemento)
            return resultados

    def guardar_configuracion_optima(self, config: ConfiguracionOptimaRegistro) -> None:
        with self.sesion() as conexion:
            conexion.execute(
                """
                INSERT INTO configuraciones_optimas (
                    modelo_id, hash_hardware, n_gpu_layers, ctx_size,
                    batch_size, kv_cache_tipo, tok_s_medido, gtt_pico_mb,
                    fecha_afinamiento, motivo_descarte_o_nota, es_recomendada,
                    threads, ubatch_size, flash_attn, extra_args_json
                )
                VALUES (
                    :modelo_id, :hash_hardware, :n_gpu_layers, :ctx_size,
                    :batch_size, :kv_cache_tipo, :tok_s_medido, :gtt_pico_mb,
                    :fecha_afinamiento, :motivo_descarte_o_nota, :es_recomendada,
                    :threads, :ubatch_size, :flash_attn, :extra_args_json
                )
                ON CONFLICT(modelo_id, hash_hardware) DO UPDATE SET
                    n_gpu_layers = excluded.n_gpu_layers,
                    ctx_size = excluded.ctx_size,
                    batch_size = excluded.batch_size,
                    kv_cache_tipo = excluded.kv_cache_tipo,
                    tok_s_medido = excluded.tok_s_medido,
                    gtt_pico_mb = excluded.gtt_pico_mb,
                    fecha_afinamiento = excluded.fecha_afinamiento,
                    motivo_descarte_o_nota = excluded.motivo_descarte_o_nota,
                    es_recomendada = excluded.es_recomendada,
                    threads = excluded.threads,
                    ubatch_size = excluded.ubatch_size,
                    flash_attn = excluded.flash_attn,
                    extra_args_json = excluded.extra_args_json;
                """,
                {
                    "modelo_id": config.modelo_id,
                    "hash_hardware": config.hash_hardware,
                    "n_gpu_layers": config.n_gpu_layers,
                    "ctx_size": config.ctx_size,
                    "batch_size": config.batch_size,
                    "kv_cache_tipo": config.kv_cache_tipo,
                    "tok_s_medido": config.tok_s_medido,
                    "gtt_pico_mb": config.gtt_pico_mb,
                    "fecha_afinamiento": config.fecha_afinamiento,
                    "motivo_descarte_o_nota": config.motivo_descarte_o_nota,
                    "es_recomendada": 1 if config.es_recomendada else 0,
                    "threads": config.threads,
                    "ubatch_size": config.ubatch_size,
                    "flash_attn": config.flash_attn,
                    "extra_args_json": config.extra_args_json,
                },
            )

    def obtener_configuracion_optima(
        self, modelo_id: str, hash_hardware: str
    ) -> Optional[dict[str, Any]]:
        import json

        with self.sesion() as conexion:
            cursor = conexion.execute(
                """
                SELECT * FROM configuraciones_optimas
                WHERE modelo_id = ? AND hash_hardware = ?;
                """,
                (modelo_id, hash_hardware),
            )
            fila = cursor.fetchone()
            if not fila:
                cursor = conexion.execute(
                    """
                    SELECT * FROM configuraciones_optimas
                    WHERE modelo_id = ?
                    ORDER BY tok_s_medido DESC LIMIT 1;
                    """,
                    (modelo_id,),
                )
                fila = cursor.fetchone()
            if fila:
                resultado = dict(fila)
                resultado["es_recomendada"] = bool(resultado["es_recomendada"])
                resultado["origen_config"] = "configuraciones_optimas"
                return resultado

            # Fallback automático: buscar la mejor configuración probada en bench_configs
            cursor_bench = conexion.execute(
                """
                SELECT bc.args_json, bc.score, bc.gtt_pico_mb, bs.inicio
                FROM bench_configs bc
                JOIN bench_sesiones bs ON bc.sesion_id = bs.id
                WHERE bs.modelo_id = ? AND bc.estado = 'ok'
                ORDER BY bc.score DESC
                LIMIT 1;
                """,
                (modelo_id,),
            )
            fb = cursor_bench.fetchone()
            if fb and fb["args_json"]:
                try:
                    args = json.loads(fb["args_json"])
                    return {
                        "modelo_id": modelo_id,
                        "hash_hardware": hash_hardware,
                        "n_gpu_layers": args.get("n_gpu_layers", 0),
                        "ctx_size": args.get("ctx_size", 4096),
                        "batch_size": args.get("batch_size", 512),
                        "ubatch_size": args.get("ubatch_size", 512),
                        "threads": args.get("threads", 4),
                        "kv_cache_tipo": args.get("kv_cache_tipo", "f16"),
                        "flash_attn": 1 if args.get("flash_attn") else 0,
                        "tok_s_medido": 0.0,
                        "gtt_pico_mb": fb["gtt_pico_mb"] or 0.0,
                        "motivo_descarte_o_nota": f"Mejor config de benchmark (Score: {fb['score']:.2f})",
                        "es_recomendada": True,
                        "origen_config": "bench_configs",
                    }
                except Exception:
                    pass
            return None

    def listar_configuraciones_optimas(
        self, hash_hardware: Optional[str] = None
    ) -> list[dict[str, Any]]:
        with self.sesion() as conexion:
            if hash_hardware:
                cursor = conexion.execute(
                    """
                    SELECT co.*, m.filename, m.estado, m.license
                    FROM configuraciones_optimas co
                    LEFT JOIN modelos m ON co.modelo_id = m.id
                    WHERE co.hash_hardware = ?
                    ORDER BY co.es_recomendada DESC, co.tok_s_medido DESC;
                    """,
                    (hash_hardware,),
                )
            else:
                cursor = conexion.execute(
                    """
                    SELECT co.*, m.filename, m.estado, m.license
                    FROM configuraciones_optimas co
                    LEFT JOIN modelos m ON co.modelo_id = m.id
                    ORDER BY co.es_recomendada DESC, co.tok_s_medido DESC;
                    """
                )
            resultados = []
            for fila in cursor.fetchall():
                item = dict(fila)
                item["es_recomendada"] = bool(item["es_recomendada"])
                resultados.append(item)
            return resultados

    def registrar_modulo_instalado(self, nombre: str) -> None:
        marca_tiempo = datetime.now(timezone.utc).isoformat()
        with self.sesion() as conexion:
            conexion.execute(
                """
                INSERT INTO modulos_instalados (nombre, fecha)
                VALUES (?, ?)
                ON CONFLICT(nombre) DO UPDATE SET fecha = excluded.fecha;
                """,
                (nombre, marca_tiempo),
            )

    def verificar_modulo_instalado(self, nombre: str) -> bool:
        with self.sesion() as conexion:
            cursor = conexion.execute(
                "SELECT 1 FROM modulos_instalados WHERE nombre = ?;",
                (nombre,),
            )
            return cursor.fetchone() is not None

    def obtener_modulos_instalados(self) -> list[dict[str, Any]]:
        with self.sesion() as conexion:
            cursor = conexion.execute(
                "SELECT nombre, fecha FROM modulos_instalados ORDER BY nombre ASC;"
            )
            return [dict(fila) for fila in cursor.fetchall()]

    # --- Métodos para Proyectos y Documentos (NotebookLM Local / Repositorio) ---

    def guardar_proyecto(self, proyecto: ProyectoRegistro) -> None:
        with self.sesion() as conexion:
            conexion.execute(
                """
                INSERT INTO proyectos (id, nombre, descripcion, ruta_directorio, fecha_creacion)
                VALUES (:id, :nombre, :descripcion, :ruta_directorio, :fecha_creacion)
                ON CONFLICT(id) DO UPDATE SET
                    nombre = excluded.nombre,
                    descripcion = excluded.descripcion,
                    ruta_directorio = excluded.ruta_directorio;
                """,
                asdict(proyecto),
            )

    def obtener_proyecto(self, proyecto_id: str) -> Optional[dict[str, Any]]:
        with self.sesion() as conexion:
            cursor = conexion.execute(
                "SELECT * FROM proyectos WHERE id = ?;", (proyecto_id,)
            )
            fila = cursor.fetchone()
            return dict(fila) if fila else None

    def listar_proyectos(self) -> list[dict[str, Any]]:
        with self.sesion() as conexion:
            cursor = conexion.execute(
                "SELECT * FROM proyectos ORDER BY fecha_creacion DESC;"
            )
            return [dict(fila) for fila in cursor.fetchall()]

    def eliminar_proyecto(self, proyecto_id: str) -> bool:
        with self.sesion() as conexion:
            cursor = conexion.execute(
                "DELETE FROM proyectos WHERE id = ?;", (proyecto_id,)
            )
            return cursor.rowcount > 0

    def guardar_documento_proyecto(self, doc: DocumentoProyectoRegistro) -> int:
        with self.sesion() as conexion:
            cursor = conexion.execute(
                """
                INSERT INTO documentos_proyecto (
                    proyecto_id, ruta_relativa, ruta_absoluta, tipo_documento,
                    sha256, nodos_ast_count, n_tokens_est, fecha_indexacion
                )
                VALUES (
                    :proyecto_id, :ruta_relativa, :ruta_absoluta, :tipo_documento,
                    :sha256, :nodos_ast_count, :n_tokens_est, :fecha_indexacion
                );
                """,
                {
                    "proyecto_id": doc.proyecto_id,
                    "ruta_relativa": doc.ruta_relativa,
                    "ruta_absoluta": doc.ruta_absoluta,
                    "tipo_documento": doc.tipo_documento,
                    "sha256": doc.sha256,
                    "nodos_ast_count": doc.nodos_ast_count,
                    "n_tokens_est": doc.n_tokens_est,
                    "fecha_indexacion": doc.fecha_indexacion,
                },
            )
            return cursor.lastrowid or 0

    def listar_documentos_proyecto(self, proyecto_id: str) -> list[dict[str, Any]]:
        with self.sesion() as conexion:
            cursor = conexion.execute(
                "SELECT * FROM documentos_proyecto WHERE proyecto_id = ? ORDER BY ruta_relativa ASC;",
                (proyecto_id,),
            )
            return [dict(fila) for fila in cursor.fetchall()]

    def eliminar_documentos_proyecto(self, proyecto_id: str) -> None:
        with self.sesion() as conexion:
            conexion.execute("DELETE FROM documentos_proyecto WHERE proyecto_id = ?;", (proyecto_id,))

    # --- Métodos para Sesiones y Mensajes de Chat ---

    def guardar_sesion_chat(self, sesion: SesionChatRegistro) -> None:
        with self.sesion() as conexion:
            conexion.execute(
                """
                INSERT INTO sesiones_chat (id, proyecto_id, modelo_id, titulo, fecha_creacion, fecha_actualizacion)
                VALUES (:id, :proyecto_id, :modelo_id, :titulo, :fecha_creacion, :fecha_actualizacion)
                ON CONFLICT(id) DO UPDATE SET
                    titulo = excluded.titulo,
                    fecha_actualizacion = excluded.fecha_actualizacion;
                """,
                asdict(sesion),
            )

    def obtener_sesion_chat(self, sesion_id: str) -> Optional[dict[str, Any]]:
        with self.sesion() as conexion:
            cursor = conexion.execute(
                "SELECT * FROM sesiones_chat WHERE id = ?;", (sesion_id,)
            )
            fila = cursor.fetchone()
            return dict(fila) if fila else None

    def listar_sesiones_chat(self, proyecto_id: Optional[str] = None) -> list[dict[str, Any]]:
        with self.sesion() as conexion:
            if proyecto_id:
                cursor = conexion.execute(
                    "SELECT * FROM sesiones_chat WHERE proyecto_id = ? ORDER BY fecha_actualizacion DESC;",
                    (proyecto_id,),
                )
            else:
                cursor = conexion.execute(
                    "SELECT * FROM sesiones_chat ORDER BY fecha_actualizacion DESC;"
                )
            return [dict(fila) for fila in cursor.fetchall()]

    def eliminar_sesion_chat(self, sesion_id: str) -> bool:
        with self.sesion() as conexion:
            cursor = conexion.execute("DELETE FROM sesiones_chat WHERE id = ?;", (sesion_id,))
            return cursor.rowcount > 0

    def guardar_mensaje_chat(self, msg: MensajeChatRegistro) -> int:
        with self.sesion() as conexion:
            cursor = conexion.execute(
                """
                INSERT INTO mensajes_chat (
                    sesion_id, rol, contenido, tokens_prompt, tokens_generados, fuentes_ast_json, fecha
                )
                VALUES (:sesion_id, :rol, :contenido, :tokens_prompt, :tokens_generados, :fuentes_ast_json, :fecha);
                """,
                {
                    "sesion_id": msg.sesion_id,
                    "rol": msg.rol,
                    "contenido": msg.contenido,
                    "tokens_prompt": msg.tokens_prompt,
                    "tokens_generados": msg.tokens_generados,
                    "fuentes_ast_json": msg.fuentes_ast_json,
                    "fecha": msg.fecha,
                },
            )
            # Actualizar fecha de la sesión
            conexion.execute(
                "UPDATE sesiones_chat SET fecha_actualizacion = ? WHERE id = ?;",
                (msg.fecha, msg.sesion_id),
            )
            return cursor.lastrowid or 0

    def obtener_mensajes_sesion(self, sesion_id: str) -> list[dict[str, Any]]:
        with self.sesion() as conexion:
            cursor = conexion.execute(
                "SELECT * FROM mensajes_chat WHERE sesion_id = ? ORDER BY id ASC;",
                (sesion_id,),
            )
            return [dict(fila) for fila in cursor.fetchall()]


if __name__ == "__main__":
    gestor = GestorCache()
    print("=== GUARIDA: GESTOR DE CACHE (SQLITE) ===")
    print(f"Ruta Base de Datos: {gestor.ruta_db}")
    gestor.registrar_modulo_instalado("core")
    print("Modulo 'core' registrado con exito.")
    modulos = gestor.obtener_modulos_instalados()
    print(f"Modulos instalados: {modulos}")

