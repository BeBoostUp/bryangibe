"""
Servidor MCP de Google Analytics 4 (stdio, JSON-RPC 2.0) — Python puro. MULTICUENTA.
Cada herramienta acepta 'account' (etiqueta de login del .env, p.ej. 'bryan' o
'academy'). Si solo hay una cuenta configurada, se usa por defecto.
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ga4 import engine  # noqa: E402
from ga4 import extra  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "ga4", "version": "2.0.0"}

_PID = "property_id: número o 'properties/123456' (via list_properties)."
_AC = ("Etiqueta de cuenta de login del .env (p.ej. 'bryan' o 'academy'). "
       "Opcional si solo hay una configurada.")


def _p(*extra):
    p = {}
    for e in extra:
        p.update(e)
    p["account"] = {"type": "string", "description": _AC}
    return p


TOOLS = [
    {"name": "list_login_accounts",
     "description": "Lista las cuentas de login configuradas en el .env (bryan, academy).",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "list_accounts",
     "description": "Lista las cuentas de Google Analytics accesibles (Admin API). " + _AC,
     "inputSchema": {"type": "object", "properties": _p()}},
    {"name": "list_properties",
     "description": "Lista las propiedades GA4 de una cuenta. account_id: número o 'accounts/123'. " + _AC,
     "inputSchema": {"type": "object", "properties": _p({"account_id": {"type": "string"}}),
                     "required": ["account_id"]}},
    {"name": "get_property",
     "description": "Detalles de una propiedad GA4. " + _PID,
     "inputSchema": {"type": "object", "properties": _p({"property_id": {"type": "string"}}),
                     "required": ["property_id"]}},
    {"name": "list_data_streams",
     "description": "Lista los flujos de datos (web/app) de una propiedad. " + _PID,
     "inputSchema": {"type": "object", "properties": _p({"property_id": {"type": "string"}}),
                     "required": ["property_id"]}},
    {"name": "list_key_events",
     "description": "Lista los eventos clave (conversiones) de una propiedad GA4. " + _PID,
     "inputSchema": {"type": "object", "properties": _p({"property_id": {"type": "string"}}),
                     "required": ["property_id"]}},
    {"name": "get_metadata",
     "description": "Dimensiones y métricas disponibles (incluye personalizadas). " + _PID,
     "inputSchema": {"type": "object", "properties": _p({"property_id": {"type": "string"}}),
                     "required": ["property_id"]}},
    {"name": "run_report",
     "description": ("Informe GA4 (Data API). metrics/dimensions: nombres de API (p.ej. "
                     "metrics=['sessions','conversions'], dimensions=['date','sessionDefaultChannelGroup']). "
                     "Fechas: 'YYYY-MM-DD' o 'NdaysAgo'/'today'/'yesterday'. " + _PID),
     "inputSchema": {"type": "object", "properties": _p(
         {"property_id": {"type": "string"},
          "metrics": {"type": "array", "items": {"type": "string"}},
          "dimensions": {"type": "array", "items": {"type": "string"}},
          "start_date": {"type": "string"}, "end_date": {"type": "string"},
          "limit": {"type": "integer"},
          "order_bys": {"type": "array", "items": {"type": "object"}},
          "dimension_filter": {"type": "object"}}),
         "required": ["property_id", "metrics"]}},
    {"name": "run_realtime_report",
     "description": ("Informe en tiempo real (~30 min). p.ej. metrics=['activeUsers']. " + _PID),
     "inputSchema": {"type": "object", "properties": _p(
         {"property_id": {"type": "string"},
          "metrics": {"type": "array", "items": {"type": "string"}},
          "dimensions": {"type": "array", "items": {"type": "string"}},
          "limit": {"type": "integer"}}),
         "required": ["property_id", "metrics"]}},
]


TOOLS.extend(extra.TOOLS)


def call_tool(name, a):
    acct = a.get("account")
    if name == "list_login_accounts":
        return engine.list_login_accounts()
    if name == "list_accounts":
        return engine.list_accounts(acct)
    if name == "list_properties":
        return engine.list_properties(a["account_id"], acct)
    if name == "get_property":
        return engine.get_property(a["property_id"], acct)
    if name == "list_data_streams":
        return engine.list_data_streams(a["property_id"], acct)
    if name == "list_key_events":
        return engine.list_key_events(a["property_id"], acct)
    if name == "get_metadata":
        return engine.get_metadata(a["property_id"], acct)
    if name == "run_report":
        return engine.run_report(a["property_id"], a["metrics"], a.get("dimensions"),
                                 a.get("start_date", "28daysAgo"), a.get("end_date", "today"),
                                 a.get("limit", 100), a.get("order_bys"), a.get("dimension_filter"), acct)
    if name == "run_realtime_report":
        return engine.run_realtime_report(a["property_id"], a["metrics"],
                                          a.get("dimensions"), a.get("limit", 100), acct)
    if name in extra.HANDLERS:
        return extra.HANDLERS[name](a)
    raise ValueError(f"Herramienta desconocida: {name}")


def send(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def handle(req):
    method = req.get("method")
    rid = req.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": PROTOCOL_VERSION, "capabilities": {"tools": {}},
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
