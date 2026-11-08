"""
Servidor MCP de Google Tag Manager (stdio, JSON-RPC 2.0) — Python puro. MULTICUENTA.
Expone el motor gtm/engine.py como herramientas nativas de Claude Code.

Cada herramienta acepta 'account' (etiqueta de login del .env, p.ej. 'bryan' o
'academy'). Si solo hay una cuenta configurada, se usa por defecto.
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gtm import engine  # noqa: E402
from gtm import extra  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "tagmanager", "version": "2.0.0"}

_WS = ("El 'path' del workspace: accounts/{accId}/containers/{contId}/workspaces/{wsId} "
       "(via list_workspaces).")
_AC = ("Etiqueta de cuenta de login del .env (p.ej. 'bryan' o 'academy'). "
       "Opcional si solo hay una configurada.")


def _acct():
    return {"account": {"type": "string", "description": _AC}}


def _props(*extra):
    p = {}
    for e in extra:
        p.update(e)
    p.update(_acct())
    return p


TOOLS = [
    {"name": "list_login_accounts",
     "description": "Lista las cuentas de login configuradas en el .env (bryan, academy).",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "list_accounts",
     "description": "Lista las cuentas de Google Tag Manager accesibles. " + _AC,
     "inputSchema": {"type": "object", "properties": _props()}},
    {"name": "list_containers",
     "description": "Lista los contenedores de una cuenta GTM. " + _AC,
     "inputSchema": {"type": "object", "properties": _props({"account_id": {"type": "string"}}),
                     "required": ["account_id"]}},
    {"name": "list_workspaces",
     "description": "Lista los workspaces de un contenedor. " + _AC,
     "inputSchema": {"type": "object", "properties": _props(
         {"account_id": {"type": "string"}, "container_id": {"type": "string"}}),
         "required": ["account_id", "container_id"]}},
    {"name": "list_tags",
     "description": "Lista las etiquetas (tags) de un workspace. " + _WS,
     "inputSchema": {"type": "object", "properties": _props({"workspace_path": {"type": "string"}}),
                     "required": ["workspace_path"]}},
    {"name": "list_triggers",
     "description": "Lista los activadores (triggers) de un workspace. " + _WS,
     "inputSchema": {"type": "object", "properties": _props({"workspace_path": {"type": "string"}}),
                     "required": ["workspace_path"]}},
    {"name": "list_variables",
     "description": "Lista las variables de un workspace. " + _WS,
     "inputSchema": {"type": "object", "properties": _props({"workspace_path": {"type": "string"}}),
                     "required": ["workspace_path"]}},
    {"name": "get_resource",
     "description": "GET genérico de cualquier recurso GTM por su path.",
     "inputSchema": {"type": "object", "properties": _props({"path": {"type": "string"}}),
                     "required": ["path"]}},
    {"name": "create_workspace",
     "description": "Crea un workspace nuevo en un contenedor.",
     "inputSchema": {"type": "object", "properties": _props(
         {"account_id": {"type": "string"}, "container_id": {"type": "string"},
          "name": {"type": "string"}, "description": {"type": "string"}}),
         "required": ["account_id", "container_id", "name"]}},
    {"name": "create_variable",
     "description": ("Crea una variable. type: 'v' (Data Layer), 'c' (constante)... "
                     "parameter: lista de {type, key, value/list/map}. " + _WS),
     "inputSchema": {"type": "object", "properties": _props(
         {"workspace_path": {"type": "string"}, "name": {"type": "string"},
          "type": {"type": "string"}, "parameter": {"type": "array", "items": {"type": "object"}}}),
         "required": ["workspace_path", "name", "type"]}},
    {"name": "create_trigger",
     "description": ("Crea un activador. type: 'customEvent', 'click', 'pageview'... "
                     "extra: campos adicionales. " + _WS),
     "inputSchema": {"type": "object", "properties": _props(
         {"workspace_path": {"type": "string"}, "name": {"type": "string"},
          "type": {"type": "string"}, "extra": {"type": "object"}}),
         "required": ["workspace_path", "name", "type"]}},
    {"name": "create_tag",
     "description": ("Crea una etiqueta. type: 'awct' (Ads Conv), 'gaawe' (GA4), 'html'... "
                     "parameter: lista de dicts. firing_trigger_id: lista de IDs. " + _WS),
     "inputSchema": {"type": "object", "properties": _props(
         {"workspace_path": {"type": "string"}, "name": {"type": "string"},
          "type": {"type": "string"}, "parameter": {"type": "array", "items": {"type": "object"}},
          "firing_trigger_id": {"type": "array", "items": {"type": "string"}},
          "extra": {"type": "object"}}),
         "required": ["workspace_path", "name", "type"]}},
    {"name": "create_version",
     "description": "Congela el workspace en una versión (previo a publicar). " + _WS,
     "inputSchema": {"type": "object", "properties": _props(
         {"workspace_path": {"type": "string"}, "name": {"type": "string"}, "notes": {"type": "string"}}),
         "required": ["workspace_path"]}},
    {"name": "publish_version",
     "description": "PUBLICA una versión. version_path: accounts/{a}/containers/{c}/versions/{v}.",
     "inputSchema": {"type": "object", "properties": _props({"version_path": {"type": "string"}}),
                     "required": ["version_path"]}},
    {"name": "delete_resource",
     "description": "Borra un tag/trigger/variable/workspace por su path completo.",
     "inputSchema": {"type": "object", "properties": _props({"path": {"type": "string"}}),
                     "required": ["path"]}},
    {"name": "create_datalayer_variable",
     "description": "ATAJO: variable de capa de datos (Data Layer Variable). " + _WS,
     "inputSchema": {"type": "object", "properties": _props(
         {"workspace_path": {"type": "string"}, "name": {"type": "string"},
          "data_layer_name": {"type": "string"}, "version": {"type": "integer"}}),
         "required": ["workspace_path", "name"]}},
    {"name": "create_custom_event_trigger",
     "description": "ATAJO: trigger de evento personalizado (dataLayer event == event_name). " + _WS,
     "inputSchema": {"type": "object", "properties": _props(
         {"workspace_path": {"type": "string"}, "name": {"type": "string"},
          "event_name": {"type": "string"}}),
         "required": ["workspace_path", "name", "event_name"]}},
    {"name": "create_google_ads_conversion_tag",
     "description": "ATAJO: tag de conversión de Google Ads (awct). " + _WS,
     "inputSchema": {"type": "object", "properties": _props(
         {"workspace_path": {"type": "string"}, "name": {"type": "string"},
          "conversion_id": {"type": "string"}, "conversion_label": {"type": "string"},
          "firing_trigger_id": {"type": "array", "items": {"type": "string"}}}),
         "required": ["workspace_path", "name", "conversion_id", "conversion_label", "firing_trigger_id"]}},
]


TOOLS.extend(extra.TOOLS)


def call_tool(name, a):
    acct = a.get("account")
    if name == "list_login_accounts":
        return engine.list_login_accounts()
    if name == "list_accounts":
        return engine.list_accounts(acct)
    if name == "list_containers":
        return engine.list_containers(a["account_id"], acct)
    if name == "list_workspaces":
        return engine.list_workspaces(a["account_id"], a["container_id"], acct)
    if name == "list_tags":
        return engine.list_tags(a["workspace_path"], acct)
    if name == "list_triggers":
        return engine.list_triggers(a["workspace_path"], acct)
    if name == "list_variables":
        return engine.list_variables(a["workspace_path"], acct)
    if name == "get_resource":
        return engine.get_resource(a["path"], acct)
    if name == "create_workspace":
        return engine.create_workspace(a["account_id"], a["container_id"], a["name"],
                                       a.get("description"), acct)
    if name == "create_variable":
        return engine.create_variable(a["workspace_path"], a["name"], a["type"], a.get("parameter"), acct)
    if name == "create_trigger":
        return engine.create_trigger(a["workspace_path"], a["name"], a["type"], a.get("extra"), acct)
    if name == "create_tag":
        return engine.create_tag(a["workspace_path"], a["name"], a["type"], a.get("parameter"),
                                 a.get("firing_trigger_id"), a.get("extra"), acct)
    if name == "create_version":
        return engine.create_version(a["workspace_path"], a.get("name"), a.get("notes"), acct)
    if name == "publish_version":
        return engine.publish_version(a["version_path"], acct)
    if name == "delete_resource":
        return engine.delete_resource(a["path"], acct)
    if name == "create_datalayer_variable":
        return engine.create_datalayer_variable(a["workspace_path"], a["name"],
                                                a.get("data_layer_name"), a.get("version", 2), acct)
    if name == "create_custom_event_trigger":
        return engine.create_custom_event_trigger(a["workspace_path"], a["name"], a["event_name"], acct)
    if name == "create_google_ads_conversion_tag":
        return engine.create_google_ads_conversion_tag(a["workspace_path"], a["name"],
                                                       a["conversion_id"], a["conversion_label"],
                                                       a["firing_trigger_id"], acct)
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
