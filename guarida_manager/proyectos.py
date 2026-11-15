"""Módulo de Gestión de Proyectos, Indexación de Repositorio y Sesiones de Chat (NotebookLM Local).

Permite crear proyectos locales, adjuntar documentos o escanear repositorios enteros,
construir árboles de nodos AST y fragmentos semánticos, indexar embeddings localmente
y mantener sesiones de chat persistentes con citas de fuentes verificables (RAG local).
"""

import hashlib
import json
import os
import re
import time
import uuid
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from guarida_manager.arbol_nodos import (
    ArbolNodosCodigo,
    NodoAST,
    TipoNodoAST,
    minificar_codigo_bpe,
    similitud_coseno,
)
from guarida_manager.cache import (
    DocumentoProyectoRegistro,
    GestorCache,
    MensajeChatRegistro,
    ProyectoRegistro,
    SesionChatRegistro,
)
from guarida_manager.logger import obtener_logger

logger = obtener_logger("proyectos")

DIRECTORIOS_IGNORADOS = {
    ".git", ".svn", ".hg", "__pycache__", ".pytest_cache", ".venv", "venv",
    "env", "node_modules", "dist", "build", ".idea", ".vscode", ".antigravity",
    "brain", "logs", "binarios", ".ssh", ".gnupg", ".aws", ".azure", ".kube",
}

EXTENSIONES_CODIGO_GENERICO = {
    ".c", ".cpp", ".h", ".hpp", ".rs", ".go", ".java", ".js", ".ts", ".tsx", ".jsx",
    ".cs", ".kt", ".swift", ".php", ".rb", ".sh", ".ps1", ".lua",
}

EXTENSIONES_DOCUMENTOS = {".pdf", ".docx", ".odt"}

EXTENSIONES_SOPORTADAS = (
    {".py", ".md", ".txt", ".rst", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg"}
    | EXTENSIONES_CODIGO_GENERICO
    | EXTENSIONES_DOCUMENTOS
)

# Archivos que pueden contener secretos: nunca se indexan (evita que acaben en un prompt).
NOMBRES_SENSIBLES = {
    ".env", ".netrc", ".npmrc", ".pypirc", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519",
    "credentials", "credentials.json", "secrets.json", "secrets.yaml", "secrets.yml",
    "guarida.db",
}
SUFIJOS_SENSIBLES = (".pem", ".key", ".p12", ".pfx", ".jks", ".kdbx", ".db", ".sqlite", ".sqlite3", ".gguf", ".safetensors")
PREFIJOS_SENSIBLES = (".env.",)
TAMANO_MAX_ARCHIVO_BYTES = 1_000_000
TAMANO_MAX_DOCUMENTO_BYTES = 25_000_000
RRF_K = 60
# Los modelos de embeddings no causales exigen que el texto quepa en un solo ubatch (~512 tokens).
LIMITE_CHARS_EMBEDDING = 1800

_RE_DEFINICION_GENERICA = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?(?:public\s+|private\s+|protected\s+|static\s+|pub(?:\([a-z]+\))?\s+)*"
    r"(?:(?:function|class|interface|struct|enum|impl|trait|fn|func|def|type)\b|const\s+\w+\s*=\s*(?:async\s*)?\()",
)


def _estimar_tokens(texto: str) -> int:
    return max(1, len(texto) // 4)


def es_archivo_sensible(ruta: Path) -> bool:
    """True si el nombre del archivo sugiere credenciales, claves o binarios que no deben indexarse."""
    nombre = ruta.name.lower()
    return (
        nombre in NOMBRES_SENSIBLES
        or nombre.endswith(SUFIJOS_SENSIBLES)
        or nombre.startswith(PREFIJOS_SENSIBLES)
    )


def ruta_dentro_de_base(ruta: Path, base: Path) -> bool:
    """True si `ruta` (resuelta, sin seguir fuera de la base) permanece dentro del directorio `base`."""
    try:
        ruta.resolve().relative_to(base.resolve())
        return True
    except (ValueError, OSError):
        return False


def extraer_texto_docx(ruta: Path) -> str:
    """Extrae texto de documentos Microsoft Word (.docx) sin dependencias externas."""
    try:
        with zipfile.ZipFile(ruta, "r") as z:
            if "word/document.xml" not in z.namelist():
                return ""
            xml_content = z.read("word/document.xml")
            root = ET.fromstring(xml_content)
            parrafos = []
            for elem in root.iter():
                if elem.tag.endswith("}p"):
                    textos = [sub.text for sub in elem.iter() if sub.tag.endswith("}t") and sub.text]
                    if textos:
                        parrafos.append("".join(textos))
            return "\n\n".join(parrafos)
    except Exception as e:
        logger.warning(f"Error al extraer texto DOCX de {ruta}: {e}")
        return ""


def extraer_texto_odt(ruta: Path) -> str:
    """Extrae texto de documentos OpenDocument (.odt) sin dependencias externas."""
    try:
        with zipfile.ZipFile(ruta, "r") as z:
            if "content.xml" not in z.namelist():
                return ""
            xml_content = z.read("content.xml")
            root = ET.fromstring(xml_content)
            parrafos = []
            for elem in root.iter():
                if elem.tag.endswith(("}p", "}h")):
                    txt = "".join(elem.itertext()).strip()
                    if txt:
                        parrafos.append(txt)
            return "\n\n".join(parrafos)
    except Exception as e:
        logger.warning(f"Error al extraer texto ODT de {ruta}: {e}")
        return ""


def extraer_texto_pdf(ruta: Path) -> str:
    """Extrae texto estructurado por páginas de un archivo PDF usando pypdf."""
    try:
        import pypdf
        reader = pypdf.PdfReader(str(ruta))
        paginas_texto = []
        for idx, page in enumerate(reader.pages, start=1):
            txt = page.extract_text() or ""
            txt = txt.strip()
            if txt:
                paginas_texto.append(f"# Página {idx}\n{txt}")
        return "\n\n".join(paginas_texto)
    except Exception as e:
        logger.warning(f"Error al extraer texto PDF de {ruta}: {e}")
        return ""


def extraer_contenido_archivo(ruta: Path) -> str:
    """Extrae el contenido textual según la extensión (código, texto plano u ofimática)."""
    sufijo = ruta.suffix.lower()
    if sufijo == ".pdf":
        return extraer_texto_pdf(ruta)
    if sufijo == ".docx":
        return extraer_texto_docx(ruta)
    if sufijo == ".odt":
        return extraer_texto_odt(ruta)
    return ruta.read_text(encoding="utf-8", errors="replace")


@dataclass
class ChunkDocumento:
    """Fragmento de texto semántico para documentos planos o markdown."""
    id_chunk: str
    ruta_archivo: str
    seccion: str
    linea_inicio: int
    linea_fin: int
    texto: str
    embedding: Optional[list[float]] = None
    simbolos: set[str] = field(default_factory=set)

    def texto_para_vectorizacion(self) -> str:
        partes = [
            f"Archivo: {self.ruta_archivo}",
            f"Sección: {self.seccion}",
            f"Líneas: {self.linea_inicio}-{self.linea_fin}",
            f"Contenido:\n{self.texto}",
        ]
        return "\n".join(partes)


def fragmentar_documento_texto(
    ruta_archivo: str,
    contenido: str,
    max_tokens_chunk: int = 256,
    solapamiento: int = 5,
) -> list[ChunkDocumento]:
    """Divide un archivo de texto o markdown en bloques de ~`max_tokens_chunk` tokens respetando encabezados."""
    lineas = contenido.splitlines()
    if not lineas:
        return []

    chunks: list[ChunkDocumento] = []
    bloque_actual: list[str] = []
    linea_inicio_bloque = 1
    seccion_actual = "General"

    for idx, linea in enumerate(lineas, start=1):
        strip_l = linea.strip()
        # Detección de encabezados markdown (# Titulo)
        if strip_l.startswith("#"):
            if bloque_actual:
                txt = "\n".join(bloque_actual).strip()
                if txt:
                    simbolos = set(re.findall(r"[a-zA-Z0-9_]{3,}", txt.lower()))
                    chunks.append(
                        ChunkDocumento(
                            id_chunk=f"{ruta_archivo}:{linea_inicio_bloque}",
                            ruta_archivo=ruta_archivo,
                            seccion=seccion_actual,
                            linea_inicio=linea_inicio_bloque,
                            linea_fin=idx - 1,
                            texto=txt,
                            simbolos=simbolos,
                        )
                    )
                bloque_actual = []
            seccion_actual = strip_l.lstrip("#").strip()
            linea_inicio_bloque = idx

        bloque_actual.append(linea)

        if len(bloque_actual) > solapamiento and _estimar_tokens("\n".join(bloque_actual)) >= max_tokens_chunk:
            txt = "\n".join(bloque_actual).strip()
            if txt:
                simbolos = set(re.findall(r"[a-zA-Z0-9_]{3,}", txt.lower()))
                chunks.append(
                    ChunkDocumento(
                        id_chunk=f"{ruta_archivo}:{linea_inicio_bloque}",
                        ruta_archivo=ruta_archivo,
                        seccion=seccion_actual,
                        linea_inicio=linea_inicio_bloque,
                        linea_fin=idx,
                        texto=txt,
                        simbolos=simbolos,
                    )
                )
            # Mantener solapamiento
            bloque_actual = bloque_actual[-solapamiento:]
            linea_inicio_bloque = max(1, idx - solapamiento + 1)

    if bloque_actual:
        txt = "\n".join(bloque_actual).strip()
        if txt:
            simbolos = set(re.findall(r"[a-zA-Z0-9_]{3,}", txt.lower()))
            chunks.append(
                ChunkDocumento(
                    id_chunk=f"{ruta_archivo}:{linea_inicio_bloque}",
                    ruta_archivo=ruta_archivo,
                    seccion=seccion_actual,
                    linea_inicio=linea_inicio_bloque,
                    linea_fin=len(lineas),
                    texto=txt,
                    simbolos=simbolos,
                )
            )

    return chunks


def fragmentar_codigo_generico(
    ruta_archivo: str,
    contenido: str,
    max_tokens_chunk: int = 320,
) -> list[ChunkDocumento]:
    """Fragmenta código no Python en bloques que empiezan en cada definición (function/class/fn/func/...)."""
    lineas = contenido.splitlines()
    if not lineas:
        return []

    chunks: list[ChunkDocumento] = []
    inicio = 1
    nombre = "cabecera"
    bloque: list[str] = []

    def _volcar(fin: int) -> None:
        txt = "\n".join(bloque).strip()
        if txt:
            chunks.append(
                ChunkDocumento(
                    id_chunk=f"{ruta_archivo}:{inicio}",
                    ruta_archivo=ruta_archivo,
                    seccion=nombre,
                    linea_inicio=inicio,
                    linea_fin=fin,
                    texto=txt,
                    simbolos=set(re.findall(r"[a-zA-Z0-9_]{3,}", txt.lower())),
                )
            )

    for idx, linea in enumerate(lineas, start=1):
        es_def = bool(_RE_DEFINICION_GENERICA.match(linea)) and not linea.startswith((" ", "\t", "}"))
        desborda = bloque and _estimar_tokens("\n".join(bloque)) >= max_tokens_chunk
        if bloque and (es_def or desborda):
            _volcar(idx - 1)
            bloque = []
            inicio = idx
            if es_def:
                nombre = linea.strip()[:80]
        elif es_def and not bloque:
            nombre = linea.strip()[:80]
        bloque.append(linea)

    _volcar(len(lineas))
    return chunks


class GestorProyectos:
    """Controlador principal de proyectos, indexación local de código/documentos y RAG offline."""

    def __init__(self, gestor_cache: Optional[GestorCache] = None) -> None:
        self.cache = gestor_cache or GestorCache()
        # Árboles AST cargados en memoria por proyecto {proyecto_id: ArbolNodosCodigo}
        self._arboles_codigo: dict[str, ArbolNodosCodigo] = {}
        # Chunks de documentos texto por proyecto {proyecto_id: list[ChunkDocumento]}
        self._chunks_texto: dict[str, list[ChunkDocumento]] = {}

    def crear_proyecto(
        self,
        nombre: str,
        ruta_directorio: Path | str,
        descripcion: str = "",
        proyecto_id: Optional[str] = None,
    ) -> ProyectoRegistro:
        ruta = Path(ruta_directorio).resolve()
        p_id = proyecto_id or str(uuid.uuid4())[:8]
        fecha = datetime.now(timezone.utc).isoformat()
        reg = ProyectoRegistro(
            id=p_id,
            nombre=nombre.strip(),
            descripcion=descripcion.strip(),
            ruta_directorio=str(ruta),
            fecha_creacion=fecha,
        )
        self.cache.guardar_proyecto(reg)
        logger.info(f"Proyecto '{nombre}' [{p_id}] registrado en {ruta}")
        return reg

    def listar_proyectos(self) -> list[dict[str, Any]]:
        return self.cache.listar_proyectos()

    def obtener_proyecto(self, proyecto_id: str) -> Optional[dict[str, Any]]:
        return self.cache.obtener_proyecto(proyecto_id)

    def eliminar_proyecto(self, proyecto_id: str) -> bool:
        self._arboles_codigo.pop(proyecto_id, None)
        self._chunks_texto.pop(proyecto_id, None)
        return self.cache.eliminar_proyecto(proyecto_id)

    def escanear_e_indexar_proyecto(
        self,
        proyecto_id: str,
        funcion_embedding: Optional[Callable[[str], list[float]]] = None,
        extensiones: Optional[set[str]] = None,
        callback_progreso: Optional[Callable[[str, float], None]] = None,
        modelo_emb_id: str = "",
    ) -> dict[str, Any]:
        """Escanea el proyecto, extrae nodos AST/fragmentos y los indexa de forma incremental.

        Los embeddings se persisten en SQLite (clave = modelo + SHA-256 del texto), de modo que una
        reindexación solo vectoriza los nodos/fragmentos nuevos o modificados.
        """
        proy = self.obtener_proyecto(proyecto_id)
        if not proy:
            raise ValueError(f"Proyecto '{proyecto_id}' no encontrado.")

        ruta_base = Path(proy["ruta_directorio"])
        if not ruta_base.exists():
            raise FileNotFoundError(f"El directorio del proyecto no existe: {ruta_base}")

        exts = extensiones or EXTENSIONES_SOPORTADAS
        archivos_candidatos: list[Path] = []
        omitidos_seguridad = 0

        for root, dirs, files in os.walk(ruta_base, followlinks=False):
            dirs[:] = [
                d for d in dirs
                if d not in DIRECTORIOS_IGNORADOS
                and not d.startswith(".")
                and not (Path(root) / d).is_symlink()
            ]
            for f in files:
                p = Path(root) / f
                try:
                    if (
                        es_archivo_sensible(p)
                        or p.is_symlink()
                        or not ruta_dentro_de_base(p, ruta_base)
                    ):
                        omitidos_seguridad += 1
                        continue
                    if p.suffix.lower() not in exts:
                        continue
                    limite_bytes = (
                        TAMANO_MAX_DOCUMENTO_BYTES
                        if p.suffix.lower() in EXTENSIONES_DOCUMENTOS
                        else TAMANO_MAX_ARCHIVO_BYTES
                    )
                    if p.stat().st_size > limite_bytes:
                        omitidos_seguridad += 1
                        continue
                except OSError:
                    omitidos_seguridad += 1
                    continue
                archivos_candidatos.append(p)

        total_archivos = len(archivos_candidatos)
        if total_archivos == 0:
            return {
                "total_archivos": 0, "nodos_ast": 0, "chunks_texto": 0, "archivos_procesados": 0,
                "archivos_sin_cambios": 0, "omitidos_seguridad": omitidos_seguridad,
            }

        arbol = ArbolNodosCodigo()
        chunks_docs: list[ChunkDocumento] = []
        nodos_ast_totales = 0
        chunks_totales = 0
        archivos_procesados = 0
        archivos_sin_cambios = 0

        hashes_previos = self.cache.obtener_documentos_hash(proyecto_id)
        self.cache.eliminar_documentos_proyecto(proyecto_id)

        for i, archivo in enumerate(archivos_candidatos, start=1):
            pct = (i / total_archivos) * (30.0 if funcion_embedding else 100.0)
            ruta_rel = str(archivo.relative_to(ruta_base))
            faltan = total_archivos - i
            if callback_progreso:
                callback_progreso(
                    f"Fichero {i}/{total_archivos}: {ruta_rel} (faltan {faltan} archivos)",
                    pct,
                )

            try:
                contenido = extraer_contenido_archivo(archivo)
            except Exception:
                continue

            sha256_archivo = hashlib.sha256(contenido.encode("utf-8")).hexdigest()
            if hashes_previos.get(ruta_rel) == sha256_archivo:
                archivos_sin_cambios += 1
            sufijo = archivo.suffix.lower()
            if sufijo == ".py":
                tipo_doc = "codigo_python"
            elif sufijo in EXTENSIONES_CODIGO_GENERICO:
                tipo_doc = "codigo_generico"
            elif sufijo in EXTENSIONES_DOCUMENTOS:
                tipo_doc = "documento_ofimatico"
            else:
                tipo_doc = "documento_texto"
            nodos_en_archivo = 0
            tokens_est = len(contenido) // 4

            if sufijo == ".py":
                try:
                    arbol.construir_desde_codigo_python(contenido, ruta_archivo=ruta_rel)
                    nodos_en_archivo = len([n for n in arbol.nodos.values() if n.ruta_archivo == ruta_rel])
                    nodos_ast_totales += nodos_en_archivo
                except Exception as e_ast:
                    logger.debug(f"Fallo al parsear AST para {ruta_rel}: {e_ast}")
            else:
                if tipo_doc == "codigo_generico":
                    chunks_arch = fragmentar_codigo_generico(ruta_rel, contenido)
                else:
                    chunks_arch = fragmentar_documento_texto(ruta_rel, contenido)
                chunks_docs.extend(chunks_arch)
                chunks_totales += len(chunks_arch)
                nodos_en_archivo = len(chunks_arch)

            doc_reg = DocumentoProyectoRegistro(
                id=None,
                proyecto_id=proyecto_id,
                ruta_relativa=ruta_rel,
                ruta_absoluta=str(archivo),
                tipo_documento=tipo_doc,
                sha256=sha256_archivo,
                nodos_ast_count=nodos_en_archivo,
                n_tokens_est=tokens_est,
                fecha_indexacion=datetime.now(timezone.utc).isoformat(),
            )
            self.cache.guardar_documento_proyecto(doc_reg)
            archivos_procesados += 1

        # Vectorización incremental: caché persistente en SQLite por (modelo + SHA-256 del texto)
        embeddings_calculados = 0
        embeddings_reutilizados = 0
        errores_embedding = 0
        if funcion_embedding:
            total_chunks = len(chunks_docs)
            t_inicio_vec = time.perf_counter()

            if callback_progreso:
                callback_progreso(
                    f"Iniciando vectorización de {total_chunks} fragmentos...",
                    30.0,
                )

            def _vectorizar(txt: str) -> list[float]:
                nonlocal embeddings_calculados, embeddings_reutilizados
                clave = hashlib.sha256(f"{modelo_emb_id}\x00{txt}".encode("utf-8")).hexdigest()
                previo = self.cache.obtener_embedding(clave)
                if previo:
                    embeddings_reutilizados += 1
                    return previo
                vec = funcion_embedding(txt[:LIMITE_CHARS_EMBEDDING])
                if vec:
                    self.cache.guardar_embedding(clave, modelo_emb_id or "desconocido", vec)
                    embeddings_calculados += 1
                return vec

            arbol.indexar_embeddings(_vectorizar, usar_cache=False)
            errores_embedding += sum(1 for n in arbol.nodos.values() if not n.embedding)

            for idx_ch, ch in enumerate(chunks_docs, start=1):
                try:
                    vec = _vectorizar(ch.texto_para_vectorizacion())
                    if vec:
                        ch.embedding = vec
                except Exception as e_emb:
                    errores_embedding += 1
                    logger.warning(f"Fallo de embedding en {ch.id_chunk}: {e_emb}")

                if callback_progreso and (idx_ch % 10 == 0 or idx_ch == 1 or idx_ch == total_chunks):
                    pct_vec = 30.0 + (idx_ch / max(1, total_chunks)) * 70.0
                    t_trans = time.perf_counter() - t_inicio_vec
                    ch_por_seg = idx_ch / max(0.001, t_trans)
                    restantes = total_chunks - idx_ch
                    seg_est = restantes / max(0.01, ch_por_seg)
                    eta_str = f"{int(seg_est)}s" if seg_est < 60 else f"{int(seg_est // 60)}m {int(seg_est % 60)}s"
                    callback_progreso(
                        f"Fragmento {idx_ch}/{total_chunks} ({ch.ruta_archivo}) | "
                        f"Nuevos: {embeddings_calculados}, Caché: {embeddings_reutilizados} | "
                        f"Faltan {restantes} (~{eta_str} restantes)...",
                        pct_vec,
                    )

        self._arboles_codigo[proyecto_id] = arbol
        self._chunks_texto[proyecto_id] = chunks_docs

        resumen = {
            "total_archivos": total_archivos,
            "archivos_procesados": archivos_procesados,
            "archivos_sin_cambios": archivos_sin_cambios,
            "omitidos_seguridad": omitidos_seguridad,
            "nodos_ast": nodos_ast_totales,
            "chunks_texto": chunks_totales,
            "embeddings_calculados": embeddings_calculados,
            "embeddings_reutilizados": embeddings_reutilizados,
            "errores_embedding": errores_embedding,
        }
        logger.info(f"Indexación completada para proyecto '{proyecto_id}': {resumen}")
        return resumen

    def buscar_contexto_hibrido(
        self,
        proyecto_id: str,
        consulta: str,
        vector_consulta: Optional[list[float]] = None,
        top_k: int = 5,
        funcion_embedding: Optional[Callable[[str], list[float]]] = None,
    ) -> tuple[str, list[dict[str, Any]]]:
        """Búsqueda híbrida con Reciprocal Rank Fusion real (ranking denso + ranking léxico) sobre AST y documentos.

        Funciona también sin embeddings (solo ranking léxico) cuando el servidor vectorial no está disponible.
        """
        arbol = self._arboles_codigo.get(proyecto_id)
        chunks = self._chunks_texto.get(proyecto_id, [])

        if vector_consulta is None and funcion_embedding is not None:
            try:
                vector_consulta = funcion_embedding(consulta[:LIMITE_CHARS_EMBEDDING])
            except Exception as e_q:
                logger.warning(f"No se pudo vectorizar la consulta; se usa solo ranking léxico: {e_q}")
                vector_consulta = None

        fuentes: list[dict[str, Any]] = []
        tokens_q = set(re.findall(r"[a-zA-Z0-9_]{3,}", consulta.lower()))
        consulta_min = consulta.lower()

        # Elementos unificados: (objeto, simbolos léxicos, embedding)
        elementos: list[tuple[Any, set[str], Optional[list[float]]]] = []
        if arbol:
            for nodo in arbol.nodos.values():
                if nodo.tipo == TipoNodoAST.MODULO:
                    continue
                lex = set(nodo.simbolos) | set(nodo.nombre.lower().split("_"))
                if nodo.nombre.lower() in consulta_min:
                    lex.add("__nombre_exacto__")
                elementos.append((nodo, lex, nodo.embedding))
        for ch in chunks:
            elementos.append((ch, ch.simbolos, ch.embedding))

        ranking_denso: list[int] = []
        if vector_consulta:
            sims = [
                (i, similitud_coseno(vector_consulta, emb))
                for i, (_, _, emb) in enumerate(elementos)
                if emb
            ]
            ranking_denso = [i for i, s in sorted(sims, key=lambda x: x[1], reverse=True) if s > 0.0]

        lexicos: list[tuple[int, float]] = []
        for i, (_, lex, _) in enumerate(elementos):
            puntos = float(len(tokens_q & lex))
            if "__nombre_exacto__" in lex:
                puntos += 3.0
            if puntos > 0:
                lexicos.append((i, puntos))
        ranking_lexico = [i for i, _ in sorted(lexicos, key=lambda x: x[1], reverse=True)]

        puntuacion_rrf: dict[int, float] = {}
        for ranking in (ranking_denso, ranking_lexico):
            for pos, idx in enumerate(ranking, start=1):
                puntuacion_rrf[idx] = puntuacion_rrf.get(idx, 0.0) + 1.0 / (RRF_K + pos)

        maximo_teorico = 2.0 / (RRF_K + 1)
        mejores = sorted(puntuacion_rrf.items(), key=lambda x: x[1], reverse=True)[:top_k]

        candidatos_ast: list[tuple[NodoAST, float]] = []
        candidatos_chunks: list[tuple[ChunkDocumento, float]] = []
        for idx, punt in mejores:
            relevancia = round(min(1.0, punt / maximo_teorico), 4)
            obj = elementos[idx][0]
            if isinstance(obj, NodoAST):
                candidatos_ast.append((obj, relevancia))
            else:
                candidatos_chunks.append((obj, relevancia))

        bloques_contexto: list[str] = []

        # Formatear contexto de código AST
        if candidatos_ast:
            bloques_contexto.append("=== FRAGMENTOS DE CÓDIGO (ÁRBOL AST) ===")
            for nodo, score in candidatos_ast:
                fuentes.append({
                    "tipo": "ast_nodo",
                    "archivo": nodo.ruta_archivo,
                    "lineas": f"{nodo.linea_inicio}-{nodo.linea_fin}",
                    "nombre": nodo.nombre,
                    "relevancia": score,
                })
                codigo_comp = minificar_codigo_bpe(nodo.codigo)
                bloques_contexto.append(
                    f"[Fuente: {nodo.ruta_archivo}:{nodo.linea_inicio}-{nodo.linea_fin} ({nodo.tipo.value} {nodo.nombre}, Relevancia: {score:.2f})]\n"
                    f"{codigo_comp}"
                )

        # Formatear contexto de documentación
        if candidatos_chunks:
            bloques_contexto.append("\n=== DOCUMENTOS Y ESPECIFICACIONES ===")
            for ch, score in candidatos_chunks:
                fuentes.append({
                    "tipo": "documento_chunk",
                    "archivo": ch.ruta_archivo,
                    "lineas": f"{ch.linea_inicio}-{ch.linea_fin}",
                    "seccion": ch.seccion,
                    "relevancia": score,
                })
                bloques_contexto.append(
                    f"[Fuente: {ch.ruta_archivo}:{ch.linea_inicio}-{ch.linea_fin} (Sección: {ch.seccion}, Relevancia: {score:.2f})]\n"
                    f"{ch.texto}"
                )

        contexto_final = "\n\n".join(bloques_contexto)
        return contexto_final, fuentes

    # --- Sesiones de Chat ---

    def crear_sesion(
        self,
        modelo_id: str,
        titulo: str = "",
        proyecto_id: Optional[str] = None,
    ) -> SesionChatRegistro:
        s_id = str(uuid.uuid4())[:8]
        fecha = datetime.now(timezone.utc).isoformat()
        tit = titulo.strip() or f"Sesión {s_id} ({modelo_id})"
        reg = SesionChatRegistro(
            id=s_id,
            proyecto_id=proyecto_id,
            modelo_id=modelo_id,
            titulo=tit,
            fecha_creacion=fecha,
            fecha_actualizacion=fecha,
        )
        self.cache.guardar_sesion_chat(reg)
        return reg

    def listar_sesiones(self, proyecto_id: Optional[str] = None) -> list[dict[str, Any]]:
        return self.cache.listar_sesiones_chat(proyecto_id=proyecto_id)

    def obtener_sesion(self, sesion_id: str) -> Optional[dict[str, Any]]:
        return self.cache.obtener_sesion_chat(sesion_id)

    def registrar_mensaje(
        self,
        sesion_id: str,
        rol: str,
        contenido: str,
        fuentes: Optional[list[dict[str, Any]]] = None,
        tokens_prompt: int = 0,
        tokens_generados: int = 0,
    ) -> int:
        fecha = datetime.now(timezone.utc).isoformat()
        fuentes_json = json.dumps(fuentes, ensure_ascii=False) if fuentes else None
        msg = MensajeChatRegistro(
            id=None,
            sesion_id=sesion_id,
            rol=rol,
            contenido=contenido,
            tokens_prompt=tokens_prompt,
            tokens_generados=tokens_generados,
            fuentes_ast_json=fuentes_json,
            fecha=fecha,
        )
        return self.cache.guardar_mensaje_chat(msg)

    def obtener_historial_sesion(self, sesion_id: str) -> list[dict[str, Any]]:
        return self.cache.obtener_mensajes_sesion(sesion_id)
