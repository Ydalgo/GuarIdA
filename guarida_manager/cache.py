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
                    fecha_afinamiento, motivo_descarte_o_nota, es_recomendada
                )
                VALUES (
                    :modelo_id, :hash_hardware, :n_gpu_layers, :ctx_size,
                    :batch_size, :kv_cache_tipo, :tok_s_medido, :gtt_pico_mb,
                    :fecha_afinamiento, :motivo_descarte_o_nota, :es_recomendada
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
                    es_recomendada = excluded.es_recomendada;
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
                },
            )

    def obtener_configuracion_optima(
        self, modelo_id: str, hash_hardware: str
    ) -> Optional[dict[str, Any]]:
        with self.sesion() as conexion:
            cursor = conexion.execute(
                """
                SELECT * FROM configuraciones_optimas
                WHERE modelo_id = ? AND hash_hardware = ?;
                """,
                (modelo_id, hash_hardware),
            )
            fila = cursor.fetchone()
            if fila:
                resultado = dict(fila)
                resultado["es_recomendada"] = bool(resultado["es_recomendada"])
                return resultado
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


if __name__ == "__main__":
    gestor = GestorCache()
    print("=== GUARIDA: GESTOR DE CACHE (SQLITE) ===")
    print(f"Ruta Base de Datos: {gestor.ruta_db}")
    gestor.registrar_modulo_instalado("core")
    print("Modulo 'core' registrado con exito.")
    modulos = gestor.obtener_modulos_instalados()
    print(f"Modulos instalados: {modulos}")

