"""
Servidor MCP de Google Workspace (stdio, JSON-RPC 2.0) — Python puro, sin SDK.
Expone Gmail (borradores + envio con adjuntos) y Drive (subida de archivos).

Se lanza con:  python3 /Users/bryangibe/workspace-mcp/ws/mcp_server.py
Las credenciales salen del .env del repo (via ws/engine.py).

Los adjuntos y las subidas se leen del disco por ruta local: el contenido
binario nunca pasa por el modelo.
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ws import engine as ws  # noqa: E402
from ws import gmail_engine as extra  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "gmail", "version": "2.0.0"}

_ACCT = ("Etiqueta de cuenta (opcional). Por defecto 'bryan'. "
         "Solo si quieres forzar otra cuenta configurada.")
_ATT = ("Lista de RUTAS LOCALES de archivos a adjuntar, p.ej. "
        "['/Users/bryangibe/Desktop/FACTURACION/.../BGB2025179_Asister_AF_SLU.pdf']. "
        "Se leen del disco.")

TOOLS = [
    {
        "name": "send_email",
        "description": ("Envia un correo desde la cuenta de Gmail configurada, con "
                        "adjuntos opcionales leidos del disco. ENVIA DE VERDAD: usar "
                        "solo con confirmacion explicita del usuario."),
        "inputSchema": {"type": "object", "properties": {
            "to": {"type": "array", "items": {"type": "string"},
                   "description": "Destinatarios."},
            "subject": {"type": "string"},
            "body": {"type": "string", "description": "Texto plano del correo."},
            "attachments": {"type": "array", "items": {"type": "string"}, "description": _ATT},
            "cc": {"type": "array", "items": {"type": "string"}},
            "bcc": {"type": "array", "items": {"type": "string"}},
            "html": {"type": "string", "description": "Version HTML opcional."},
            "account": {"type": "string", "description": _ACCT},
        }, "required": ["to", "subject", "body"]},
    },
    {
        "name": "create_draft",
        "description": ("Crea un borrador en Gmail con adjuntos opcionales leidos del "
                        "disco. No envia nada."),
        "inputSchema": {"type": "object", "properties": {
            "to": {"type": "array", "items": {"type": "string"}},
            "subject": {"type": "string"},
            "body": {"type": "string"},
            "attachments": {"type": "array", "items": {"type": "string"}, "description": _ATT},
            "cc": {"type": "array", "items": {"type": "string"}},
            "bcc": {"type": "array", "items": {"type": "string"}},
            "html": {"type": "string"},
            "account": {"type": "string", "description": _ACCT},
        }, "required": ["to", "subject", "body"]},
    },
    {
        "name": "send_draft",
        "description": "Envia un borrador ya existente por su draftId. ENVIA DE VERDAD.",
        "inputSchema": {"type": "object", "properties": {
            "draft_id": {"type": "string"},
            "account": {"type": "string", "description": _ACCT},
        }, "required": ["draft_id"]},
    },
    {
        "name": "drive_upload",
        "description": ("Sube un archivo local a Google Drive. Si ya existe uno con el "
                        "mismo nombre en la carpeta destino, lo reemplaza (conservando "
                        "el enlace) salvo que overwrite sea false."),
        "inputSchema": {"type": "object", "properties": {
            "local_path": {"type": "string", "description": "Ruta local del archivo."},
            "parent_id": {"type": "string", "description": "ID de la carpeta destino en Drive."},
            "name": {"type": "string", "description": "Nombre en Drive. Por defecto el del archivo."},
            "overwrite": {"type": "boolean", "description": "Por defecto true."},
            "account": {"type": "string", "description": _ACCT},
        }, "required": ["local_path"]},
    },
    {
        "name": "drive_list",
        "description": "Lista archivos y carpetas de Drive. Filtra por carpeta padre y/o nombre.",
        "inputSchema": {"type": "object", "properties": {
            "parent_id": {"type": "string", "description": "ID de la carpeta a listar."},
            "name_contains": {"type": "string", "description": "Filtro por nombre."},
            "page_size": {"type": "integer", "description": "Por defecto 100."},
            "account": {"type": "string", "description": _ACCT},
        }},
    },
    {
        "name": "drive_create_folder",
        "description": "Crea una carpeta en Drive. Si ya existe con ese nombre, devuelve la existente.",
        "inputSchema": {"type": "object", "properties": {
            "name": {"type": "string"},
            "parent_id": {"type": "string", "description": "ID de la carpeta padre."},
            "account": {"type": "string", "description": _ACCT},
        }, "required": ["name"]},
    },
    {
        "name": "whoami",
        "description": "Devuelve la cuenta de Google con la que esta autenticado el servidor.",
        "inputSchema": {"type": "object", "properties": {
            "account": {"type": "string", "description": _ACCT},
        }},
    },
]


TOOLS.extend(extra.TOOLS)


def call_tool(name, a):
    if name == "send_email":
        return ws.send_email(a["to"], a["subject"], a["body"],
                             attachments=a.get("attachments"), cc=a.get("cc"),
                             bcc=a.get("bcc"), html=a.get("html"),
                             account=a.get("account"))
    if name == "create_draft":
        return ws.create_draft(a["to"], a["subject"], a["body"],
                               attachments=a.get("attachments"), cc=a.get("cc"),
                               bcc=a.get("bcc"), html=a.get("html"),
                               account=a.get("account"))
    if name == "send_draft":
        return ws.send_draft(a["draft_id"], account=a.get("account"))
    if name == "drive_upload":
        return ws.drive_upload(a["local_path"], parent_id=a.get("parent_id"),
                               name=a.get("name"),
                               overwrite=a.get("overwrite", True),
                               account=a.get("account"))
    if name == "drive_list":
        return ws.drive_list(parent_id=a.get("parent_id"),
                             name_contains=a.get("name_contains"),
                             page_size=a.get("page_size", 100),
                             account=a.get("account"))
    if name == "drive_create_folder":
        return ws.drive_create_folder(a["name"], parent_id=a.get("parent_id"),
                                      account=a.get("account"))
    if name == "whoami":
        return ws.whoami(account=a.get("account"))
    if name in extra.HANDLERS:
        return extra.HANDLERS[name](a)
    raise ValueError("Herramienta desconocida: " + str(name))


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
                    "result": {"content": [{"type": "text", "text": text}],
                               "isError": False}}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": rid,
                    "result": {"content": [{"type": "text", "text": "ERROR: " + str(e)}],
                               "isError": True}}
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
