import ast
import hashlib
import math
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from guarida_manager.roles import MensajeInterModelo, RolAgente

# Caché en memoria de vectores indexada por SHA-256 del texto canónico del nodo
_CACHE_EMBEDDINGS_AST: dict[str, list[float]] = {}


def minificar_codigo_bpe(codigo: str) -> str:
    """Comprime código Python para tokenizadores BPE: elimina docstrings/comentarios, compacta operadores y usa tabs."""
    lineas_salida: list[str] = []
    en_docstring = False
    delim_doc = ""

    for linea in codigo.splitlines():
        strip_l = linea.strip()
        if not strip_l:
            continue

        if en_docstring:
            if delim_doc in strip_l:
                en_docstring = False
            continue

        if strip_l.startswith(("'''", '"""')):
            delim_doc = strip_l[:3]
            contenido_doc = strip_l[3:]
            if contenido_doc.endswith(delim_doc) and len(strip_l) > 6:
                resumen = contenido_doc[:-3].strip()
                if resumen:
                    espacios = len(linea) - len(linea.lstrip(" "))
                    tabs = "\t" * (espacios // 4)
                    lineas_salida.append(f"{tabs}# {resumen}")
                continue
            en_docstring = True
            resumen_ini = contenido_doc.strip()
            if resumen_ini:
                espacios = len(linea) - len(linea.lstrip(" "))
                tabs = "\t" * (espacios // 4)
                lineas_salida.append(f"{tabs}# {resumen_ini}")
            continue

        if strip_l.startswith("#"):
            continue

        # Compactar espacios alrededor de operadores comunes fuera de literales para ahorrar tokens BPE
        if '"' not in strip_l and "'" not in strip_l:
            strip_l = re.sub(r"\s*([=,+*/<>!]+|->)\s*", r"\1", strip_l)
            strip_l = re.sub(r":\s+", ":", strip_l)

        espacios = len(linea) - len(linea.lstrip(" "))
        tabs = "\t" * (espacios // 4)
        lineas_salida.append(f"{tabs}{strip_l}")

    return "\n".join(lineas_salida)


def _extraer_simbolos_nodo_ast(nodo_ast: ast.AST) -> set[str]:
    """Extrae identificadores léxicos (nombres, atributos, argumentos y constantes) de un subárbol AST."""
    simbolos: set[str] = set()
    for sub in ast.walk(nodo_ast):
        if isinstance(sub, ast.Name):
            simbolos.add(sub.id.lower())
        elif isinstance(sub, ast.Attribute):
            simbolos.add(sub.attr.lower())
        elif isinstance(sub, ast.arg):
            simbolos.add(sub.arg.lower())
        elif isinstance(sub, ast.Constant) and isinstance(sub.value, (str, int)):
            val_str = str(sub.value).strip().lower()
            if 1 <= len(val_str) <= 32 and " " not in val_str:
                simbolos.add(val_str)
    return simbolos


class TipoNodoAST(str, Enum):
    MODULO = "modulo"
    CLASE = "clase"
    FUNCION = "funcion"
    METODO = "metodo"
    BLOQUE = "bloque"


@dataclass
class NodoAST:
    """Nodo sintáctico del árbol de código con soporte para embeddings vectoriales."""

    id_nodo: str
    tipo: TipoNodoAST
    nombre: str
    ruta_archivo: str
    linea_inicio: int
    linea_fin: int
    codigo: str
    docstring: str = ""
    resumen_sintactico: str = ""
    padre_id: Optional[str] = None
    hijos_ids: list[str] = field(default_factory=list)
    embedding: Optional[list[float]] = None
    simbolos: set[str] = field(default_factory=set)

    def texto_para_vectorizacion(self) -> str:
        """Genera una representación canónica del nodo optimizada para el modelo de embeddings."""
        partes = [
            f"Tipo: {self.tipo.value}",
            f"Nombre: {self.nombre}",
            f"Ubicación: {self.ruta_archivo}:{self.linea_inicio}-{self.linea_fin}",
        ]
        if self.docstring:
            partes.append(f"Docstring: {self.docstring}")
        if self.resumen_sintactico:
            partes.append(f"Firma/Resumen: {self.resumen_sintactico}")
        if self.tipo in (TipoNodoAST.FUNCION, TipoNodoAST.METODO, TipoNodoAST.BLOQUE):
            partes.append(f"Código:\n{self.codigo}")
        return "\n".join(partes)


def similitud_coseno(v1: list[float], v2: list[float]) -> float:
    """Calcula la similitud de coseno entre dos vectores numéricos sin dependencias externas."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0

    dot = sum(a * b for a, b in zip(v1, v2))
    norm_a = math.sqrt(sum(a * a for a in v1))
    norm_b = math.sqrt(sum(b * b for b in v2))

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    return max(-1.0, min(1.0, dot / (norm_a * norm_b)))


class ArbolNodosCodigo:
    """Estructura de árbol de nodos para indexación jerárquica y navegación semántica en AST."""

    def __init__(self, ruta_raiz: str = "proyecto"):
        self.ruta_raiz = ruta_raiz
        self.nodos: dict[str, NodoAST] = {}

    def agregar_nodo(self, nodo: NodoAST) -> None:
        """Registra un nodo en el árbol y mantiene la coherencia de enlaces padre-hijo."""
        self.nodos[nodo.id_nodo] = nodo
        if nodo.padre_id and nodo.padre_id in self.nodos:
            padre = self.nodos[nodo.padre_id]
            if nodo.id_nodo not in padre.hijos_ids:
                padre.hijos_ids.append(nodo.id_nodo)

    def obtener_nodo(self, id_nodo: str) -> Optional[NodoAST]:
        return self.nodos.get(id_nodo)

    def construir_desde_codigo_python(self, codigo_fuente: str, ruta_archivo: str = "modulo.py") -> None:
        """Parsea código Python en un árbol de nodos AST jerárquico."""
        try:
            arbol_ast = ast.parse(codigo_fuente, filename=ruta_archivo)
        except SyntaxError:
            # Si el código tiene errores sintácticos, crear un único nodo de bloque
            nodo_error = NodoAST(
                id_nodo=f"{ruta_archivo}::raiz",
                tipo=TipoNodoAST.MODULO,
                nombre=ruta_archivo,
                ruta_archivo=ruta_archivo,
                linea_inicio=1,
                linea_fin=len(codigo_fuente.splitlines()),
                codigo=codigo_fuente,
                docstring="Error de sintaxis al parsear AST",
            )
            self.agregar_nodo(nodo_error)
            return

        lineas_codigo = codigo_fuente.splitlines()

        id_raiz = f"{ruta_archivo}::raiz"
        docstring_modulo = ast.get_docstring(arbol_ast) or ""
        nodo_raiz = NodoAST(
            id_nodo=id_raiz,
            tipo=TipoNodoAST.MODULO,
            nombre=ruta_archivo,
            ruta_archivo=ruta_archivo,
            linea_inicio=1,
            linea_fin=len(lineas_codigo) if lineas_codigo else 1,
            codigo=codigo_fuente,
            docstring=docstring_modulo,
            resumen_sintactico=f"Módulo Python: {ruta_archivo}",
        )
        self.agregar_nodo(nodo_raiz)

        def _obtener_fragmento(linea_ini: int, linea_f: int) -> str:
            return "\n".join(lineas_codigo[max(0, linea_ini - 1) : linea_f])

        for elem in arbol_ast.body:
            if isinstance(elem, ast.ClassDef):
                id_clase = f"{id_raiz}::clase::{elem.name}"
                doc_clase = ast.get_docstring(elem) or ""
                bases = [ast.unparse(b) for b in elem.bases] if hasattr(ast, "unparse") else []
                resumen_clase = f"class {elem.name}({', '.join(bases)})"
                nodo_clase = NodoAST(
                    id_nodo=id_clase,
                    tipo=TipoNodoAST.CLASE,
                    nombre=elem.name,
                    ruta_archivo=ruta_archivo,
                    linea_inicio=elem.lineno,
                    linea_fin=elem.end_lineno or elem.lineno,
                    codigo=_obtener_fragmento(elem.lineno, elem.end_lineno or elem.lineno),
                    docstring=doc_clase,
                    resumen_sintactico=resumen_clase,
                    padre_id=id_raiz,
                    simbolos={elem.name.lower()} | _extraer_simbolos_nodo_ast(elem),
                )
                self.agregar_nodo(nodo_clase)

                # Métodos de la clase
                for sub in elem.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        id_metodo = f"{id_clase}::metodo::{sub.name}"
                        doc_metodo = ast.get_docstring(sub) or ""
                        args_str = ", ".join(a.arg for a in sub.args.args)
                        nodo_metodo = NodoAST(
                            id_nodo=id_metodo,
                            tipo=TipoNodoAST.METODO,
                            nombre=sub.name,
                            ruta_archivo=ruta_archivo,
                            linea_inicio=sub.lineno,
                            linea_fin=sub.end_lineno or sub.lineno,
                            codigo=_obtener_fragmento(sub.lineno, sub.end_lineno or sub.lineno),
                            docstring=doc_metodo,
                            resumen_sintactico=f"def {sub.name}({args_str})",
                            padre_id=id_clase,
                            simbolos={sub.name.lower()} | _extraer_simbolos_nodo_ast(sub),
                        )
                        self.agregar_nodo(nodo_metodo)

            elif isinstance(elem, (ast.FunctionDef, ast.AsyncFunctionDef)):
                id_func = f"{id_raiz}::funcion::{elem.name}"
                doc_func = ast.get_docstring(elem) or ""
                args_str = ", ".join(a.arg for a in elem.args.args)
                nodo_func = NodoAST(
                    id_nodo=id_func,
                    tipo=TipoNodoAST.FUNCION,
                    nombre=elem.name,
                    ruta_archivo=ruta_archivo,
                    linea_inicio=elem.lineno,
                    linea_fin=elem.end_lineno or elem.lineno,
                    codigo=_obtener_fragmento(elem.lineno, elem.end_lineno or elem.lineno),
                    docstring=doc_func,
                    resumen_sintactico=f"def {elem.name}({args_str})",
                    padre_id=id_raiz,
                    simbolos={elem.name.lower()} | _extraer_simbolos_nodo_ast(elem),
                )
                self.agregar_nodo(nodo_func)

    def indexar_embeddings(
        self,
        funcion_calcular_embedding: Callable[[str], list[float]],
        usar_cache: bool = True,
    ) -> int:
        """Calcula y almacena el vector de embedding para cada nodo usando caché SHA-256."""
        nodos_indexados = 0
        for nodo in self.nodos.values():
            texto = nodo.texto_para_vectorizacion()
            hash_texto = hashlib.sha256(texto.encode("utf-8")).hexdigest()
            if usar_cache and hash_texto in _CACHE_EMBEDDINGS_AST:
                nodo.embedding = _CACHE_EMBEDDINGS_AST[hash_texto]
                nodos_indexados += 1
                continue
            try:
                vector = funcion_calcular_embedding(texto)
                if vector:
                    nodo.embedding = vector
                    if usar_cache:
                        _CACHE_EMBEDDINGS_AST[hash_texto] = vector
                    nodos_indexados += 1
            except Exception:
                pass
        return nodos_indexados

    def buscar_nodos_relevantes(
        self,
        vector_consulta: list[float],
        top_k: int = 3,
        umbral_similitud: float = 0.0,
        excluir_modulos: bool = True,
        consulta_texto: str = "",
    ) -> list[tuple[NodoAST, float]]:
        """Recupera los nodos mediante fusión híbrida RRF (similitud de coseno + coincidencia léxica AST)."""
        candidatos: list[tuple[NodoAST, float]] = []
        tokens_q = set(re.findall(r"[a-zA-Z0-9_]{2,}", consulta_texto.lower())) if consulta_texto else set()

        for nodo in self.nodos.values():
            if excluir_modulos and nodo.tipo == TipoNodoAST.MODULO:
                continue
            if nodo.embedding:
                sim = similitud_coseno(vector_consulta, nodo.embedding)
                boost_lexico = 0.0
                if tokens_q:
                    if nodo.nombre.lower() in consulta_texto.lower():
                        boost_lexico += 0.30
                    solapamiento = len(tokens_q & nodo.simbolos)
                    if solapamiento > 0:
                        boost_lexico += min(0.25, 0.08 * solapamiento)
                score_final = min(1.0, sim + boost_lexico) if sim >= umbral_similitud else sim
                if score_final >= umbral_similitud:
                    candidatos.append((nodo, round(score_final, 4)))

        prioridad_tipo = {
            TipoNodoAST.METODO: 4,
            TipoNodoAST.FUNCION: 3,
            TipoNodoAST.BLOQUE: 2,
            TipoNodoAST.CLASE: 1,
            TipoNodoAST.MODULO: 0,
        }
        candidatos.sort(key=lambda x: (x[1], prioridad_tipo.get(x[0].tipo, 0)), reverse=True)
        return candidatos[:top_k]

    def construir_contexto_optimo(
        self,
        nodos_relevantes: list[tuple[NodoAST, float]],
        incluir_padre: bool = True,
        comprimir_bpe: bool = True,
        incluir_hermanos: bool = True,
    ) -> str:
        """Ensambla contexto ultra-compacto combinando Esqueleto AST y Minificación BPE."""
        bloques: list[str] = []
        nodos_incluidos: set[str] = set()

        for nodo, score in nodos_relevantes:
            if nodo.id_nodo in nodos_incluidos:
                continue

            if comprimir_bpe:
                lineas_esqueleto: list[str] = []
                if incluir_padre and nodo.padre_id and nodo.padre_id in self.nodos:
                    padre = self.nodos[nodo.padre_id]
                    if padre.tipo != TipoNodoAST.MODULO:
                        lineas_esqueleto.append(f"{padre.resumen_sintactico}:")
                        if incluir_hermanos:
                            for h_id in padre.hijos_ids:
                                if h_id != nodo.id_nodo and h_id in self.nodos:
                                    hermano = self.nodos[h_id]
                                    lineas_esqueleto.append(f"\t{hermano.resumen_sintactico}:...")
                        nodos_incluidos.add(padre.id_nodo)

                codigo_min = minificar_codigo_bpe(nodo.codigo)
                lineas_esqueleto.append(codigo_min)
                bloques.append("\n".join(lineas_esqueleto))
            else:
                if incluir_padre and nodo.padre_id and nodo.padre_id in self.nodos:
                    padre = self.nodos[nodo.padre_id]
                    if padre.id_nodo not in nodos_incluidos and padre.tipo != TipoNodoAST.MODULO:
                        bloques.append(
                            f"### Contenedor: {padre.tipo.value} `{padre.nombre}`\n"
                            f"```python\n{padre.resumen_sintactico}\n```"
                        )
                        nodos_incluidos.add(padre.id_nodo)

                bloques.append(
                    f"### Nodo Recuperado: [{nodo.tipo.value}] `{nodo.nombre}` (Relevancia: {score:.2f})\n"
                    f"Ubicación: `{nodo.ruta_archivo}:{nodo.linea_inicio}-{nodo.linea_fin}`\n"
                    f"```python\n{nodo.codigo}\n```"
                )
            nodos_incluidos.add(nodo.id_nodo)

        return "\n".join(bloques)

    def generar_mensaje_inter_modelo(
        self,
        consulta_usuario: str,
        nodos_relevantes: list[tuple[NodoAST, float]],
    ) -> MensajeInterModelo:
        """Crea un MensajeInterModelo normalizado con tipo_accion='CONSULTA_NODOS'."""
        contexto = self.construir_contexto_optimo(nodos_relevantes, incluir_hermanos=False)
        payload = {
            "consulta": consulta_usuario,
            "total_nodos_encontrados": len(nodos_relevantes),
            "nodos": [
                {
                    "id": n.id_nodo,
                    "tipo": n.tipo.value,
                    "nombre": n.nombre,
                    "relevancia": score,
                    "ubicacion": f"{n.ruta_archivo}:{n.linea_inicio}-{n.linea_fin}",
                }
                for n, score in nodos_relevantes
            ],
            "contexto_sintactico": contexto,
        }

        return MensajeInterModelo(
            emisor_rol=RolAgente.EMBEDDING_INDEXER.value,
            receptor_rol=RolAgente.CODER.value,
            tipo_accion="CONSULTA_NODOS",
            idioma_comunicacion="es",
            payload=payload,
        )
