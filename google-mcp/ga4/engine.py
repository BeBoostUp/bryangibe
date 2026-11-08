"""
Motor de Google Analytics 4 — LECTURA (Data API v1beta + Admin API v1beta). MULTICUENTA.
Mismo patrón que los MCP de Google Ads / Search Console / Tag Manager de Bryan.

MULTICUENTA: cada GA4_REFRESH_TOKEN_<label> del .env es una cuenta de login
(p.ej. GA4_REFRESH_TOKEN_BRYAN, GA4_REFRESH_TOKEN_MARKETING). Cada función acepta
'account' (la etiqueta). Si solo hay una, se usa por defecto.
Back-compat: GA4_REFRESH_TOKEN (sin sufijo) -> 'default'.

Scope: analytics.readonly.

Uso por CLI:  python3 ga4/engine.py <comando> [args] [--account <label>]
"""
import os
import sys
import json
import time
import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

CLIENT_ID = os.environ.get("GA4_CLIENT_ID", "").strip()
CLIENT_SECRET = os.environ.get("GA4_CLIENT_SECRET", "").strip()
DATA = "https://analyticsdata.googleapis.com/v1beta"
ADMIN = "https://analyticsadmin.googleapis.com/v1beta"
_PREFIX = "GA4_REFRESH_TOKEN_"

_token_cache = {}


class Ga4Error(Exception):
    pass


# ----------------------------------------------------------------------------
# CUENTAS (login)
# ----------------------------------------------------------------------------
def _accounts():
    accts = {}
    for k, v in os.environ.items():
        if k.startswith(_PREFIX) and v.strip():
            accts[k[len(_PREFIX):].lower()] = v.strip()
    single = os.environ.get("GA4_REFRESH_TOKEN", "").strip()
    if single and not accts:
        accts["default"] = single
    return accts


def list_login_accounts():
    """Etiquetas de cuenta de login configuradas en el .env."""
    return list(_accounts().keys())


def _label(account=None):
    accts = _accounts()
    if not accts:
        raise Ga4Error("No hay refresh tokens en el .env. Genera uno con: "
                       "python3 get_refresh_token.py <etiqueta>")
    if account:
        a = str(account).lower()
        if a not in accts:
            raise Ga4Error(f"Cuenta '{account}' no encontrada. Disponibles: {list(accts)}")
        return a
    if len(accts) == 1:
        return next(iter(accts))
    raise Ga4Error(f"Hay varias cuentas; indica 'account'. Disponibles: {list(accts)}")


# ----------------------------------------------------------------------------
# NÚCLEO: auth + llamadas REST
# ----------------------------------------------------------------------------
def get_access_token(label, refresh_token):
    now = time.time()
    c = _token_cache.get(label)
    if c and now < c["expires"] - 60:
        return c["token"]
    if not (CLIENT_ID and CLIENT_SECRET):
        raise Ga4Error("Faltan GA4_CLIENT_ID / GA4_CLIENT_SECRET en el .env.")
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
        "refresh_token": refresh_token, "grant_type": "refresh_token",
    })
    if r.status_code != 200:
        raise Ga4Error(f"OAuth token HTTP {r.status_code}: {r.text}")
    data = r.json()
    _token_cache[label] = {"token": data["access_token"], "expires": now + data.get("expires_in", 3600)}
    return _token_cache[label]["token"]


def _headers(account=None):
    label = _label(account)
    return {"Authorization": f"Bearer {get_access_token(label, _accounts()[label])}",
            "Content-Type": "application/json"}


def _get(url, account=None, params=None):
    r = requests.get(url, headers=_headers(account), params=params)
    if r.status_code != 200:
        raise Ga4Error(f"GET {url} HTTP {r.status_code}: {r.text}")
    return r.json()


def _post(url, account=None, body=None):
    r = requests.post(url, headers=_headers(account), json=body or {})
    if r.status_code != 200:
        raise Ga4Error(f"POST {url} HTTP {r.status_code}: {r.text}")
    return r.json()


def _pid(property_id):
    return str(property_id).replace("properties/", "").strip()


# ----------------------------------------------------------------------------
# ADMIN API — descubrimiento
# ----------------------------------------------------------------------------
def list_accounts(account=None):
    return _get(f"{ADMIN}/accounts", account).get("accounts", [])


def list_properties(account_id, account=None):
    aid = str(account_id).replace("accounts/", "").strip()
    return _get(f"{ADMIN}/properties", account,
                params={"filter": f"parent:accounts/{aid}"}).get("properties", [])


def get_property(property_id, account=None):
    return _get(f"{ADMIN}/properties/{_pid(property_id)}", account)


def list_data_streams(property_id, account=None):
    return _get(f"{ADMIN}/properties/{_pid(property_id)}/dataStreams", account).get("dataStreams", [])


def list_key_events(property_id, account=None):
    return _get(f"{ADMIN}/properties/{_pid(property_id)}/keyEvents", account).get("keyEvents", [])


# ----------------------------------------------------------------------------
# DATA API — informes
# ----------------------------------------------------------------------------
def run_report(property_id, metrics, dimensions=None, start_date="28daysAgo",
               end_date="today", limit=100, order_bys=None, dimension_filter=None, account=None):
    body = {"dateRanges": [{"startDate": start_date, "endDate": end_date}],
            "metrics": [{"name": m} for m in metrics], "limit": limit}
    if dimensions:
        body["dimensions"] = [{"name": d} for d in dimensions]
    if order_bys:
        body["orderBys"] = order_bys
    if dimension_filter:
        body["dimensionFilter"] = dimension_filter
    return _post(f"{DATA}/properties/{_pid(property_id)}:runReport", account, body)


def run_realtime_report(property_id, metrics, dimensions=None, limit=100, account=None):
    body = {"metrics": [{"name": m} for m in metrics], "limit": limit}
    if dimensions:
        body["dimensions"] = [{"name": d} for d in dimensions]
    return _post(f"{DATA}/properties/{_pid(property_id)}:runRealtimeReport", account, body)


def get_metadata(property_id, account=None):
    return _get(f"{DATA}/properties/{_pid(property_id)}/metadata", account)


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
        print("Comandos: logins | accounts | properties <accId> | property <propId> | "
              "streams <propId> | keyevents <propId> | metadata <propId> | "
              "report <propId> <metric1,metric2> [dim1,dim2]   [--account <label>]")
        return
    cmd = argv[0]
    if cmd == "logins":
        print(json.dumps(list_login_accounts(), indent=2, ensure_ascii=False))
    elif cmd == "accounts":
        print(json.dumps(list_accounts(acct), indent=2, ensure_ascii=False))
    elif cmd == "properties":
        print(json.dumps(list_properties(argv[1], acct), indent=2, ensure_ascii=False))
    elif cmd == "property":
        print(json.dumps(get_property(argv[1], acct), indent=2, ensure_ascii=False))
    elif cmd == "streams":
        print(json.dumps(list_data_streams(argv[1], acct), indent=2, ensure_ascii=False))
    elif cmd == "keyevents":
        print(json.dumps(list_key_events(argv[1], acct), indent=2, ensure_ascii=False))
    elif cmd == "metadata":
        print(json.dumps(get_metadata(argv[1], acct), indent=2, ensure_ascii=False))
    elif cmd == "report":
        mets = argv[2].split(",")
        dims = argv[3].split(",") if len(argv) > 3 else None
        print(json.dumps(run_report(argv[1], mets, dims, account=acct), indent=2, ensure_ascii=False))
    else:
        print("Comando desconocido:", cmd)


if __name__ == "__main__":
    _main(sys.argv[1:])
