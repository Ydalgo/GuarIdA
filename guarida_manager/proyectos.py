"""Módulo de Gestión de Proyectos, Indexación de Repositorio y Sesiones de Chat (NotebookLM Local).

Permite crear proyectos locales, adjuntar documentos o escanear repositorios enteros,
construir árboles de nodos AST y fragmentos semánticos, indexar embeddings localmente
y mantener sesiones de chat persistentes con citas de fuentes verificables (RAG local).
"""

import hashlib
import json
import os
import re
import uuid
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
    "brain", "logs", "binarios"
}

EXTENSIONES_SOPORTADAS = {
    ".py", ".md", ".txt", ".rst", ".json", ".yaml", ".yml", ".toml", ".ini",
    ".cfg", ".c", ".cpp", ".h", ".hpp", ".rs", ".go", ".java", ".js", ".ts",
}


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
    max_lineas_chunk: int = 40,
    solapamiento: int = 5,
) -> list[ChunkDocumento]:
    """Divide un archivo de texto o markdown en bloques lógicos respetando encabezados."""
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

        if len(bloque_actual) >= max_lineas_chunk:
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
    ) -> dict[str, Any]:
        """Escanea recursivamente los archivos del proyecto, extrae nodos AST y fragmentos y los indexa."""
        proy = self.obtener_proyecto(proyecto_id)
        if not proy:
            raise ValueError(f"Proyecto '{proyecto_id}' no encontrado.")

        ruta_base = Path(proy["ruta_directorio"])
        if not ruta_base.exists():
            raise FileNotFoundError(f"El directorio del proyecto no existe: {ruta_base}")

        exts = extensiones or EXTENSIONES_SOPORTADAS
        archivos_candidatos: list[Path] = []

        for root, dirs, files in os.walk(ruta_base):
            dirs[:] = [d for d in dirs if d not in DIRECTORIOS_IGNORADOS and not d.startswith(".")]
            for f in files:
                p = Path(root) / f
                if p.suffix.lower() in exts:
                    archivos_candidatos.append(p)

        total_archivos = len(archivos_candidatos)
        if total_archivos == 0:
            return {"total_archivos": 0, "nodos_ast": 0, "chunks_texto": 0, "archivos_procesados": 0}

        arbol = ArbolNodosCodigo()
        chunks_docs: list[ChunkDocumento] = []
        nodos_ast_totales = 0
        chunks_totales = 0
        archivos_procesados = 0

        self.cache.eliminar_documentos_proyecto(proyecto_id)

        for i, archivo in enumerate(archivos_candidatos, start=1):
            pct = (i / total_archivos) * 100.0
            ruta_rel = str(archivo.relative_to(ruta_base))
            if callback_progreso:
                callback_progreso(f"Indexando {ruta_rel}...", pct)

            try:
                contenido = archivo.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            sha256_archivo = hashlib.sha256(contenido.encode("utf-8")).hexdigest()
            tipo_doc = "codigo_python" if archivo.suffix.lower() == ".py" else "documento_texto"
            nodos_en_archivo = 0
            tokens_est = len(contenido) // 4

            if archivo.suffix.lower() == ".py":
                try:
                    arbol.construir_desde_codigo_python(contenido, ruta_archivo=ruta_rel)
                    nodos_en_archivo = len([n for n in arbol.nodos.values() if n.ruta_archivo == ruta_rel])
                    nodos_ast_totales += nodos_en_archivo
                except Exception as e_ast:
                    logger.debug(f"Fallo al parsear AST para {ruta_rel}: {e_ast}")
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

        # Vectorización con embeddings si se provee la función
        embeddings_calculados = 0
        if funcion_embedding:
            if callback_progreso:
                callback_progreso("Calculando embeddings vectoriales de nodos AST...", 90.0)
            embeddings_ast = arbol.indexar_embeddings(funcion_embedding, usar_cache=True)
            embeddings_calculados += embeddings_ast

            # Embeddings para chunks de texto
            for ch in chunks_docs:
                txt = ch.texto_para_vectorizacion()
                try:
                    vec = funcion_embedding(txt)
                    if vec:
                        ch.embedding = vec
                        embeddings_calculados += 1
                except Exception:
                    pass

        self._arboles_codigo[proyecto_id] = arbol
        self._chunks_texto[proyecto_id] = chunks_docs

        resumen = {
            "total_archivos": total_archivos,
            "archivos_procesados": archivos_procesados,
            "nodos_ast": nodos_ast_totales,
            "chunks_texto": chunks_totales,
            "embeddings_calculados": embeddings_calculados,
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
        """Realiza búsqueda híbrida RRF combinando Nodos AST de código y Chunks de documentación."""
        arbol = self._arboles_codigo.get(proyecto_id)
        chunks = self._chunks_texto.get(proyecto_id, [])

        if vector_consulta is None and funcion_embedding is not None:
            try:
                vector_consulta = funcion_embedding(consulta)
            except Exception:
                vector_consulta = None

        fuentes: list[dict[str, Any]] = []
        candidatos_ast: list[tuple[NodoAST, float]] = []

        if arbol and vector_consulta:
            candidatos_ast = arbol.buscar_nodos_relevantes(
                vector_consulta=vector_consulta,
                top_k=top_k,
                consulta_texto=consulta,
            )

        candidatos_chunks: list[tuple[ChunkDocumento, float]] = []
        tokens_q = set(re.findall(r"[a-zA-Z0-9_]{3,}", consulta.lower()))

        for ch in chunks:
            sim = 0.0
            if vector_consulta and ch.embedding:
                sim = similitud_coseno(vector_consulta, ch.embedding)
            # Boost léxico
            boost_lexico = 0.0
            if tokens_q and ch.simbolos:
                solap = len(tokens_q & ch.simbolos)
                if solap > 0:
                    boost_lexico = min(0.30, 0.08 * solap)
            score = min(1.0, sim + boost_lexico)
            if score > 0.15:
                candidatos_chunks.append((ch, round(score, 4)))

        candidatos_chunks.sort(key=lambda x: x[1], reverse=True)
        candidatos_chunks = candidatos_chunks[:top_k]

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
