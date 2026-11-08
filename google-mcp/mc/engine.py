"""
Motor de Google Merchant Center — Merchant API (merchantapi.googleapis.com). MULTICUENTA.
Mismo patrón que los MCP de Google Ads / Search Console / Tag Manager / GA4 de Bryan.

MULTICUENTA: cada MC_REFRESH_TOKEN_<label> del .env es una cuenta de login
(p.ej. MC_REFRESH_TOKEN_BRYAN, MC_REFRESH_TOKEN_MARKETING). Cada función acepta
'account' (la etiqueta de login). Si solo hay una, se usa por defecto.
Back-compat: MC_REFRESH_TOKEN (sin sufijo) -> 'default'.

OJO con la nomenclatura:
  - 'account'    = etiqueta de LOGIN del .env  (bryan | academy)
  - 'account_id' = ID de la cuenta de MERCHANT CENTER (p.ej. 5089123456)

Scope: https://www.googleapis.com/auth/content  (lectura Y escritura)

Uso por CLI:  python3 mc/engine.py <comando> [args] [--account <label>]
"""
import os
import sys
import json
import time
import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

CLIENT_ID = os.environ.get("MC_CLIENT_ID", "").strip()
CLIENT_SECRET = os.environ.get("MC_CLIENT_SECRET", "").strip()
BASE = "https://merchantapi.googleapis.com"
_PREFIX = "MC_REFRESH_TOKEN_"

# Merchant API: v1beta se retiró el 28-02-2026, se usa v1. Si una sub-API aún no
# tuviera v1 (404/409), se reintenta con la alternativa.
_VER_PRIMARY = os.environ.get("MC_API_VERSION", "v1").strip() or "v1"
_VER_ALT = "v1beta" if _VER_PRIMARY == "v1" else "v1"

_token_cache = {}


class McError(Exception):
    pass


# ----------------------------------------------------------------------------
# CUENTAS (login)
# ----------------------------------------------------------------------------
def _accounts():
    accts = {}
    for k, v in os.environ.items():
        if k.startswith(_PREFIX) and v.strip():
            accts[k[len(_PREFIX):].lower()] = v.strip()
    single = os.environ.get("MC_REFRESH_TOKEN", "").strip()
    if single and not accts:
        accts["default"] = single
    return accts


def list_login_accounts():
    """Etiquetas de cuenta de login configuradas en el .env."""
    return list(_accounts().keys())


def _label(account=None):
    accts = _accounts()
    if not accts:
        raise McError("No hay refresh tokens en el .env. Genera uno con: "
                      "python3 get_refresh_token.py <etiqueta>")
    if account:
        a = str(account).lower()
        if a not in accts:
            raise McError(f"Cuenta '{account}' no encontrada. Disponibles: {list(accts)}")
        return a
    if len(accts) == 1:
        return next(iter(accts))
    raise McError(f"Hay varias cuentas; indica 'account'. Disponibles: {list(accts)}")


# ----------------------------------------------------------------------------
# NÚCLEO: auth + llamadas REST
# ----------------------------------------------------------------------------
def get_access_token(label, refresh_token):
    now = time.time()
    c = _token_cache.get(label)
    if c and now < c["expires"] - 60:
        return c["token"]
    if not (CLIENT_ID and CLIENT_SECRET):
        raise McError("Faltan MC_CLIENT_ID / MC_CLIENT_SECRET en el .env.")
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
        "refresh_token": refresh_token, "grant_type": "refresh_token",
    })
    if r.status_code != 200:
        raise McError(f"OAuth token HTTP {r.status_code}: {r.text}")
    data = r.json()
    _token_cache[label] = {"token": data["access_token"], "expires": now + data.get("expires_in", 3600)}
    return _token_cache[label]["token"]


def _headers(account=None):
    label = _label(account)
    return {"Authorization": f"Bearer {get_access_token(label, _accounts()[label])}",
            "Content-Type": "application/json"}


def _raw(method, url, account=None, params=None, body=None):
    r = requests.request(method, url, headers=_headers(account), params=params, json=body)
    return r


def _call(method, sub, path, account=None, params=None, body=None):
    """Llama a {BASE}/{sub}/{version}/{path} con fallback de versión v1beta<->v1."""
    last = None
    for ver in (_VER_PRIMARY, _VER_ALT):
        r = _raw(method, f"{BASE}/{sub}/{ver}/{path}", account, params, body)
        if r.status_code < 300:
            return r.json() if r.text.strip() else {"ok": True}
        last = r
        if r.status_code not in (404, 409):  # 409 = version retirada
            break
    raise McError(f"{method} {sub}/{path} HTTP {last.status_code}: {last.text}")


def _acc(account_id):
    """Normaliza 5089123456 | accounts/5089123456 -> 'accounts/5089123456'."""
    a = str(account_id).strip()
    return a if a.startswith("accounts/") else f"accounts/{a}"


def _page(page_size=None, page_token=None, extra=None):
    p = {}
    if page_size:
        p["pageSize"] = page_size
    if page_token:
        p["pageToken"] = page_token
    if extra:
        p.update({k: v for k, v in extra.items() if v is not None})
    return p or None


# ----------------------------------------------------------------------------
# CUENTAS DE MERCHANT CENTER  (sub-API: accounts)
# ----------------------------------------------------------------------------
def list_accounts(page_size=100, page_token=None, filter=None, account=None):
    """Cuentas de Merchant Center accesibles con este login (incluye MCA/multi-cliente)."""
    return _call("GET", "accounts", "accounts", account,
                 params=_page(page_size, page_token, {"filter": filter}))


def get_account(account_id, account=None):
    return _call("GET", "accounts", _acc(account_id), account)


def list_subaccounts(account_id, page_size=200, page_token=None, account=None):
    """Subcuentas de una cuenta multi-cliente (MCA)."""
    return _call("GET", "accounts", f"{_acc(account_id)}:listSubaccounts", account,
                 params=_page(page_size, page_token))


def update_account(account_id, body, update_mask, account=None):
    """PATCH de la cuenta. update_mask p.ej. 'accountName,timeZone'."""
    return _call("PATCH", "accounts", _acc(account_id), account,
                 params={"updateMask": update_mask}, body=body)


# Recursos singleton de una cuenta: GET accounts/{id}/<recurso>
_SINGLETONS = {"businessInfo", "homepage", "shippingSettings", "automaticImprovements",
               "autofeedSettings", "emailPreferences", "businessIdentity"}
# Colecciones de una cuenta: GET accounts/{id}/<recurso>
_COLLECTIONS = {"users", "programs", "regions", "onlineReturnPolicies",
                "termsOfServiceAgreementStates", "issues"}


def get_account_resource(account_id, resource, account=None):
    """Ajuste singleton de la cuenta: businessInfo | homepage | shippingSettings |
    automaticImprovements | autofeedSettings | emailPreferences | businessIdentity."""
    if resource not in _SINGLETONS:
        raise McError(f"Recurso '{resource}' no reconocido. Usa uno de: {sorted(_SINGLETONS)}")
    return _call("GET", "accounts", f"{_acc(account_id)}/{resource}", account)


def patch_account_resource(account_id, resource, body, update_mask, account=None):
    """PATCH de un ajuste singleton de la cuenta (ESCRITURA)."""
    if resource not in _SINGLETONS:
        raise McError(f"Recurso '{resource}' no reconocido. Usa uno de: {sorted(_SINGLETONS)}")
    return _call("PATCH", "accounts", f"{_acc(account_id)}/{resource}", account,
                 params={"updateMask": update_mask}, body=body)


def list_account_resources(account_id, resource, page_size=100, page_token=None, account=None):
    """Colección de la cuenta: users | programs | regions | onlineReturnPolicies |
    termsOfServiceAgreementStates | issues."""
    if resource not in _COLLECTIONS:
        raise McError(f"Recurso '{resource}' no reconocido. Usa uno de: {sorted(_COLLECTIONS)}")
    return _call("GET", "accounts", f"{_acc(account_id)}/{resource}", account,
                 params=_page(page_size, page_token))


def insert_shipping_settings(account_id, body, account=None):
    """Reemplaza la configuración de envíos de la cuenta (ESCRITURA)."""
    return _call("POST", "accounts", f"{_acc(account_id)}/shippingSettings:insert", account, body=body)


# ----------------------------------------------------------------------------
# PRODUCTOS  (sub-API: products)
# ----------------------------------------------------------------------------
def list_products(account_id, page_size=50, page_token=None, account=None):
    """Productos procesados (con su estado y problemas). Nombre: accounts/X/products/es~es~online~SKU."""
    return _call("GET", "products", f"{_acc(account_id)}/products", account,
                 params=_page(page_size, page_token))


def get_product(account_id, product_id, account=None):
    """product_id: 'online~es~es~SKU' o el name completo 'accounts/X/products/...'."""
    pid = str(product_id).strip()
    path = pid if pid.startswith("accounts/") else f"{_acc(account_id)}/products/{pid}"
    return _call("GET", "products", path, account)


def insert_product_input(account_id, data_source, product_input, account=None):
    """Alta/actualización (upsert) de un producto en una fuente de datos (ESCRITURA).
    data_source: 'accounts/X/dataSources/123' o solo el ID numérico.
    product_input: dict con offerId, contentLanguage, feedLabel, channel y attributes."""
    ds = str(data_source).strip()
    if not ds.startswith("accounts/"):
        ds = f"{_acc(account_id)}/dataSources/{ds}"
    return _call("POST", "products", f"{_acc(account_id)}/productInputs:insert", account,
                 params={"dataSource": ds}, body=product_input)


def update_product_input(product_input_name, data_source, product_input, update_mask, account=None):
    """PATCH de un productInput existente (ESCRITURA).
    product_input_name: 'accounts/X/productInputs/online~es~es~SKU'."""
    return _call("PATCH", "products", str(product_input_name).strip(), account,
                 params={"dataSource": data_source, "updateMask": update_mask},
                 body=product_input)


def delete_product_input(product_input_name, data_source=None, account=None):
    """Borra un productInput de una fuente de datos (ESCRITURA, irreversible)."""
    params = {"dataSource": data_source} if data_source else None
    return _call("DELETE", "products", str(product_input_name).strip(), account, params=params)


# ----------------------------------------------------------------------------
# INVENTARIO LOCAL / REGIONAL  (sub-API: inventories)
# ----------------------------------------------------------------------------
def list_inventories(account_id, product_id, kind="regional", page_size=100, page_token=None, account=None):
    """kind: 'regional' | 'local'."""
    res = "regionalInventories" if kind == "regional" else "localInventories"
    pid = str(product_id).strip()
    parent = pid if pid.startswith("accounts/") else f"{_acc(account_id)}/products/{pid}"
    return _call("GET", "inventories", f"{parent}/{res}", account, params=_page(page_size, page_token))


def insert_inventory(account_id, product_id, body, kind="regional", account=None):
    """Alta/actualización de inventario regional o local (ESCRITURA)."""
    res = "regionalInventories" if kind == "regional" else "localInventories"
    pid = str(product_id).strip()
    parent = pid if pid.startswith("accounts/") else f"{_acc(account_id)}/products/{pid}"
    return _call("POST", "inventories", f"{parent}/{res}:insert", account, body=body)


# ----------------------------------------------------------------------------
# FUENTES DE DATOS (feeds)  (sub-API: datasources)
# ----------------------------------------------------------------------------
def list_data_sources(account_id, page_size=100, page_token=None, account=None):
    return _call("GET", "datasources", f"{_acc(account_id)}/dataSources", account,
                 params=_page(page_size, page_token))


def get_data_source(account_id, data_source_id, account=None):
    ds = str(data_source_id).strip()
    path = ds if ds.startswith("accounts/") else f"{_acc(account_id)}/dataSources/{ds}"
    return _call("GET", "datasources", path, account)


def create_data_source(account_id, body, account=None):
    """Crea una fuente de datos, p.ej. una suplementaria (ESCRITURA).
    body p.ej. {"displayName":"Suplementario titulos",
                "supplementalProductDataSource":{"contentLanguage":"es","feedLabel":"ES"}}"""
    return _call("POST", "datasources", f"{_acc(account_id)}/dataSources", account, body=body)


def update_data_source(account_id, data_source_id, body, update_mask, account=None):
    ds = str(data_source_id).strip()
    path = ds if ds.startswith("accounts/") else f"{_acc(account_id)}/dataSources/{ds}"
    return _call("PATCH", "datasources", path, account,
                 params={"updateMask": update_mask}, body=body)


def delete_data_source(account_id, data_source_id, account=None):
    """Borra una fuente de datos (ESCRITURA, irreversible)."""
    ds = str(data_source_id).strip()
    path = ds if ds.startswith("accounts/") else f"{_acc(account_id)}/dataSources/{ds}"
    return _call("DELETE", "datasources", path, account)


def fetch_data_source(account_id, data_source_id, account=None):
    """Fuerza la descarga inmediata de un feed por URL (ESCRITURA)."""
    ds = str(data_source_id).strip()
    path = ds if ds.startswith("accounts/") else f"{_acc(account_id)}/dataSources/{ds}"
    return _call("POST", "datasources", f"{path}:fetch", account, body={})


# ----------------------------------------------------------------------------
# INFORMES  (sub-API: reports)
# ----------------------------------------------------------------------------
def run_report(account_id, query, page_size=100, page_token=None, account=None):
    """Consulta en Merchant Center Query Language. Tablas principales:
      product_view                       -> catálogo + item_issues + estado de aprobación
      product_performance_view           -> clics, impresiones, conversiones (requiere WHERE date)
      price_competitiveness_product_view -> tu precio vs benchmark del mercado
      price_insights_product_view        -> precio sugerido y uplift previsto
      best_sellers_product_cluster_view  -> más vendidos por categoría/marca
      competitive_visibility_competitor_view -> competidores que aparecen contigo
    """
    body = {"query": query, "pageSize": page_size}
    if page_token:
        body["pageToken"] = page_token
    return _call("POST", "reports", f"{_acc(account_id)}/reports:search", account, body=body)


def product_issues(account_id, limit=200, account=None):
    """Atajo: productos con problemas/desaprobaciones (product_view)."""
    q = ("SELECT id, offer_id, title, brand, price, availability, item_issues, "
         "aggregated_reporting_context_status, click_potential "
         f"FROM product_view LIMIT {int(limit)}")
    return run_report(account_id, q, page_size=min(int(limit), 250), account=account)


def product_performance(account_id, start_date, end_date, limit=100, account=None):
    """Atajo: rendimiento por producto entre dos fechas 'YYYY-MM-DD'."""
    q = ("SELECT offer_id, title, brand, clicks, impressions, click_through_rate, "
         "conversions, conversion_value FROM product_performance_view "
         f"WHERE date BETWEEN '{start_date}' AND '{end_date}' "
         f"ORDER BY clicks DESC LIMIT {int(limit)}")
    return run_report(account_id, q, page_size=min(int(limit), 250), account=account)


# ----------------------------------------------------------------------------
# PROMOCIONES  (sub-API: promotions)  y  CUOTAS  (sub-API: quota)
# ----------------------------------------------------------------------------
def list_promotions(account_id, page_size=50, page_token=None, account=None):
    return _call("GET", "promotions", f"{_acc(account_id)}/promotions", account,
                 params=_page(page_size, page_token))


def insert_promotion(account_id, body, data_source=None, account=None):
    """Crea/actualiza una promoción (ESCRITURA)."""
    params = {"dataSource": data_source} if data_source else None
    return _call("POST", "promotions", f"{_acc(account_id)}/promotions:insert", account,
                 params=params, body=body)


def list_quotas(account_id, page_size=100, page_token=None, account=None):
    """Consumo de cuota de la API por grupo/método."""
    return _call("GET", "quota", f"{_acc(account_id)}/quotas", account,
                 params=_page(page_size, page_token))


# ----------------------------------------------------------------------------
# ESCAPE HATCH: cualquier endpoint de Merchant API no cubierto arriba
# ----------------------------------------------------------------------------
def api_request(method, sub_api, path, params=None, body=None, account=None):
    """Llamada cruda a {BASE}/{sub_api}/{version}/{path}.
    sub_api: accounts | products | inventories | datasources | reports | promotions |
             quota | conversions | notifications | lfp | issueresolution | ordertracking"""
    return _call(method.upper(), sub_api, path.lstrip("/"), account, params=params, body=body)


# ----------------------------------------------------------------------------
# CLI mínimo
# ----------------------------------------------------------------------------
def _main(argv):
    acct = None
    if "--account" in argv:
        i = argv.index("--account")
        acct = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    if not argv:
        print("Comandos: logins | accounts | account <accId> | subaccounts <accId> | "
              "products <accId> | datasources <accId> | issues <accId> | "
              "perf <accId> <start> <end> | report <accId> \"<query>\"   [--account <label>]")
        return
    cmd = argv[0]
    out = None
    if cmd == "logins":
        out = list_login_accounts()
    elif cmd == "accounts":
        out = list_accounts(account=acct)
    elif cmd == "account":
        out = get_account(argv[1], acct)
    elif cmd == "subaccounts":
        out = list_subaccounts(argv[1], account=acct)
    elif cmd == "products":
        out = list_products(argv[1], account=acct)
    elif cmd == "datasources":
        out = list_data_sources(argv[1], account=acct)
    elif cmd == "issues":
        out = product_issues(argv[1], account=acct)
    elif cmd == "perf":
        out = product_performance(argv[1], argv[2], argv[3], account=acct)
    elif cmd == "report":
        out = run_report(argv[1], argv[2], account=acct)
    else:
        print("Comando desconocido:", cmd)
        return
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    _main(sys.argv[1:])
