"""
Extensión GTM: cobertura COMPLETA de la Tag Manager API v2.
  - update/delete de cualquier entidad (con fingerprint automático)
  - carpetas, variables integradas, plantillas, clientes, zonas, transformaciones, gtag config
  - versiones (listar, live, latest, set_latest, undelete, update, delete)
  - workspaces (update, delete, sync, quick_preview, resolve_conflict, status, revert)
  - entornos (crear, editar, borrar, reautorizar)
  - permisos de usuario (listar, crear, editar, borrar)
  - contenedores (crear, editar, borrar, lookup, combine, move_tag_id, snippet) y cuentas (update)
  - destinos (listar, get, link)
  - api_request cruda
Requiere scopes: tagmanager.edit.containers, tagmanager.edit.containerversions, tagmanager.publish,
tagmanager.delete.containers, tagmanager.manage.accounts, tagmanager.manage.users (+ readonly).
    python3 get_refresh_token.py <etiqueta>
"""
import requests
from gtm import engine as gtm


def _req(method, path, account=None, params=None, body=None):
    r = requests.request(method.upper(), gtm._url(path), headers=gtm._headers(account),
                         params=params, json=body, timeout=120)
    if r.status_code >= 400:
        raise gtm.GtmError(f"{method.upper()} {path} HTTP {r.status_code}: {r.text[:900]}")
    return r.json() if r.text.strip() else {"ok": True}


def api_request(method, path, params=None, body=None, account=None):
    return _req(method, path, account, params, body)


# ------------------------------------------------------------- entidades genéricas
def update_entity(path, body, account=None):
    """PUT de tag/trigger/variable/folder/client/zone/template/transformation/gtag_config/
    workspace/container/account/environment/user_permission. Mezcla con el estado actual
    y usa su fingerprint (evita 412)."""
    cur = _req("GET", path, account)
    merged = dict(cur)
    merged.update(body)
    return _req("PUT", path, account, {"fingerprint": cur.get("fingerprint")}, merged)


def revert_entity(path, account=None):
    """Descarta los cambios del workspace en una entidad (tags/{id}:revert, etc.)."""
    return _req("POST", f"{path}:revert", account)


def list_entities(workspace_path, kind, account=None):
    """kind: tags | triggers | variables | folders | built_in_variables | templates | clients |
    zones | transformations | gtag_config"""
    key = {"tags": "tag", "triggers": "trigger", "variables": "variable", "folders": "folder",
           "built_in_variables": "builtInVariable", "templates": "template", "clients": "client",
           "zones": "zone", "transformations": "transformation", "gtag_config": "gtagConfig"}[kind]
    out, token = [], None
    while True:
        d = _req("GET", f"{workspace_path}/{kind}", account, {"pageToken": token} if token else None)
        out.extend(d.get(key, []))
        token = d.get("nextPageToken")
        if not token:
            return out


def create_entity(workspace_path, kind, body, account=None):
    return _req("POST", f"{workspace_path}/{kind}", account, body=body)


# ------------------------------------------------------------- carpetas y built-ins
def create_folder(workspace_path, name, notes=None, account=None):
    body = {"name": name}
    if notes:
        body["notes"] = notes
    return _req("POST", f"{workspace_path}/folders", account, body=body)


def move_to_folder(folder_path, tag_ids=None, trigger_ids=None, variable_ids=None, account=None):
    params = {}
    if tag_ids:
        params["tagId"] = tag_ids
    if trigger_ids:
        params["triggerId"] = trigger_ids
    if variable_ids:
        params["variableId"] = variable_ids
    return _req("POST", f"{folder_path}:move_entities_to_folder", account, params, {})


def folder_entities(folder_path, account=None):
    return _req("GET", f"{folder_path}:entities", account)


def enable_builtin_variables(workspace_path, types, account=None):
    """types p.ej. ['pageUrl','pageHostname','pagePath','referrer','event','clickClasses','clickId',
    'clickTarget','clickUrl','clickText','formId','formClasses','scrollDepthThreshold','videoStatus'...]"""
    return _req("POST", f"{workspace_path}/built_in_variables", account, {"type": types}, {})


def disable_builtin_variables(workspace_path, types, account=None):
    return _req("DELETE", f"{workspace_path}/built_in_variables", account, {"type": types})


# ------------------------------------------------------------- versiones
def list_version_headers(account_id, container_id, include_deleted=False, account=None):
    return _req("GET", f"accounts/{account_id}/containers/{container_id}/version_headers", account,
                {"includeDeleted": include_deleted}).get("containerVersionHeader", [])


def get_version(version_path, account=None):
    return _req("GET", version_path, account)


def get_live_version(account_id, container_id, account=None):
    return _req("GET", f"accounts/{account_id}/containers/{container_id}/versions:live", account)


def get_latest_version_header(account_id, container_id, account=None):
    return _req("GET", f"accounts/{account_id}/containers/{container_id}/version_headers:latest", account)


def set_latest_version(version_path, account=None):
    return _req("POST", f"{version_path}:set_latest", account)


def undelete_version(version_path, account=None):
    return _req("POST", f"{version_path}:undelete", account)


def update_version(version_path, name=None, description=None, account=None):
    cur = _req("GET", version_path, account)
    body = dict(cur)
    if name is not None:
        body["name"] = name
    if description is not None:
        body["description"] = description
    return _req("PUT", version_path, account, {"fingerprint": cur.get("fingerprint")}, body)


def delete_version(version_path, account=None):
    return _req("DELETE", version_path, account)


# ------------------------------------------------------------- workspaces
def update_workspace(workspace_path, name=None, description=None, account=None):
    body = {}
    if name is not None:
        body["name"] = name
    if description is not None:
        body["description"] = description
    return update_entity(workspace_path, body, account)


def delete_workspace(workspace_path, account=None):
    return _req("DELETE", workspace_path, account)


def sync_workspace(workspace_path, account=None):
    return _req("POST", f"{workspace_path}:sync", account)


def quick_preview(workspace_path, account=None):
    return _req("POST", f"{workspace_path}:quick_preview", account)


def workspace_status(workspace_path, account=None):
    """Cambios pendientes y conflictos de merge del workspace."""
    return _req("GET", f"{workspace_path}/status", account)


def resolve_conflict(workspace_path, entity, account=None):
    """entity: objeto Entity con changeStatus y el recurso resuelto (de workspace_status)."""
    return _req("POST", f"{workspace_path}:resolve_conflict", account, body=entity)


# ------------------------------------------------------------- entornos
def list_environments(account_id, container_id, account=None):
    return _req("GET", f"accounts/{account_id}/containers/{container_id}/environments", account).get("environment", [])


def create_environment(account_id, container_id, name, description=None, url=None, enable_debug=None, account=None):
    body = {"name": name}
    if description:
        body["description"] = description
    if url:
        body["url"] = url
    if enable_debug is not None:
        body["enableDebug"] = enable_debug
    return _req("POST", f"accounts/{account_id}/containers/{container_id}/environments", account, body=body)


def reauthorize_environment(environment_path, account=None):
    cur = _req("GET", environment_path, account)
    return _req("POST", f"{environment_path}:reauthorize", account, body=cur)


# ------------------------------------------------------------- usuarios
def list_user_permissions(account_id, account=None):
    return _req("GET", f"accounts/{account_id}/user_permissions", account).get("userPermission", [])


def create_user_permission(account_id, email, account_access="user", container_access=None, account=None):
    """account_access: user | admin. container_access: [{containerId, permission: read|edit|approve|publish|noAccess}]"""
    body = {"emailAddress": email, "accountAccess": {"permission": account_access}}
    if container_access:
        body["containerAccess"] = container_access
    return _req("POST", f"accounts/{account_id}/user_permissions", account, body=body)


def update_user_permission(permission_path, body, account=None):
    cur = _req("GET", permission_path, account)
    merged = dict(cur)
    merged.update(body)
    return _req("PUT", permission_path, account, body=merged)


def delete_user_permission(permission_path, account=None):
    return _req("DELETE", permission_path, account)


# ------------------------------------------------------------- contenedores / cuentas / destinos
def create_container(account_id, name, usage_context=None, domain_names=None, notes=None, account=None):
    """usage_context: ['web'] | ['androidSdk5'] | ['iosSdk5'] | ['server'] | ['amp']"""
    body = {"name": name, "usageContext": usage_context or ["web"]}
    if domain_names:
        body["domainName"] = domain_names
    if notes:
        body["notes"] = notes
    return _req("POST", f"accounts/{account_id}/containers", account, body=body)


def delete_container(container_path, account=None):
    return _req("DELETE", container_path, account)


def lookup_container(destination_id=None, tag_id=None, account=None):
    params = {}
    if destination_id:
        params["destinationId"] = destination_id
    if tag_id:
        params["tagId"] = tag_id
    return _req("GET", "accounts/containers:lookup", account, params)


def container_snippet(container_path, account=None):
    return _req("GET", f"{container_path}:snippet", account)


def combine_containers(container_path, into_container_id, allow_user_permission_feature_update=False,
                       setting_source="current", account=None):
    return _req("POST", f"{container_path}:combine", account,
                {"containerId": into_container_id, "settingSource": setting_source,
                 "allowUserPermissionFeatureUpdate": allow_user_permission_feature_update}, {})


def move_tag_id(container_path, tag_id, tag_name=None, copy_users=False, copy_settings=True,
                copy_terms_of_service=True, allow_user_permission_feature_update=False, account=None):
    params = {"tagId": tag_id, "copyUsers": copy_users, "copySettings": copy_settings,
              "copyTermsOfService": copy_terms_of_service,
              "allowUserPermissionFeatureUpdate": allow_user_permission_feature_update}
    if tag_name:
        params["tagName"] = tag_name
    return _req("POST", f"{container_path}:move_tag_id", account, params, {})


def list_destinations(container_path, account=None):
    return _req("GET", f"{container_path}/destinations", account).get("destination", [])


def link_destination(container_path, destination_id, allow_user_permission_feature_update=False, account=None):
    return _req("POST", f"{container_path}/destinations:link", account,
                {"destinationId": destination_id,
                 "allowUserPermissionFeatureUpdate": allow_user_permission_feature_update}, {})


# ------------------------------------------------------------- atajos GA4
def create_ga4_config_tag(workspace_path, name, measurement_id, firing_trigger_id="2147479553",
                          send_page_view=True, account=None):
    """Etiqueta 'Google tag' (googtag) para GA4. 2147479553 = All Pages / Initialization."""
    param = [{"type": "template", "key": "tagId", "value": measurement_id}]
    if not send_page_view:
        param.append({"type": "list", "key": "configSettingsTable", "list": [
            {"type": "map", "map": [{"type": "template", "key": "parameter", "value": "send_page_view"},
                                    {"type": "template", "key": "parameterValue", "value": "false"}]}]})
    return gtm.create_tag(workspace_path, name, "googtag", param, firing_trigger_id, account=account)


def create_ga4_event_tag(workspace_path, name, measurement_id, event_name, firing_trigger_id,
                         event_params=None, account=None):
    """event_params: {clave: valor} -> parámetros del evento GA4 (gaawe)."""
    param = [{"type": "template", "key": "eventName", "value": event_name},
             {"type": "template", "key": "measurementIdOverride", "value": measurement_id}]
    if event_params:
        param.append({"type": "list", "key": "eventSettingsTable", "list": [
            {"type": "map", "map": [{"type": "template", "key": "parameter", "value": k},
                                    {"type": "template", "key": "parameterValue", "value": str(v)}]}
            for k, v in event_params.items()]})
    return gtm.create_tag(workspace_path, name, "gaawe", param, firing_trigger_id, account=account)


# ------------------------------------------------------------- tools
_AC = "Etiqueta de cuenta de login del .env (bryan | academy). Opcional si solo hay una."
_WS = "path del workspace: accounts/{a}/containers/{c}/workspaces/{w}"
_S = {"type": "string"}
_B = {"type": "boolean"}
_O = {"type": "object"}
_LS = {"type": "array", "items": {"type": "string"}}
_W = {"workspace_path": {"type": "string", "description": _WS}}
_AC2 = {"account_id": _S, "container_id": _S}


def _t(name, desc, props=None, req=None):
    p = dict(props or {})
    p["account"] = {"type": "string", "description": _AC}
    return {"name": name, "description": desc, "inputSchema": {"type": "object", "properties": p, "required": req or []}}


TOOLS = [
    _t("update_entity", ("ESCRITURA: modifica CUALQUIER entidad por su path (tag, trigger, variable, folder, client, zone, "
                         "template, transformation, gtag_config, workspace, container, account, environment). "
                         "body = campos a cambiar; se mezcla con el actual y usa su fingerprint."),
       {"path": _S, "body": _O}, ["path", "body"]),
    _t("revert_entity", "Descarta los cambios del workspace en una entidad (vuelve a la última versión).", {"path": _S}, ["path"]),
    _t("list_entities", "Lista con paginación: kind = tags | triggers | variables | folders | built_in_variables | templates | clients | zones | transformations | gtag_config.",
       dict(_W, kind=_S), ["workspace_path", "kind"]),
    _t("create_entity", "ESCRITURA genérica: crea cualquier entidad (kind + body JSON de la API).", dict(_W, kind=_S, body=_O),
       ["workspace_path", "kind", "body"]),
    _t("create_folder", "ESCRITURA: crea una carpeta en el workspace.", dict(_W, name=_S, notes=_S), ["workspace_path", "name"]),
    _t("move_to_folder", "ESCRITURA: mueve tags/triggers/variables (ids) a una carpeta (folder_path completo).",
       {"folder_path": _S, "tag_ids": _LS, "trigger_ids": _LS, "variable_ids": _LS}, ["folder_path"]),
    _t("folder_entities", "Entidades dentro de una carpeta.", {"folder_path": _S}, ["folder_path"]),
    _t("enable_builtin_variables", "ESCRITURA: activa variables integradas (pageUrl, clickUrl, clickText, formId, scrollDepthThreshold...).",
       dict(_W, types=_LS), ["workspace_path", "types"]),
    _t("disable_builtin_variables", "ESCRITURA: desactiva variables integradas.", dict(_W, types=_LS), ["workspace_path", "types"]),
    _t("list_version_headers", "Versiones del contenedor (cabeceras).", dict(_AC2, include_deleted=_B), ["account_id", "container_id"]),
    _t("get_version", "Versión completa (con todos sus tags/triggers/variables).", {"version_path": _S}, ["version_path"]),
    _t("get_live_version", "Versión publicada actualmente.", _AC2, ["account_id", "container_id"]),
    _t("get_latest_version_header", "Última versión creada.", _AC2, ["account_id", "container_id"]),
    _t("set_latest_version", "ESCRITURA: marca una versión como la última (para nuevos workspaces).", {"version_path": _S}, ["version_path"]),
    _t("undelete_version", "ESCRITURA: recupera una versión borrada.", {"version_path": _S}, ["version_path"]),
    _t("update_version", "ESCRITURA: renombra/describe una versión.", {"version_path": _S, "name": _S, "description": _S}, ["version_path"]),
    _t("delete_version", "ESCRITURA: borra una versión (no la publicada).", {"version_path": _S}, ["version_path"]),
    _t("update_workspace", "ESCRITURA: renombra/describe un workspace.", dict(_W, name=_S, description=_S), ["workspace_path"]),
    _t("delete_workspace", "ESCRITURA: borra un workspace (se pierden sus cambios).", _W, ["workspace_path"]),
    _t("sync_workspace", "ESCRITURA: sincroniza el workspace con la última versión (devuelve conflictos si los hay).", _W, ["workspace_path"]),
    _t("quick_preview", "Vista previa rápida del workspace (compila sin versionar).", _W, ["workspace_path"]),
    _t("workspace_status", "Cambios pendientes y conflictos del workspace.", _W, ["workspace_path"]),
    _t("resolve_conflict", "ESCRITURA: resuelve un conflicto de merge (entity de workspace_status con la resolución).",
       dict(_W, entity=_O), ["workspace_path", "entity"]),
    _t("list_environments", "Entornos del contenedor (live, latest, personalizados).", _AC2, ["account_id", "container_id"]),
    _t("create_environment", "ESCRITURA: crea un entorno personalizado.", dict(_AC2, name=_S, description=_S, url=_S, enable_debug=_B),
       ["account_id", "container_id", "name"]),
    _t("reauthorize_environment", "ESCRITURA: regenera el código de autorización de un entorno.", {"environment_path": _S}, ["environment_path"]),
    _t("list_user_permissions", "Usuarios de la cuenta GTM y sus permisos.", {"account_id": _S}, ["account_id"]),
    _t("create_user_permission", ("ESCRITURA: da acceso a un usuario. account_access: user | admin. "
                                  "container_access: [{containerId, permission: read|edit|approve|publish|noAccess}]"),
       {"account_id": _S, "email": _S, "account_access": _S, "container_access": {"type": "array", "items": _O}},
       ["account_id", "email"]),
    _t("update_user_permission", "ESCRITURA: cambia permisos (permission_path completo; body con accountAccess/containerAccess).",
       {"permission_path": _S, "body": _O}, ["permission_path", "body"]),
    _t("delete_user_permission", "ESCRITURA: quita a un usuario.", {"permission_path": _S}, ["permission_path"]),
    _t("create_container", "ESCRITURA: crea un contenedor. usage_context: ['web'] | ['server'] | ['androidSdk5'] | ['iosSdk5'] | ['amp'].",
       {"account_id": _S, "name": _S, "usage_context": _LS, "domain_names": _LS, "notes": _S}, ["account_id", "name"]),
    _t("delete_container", "ESCRITURA: borra un contenedor (IRREVERSIBLE).", {"container_path": _S}, ["container_path"]),
    _t("lookup_container", "Busca un contenedor por destination_id (G-XXXX / AW-XXXX) o tag_id (GTM-XXXX).", {"destination_id": _S, "tag_id": _S}),
    _t("container_snippet", "Snippet de instalación del contenedor.", {"container_path": _S}, ["container_path"]),
    _t("combine_containers", "ESCRITURA: fusiona un contenedor en otro.", {"container_path": _S, "into_container_id": _S,
       "allow_user_permission_feature_update": _B, "setting_source": _S}, ["container_path", "into_container_id"]),
    _t("move_tag_id", "ESCRITURA: mueve un tag ID (GTM-XXXX) a otro contenedor nuevo.",
       {"container_path": _S, "tag_id": _S, "tag_name": _S, "copy_users": _B, "copy_settings": _B, "copy_terms_of_service": _B,
        "allow_user_permission_feature_update": _B}, ["container_path", "tag_id"]),
    _t("list_destinations", "Destinos (Google tags) vinculados al contenedor.", {"container_path": _S}, ["container_path"]),
    _t("link_destination", "ESCRITURA: vincula un destino (G-XXXX) al contenedor.",
       {"container_path": _S, "destination_id": _S, "allow_user_permission_feature_update": _B}, ["container_path", "destination_id"]),
    _t("create_ga4_config_tag", "ATAJO: etiqueta Google tag (GA4 config) con el measurement_id. Trigger por defecto: Initialization/All Pages.",
       dict(_W, name=_S, measurement_id=_S, firing_trigger_id=_S, send_page_view=_B), ["workspace_path", "name", "measurement_id"]),
    _t("create_ga4_event_tag", "ATAJO: etiqueta de evento GA4 (gaawe) con parámetros.",
       dict(_W, name=_S, measurement_id=_S, event_name=_S, firing_trigger_id=_S, event_params=_O),
       ["workspace_path", "name", "measurement_id", "event_name", "firing_trigger_id"]),
    _t("api_request", ("Llamada cruda a Tag Manager API v2. method: GET|POST|PUT|DELETE. path relativo a "
                       "https://tagmanager.googleapis.com/tagmanager/v2/, p.ej. 'accounts/1/containers/2/workspaces/3/tags'."),
       {"method": _S, "path": _S, "params": _O, "body": _O}, ["method", "path"]),
]

HANDLERS = {
    "update_entity": lambda a: update_entity(a["path"], a["body"], a.get("account")),
    "revert_entity": lambda a: revert_entity(a["path"], a.get("account")),
    "list_entities": lambda a: list_entities(a["workspace_path"], a["kind"], a.get("account")),
    "create_entity": lambda a: create_entity(a["workspace_path"], a["kind"], a["body"], a.get("account")),
    "create_folder": lambda a: create_folder(a["workspace_path"], a["name"], a.get("notes"), a.get("account")),
    "move_to_folder": lambda a: move_to_folder(a["folder_path"], a.get("tag_ids"), a.get("trigger_ids"), a.get("variable_ids"), a.get("account")),
    "folder_entities": lambda a: folder_entities(a["folder_path"], a.get("account")),
    "enable_builtin_variables": lambda a: enable_builtin_variables(a["workspace_path"], a["types"], a.get("account")),
    "disable_builtin_variables": lambda a: disable_builtin_variables(a["workspace_path"], a["types"], a.get("account")),
    "list_version_headers": lambda a: list_version_headers(a["account_id"], a["container_id"], a.get("include_deleted", False), a.get("account")),
    "get_version": lambda a: get_version(a["version_path"], a.get("account")),
    "get_live_version": lambda a: get_live_version(a["account_id"], a["container_id"], a.get("account")),
    "get_latest_version_header": lambda a: get_latest_version_header(a["account_id"], a["container_id"], a.get("account")),
    "set_latest_version": lambda a: set_latest_version(a["version_path"], a.get("account")),
    "undelete_version": lambda a: undelete_version(a["version_path"], a.get("account")),
    "update_version": lambda a: update_version(a["version_path"], a.get("name"), a.get("description"), a.get("account")),
    "delete_version": lambda a: delete_version(a["version_path"], a.get("account")),
    "update_workspace": lambda a: update_workspace(a["workspace_path"], a.get("name"), a.get("description"), a.get("account")),
    "delete_workspace": lambda a: delete_workspace(a["workspace_path"], a.get("account")),
    "sync_workspace": lambda a: sync_workspace(a["workspace_path"], a.get("account")),
    "quick_preview": lambda a: quick_preview(a["workspace_path"], a.get("account")),
    "workspace_status": lambda a: workspace_status(a["workspace_path"], a.get("account")),
    "resolve_conflict": lambda a: resolve_conflict(a["workspace_path"], a["entity"], a.get("account")),
    "list_environments": lambda a: list_environments(a["account_id"], a["container_id"], a.get("account")),
    "create_environment": lambda a: create_environment(a["account_id"], a["container_id"], a["name"], a.get("description"),
                                                       a.get("url"), a.get("enable_debug"), a.get("account")),
    "reauthorize_environment": lambda a: reauthorize_environment(a["environment_path"], a.get("account")),
    "list_user_permissions": lambda a: list_user_permissions(a["account_id"], a.get("account")),
    "create_user_permission": lambda a: create_user_permission(a["account_id"], a["email"], a.get("account_access", "user"),
                                                               a.get("container_access"), a.get("account")),
    "update_user_permission": lambda a: update_user_permission(a["permission_path"], a["body"], a.get("account")),
    "delete_user_permission": lambda a: delete_user_permission(a["permission_path"], a.get("account")),
    "create_container": lambda a: create_container(a["account_id"], a["name"], a.get("usage_context"), a.get("domain_names"),
                                                   a.get("notes"), a.get("account")),
    "delete_container": lambda a: delete_container(a["container_path"], a.get("account")),
    "lookup_container": lambda a: lookup_container(a.get("destination_id"), a.get("tag_id"), a.get("account")),
    "container_snippet": lambda a: container_snippet(a["container_path"], a.get("account")),
    "combine_containers": lambda a: combine_containers(a["container_path"], a["into_container_id"],
                                                       a.get("allow_user_permission_feature_update", False),
                                                       a.get("setting_source", "current"), a.get("account")),
    "move_tag_id": lambda a: move_tag_id(a["container_path"], a["tag_id"], a.get("tag_name"), a.get("copy_users", False),
                                         a.get("copy_settings", True), a.get("copy_terms_of_service", True),
                                         a.get("allow_user_permission_feature_update", False), a.get("account")),
    "list_destinations": lambda a: list_destinations(a["container_path"], a.get("account")),
    "link_destination": lambda a: link_destination(a["container_path"], a["destination_id"],
                                                   a.get("allow_user_permission_feature_update", False), a.get("account")),
    "create_ga4_config_tag": lambda a: create_ga4_config_tag(a["workspace_path"], a["name"], a["measurement_id"],
                                                             a.get("firing_trigger_id", "2147479553"), a.get("send_page_view", True), a.get("account")),
    "create_ga4_event_tag": lambda a: create_ga4_event_tag(a["workspace_path"], a["name"], a["measurement_id"], a["event_name"],
                                                           a["firing_trigger_id"], a.get("event_params"), a.get("account")),
    "api_request": lambda a: api_request(a["method"], a["path"], a.get("params"), a.get("body"), a.get("account")),
}
