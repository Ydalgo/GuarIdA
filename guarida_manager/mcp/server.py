"""Servidor MCP (Model Context Protocol) local sobre stdio para exponer memoria, grafo AST y privacidad."""

import json
import sys
from typing import Any, Optional, TextIO

from guarida_manager.cache import GestorCache
from guarida_manager.proyectos import GestorProyectos
from guarida_manager.security import SanitizadorPrivacidad


class ServidorMCPGuarida:
    """Servidor JSON-RPC 2.0 MCP sobre stdio para integrar GuarIdA con agentes e IDEs locales."""

    PROTOCOL_VERSION = "2024-11-05"

    def __init__(
        self,
        gestor_cache: Optional[GestorCache] = None,
        gestor_proyectos: Optional[GestorProyectos] = None,
    ) -> None:
        if gestor_proyectos is not None:
            self.proyectos = gestor_proyectos
            self.cache = gestor_cache or gestor_proyectos.cache
        else:
            self.cache = gestor_cache or GestorCache()
            self.proyectos = GestorProyectos(gestor_cache=self.cache)

    @staticmethod
    def _respuesta_ok(req_id: Any, result: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    @staticmethod
    def _respuesta_error(req_id: Any, code: int, message: str) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": code, "message": message},
        }

    @staticmethod
    def definiciones_herramientas() -> list[dict[str, Any]]:
        """Catálogo de herramientas MCP expuestas por GuarIdA."""
        return [
            {
                "name": "guarida_listar_proyectos",
                "description": "Lista los proyectos registrados en GuarIdA junto con su directorio raíz.",
                "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            },
            {
                "name": "guarida_buscar_contexto",
                "description": "Ejecuta búsqueda híbrida (BM25 + vectorial + grafo AST multihop) en un proyecto.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "proyecto_id": {"type": "string"},
                        "consulta": {"type": "string"},
                        "top_k": {"type": "integer", "default": 5},
                    },
                    "required": ["proyecto_id", "consulta"],
                },
            },
            {
                "name": "guarida_expandir_grafo_ast",
                "description": "Navega dependencias del grafo AST en SQLite mediante consultas recursivas (WITH RECURSIVE).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "proyecto_id": {"type": "string"},
                        "nodos_semilla": {"type": "array", "items": {"type": "string"}},
                        "max_profundidad": {"type": "integer", "default": 2},
                        "incluir_entrantes": {"type": "boolean", "default": True},
                    },
                    "required": ["proyecto_id", "nodos_semilla"],
                },
            },
            {
                "name": "guarida_registrar_hecho",
                "description": "Registra un hecho declarativo inmutable (sujeto, predicado, objeto) marcando contradicciones previas como superseded.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "sujeto": {"type": "string"},
                        "predicado": {"type": "string"},
                        "objeto": {"type": "string"},
                        "proyecto_id": {"type": "string"},
                        "sesion_id": {"type": "string"},
                    },
                    "required": ["sujeto", "predicado", "objeto"],
                },
            },
            {
                "name": "guarida_consultar_memoria",
                "description": "Recupera hechos declarativos activos o historial completo con trazabilidad superseded.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "proyecto_id": {"type": "string"},
                        "sesion_id": {"type": "string"},
                        "incluir_superseded": {"type": "boolean", "default": False},
                    },
                },
            },
            {
                "name": "guarida_sanitizar_texto",
                "description": "Aplica sanitización de bloques <private>, secretos y anonimización RGPD con auditoría HMAC.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "texto": {"type": "string"},
                        "modo": {"type": "string", "enum": ["estandar", "rgpd_estricto"], "default": "estandar"},
                        "origen": {"type": "string", "default": "mcp"},
                    },
                    "required": ["texto"],
                },
            },
        ]

    def _ejecutar_herramienta(self, nombre: str, args: dict[str, Any]) -> dict[str, Any]:
        if nombre == "guarida_listar_proyectos":
            return {"proyectos": self.proyectos.listar_proyectos()}

        if nombre == "guarida_buscar_contexto":
            proyecto_id = str(args["proyecto_id"])
            consulta = str(args["consulta"])
            top_k = int(args.get("top_k", 5))
            if (
                proyecto_id not in self.proyectos._arboles_codigo
                and proyecto_id not in self.proyectos._chunks_texto
            ):
                if self.proyectos.obtener_proyecto(proyecto_id):
                    self.proyectos.escanear_e_indexar_proyecto(proyecto_id)
            contexto, fuentes = self.proyectos.buscar_contexto_hibrido(
                proyecto_id=proyecto_id,
                consulta=consulta,
                top_k=top_k,
            )
            return {"contexto": contexto, "fuentes": fuentes}

        if nombre == "guarida_expandir_grafo_ast":
            proyecto_id = str(args["proyecto_id"])
            semillas = [str(s) for s in args.get("nodos_semilla", [])]
            max_prof = int(args.get("max_profundidad", 2))
            incluir_entrantes = bool(args.get("incluir_entrantes", True))
            dependencias = self.cache.expandir_dependencias_ast_recursivo(
                proyecto_id=proyecto_id,
                nodos_semilla=semillas,
                max_profundidad=max_prof,
                incluir_entrantes=incluir_entrantes,
            )
            return {"dependencias": dependencias}

        if nombre == "guarida_registrar_hecho":
            hecho_id = self.proyectos.registrar_hecho(
                sujeto=str(args["sujeto"]),
                predicado=str(args["predicado"]),
                objeto=str(args["objeto"]),
                proyecto_id=args.get("proyecto_id"),
                sesion_id=args.get("sesion_id"),
                origen_tipo="mcp",
            )
            return {"id": hecho_id, "estado": "activo"}

        if nombre == "guarida_consultar_memoria":
            proyecto_id = args.get("proyecto_id")
            sesion_id = args.get("sesion_id")
            incluir_superseded = bool(args.get("incluir_superseded", False))
            hechos = (
                self.proyectos.obtener_auditoria_hechos(proyecto_id=proyecto_id, sesion_id=sesion_id)
                if incluir_superseded
                else self.proyectos.obtener_hechos_activos(proyecto_id=proyecto_id, sesion_id=sesion_id)
            )
            return {"hechos": hechos}

        if nombre == "guarida_sanitizar_texto":
            texto = str(args["texto"])
            modo = str(args.get("modo", self.proyectos.sanitizador.modo))
            origen = str(args.get("origen", "mcp"))
            san = SanitizadorPrivacidad(modo=modo)
            res = san.sanitizar_texto(texto, origen=origen)
            return {
                "texto_sanitizado": res.texto_sanitizado,
                "total_redacciones": res.total_redacciones,
                "modo": res.modo,
                "eventos_auditoria": [
                    {
                        "timestamp_utc": ev.timestamp_utc,
                        "regla": ev.regla,
                        "etiqueta": ev.etiqueta,
                        "origen": ev.origen,
                        "hmac_sha256": ev.hmac_sha256,
                    }
                    for ev in res.eventos_auditoria
                ],
            }

        raise KeyError(f"Herramienta MCP desconocida: '{nombre}'")

    def procesar_mensaje(self, solicitud: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Procesa un mensaje JSON-RPC 2.0 del protocolo MCP y devuelve respuesta (o None si es notificación)."""
        metodo = solicitud.get("method")
        req_id = solicitud.get("id")
        params = solicitud.get("params") or {}

        # Las notificaciones en JSON-RPC 2.0 no llevan campo 'id' ni esperan respuesta
        if req_id is None:
            return None

        if metodo == "initialize":
            return self._respuesta_ok(
                req_id,
                {
                    "protocolVersion": self.PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "guarida-mcp", "version": "0.1.0"},
                },
            )

        if metodo == "ping":
            return self._respuesta_ok(req_id, {})

        if metodo == "tools/list":
            return self._respuesta_ok(req_id, {"tools": self.definiciones_herramientas()})

        if metodo == "tools/call":
            nombre = params.get("name")
            args = params.get("arguments") or {}
            if not nombre:
                return self._respuesta_error(req_id, -32602, "Falta el parámetro 'name'.")
            try:
                resultado = self._ejecutar_herramienta(str(nombre), dict(args))
                return self._respuesta_ok(
                    req_id,
                    {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(resultado, ensure_ascii=False, indent=2),
                            }
                        ],
                        "isError": False,
                    },
                )
            except KeyError as e_key:
                return self._respuesta_error(req_id, -32602, str(e_key))
            except Exception as e_exec:
                return self._respuesta_ok(
                    req_id,
                    {
                        "content": [{"type": "text", "text": f"Error: {e_exec}"}],
                        "isError": True,
                    },
                )

        return self._respuesta_error(req_id, -32601, f"Método no soportado: '{metodo}'")

    def servir_stdio(
        self,
        stream_in: Optional[TextIO] = None,
        stream_out: Optional[TextIO] = None,
    ) -> None:
        """Bucle principal leyendo peticiones JSON-RPC por línea desde stdin y escribiendo en stdout."""
        entrada = stream_in or sys.stdin
        salida = stream_out or sys.stdout

        for linea in entrada:
            linea_limpia = linea.strip()
            if not linea_limpia:
                continue
            try:
                solicitud = json.loads(linea_limpia)
                respuesta = self.procesar_mensaje(solicitud)
            except json.JSONDecodeError as e_json:
                respuesta = self._respuesta_error(None, -32700, f"JSON inválido: {e_json}")
            if respuesta is not None:
                salida.write(json.dumps(respuesta, ensure_ascii=False) + "\n")
                salida.flush()


if __name__ == "__main__":
    ServidorMCPGuarida().servir_stdio()
