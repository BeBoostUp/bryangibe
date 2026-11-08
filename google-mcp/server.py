"""
MCP de Google UNIFICADO (stdio, JSON-RPC 2.0) — Python puro, sin SDK.

Un solo servidor 'google' con todo el ecosistema:
  ads_*       Google Ads (API v25)            gtm_*       Google Tag Manager
  ga4_*       Google Analytics 4              gsc_*       Search Console
  merchant_*  Merchant Center                 gmail_* / drive_*  Gmail y Drive
  google_*, youtube_*, gbp_*, sheets_*, docs_*, slides_*, forms_*, calendar_*,
  tasks_*, contacts_*, cloud_*, bigquery_*, indexing_*, site_verification_*,
  pagespeed, crux, looker_studio_*, adsense_*, postmaster_*
  + google_api_request: cualquier endpoint de cualquier API de Google.

Cuentas: SOLO bryan@bryangibe.com ('bryan') y academy@bryangibe.com ('academy').
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from core import accounts  # noqa: E402

# IMPORTANTE: antes de importar ningún módulo, para que solo vean cuentas permitidas.
accounts.bootstrap(verify=os.environ.get("GOOGLE_MCP_SKIP_VERIFY") != "1")

import importlib  # noqa: E402
from core import google_tools  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "google", "version": "3.0.0"}

# (módulo, prefijo, etiqueta legible)
MODULES = [
    ("gads.mcp_server", "ads_", "Google Ads"),
    ("ga4.mcp_server", "ga4_", "GA4"),
    ("gtm.mcp_server", "gtm_", "Tag Manager"),
    ("mc.mcp_server", "merchant_", "Merchant Center"),
    ("gsc.mcp_server", "gsc_", "Search Console"),
    ("ws.mcp_server", "gmail_", "Gmail/Drive"),
]

_ACCT_NOTE = (" [Cuentas permitidas: 'bryan' = bryan@bryangibe.com, 'academy' = academy@bryangibe.com]")

TOOLS = []
ROUTES = {}          # nombre público -> (módulo, nombre interno)
LOAD_ERRORS = {}


def _public_name(prefix, name):
    if prefix == "gmail_" and (name.startswith("gmail_") or name.startswith("drive_")):
        return name
    return prefix + name


for modname, prefix, title in MODULES:
    try:
        mod = importlib.import_module(modname)
    except Exception as e:  # un módulo roto no tumba el resto
        LOAD_ERRORS[title] = str(e)
        continue
    for t in mod.TOOLS:
        pub = _public_name(prefix, t["name"])
        t = dict(t, name=pub, description=f"[{title}] " + t.get("description", ""))
        props = (t.get("inputSchema") or {}).get("properties") or {}
        if "account" in props:
            props["account"] = dict(props["account"], description=(props["account"].get("description", "") + _ACCT_NOTE))
        TOOLS.append(t)

# Rutas: nombre público -> (módulo, nombre interno)
for modname, prefix, title in MODULES:
    if title in LOAD_ERRORS:
        continue
    mod = sys.modules[modname]
    for t in mod.TOOLS:
        ROUTES[_public_name(prefix, t["name"])] = (mod, t["name"])

TOOLS.extend(google_tools.TOOLS)


def inventory(services=None):
    labels = [l for l in accounts.ALLOWED if accounts.STATUS.get(l, {}).get("source")]
    want = set(services or ["ads", "ga4", "gtm", "gsc", "merchant", "youtube", "gbp", "cloud"])
    plan = {"ads": "ads_list_accounts", "ga4": "ga4_list_account_summaries", "gtm": "gtm_list_accounts",
            "gsc": "gsc_list_sites", "merchant": "merchant_list_accounts", "youtube": "youtube_my_channels",
            "gbp": "gbp_list_accounts", "cloud": "cloud_list_projects"}
    out = {}
    for svc, tool in plan.items():
        if svc not in want:
            continue
        out[svc] = {}
        for label in labels:
            try:
                out[svc][label] = call_tool(tool, {"account": label})
            except Exception as e:
                out[svc][label] = {"error": str(e)[:500]}
    return {"cuentas": {l: accounts.ALLOWED[l] for l in labels}, "inventario": out}


def call_tool(name, args):
    acct = args.get("account")
    if acct:  # nunca otra cuenta que las permitidas
        a = str(acct).lower().strip()
        a = {e: l for l, e in accounts.ALLOWED.items()}.get(a, a)
        if a not in accounts.ALLOWED:
            raise ValueError(f"Cuenta '{acct}' NO permitida. Solo: " +
                             ", ".join(f"{l} ({e})" for l, e in accounts.ALLOWED.items()))
        args = dict(args, account=a)
    if name == "google_inventory":
        return inventory(args.get("services"))
    if name in google_tools.HANDLERS:
        return google_tools.HANDLERS[name](args)
    if name in ROUTES:
        mod, internal = ROUTES[name]
        return mod.call_tool(internal, args)
    raise ValueError(f"Herramienta desconocida: {name}")


def handle(req):
    method, rid = req.get("method"), req.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": PROTOCOL_VERSION, "capabilities": {"tools": {}}, "serverInfo": SERVER_INFO}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        p = req.get("params", {})
        try:
            res = call_tool(p.get("name"), p.get("arguments") or {})
            text = json.dumps(res, ensure_ascii=False, indent=2, default=str)
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"type": "text", "text": text}], "isError": False}}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"type": "text", "text": f"ERROR: {e}"}], "isError": True}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}
    return None


def main():
    if LOAD_ERRORS:
        sys.stderr.write("Módulos con error al cargar: %s\n" % LOAD_ERRORS)
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
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
