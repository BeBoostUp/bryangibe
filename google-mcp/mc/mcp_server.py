"""
Servidor MCP de Google Merchant Center (stdio, JSON-RPC 2.0) — Python puro. MULTICUENTA.
Cada herramienta acepta 'account' (etiqueta de login del .env, p.ej. 'bryan' o
'academy'). Si solo hay una cuenta configurada, se usa por defecto.
Lectura Y escritura (productos, feeds, promociones, ajustes de cuenta).
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mc import engine  # noqa: E402
from mc import extra  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "merchantcenter", "version": "2.0.0"}

_AC = ("Etiqueta de cuenta de LOGIN del .env (p.ej. 'bryan' o 'academy'). "
       "Opcional si solo hay una configurada.")
_AID = "account_id: ID de la cuenta de Merchant Center (p.ej. 5089123456)."


def _p(*extra):
    p = {}
    for e in extra:
        p.update(e)
    p["account"] = {"type": "string", "description": _AC}
    return p


_S = {"type": "string"}
_I = {"type": "integer"}
_O = {"type": "object"}
_ACCID = {"account_id": {"type": "string", "description": _AID}}
_PG = {"page_size": _I, "page_token": _S}

TOOLS = [
    # ---------------- descubrimiento ----------------
    {"name": "list_login_accounts",
     "description": "Lista las cuentas de login configuradas en el .env (bryan, academy).",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "list_accounts",
     "description": "Lista las cuentas de Merchant Center accesibles con ese login (incluye MCA). " + _AC,
     "inputSchema": {"type": "object", "properties": _p(_PG, {"filter": _S})}},
    {"name": "get_account",
     "description": "Detalles de una cuenta de Merchant Center. " + _AID,
     "inputSchema": {"type": "object", "properties": _p(_ACCID), "required": ["account_id"]}},
    {"name": "list_subaccounts",
     "description": "Subcuentas de una cuenta multi-cliente (MCA). " + _AID,
     "inputSchema": {"type": "object", "properties": _p(_ACCID, _PG), "required": ["account_id"]}},
    {"name": "get_account_resource",
     "description": ("Ajuste singleton de la cuenta. resource: businessInfo | homepage | "
                     "shippingSettings | automaticImprovements | autofeedSettings | "
                     "emailPreferences | businessIdentity. " + _AID),
     "inputSchema": {"type": "object", "properties": _p(_ACCID, {"resource": _S}),
                     "required": ["account_id", "resource"]}},
    {"name": "list_account_resources",
     "description": ("Colección de la cuenta. resource: users | programs | regions | "
                     "onlineReturnPolicies | termsOfServiceAgreementStates | issues. " + _AID),
     "inputSchema": {"type": "object", "properties": _p(_ACCID, {"resource": _S}, _PG),
                     "required": ["account_id", "resource"]}},

    # ---------------- productos ----------------
    {"name": "list_products",
     "description": "Lista productos procesados de la cuenta (incluye estado y problemas). " + _AID,
     "inputSchema": {"type": "object", "properties": _p(_ACCID, _PG), "required": ["account_id"]}},
    {"name": "get_product",
     "description": ("Detalle de un producto. product_id: 'online~es~ES~SKU' o el name completo "
                     "'accounts/X/products/...'. " + _AID),
     "inputSchema": {"type": "object", "properties": _p(_ACCID, {"product_id": _S}),
                     "required": ["account_id", "product_id"]}},
    {"name": "run_report",
     "description": ("Informe con Merchant Center Query Language. Tablas: product_view (catálogo + "
                     "item_issues), product_performance_view (clics/impresiones/conversiones, exige "
                     "WHERE date BETWEEN), price_competitiveness_product_view, "
                     "price_insights_product_view, best_sellers_product_cluster_view, "
                     "competitive_visibility_competitor_view. " + _AID),
     "inputSchema": {"type": "object", "properties": _p(_ACCID, {"query": _S}, _PG),
                     "required": ["account_id", "query"]}},
    {"name": "product_issues",
     "description": "Atajo: productos con problemas/desaprobaciones y su click_potential. " + _AID,
     "inputSchema": {"type": "object", "properties": _p(_ACCID, {"limit": _I}),
                     "required": ["account_id"]}},
    {"name": "product_performance",
     "description": "Atajo: rendimiento por producto entre dos fechas 'YYYY-MM-DD'. " + _AID,
     "inputSchema": {"type": "object", "properties": _p(
         _ACCID, {"start_date": _S, "end_date": _S, "limit": _I}),
         "required": ["account_id", "start_date", "end_date"]}},

    # ---------------- escritura de productos ----------------
    {"name": "insert_product_input",
     "description": ("ESCRITURA. Alta/actualización (upsert) de un producto en una fuente de datos. "
                     "data_source: ID o 'accounts/X/dataSources/123'. product_input: dict con offerId, "
                     "contentLanguage, feedLabel, channel y attributes. " + _AID),
     "inputSchema": {"type": "object", "properties": _p(
         _ACCID, {"data_source": _S, "product_input": _O}),
         "required": ["account_id", "data_source", "product_input"]}},
    {"name": "update_product_input",
     "description": ("ESCRITURA. PATCH de un productInput existente. product_input_name: "
                     "'accounts/X/productInputs/online~es~ES~SKU'. update_mask p.ej. "
                     "'attributes.title,attributes.description'."),
     "inputSchema": {"type": "object", "properties": _p(
         {"product_input_name": _S, "data_source": _S, "product_input": _O, "update_mask": _S}),
         "required": ["product_input_name", "data_source", "product_input", "update_mask"]}},
    {"name": "delete_product_input",
     "description": "ESCRITURA IRREVERSIBLE. Borra un productInput de una fuente de datos.",
     "inputSchema": {"type": "object", "properties": _p(
         {"product_input_name": _S, "data_source": _S}),
         "required": ["product_input_name"]}},

    # ---------------- inventario ----------------
    {"name": "list_inventories",
     "description": "Inventario de un producto. kind: 'regional' (defecto) | 'local'. " + _AID,
     "inputSchema": {"type": "object", "properties": _p(
         _ACCID, {"product_id": _S, "kind": _S}, _PG),
         "required": ["account_id", "product_id"]}},
    {"name": "insert_inventory",
     "description": "ESCRITURA. Alta/actualización de inventario regional o local de un producto. " + _AID,
     "inputSchema": {"type": "object", "properties": _p(
         _ACCID, {"product_id": _S, "body": _O, "kind": _S}),
         "required": ["account_id", "product_id", "body"]}},

    # ---------------- fuentes de datos (feeds) ----------------
    {"name": "list_data_sources",
     "description": "Fuentes de datos (feeds principales, suplementarios, de promociones...). " + _AID,
     "inputSchema": {"type": "object", "properties": _p(_ACCID, _PG), "required": ["account_id"]}},
    {"name": "get_data_source",
     "description": "Detalle de una fuente de datos. " + _AID,
     "inputSchema": {"type": "object", "properties": _p(_ACCID, {"data_source_id": _S}),
                     "required": ["account_id", "data_source_id"]}},
    {"name": "create_data_source",
     "description": ("ESCRITURA. Crea una fuente de datos. body p.ej. {\"displayName\":\"Suplementario "
                     "titulos\",\"supplementalProductDataSource\":{\"contentLanguage\":\"es\","
                     "\"feedLabel\":\"ES\"}}. " + _AID),
     "inputSchema": {"type": "object", "properties": _p(_ACCID, {"body": _O}),
                     "required": ["account_id", "body"]}},
    {"name": "update_data_source",
     "description": "ESCRITURA. PATCH de una fuente de datos (update_mask obligatorio). " + _AID,
     "inputSchema": {"type": "object", "properties": _p(
         _ACCID, {"data_source_id": _S, "body": _O, "update_mask": _S}),
         "required": ["account_id", "data_source_id", "body", "update_mask"]}},
    {"name": "delete_data_source",
     "description": "ESCRITURA IRREVERSIBLE. Borra una fuente de datos. " + _AID,
     "inputSchema": {"type": "object", "properties": _p(_ACCID, {"data_source_id": _S}),
                     "required": ["account_id", "data_source_id"]}},
    {"name": "fetch_data_source",
     "description": "ESCRITURA. Fuerza la descarga inmediata de un feed por URL. " + _AID,
     "inputSchema": {"type": "object", "properties": _p(_ACCID, {"data_source_id": _S}),
                     "required": ["account_id", "data_source_id"]}},

    # ---------------- ajustes de cuenta (escritura) ----------------
    {"name": "update_account",
     "description": "ESCRITURA. PATCH de la cuenta. update_mask p.ej. 'accountName,timeZone'. " + _AID,
     "inputSchema": {"type": "object", "properties": _p(_ACCID, {"body": _O, "update_mask": _S}),
                     "required": ["account_id", "body", "update_mask"]}},
    {"name": "patch_account_resource",
     "description": ("ESCRITURA. PATCH de un ajuste singleton (businessInfo, homepage, "
                     "automaticImprovements, autofeedSettings, emailPreferences...). " + _AID),
     "inputSchema": {"type": "object", "properties": _p(
         _ACCID, {"resource": _S, "body": _O, "update_mask": _S}),
         "required": ["account_id", "resource", "body", "update_mask"]}},
    {"name": "insert_shipping_settings",
     "description": "ESCRITURA. Reemplaza por completo la configuración de envíos de la cuenta. " + _AID,
     "inputSchema": {"type": "object", "properties": _p(_ACCID, {"body": _O}),
                     "required": ["account_id", "body"]}},

    # ---------------- promociones y cuota ----------------
    {"name": "list_promotions",
     "description": "Promociones de la cuenta. " + _AID,
     "inputSchema": {"type": "object", "properties": _p(_ACCID, _PG), "required": ["account_id"]}},
    {"name": "insert_promotion",
     "description": "ESCRITURA. Crea o actualiza una promoción. " + _AID,
     "inputSchema": {"type": "object", "properties": _p(_ACCID, {"body": _O, "data_source": _S}),
                     "required": ["account_id", "body"]}},
    {"name": "list_quotas",
     "description": "Consumo de cuota de la API por grupo/método. " + _AID,
     "inputSchema": {"type": "object", "properties": _p(_ACCID, _PG), "required": ["account_id"]}},

    # ---------------- escape hatch ----------------
    {"name": "api_request",
     "description": ("Llamada cruda a Merchant API para lo no cubierto arriba. "
                     "method: GET|POST|PATCH|PUT|DELETE. sub_api: accounts | products | inventories | "
                     "datasources | reports | promotions | quota | conversions | notifications | lfp | "
                     "issueresolution | ordertracking. path: ruta tras la versión, p.ej. "
                     "'accounts/5089123456/products'."),
     "inputSchema": {"type": "object", "properties": _p(
         {"method": _S, "sub_api": _S, "path": _S, "params": _O, "body": _O}),
         "required": ["method", "sub_api", "path"]}},
]


TOOLS.extend(extra.TOOLS)


def call_tool(name, a):
    acct = a.get("account")
    if name == "list_login_accounts":
        return engine.list_login_accounts()
    if name == "list_accounts":
        return engine.list_accounts(a.get("page_size", 100), a.get("page_token"),
                                    a.get("filter"), acct)
    if name == "get_account":
        return engine.get_account(a["account_id"], acct)
    if name == "list_subaccounts":
        return engine.list_subaccounts(a["account_id"], a.get("page_size", 200),
                                       a.get("page_token"), acct)
    if name == "get_account_resource":
        return engine.get_account_resource(a["account_id"], a["resource"], acct)
    if name == "list_account_resources":
        return engine.list_account_resources(a["account_id"], a["resource"],
                                             a.get("page_size", 100), a.get("page_token"), acct)
    if name == "list_products":
        return engine.list_products(a["account_id"], a.get("page_size", 50),
                                    a.get("page_token"), acct)
    if name == "get_product":
        return engine.get_product(a["account_id"], a["product_id"], acct)
    if name == "run_report":
        return engine.run_report(a["account_id"], a["query"], a.get("page_size", 100),
                                 a.get("page_token"), acct)
    if name == "product_issues":
        return engine.product_issues(a["account_id"], a.get("limit", 200), acct)
    if name == "product_performance":
        return engine.product_performance(a["account_id"], a["start_date"], a["end_date"],
                                          a.get("limit", 100), acct)
    if name == "insert_product_input":
        return engine.insert_product_input(a["account_id"], a["data_source"],
                                           a["product_input"], acct)
    if name == "update_product_input":
        return engine.update_product_input(a["product_input_name"], a["data_source"],
                                           a["product_input"], a["update_mask"], acct)
    if name == "delete_product_input":
        return engine.delete_product_input(a["product_input_name"], a.get("data_source"), acct)
    if name == "list_inventories":
        return engine.list_inventories(a["account_id"], a["product_id"], a.get("kind", "regional"),
                                       a.get("page_size", 100), a.get("page_token"), acct)
    if name == "insert_inventory":
        return engine.insert_inventory(a["account_id"], a["product_id"], a["body"],
                                       a.get("kind", "regional"), acct)
    if name == "list_data_sources":
        return engine.list_data_sources(a["account_id"], a.get("page_size", 100),
                                        a.get("page_token"), acct)
    if name == "get_data_source":
        return engine.get_data_source(a["account_id"], a["data_source_id"], acct)
    if name == "create_data_source":
        return engine.create_data_source(a["account_id"], a["body"], acct)
    if name == "update_data_source":
        return engine.update_data_source(a["account_id"], a["data_source_id"], a["body"],
                                         a["update_mask"], acct)
    if name == "delete_data_source":
        return engine.delete_data_source(a["account_id"], a["data_source_id"], acct)
    if name == "fetch_data_source":
        return engine.fetch_data_source(a["account_id"], a["data_source_id"], acct)
    if name == "update_account":
        return engine.update_account(a["account_id"], a["body"], a["update_mask"], acct)
    if name == "patch_account_resource":
        return engine.patch_account_resource(a["account_id"], a["resource"], a["body"],
                                             a["update_mask"], acct)
    if name == "insert_shipping_settings":
        return engine.insert_shipping_settings(a["account_id"], a["body"], acct)
    if name == "list_promotions":
        return engine.list_promotions(a["account_id"], a.get("page_size", 50),
                                      a.get("page_token"), acct)
    if name == "insert_promotion":
        return engine.insert_promotion(a["account_id"], a["body"], a.get("data_source"), acct)
    if name == "list_quotas":
        return engine.list_quotas(a["account_id"], a.get("page_size", 100),
                                  a.get("page_token"), acct)
    if name == "api_request":
        return engine.api_request(a["method"], a["sub_api"], a["path"],
                                  a.get("params"), a.get("body"), acct)
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
