"""
Motor de Google Search Console API para Bryan — LECTURA + ESCRITURA de sitemaps.
MULTI-CUENTA: soporta varias cuentas de Google a la vez. Cada propiedad se
consulta con el token de la cuenta que la posee (resolución automática).

Reutiliza el MISMO cliente OAuth del proyecto de Google Ads (client_id/secret),
con un refresh token por cuenta. Credenciales en el .env:
    GSC_REFRESH_TOKEN_<ETIQUETA>=...

Un login por cuenta = todas las propiedades de esa cuenta. list_sites fusiona todas.

Uso como librería:  from gsc.gsc import list_sites, search_analytics, ...
Uso por CLI:        python3 gsc/gsc.py <comando> [args]
"""
import os
import sys
import json
import time
import datetime
import urllib.parse
import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

CLIENT_ID = os.environ.get("GSC_CLIENT_ID", "").strip()
CLIENT_SECRET = os.environ.get("GSC_CLIENT_SECRET", "").strip()

BASE = "https://searchconsole.googleapis.com/webmasters/v3"
INSPECT_URL = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"

_PREFIX = "GSC_REFRESH_TOKEN_"

_token_cache = {}          # label -> {"token": str, "expires": float}
_site_account = {}         # site_url -> label (mejor cuenta para leer, resuelto en list_sites)
_sites_loaded = False

# Ranking de permisos: mayor = mejor para leer datos. 'unverified' no puede consultar.
_PERM_RANK = {"siteOwner": 4, "siteFullUser": 3, "siteRestrictedUser": 2, "siteUnverifiedUser": 1}


class GscError(Exception):
    pass


# ----------------------------------------------------------------------------
# CUENTAS
# ----------------------------------------------------------------------------
def _accounts():
    """Descubre las cuentas del .env: cada GSC_REFRESH_TOKEN_<label> con valor.
    Back-compat: GSC_REFRESH_TOKEN (sin sufijo) se toma como cuenta 'default'."""
    accts = {}
    for k, v in os.environ.items():
        if k.startswith(_PREFIX) and v.strip():
            label = k[len(_PREFIX):].lower()
            accts[label] = v.strip()
    single = os.environ.get("GSC_REFRESH_TOKEN", "").strip()
    if single and not accts:
        accts["default"] = single
    return accts


# ----------------------------------------------------------------------------
# NÚCLEO: auth + llamadas
# ----------------------------------------------------------------------------
def get_access_token(label, refresh_token):
    now = time.time()
    c = _token_cache.get(label)
    if c and now < c["expires"] - 60:
        return c["token"]
    if not (CLIENT_ID and CLIENT_SECRET):
        raise GscError("Faltan GSC_CLIENT_ID / GSC_CLIENT_SECRET en el .env.")
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
        "refresh_token": refresh_token, "grant_type": "refresh_token",
    })
    r.raise_for_status()
    data = r.json()
    _token_cache[label] = {"token": data["access_token"], "expires": now + data.get("expires_in", 3600)}
    return _token_cache[label]["token"]


def _headers(label):
    accts = _accounts()
    if label not in accts:
        raise GscError(f"Cuenta '{label}' no encontrada en el .env. Disponibles: {list(accts) or 'ninguna'}.")
    return {
        "Authorization": f"Bearer {get_access_token(label, accts[label])}",
        "Content-Type": "application/json",
    }


def _enc(site_url):
    """Codifica el siteUrl para la ruta. Domain property: 'sc-domain:example.com'.
    URL-prefix: 'https://example.com/'."""
    return urllib.parse.quote(site_url, safe="")


def _default_dates():
    """Rango por defecto: últimos 28 días (GSC va con ~2-3 días de retraso)."""
    end = datetime.date.today() - datetime.timedelta(days=3)
    start = end - datetime.timedelta(days=27)
    return start.isoformat(), end.isoformat()


def _resolve_account(site_url, account=None):
    """Devuelve la etiqueta de cuenta que posee la propiedad.
    Si se pasa 'account' explícito, lo respeta. Si no, usa el mapa de list_sites."""
    if account:
        return account.lower()
    global _sites_loaded
    if not _sites_loaded:
        try:
            list_sites()
        except Exception:
            pass
    if site_url in _site_account:
        return _site_account[site_url]
    # Fallback: si solo hay una cuenta, úsala
    accts = _accounts()
    if len(accts) == 1:
        return next(iter(accts))
    raise GscError(f"No sé qué cuenta posee '{site_url}'. Pásalo con 'account', o revisa list_sites.")


# ----------------------------------------------------------------------------
# LECTURA
# ----------------------------------------------------------------------------
def list_sites(account=None):
    """Todas las propiedades accesibles, fusionando TODAS las cuentas.
    Cada entrada lleva 'account' (la etiqueta de la cuenta que la ve)."""
    global _sites_loaded
    accts = _accounts()
    if not accts:
        raise GscError("No hay cuentas configuradas. Añade GSC_REFRESH_TOKEN_<etiqueta> al .env y genera el token.")
    if account:
        account = account.lower()
        accts = {account: accts.get(account)}
        if accts[account] is None:
            raise GscError(f"Cuenta '{account}' no encontrada.")
    merged = {}   # site_url -> {"site_url", "best_permission", "accounts": {label: perm}}
    errors = {}
    for label in accts:
        try:
            r = requests.get(f"{BASE}/sites", headers=_headers(label))
            if r.status_code != 200:
                errors[label] = f"HTTP {r.status_code}: {r.text}"
                continue
            for e in r.json().get("siteEntry", []):
                su = e.get("siteUrl")
                perm = e.get("permissionLevel")
                entry = merged.setdefault(su, {"site_url": su, "accounts": {}})
                entry["accounts"][label] = perm
                # La mejor cuenta para leer esta propiedad = mayor rango de permiso
                prev = _site_account.get(su)
                if prev is None or _PERM_RANK.get(perm, 0) > _PERM_RANK.get(entry["accounts"].get(prev, ""), 0):
                    _site_account[su] = label
        except Exception as ex:
            errors[label] = str(ex)
    # Consolidar salida: una fila por propiedad, con la mejor cuenta y su permiso
    sites = []
    for su, entry in merged.items():
        best = _site_account.get(su)
        sites.append({
            "site_url": su,
            "account": best,
            "permission_level": entry["accounts"].get(best),
            "seen_in": entry["accounts"],
        })
    sites.sort(key=lambda s: s["site_url"])
    if account is None:
        _sites_loaded = True
    result = {"count": len(sites), "accounts": list(accts), "sites": sites}
    if errors:
        result["errors"] = errors
    return result


def search_analytics(site_url, start_date=None, end_date=None, dimensions=None,
                     row_limit=1000, start_row=0, search_type="web",
                     data_state=None, aggregation_type=None, filters=None, account=None):
    """Datos de rendimiento (clicks, impresiones, CTR, posición).

    dimensions: lista de ['query','page','country','device','date','searchAppearance'].
    search_type: web | image | video | news | discover | googleNews.
    data_state: 'all' incluye datos frescos (incl. no finalizados); por defecto 'final'.
    filters: lista de {dimension, operator, expression}.
    account: etiqueta de cuenta (opcional; se resuelve solo si se omite).
    """
    label = _resolve_account(site_url, account)
    if not start_date or not end_date:
        d_start, d_end = _default_dates()
        start_date = start_date or d_start
        end_date = end_date or d_end
    body = {
        "startDate": start_date,
        "endDate": end_date,
        "dimensions": dimensions or [],
        "rowLimit": row_limit,
        "startRow": start_row,
        "type": search_type,
    }
    if data_state:
        body["dataState"] = data_state
    if aggregation_type:
        body["aggregationType"] = aggregation_type
    if filters:
        body["dimensionFilterGroups"] = [{"groupType": "and", "filters": filters}]
    url = f"{BASE}/sites/{_enc(site_url)}/searchAnalytics/query"
    r = requests.post(url, headers=_headers(label), json=body)
    if r.status_code != 200:
        raise GscError(f"search_analytics HTTP {r.status_code}: {r.text}")
    rows = r.json().get("rows", [])
    dims = dimensions or []
    out = []
    for row in rows:
        item = {}
        keys = row.get("keys", [])
        for i, dim in enumerate(dims):
            item[dim] = keys[i] if i < len(keys) else None
        item["clicks"] = row.get("clicks")
        item["impressions"] = row.get("impressions")
        item["ctr"] = round(row.get("ctr", 0), 4)
        item["position"] = round(row.get("position", 0), 2)
        out.append(item)
    return {"site_url": site_url, "account": label, "start_date": start_date, "end_date": end_date,
            "search_type": search_type, "dimensions": dims, "row_count": len(out), "rows": out}


def top_queries(site_url, start_date=None, end_date=None, row_limit=50, search_type="web", filters=None, account=None):
    """Atajo: mejores queries por clicks."""
    return search_analytics(site_url, start_date, end_date, dimensions=["query"],
                            row_limit=row_limit, search_type=search_type, filters=filters, account=account)


def top_pages(site_url, start_date=None, end_date=None, row_limit=50, search_type="web", filters=None, account=None):
    """Atajo: mejores páginas por clicks."""
    return search_analytics(site_url, start_date, end_date, dimensions=["page"],
                            row_limit=row_limit, search_type=search_type, filters=filters, account=account)


def list_sitemaps(site_url, account=None):
    """Lista los sitemaps enviados de una propiedad."""
    label = _resolve_account(site_url, account)
    r = requests.get(f"{BASE}/sites/{_enc(site_url)}/sitemaps", headers=_headers(label))
    if r.status_code != 200:
        raise GscError(f"list_sitemaps HTTP {r.status_code}: {r.text}")
    return r.json().get("sitemap", [])


def inspect_url(site_url, inspection_url, language_code="es-ES", account=None):
    """URL Inspection: estado de indexación, cobertura, mobile usability, rich results."""
    label = _resolve_account(site_url, account)
    body = {"inspectionUrl": inspection_url, "siteUrl": site_url, "languageCode": language_code}
    r = requests.post(INSPECT_URL, headers=_headers(label), json=body)
    if r.status_code != 200:
        raise GscError(f"inspect_url HTTP {r.status_code}: {r.text}")
    return r.json().get("inspectionResult", {})


# ----------------------------------------------------------------------------
# ESCRITURA (sitemaps)
# ----------------------------------------------------------------------------
def submit_sitemap(site_url, feedpath, account=None):
    """Envía (o re-envía) un sitemap. feedpath: URL completa del sitemap."""
    label = _resolve_account(site_url, account)
    url = f"{BASE}/sites/{_enc(site_url)}/sitemaps/{_enc(feedpath)}"
    r = requests.put(url, headers=_headers(label))
    if r.status_code not in (200, 204):
        raise GscError(f"submit_sitemap HTTP {r.status_code}: {r.text}")
    return {"ok": True, "submitted": feedpath, "site_url": site_url, "account": label}


def delete_sitemap(site_url, feedpath, account=None):
    """Elimina un sitemap enviado."""
    label = _resolve_account(site_url, account)
    url = f"{BASE}/sites/{_enc(site_url)}/sitemaps/{_enc(feedpath)}"
    r = requests.delete(url, headers=_headers(label))
    if r.status_code not in (200, 204):
        raise GscError(f"delete_sitemap HTTP {r.status_code}: {r.text}")
    return {"ok": True, "deleted": feedpath, "site_url": site_url, "account": label}


# ----------------------------------------------------------------------------
# CLI para pruebas rápidas
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "sites"
    try:
        if cmd == "sites":
            print(json.dumps(list_sites(), ensure_ascii=False, indent=2))
        elif cmd == "queries":
            print(json.dumps(top_queries(sys.argv[2]), ensure_ascii=False, indent=2))
        elif cmd == "pages":
            print(json.dumps(top_pages(sys.argv[2]), ensure_ascii=False, indent=2))
        elif cmd == "sitemaps":
            print(json.dumps(list_sitemaps(sys.argv[2]), ensure_ascii=False, indent=2))
        elif cmd == "inspect":
            print(json.dumps(inspect_url(sys.argv[2], sys.argv[3]), ensure_ascii=False, indent=2))
        else:
            print(f"Comando desconocido: {cmd}. Usa: sites | queries <site> | pages <site> | sitemaps <site> | inspect <site> <url>")
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)
