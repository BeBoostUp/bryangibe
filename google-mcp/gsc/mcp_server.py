"""
Servidor MCP de Google Search Console (stdio, JSON-RPC 2.0) — Python puro, sin SDK.
Expone el motor gsc/gsc.py como herramientas nativas de Claude Code.

Se lanza con:  python3 /ruta/gsc/mcp_server.py
Las credenciales salen del .env del repo (via gsc/gsc.py).

Un solo OAuth = todas las propiedades de Search Console accesibles por la cuenta.
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gsc import engine as gsc  # noqa: E402
from gsc import extra  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "searchconsole", "version": "2.0.0"}

_DIMS = ("Dimensiones: query | page | country | device | date | searchAppearance. "
         "Se pueden combinar (p.ej. ['page','query']).")
_SITE = ("siteUrl de la propiedad. Domain property: 'sc-domain:example.com'. "
         "URL-prefix: 'https://example.com/' (con la barra final). Usa list_sites para verlas.")
_ACCT = ("Etiqueta de cuenta (opcional). Normalmente NO hace falta: se resuelve sola "
         "según qué cuenta posee la propiedad. Úsalo solo para forzar una cuenta concreta.")

TOOLS = [
    {
        "name": "list_sites",
        "description": ("Lista TODAS las propiedades de Search Console de TODAS las cuentas configuradas "
                        "(siteUrl + nivel de permiso + cuenta). Fusiona las cuentas en una sola lista."),
        "inputSchema": {"type": "object", "properties": {
            "account": {"type": "string", "description": "Opcional: limita a una sola cuenta (su etiqueta)."},
        }},
    },
    {
        "name": "search_analytics",
        "description": ("Datos de rendimiento (clicks, impresiones, CTR, posición) de una propiedad. "
                        "El endpoint estrella. Agrupa por dimensiones y admite filtros. "
                        "Por defecto: últimos 28 días (con 3 días de retraso de GSC)."),
        "inputSchema": {"type": "object", "properties": {
            "site_url": {"type": "string", "description": _SITE},
            "start_date": {"type": "string", "description": "YYYY-MM-DD. Por defecto hace 30 días."},
            "end_date": {"type": "string", "description": "YYYY-MM-DD. Por defecto hace 3 días."},
            "dimensions": {"type": "array", "items": {"type": "string"}, "description": _DIMS},
            "row_limit": {"type": "integer", "description": "Máx filas (1-25000). Por defecto 1000."},
            "start_row": {"type": "integer", "description": "Offset para paginar. Por defecto 0."},
            "search_type": {"type": "string", "enum": ["web", "image", "video", "news", "discover", "googleNews"],
                            "description": "Tipo de búsqueda. Por defecto 'web'."},
            "data_state": {"type": "string", "enum": ["final", "all"],
                           "description": "'all' incluye datos frescos aún no finalizados. Por defecto 'final'."},
            "aggregation_type": {"type": "string", "enum": ["auto", "byPage", "byProperty"]},
            "filters": {"type": "array", "items": {"type": "object"},
                        "description": ("Filtros: lista de {dimension, operator, expression}. operator: equals | "
                                        "contains | notContains | notEquals | includingRegex | excludingRegex.")},
            "account": {"type": "string", "description": _ACCT},
        }, "required": ["site_url"]},
    },
    {
        "name": "top_queries",
        "description": "Atajo: mejores consultas de búsqueda por clicks (dimensión query). Por defecto top 50, últimos 28 días.",
        "inputSchema": {"type": "object", "properties": {
            "site_url": {"type": "string", "description": _SITE},
            "start_date": {"type": "string"},
            "end_date": {"type": "string"},
            "row_limit": {"type": "integer", "description": "Por defecto 50."},
            "search_type": {"type": "string", "enum": ["web", "image", "video", "news", "discover", "googleNews"]},
            "filters": {"type": "array", "items": {"type": "object"}},
            "account": {"type": "string", "description": _ACCT},
        }, "required": ["site_url"]},
    },
    {
        "name": "top_pages",
        "description": "Atajo: mejores páginas por clicks (dimensión page). Por defecto top 50, últimos 28 días.",
        "inputSchema": {"type": "object", "properties": {
            "site_url": {"type": "string", "description": _SITE},
            "start_date": {"type": "string"},
            "end_date": {"type": "string"},
            "row_limit": {"type": "integer", "description": "Por defecto 50."},
            "search_type": {"type": "string", "enum": ["web", "image", "video", "news", "discover", "googleNews"]},
            "filters": {"type": "array", "items": {"type": "object"}},
            "account": {"type": "string", "description": _ACCT},
        }, "required": ["site_url"]},
    },
    {
        "name": "list_sitemaps",
        "description": "Lista los sitemaps enviados de una propiedad (con estado, errores, warnings, última descarga).",
        "inputSchema": {"type": "object", "properties": {
            "site_url": {"type": "string", "description": _SITE},
            "account": {"type": "string", "description": _ACCT},
        }, "required": ["site_url"]},
    },
    {
        "name": "inspect_url",
        "description": ("URL Inspection: estado de indexación de una URL concreta (cobertura, canonical, "
                        "última rastreada, mobile usability, rich results). Cuota limitada por Google."),
        "inputSchema": {"type": "object", "properties": {
            "site_url": {"type": "string", "description": _SITE},
            "inspection_url": {"type": "string", "description": "URL completa a inspeccionar (debe pertenecer a la propiedad)."},
            "language_code": {"type": "string", "description": "Por defecto es-ES."},
            "account": {"type": "string", "description": _ACCT},
        }, "required": ["site_url", "inspection_url"]},
    },
    {
        "name": "submit_sitemap",
        "description": "ESCRITURA: envía (o re-envía) un sitemap a una propiedad. feedpath = URL completa del sitemap.",
        "inputSchema": {"type": "object", "properties": {
            "site_url": {"type": "string", "description": _SITE},
            "feedpath": {"type": "string", "description": "URL completa del sitemap, p.ej. https://example.com/sitemap.xml"},
            "account": {"type": "string", "description": _ACCT},
        }, "required": ["site_url", "feedpath"]},
    },
    {
        "name": "delete_sitemap",
        "description": "ESCRITURA: elimina un sitemap enviado de una propiedad.",
        "inputSchema": {"type": "object", "properties": {
            "site_url": {"type": "string", "description": _SITE},
            "feedpath": {"type": "string", "description": "URL completa del sitemap a eliminar."},
            "account": {"type": "string", "description": _ACCT},
        }, "required": ["site_url", "feedpath"]},
    },
]


TOOLS.extend(extra.TOOLS)


def call_tool(name, args):
    if name == "list_sites":
        return gsc.list_sites(account=args.get("account"))
    if name == "search_analytics":
        return gsc.search_analytics(
            args["site_url"], args.get("start_date"), args.get("end_date"),
            dimensions=args.get("dimensions"), row_limit=args.get("row_limit", 1000),
            start_row=args.get("start_row", 0), search_type=args.get("search_type", "web"),
            data_state=args.get("data_state"), aggregation_type=args.get("aggregation_type"),
            filters=args.get("filters"), account=args.get("account"))
    if name == "top_queries":
        return gsc.top_queries(args["site_url"], args.get("start_date"), args.get("end_date"),
                               row_limit=args.get("row_limit", 50),
                               search_type=args.get("search_type", "web"),
                               filters=args.get("filters"), account=args.get("account"))
    if name == "top_pages":
        return gsc.top_pages(args["site_url"], args.get("start_date"), args.get("end_date"),
                             row_limit=args.get("row_limit", 50),
                             search_type=args.get("search_type", "web"),
                             filters=args.get("filters"), account=args.get("account"))
    if name == "list_sitemaps":
        return gsc.list_sitemaps(args["site_url"], account=args.get("account"))
    if name == "inspect_url":
        return gsc.inspect_url(args["site_url"], args["inspection_url"],
                               args.get("language_code", "es-ES"), account=args.get("account"))
    if name == "submit_sitemap":
        return gsc.submit_sitemap(args["site_url"], args["feedpath"], account=args.get("account"))
    if name == "delete_sitemap":
        return gsc.delete_sitemap(args["site_url"], args["feedpath"], account=args.get("account"))
    if name in extra.HANDLERS:
        return extra.HANDLERS[name](args)
    raise ValueError(f"Herramienta desconocida: {name}")


# ----------------------------------------------------------------------------
# Bucle JSON-RPC por stdio
# ----------------------------------------------------------------------------
def send(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def handle(req):
    method = req.get("method")
    rid = req.get("id")

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = req.get("params", {})
        tname = params.get("name")
        targs = params.get("arguments", {}) or {}
        try:
            result = call_tool(tname, targs)
            text = json.dumps(result, ensure_ascii=False, indent=2)
            return {"jsonrpc": "2.0", "id": rid,
                    "result": {"content": [{"type": "text", "text": text}], "isError": False}}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": rid,
                    "result": {"content": [{"type": "text", "text": f"ERROR: {e}"}], "isError": True}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}
    return None


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle(req)
        if resp is not None:
            send(resp)


if __name__ == "__main__":
    main()
