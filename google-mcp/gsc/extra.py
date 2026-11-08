"""
Extensión del motor de Search Console: cobertura COMPLETA de la API.
  - Sitios: get / add / delete (además de list, ya existente)
  - Sitemaps: get (además de list / submit / delete)
  - api_request: cualquier endpoint (webmasters/v3 o v1/urlInspection)
Se monta en mcp_server.py vía TOOLS + HANDLERS.
"""
import requests
from gsc import engine as gsc

ROOT = "https://searchconsole.googleapis.com"


def _label_for(site_url=None, account=None):
    if account:
        return account.lower()
    if site_url:
        try:
            return gsc._resolve_account(site_url, None)
        except Exception:
            pass
    accts = gsc._accounts()
    if len(accts) == 1:
        return next(iter(accts))
    if "bryan" in accts:
        return "bryan"
    raise gsc.GscError(f"Indica 'account'. Disponibles: {list(accts)}")


def _req(method, path, label, params=None, body=None):
    url = path if path.startswith("http") else ROOT + "/" + path.lstrip("/")
    r = requests.request(method.upper(), url, headers=gsc._headers(label), params=params,
                         json=body, timeout=120)
    if r.status_code >= 400:
        raise gsc.GscError(f"{method.upper()} {path} HTTP {r.status_code}: {r.text[:800]}")
    return r.json() if r.text.strip() else {"ok": True}


def get_site(site_url, account=None):
    label = _label_for(site_url, account)
    return _req("GET", f"webmasters/v3/sites/{gsc._enc(site_url)}", label)


def add_site(site_url, account=None):
    """Añade una propiedad a la cuenta (queda pendiente de verificación si no lo está)."""
    label = _label_for(None, account)
    _req("PUT", f"webmasters/v3/sites/{gsc._enc(site_url)}", label)
    gsc._sites_loaded = False
    return {"ok": True, "added": site_url, "account": label}


def delete_site(site_url, account=None):
    """Quita la propiedad de la cuenta (no borra datos de Google, solo el acceso)."""
    label = _label_for(site_url, account)
    _req("DELETE", f"webmasters/v3/sites/{gsc._enc(site_url)}", label)
    gsc._sites_loaded = False
    return {"ok": True, "removed": site_url, "account": label}


def get_sitemap(site_url, feedpath, account=None):
    label = _label_for(site_url, account)
    return _req("GET", f"webmasters/v3/sites/{gsc._enc(site_url)}/sitemaps/{gsc._enc(feedpath)}", label)


def api_request(method, path, params=None, body=None, account=None, site_url=None):
    """Llamada cruda. path relativo a https://searchconsole.googleapis.com/, p.ej.
    'webmasters/v3/sites' o 'v1/urlInspection/index:inspect'."""
    label = _label_for(site_url, account)
    return _req(method, path, label, params, body)


_SITE = ("siteUrl de la propiedad. Domain property: 'sc-domain:example.com'. "
         "URL-prefix: 'https://example.com/'.")
_ACCT = "Etiqueta de cuenta (opcional; se resuelve sola por propiedad)."
_S = {"type": "string"}

TOOLS = [
    {"name": "get_site",
     "description": "Detalle de una propiedad (siteUrl + permissionLevel).",
     "inputSchema": {"type": "object", "properties": {
         "site_url": {"type": "string", "description": _SITE},
         "account": {"type": "string", "description": _ACCT}}, "required": ["site_url"]}},
    {"name": "add_site",
     "description": ("ESCRITURA: añade una propiedad a la cuenta de login indicada (o la única/bryan). "
                     "Si no está verificada queda como 'siteUnverifiedUser' hasta verificar."),
     "inputSchema": {"type": "object", "properties": {
         "site_url": {"type": "string", "description": _SITE},
         "account": {"type": "string", "description": "Etiqueta de cuenta donde añadirla."}},
         "required": ["site_url"]}},
    {"name": "delete_site",
     "description": "ESCRITURA: quita una propiedad de la cuenta (deja de verse en Search Console para ese login).",
     "inputSchema": {"type": "object", "properties": {
         "site_url": {"type": "string", "description": _SITE},
         "account": {"type": "string", "description": _ACCT}}, "required": ["site_url"]}},
    {"name": "get_sitemap",
     "description": "Detalle de un sitemap enviado (estado, errores, warnings, contenidos, última descarga).",
     "inputSchema": {"type": "object", "properties": {
         "site_url": {"type": "string", "description": _SITE},
         "feedpath": {"type": "string", "description": "URL completa del sitemap."},
         "account": {"type": "string", "description": _ACCT}}, "required": ["site_url", "feedpath"]}},
    {"name": "api_request",
     "description": ("Llamada cruda a la Search Console API para cualquier endpoint. method: GET|POST|PUT|DELETE. "
                     "path relativo a https://searchconsole.googleapis.com/, p.ej. "
                     "'webmasters/v3/sites/sc-domain%3Aexample.com/searchAnalytics/query' o "
                     "'v1/urlInspection/index:inspect'. Codifica el siteUrl con urlencode. "
                     "site_url (opcional) sirve solo para resolver qué cuenta usar."),
     "inputSchema": {"type": "object", "properties": {
         "method": _S, "path": _S, "params": {"type": "object"}, "body": {"type": "object"},
         "site_url": {"type": "string", "description": _SITE},
         "account": {"type": "string", "description": _ACCT}}, "required": ["method", "path"]}},
]

HANDLERS = {
    "get_site": lambda a: get_site(a["site_url"], a.get("account")),
    "add_site": lambda a: add_site(a["site_url"], a.get("account")),
    "delete_site": lambda a: delete_site(a["site_url"], a.get("account")),
    "get_sitemap": lambda a: get_sitemap(a["site_url"], a["feedpath"], a.get("account")),
    "api_request": lambda a: api_request(a["method"], a["path"], a.get("params"), a.get("body"),
                                         a.get("account"), a.get("site_url")),
}
