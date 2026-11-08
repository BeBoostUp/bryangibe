"""
Motor de Google Tag Manager API v2 — LECTURA + ESCRITURA. MULTICUENTA.
Mismo patrón que los MCP de Google Ads / Search Console / GA4 de Bryan: Python
puro, REST, OAuth por refresh token, credenciales en el .env del repo.

MULTICUENTA: cada GTM_REFRESH_TOKEN_<label> del .env es una cuenta de login
(p.ej. GTM_REFRESH_TOKEN_BRYAN, GTM_REFRESH_TOKEN_MARKETING). Cada función acepta
'account' (la etiqueta en minúsculas). Si solo hay una, se usa por defecto.
Back-compat: GTM_REFRESH_TOKEN (sin sufijo) -> cuenta 'default'.

SEGURIDAD: nada se publica solo (workspace -> create_version -> publish_version).

Uso por CLI:  python3 gtm/engine.py <comando> [args] [--account <label>]
"""
import os
import sys
import json
import time
import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

CLIENT_ID = os.environ.get("GTM_CLIENT_ID", "").strip()
CLIENT_SECRET = os.environ.get("GTM_CLIENT_SECRET", "").strip()
BASE = "https://tagmanager.googleapis.com/tagmanager/v2"
_PREFIX = "GTM_REFRESH_TOKEN_"

_token_cache = {}


class GtmError(Exception):
    pass


# ----------------------------------------------------------------------------
# CUENTAS (login)
# ----------------------------------------------------------------------------
def _accounts():
    """Descubre las cuentas del .env: cada GTM_REFRESH_TOKEN_<label> con valor.
    Back-compat: GTM_REFRESH_TOKEN (sin sufijo) -> 'default'."""
    accts = {}
    for k, v in os.environ.items():
        if k.startswith(_PREFIX) and v.strip():
            accts[k[len(_PREFIX):].lower()] = v.strip()
    single = os.environ.get("GTM_REFRESH_TOKEN", "").strip()
    if single and not accts:
        accts["default"] = single
    return accts


def list_login_accounts():
    """Devuelve las etiquetas de cuenta configuradas en el .env."""
    return list(_accounts().keys())


def _label(account=None):
    accts = _accounts()
    if not accts:
        raise GtmError("No hay refresh tokens en el .env. Genera uno con: "
                       "python3 get_refresh_token.py <etiqueta>")
    if account:
        a = str(account).lower()
        if a not in accts:
            raise GtmError(f"Cuenta '{account}' no encontrada. Disponibles: {list(accts)}")
        return a
    if len(accts) == 1:
        return next(iter(accts))
    raise GtmError(f"Hay varias cuentas; indica 'account'. Disponibles: {list(accts)}")


# ----------------------------------------------------------------------------
# NÚCLEO: auth + llamadas REST
# ----------------------------------------------------------------------------
def get_access_token(label, refresh_token):
    now = time.time()
    c = _token_cache.get(label)
    if c and now < c["expires"] - 60:
        return c["token"]
    if not (CLIENT_ID and CLIENT_SECRET):
        raise GtmError("Faltan GTM_CLIENT_ID / GTM_CLIENT_SECRET en el .env.")
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
        "refresh_token": refresh_token, "grant_type": "refresh_token",
    })
    if r.status_code != 200:
        raise GtmError(f"OAuth token HTTP {r.status_code}: {r.text}")
    data = r.json()
    _token_cache[label] = {"token": data["access_token"], "expires": now + data.get("expires_in", 3600)}
    return _token_cache[label]["token"]


def _headers(account=None):
    label = _label(account)
    return {"Authorization": f"Bearer {get_access_token(label, _accounts()[label])}",
            "Content-Type": "application/json"}


def _url(path):
    if str(path).startswith("http"):
        return path
    return BASE + "/" + str(path).lstrip("/")


def _get(path, account=None, params=None):
    r = requests.get(_url(path), headers=_headers(account), params=params)
    if r.status_code != 200:
        raise GtmError(f"GET {path} HTTP {r.status_code}: {r.text}")
    return r.json()


def _post(path, account=None, body=None):
    r = requests.post(_url(path), headers=_headers(account), json=body or {})
    if r.status_code not in (200, 201):
        raise GtmError(f"POST {path} HTTP {r.status_code}: {r.text}")
    return r.json() if r.text else {}


def _delete(path, account=None):
    r = requests.delete(_url(path), headers=_headers(account))
    if r.status_code not in (200, 204):
        raise GtmError(f"DELETE {path} HTTP {r.status_code}: {r.text}")
    return {"deleted": path}


# ----------------------------------------------------------------------------
# LECTURA
# ----------------------------------------------------------------------------
def list_accounts(account=None):
    return _get("accounts", account).get("account", [])


def list_containers(account_id, account=None):
    return _get(f"accounts/{account_id}/containers", account).get("container", [])


def list_workspaces(account_id, container_id, account=None):
    return _get(f"accounts/{account_id}/containers/{container_id}/workspaces", account).get("workspace", [])


def list_tags(workspace_path, account=None):
    return _get(f"{workspace_path}/tags", account).get("tag", [])


def list_triggers(workspace_path, account=None):
    return _get(f"{workspace_path}/triggers", account).get("trigger", [])


def list_variables(workspace_path, account=None):
    return _get(f"{workspace_path}/variables", account).get("variable", [])


def get_resource(path, account=None):
    return _get(path, account)


# ----------------------------------------------------------------------------
# ESCRITURA (viven en un workspace hasta versionar + publicar)
# ----------------------------------------------------------------------------
def create_workspace(account_id, container_id, name, description=None, account=None):
    body = {"name": name}
    if description:
        body["description"] = description
    return _post(f"accounts/{account_id}/containers/{container_id}/workspaces", account, body)


def create_variable(workspace_path, name, type, parameter=None, account=None):
    body = {"name": name, "type": type}
    if parameter:
        body["parameter"] = parameter
    return _post(f"{workspace_path}/variables", account, body)


def create_trigger(workspace_path, name, type, extra=None, account=None):
    body = {"name": name, "type": type}
    if extra:
        body.update(extra)
    return _post(f"{workspace_path}/triggers", account, body)


def create_tag(workspace_path, name, type, parameter=None, firing_trigger_id=None,
               extra=None, account=None):
    body = {"name": name, "type": type}
    if parameter:
        body["parameter"] = parameter
    if firing_trigger_id:
        body["firingTriggerId"] = firing_trigger_id
    if extra:
        body.update(extra)
    return _post(f"{workspace_path}/tags", account, body)


def create_version(workspace_path, name=None, notes=None, account=None):
    body = {}
    if name:
        body["name"] = name
    if notes:
        body["notes"] = notes
    return _post(f"{workspace_path}:create_version", account, body)


def publish_version(version_path, account=None):
    return _post(f"{version_path}:publish", account, {})


def delete_resource(path, account=None):
    return _delete(path, account)


# ----------------------------------------------------------------------------
# ATAJOS
# ----------------------------------------------------------------------------
def create_datalayer_variable(workspace_path, name, data_layer_name=None, version=2, account=None):
    dl = data_layer_name or name
    param = [{"type": "integer", "key": "dataLayerVersion", "value": str(version)},
             {"type": "template", "key": "name", "value": dl}]
    return create_variable(workspace_path, name, "v", param, account)


def create_custom_event_trigger(workspace_path, name, event_name, account=None):
    extra = {"customEventFilter": [{"type": "equals", "parameter": [
        {"type": "template", "key": "arg0", "value": "{{_event}}"},
        {"type": "template", "key": "arg1", "value": event_name}]}]}
    return create_trigger(workspace_path, name, "customEvent", extra, account)


def create_google_ads_conversion_tag(workspace_path, name, conversion_id, conversion_label,
                                     firing_trigger_id, account=None):
    param = [{"type": "template", "key": "conversionId", "value": str(conversion_id)},
             {"type": "template", "key": "conversionLabel", "value": conversion_label}]
    return create_tag(workspace_path, name, "awct", param, firing_trigger_id, account=account)


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
        print("Comandos: logins | accounts | containers <accId> | workspaces <accId> <contId> | "
              "tags <ws_path> | triggers <ws_path> | variables <ws_path> | get <path>   [--account <label>]")
        return
    cmd = argv[0]
    if cmd == "logins":
        print(json.dumps(list_login_accounts(), indent=2, ensure_ascii=False))
    elif cmd == "accounts":
        print(json.dumps(list_accounts(acct), indent=2, ensure_ascii=False))
    elif cmd == "containers":
        print(json.dumps(list_containers(argv[1], acct), indent=2, ensure_ascii=False))
    elif cmd == "workspaces":
        print(json.dumps(list_workspaces(argv[1], argv[2], acct), indent=2, ensure_ascii=False))
    elif cmd == "tags":
        print(json.dumps(list_tags(argv[1], acct), indent=2, ensure_ascii=False))
    elif cmd == "triggers":
        print(json.dumps(list_triggers(argv[1], acct), indent=2, ensure_ascii=False))
    elif cmd == "variables":
        print(json.dumps(list_variables(argv[1], acct), indent=2, ensure_ascii=False))
    elif cmd == "get":
        print(json.dumps(get_resource(argv[1], acct), indent=2, ensure_ascii=False))
    else:
        print("Comando desconocido:", cmd)


if __name__ == "__main__":
    _main(sys.argv[1:])
