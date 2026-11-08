"""
Extensión GA4: ESCRITURA de Admin API + Data API completa.
Requiere scopes analytics.edit + analytics.manage.users (+ readonly):
    python3 get_refresh_token.py <etiqueta>   (una vez por cuenta)
Se monta en mcp_server.py vía TOOLS + HANDLERS.
"""
import requests
from ga4 import engine as ga

ADMIN_ROOT = "https://analyticsadmin.googleapis.com"
DATA_ROOT = "https://analyticsdata.googleapis.com"


def _req(method, url, account=None, params=None, body=None):
    r = requests.request(method.upper(), url, headers=ga._headers(account), params=params,
                         json=body, timeout=120)
    return r


def admin(method, path, account=None, params=None, body=None, version=None):
    """Admin API con fallback v1beta -> v1alpha (muchos recursos solo existen en alpha)."""
    versions = [version] if version else ["v1beta", "v1alpha"]
    last = None
    for v in versions:
        r = _req(method, f"{ADMIN_ROOT}/{v}/{path.lstrip('/')}", account, params, body)
        if r.status_code < 300:
            return r.json() if r.text.strip() else {"ok": True}
        last = r
        if r.status_code != 404:
            break
    raise ga.Ga4Error(f"{method.upper()} {path} HTTP {last.status_code}: {last.text[:900]}")


def data(method, path, account=None, params=None, body=None, version=None):
    versions = [version] if version else ["v1beta", "v1alpha"]
    last = None
    for v in versions:
        r = _req(method, f"{DATA_ROOT}/{v}/{path.lstrip('/')}", account, params, body)
        if r.status_code < 300:
            return r.json() if r.text.strip() else {"ok": True}
        last = r
        if r.status_code != 404:
            break
    raise ga.Ga4Error(f"{method.upper()} {path} HTTP {last.status_code}: {last.text[:900]}")


def _prop(p):
    p = str(p).strip()
    return p if p.startswith("properties/") else f"properties/{p}"


def _acc(a):
    a = str(a).strip()
    return a if a.startswith("accounts/") else f"accounts/{a}"


def _mask(body):
    return ",".join(body.keys())


# ------------------------------------------------------------- Admin: cuentas / propiedades
def list_account_summaries(account=None):
    return admin("GET", "accountSummaries", account, {"pageSize": 200}).get("accountSummaries", [])


def update_account(account_id, body, account=None):
    return admin("PATCH", _acc(account_id), account, {"updateMask": _mask(body)}, body)


def create_property(account_id, display_name, time_zone="Europe/Madrid", currency_code="EUR",
                    industry_category=None, property_type="PROPERTY_TYPE_ORDINARY", account=None):
    body = {"parent": _acc(account_id), "displayName": display_name, "timeZone": time_zone,
            "currencyCode": currency_code, "propertyType": property_type}
    if industry_category:
        body["industryCategory"] = industry_category
    return admin("POST", "properties", account, body=body)


def update_property(property_id, body, account=None):
    return admin("PATCH", _prop(property_id), account, {"updateMask": _mask(body)}, body)


def delete_property(property_id, account=None):
    """Marca la propiedad para borrado (papelera 35 días)."""
    return admin("DELETE", _prop(property_id), account)


def run_access_report(entity, body, account=None):
    """entity: properties/123 o accounts/123. body: dimensions/metrics/dateRanges del access report."""
    return admin("POST", f"{entity}:runAccessReport", account, body=body)


def search_change_history(account_id, body=None, account=None):
    return admin("POST", f"{_acc(account_id)}:searchChangeHistoryEvents", account, body=body or {})


# ------------------------------------------------------------- Admin: flujos / eventos / dims / métricas
def create_data_stream(property_id, display_name, stream_type="WEB_DATA_STREAM", default_uri=None,
                       package_name=None, bundle_id=None, account=None):
    body = {"displayName": display_name, "type": stream_type}
    if stream_type == "WEB_DATA_STREAM":
        body["webStreamData"] = {"defaultUri": default_uri}
    elif stream_type == "ANDROID_APP_DATA_STREAM":
        body["androidAppStreamData"] = {"packageName": package_name}
    elif stream_type == "IOS_APP_DATA_STREAM":
        body["iosAppStreamData"] = {"bundleId": bundle_id}
    return admin("POST", f"{_prop(property_id)}/dataStreams", account, body=body)


def update_data_stream(stream_name, body, account=None):
    return admin("PATCH", stream_name, account, {"updateMask": _mask(body)}, body)


def delete_data_stream(stream_name, account=None):
    return admin("DELETE", stream_name, account)


def get_enhanced_measurement(stream_name, account=None):
    return admin("GET", f"{stream_name}/enhancedMeasurementSettings", account)


def update_enhanced_measurement(stream_name, body, account=None):
    return admin("PATCH", f"{stream_name}/enhancedMeasurementSettings", account, {"updateMask": _mask(body)}, body)


def create_key_event(property_id, event_name, counting_method="ONCE_PER_EVENT", default_value=None, account=None):
    body = {"eventName": event_name, "countingMethod": counting_method}
    if default_value:
        body["defaultValue"] = default_value
    return admin("POST", f"{_prop(property_id)}/keyEvents", account, body=body)


def update_key_event(key_event_name, body, account=None):
    return admin("PATCH", key_event_name, account, {"updateMask": _mask(body)}, body)


def delete_key_event(key_event_name, account=None):
    return admin("DELETE", key_event_name, account)


def list_custom_dimensions(property_id, account=None):
    return admin("GET", f"{_prop(property_id)}/customDimensions", account, {"pageSize": 200}).get("customDimensions", [])


def create_custom_dimension(property_id, parameter_name, display_name, scope="EVENT", description=None, account=None):
    body = {"parameterName": parameter_name, "displayName": display_name, "scope": scope}
    if description:
        body["description"] = description
    return admin("POST", f"{_prop(property_id)}/customDimensions", account, body=body)


def archive_custom_dimension(name, account=None):
    return admin("POST", f"{name}:archive", account, body={})


def list_custom_metrics(property_id, account=None):
    return admin("GET", f"{_prop(property_id)}/customMetrics", account, {"pageSize": 200}).get("customMetrics", [])


def create_custom_metric(property_id, parameter_name, display_name, measurement_unit="STANDARD",
                         scope="EVENT", description=None, account=None):
    body = {"parameterName": parameter_name, "displayName": display_name, "scope": scope,
            "measurementUnit": measurement_unit}
    if description:
        body["description"] = description
    return admin("POST", f"{_prop(property_id)}/customMetrics", account, body=body)


def archive_custom_metric(name, account=None):
    return admin("POST", f"{name}:archive", account, body={})


# ------------------------------------------------------------- Admin: enlaces, retención, audiencias, usuarios
def list_google_ads_links(property_id, account=None):
    return admin("GET", f"{_prop(property_id)}/googleAdsLinks", account).get("googleAdsLinks", [])


def create_google_ads_link(property_id, customer_id, ads_personalization=True, account=None):
    body = {"customerId": str(customer_id).replace("-", ""), "adsPersonalizationEnabled": ads_personalization}
    return admin("POST", f"{_prop(property_id)}/googleAdsLinks", account, body=body)


def delete_google_ads_link(link_name, account=None):
    return admin("DELETE", link_name, account)


def get_data_retention(property_id, account=None):
    return admin("GET", f"{_prop(property_id)}/dataRetentionSettings", account)


def update_data_retention(property_id, event_retention="FOURTEEN_MONTHS", reset_on_activity=True, account=None):
    body = {"eventDataRetention": event_retention, "resetUserDataOnNewActivity": reset_on_activity}
    return admin("PATCH", f"{_prop(property_id)}/dataRetentionSettings", account, {"updateMask": _mask(body)}, body)


def get_attribution_settings(property_id, account=None):
    return admin("GET", f"{_prop(property_id)}/attributionSettings", account)


def update_attribution_settings(property_id, body, account=None):
    return admin("PATCH", f"{_prop(property_id)}/attributionSettings", account, {"updateMask": _mask(body)}, body)


def get_google_signals(property_id, account=None):
    return admin("GET", f"{_prop(property_id)}/googleSignalsSettings", account, version="v1alpha")


def update_google_signals(property_id, state="GOOGLE_SIGNALS_ENABLED", consent="GOOGLE_SIGNALS_CONSENT_CONSENTED", account=None):
    body = {"state": state, "consent": consent}
    return admin("PATCH", f"{_prop(property_id)}/googleSignalsSettings", account,
                 {"updateMask": _mask(body)}, body, version="v1alpha")


def list_audiences(property_id, account=None):
    return admin("GET", f"{_prop(property_id)}/audiences", account, {"pageSize": 200}, version="v1alpha").get("audiences", [])


def create_audience(property_id, body, account=None):
    """body: {displayName, description, membershipDurationDays, filterClauses:[...]} (formato Admin API alpha)."""
    return admin("POST", f"{_prop(property_id)}/audiences", account, body=body, version="v1alpha")


def archive_audience(audience_name, account=None):
    return admin("POST", f"{audience_name}:archive", account, body={}, version="v1alpha")


def list_access_bindings(entity, account=None):
    """entity: accounts/123 o properties/123. Usuarios y roles."""
    return admin("GET", f"{entity}/accessBindings", account, {"pageSize": 200}).get("accessBindings", [])


def create_access_binding(entity, user_email, roles, account=None):
    """roles: predefinedRoles/viewer | analyst | editor | admin | no-cost-data | no-revenue-data"""
    body = {"user": user_email, "roles": roles}
    return admin("POST", f"{entity}/accessBindings", account, body=body)


def update_access_binding(binding_name, roles, account=None):
    return admin("PATCH", binding_name, account, {"updateMask": "roles"}, {"roles": roles})


def delete_access_binding(binding_name, account=None):
    return admin("DELETE", binding_name, account)


def list_measurement_protocol_secrets(stream_name, account=None):
    return admin("GET", f"{stream_name}/measurementProtocolSecrets", account).get("measurementProtocolSecrets", [])


def create_measurement_protocol_secret(stream_name, display_name, account=None):
    return admin("POST", f"{stream_name}/measurementProtocolSecrets", account, body={"displayName": display_name})


def list_firebase_links(property_id, account=None):
    return admin("GET", f"{_prop(property_id)}/firebaseLinks", account).get("firebaseLinks", [])


def list_conversion_events(property_id, account=None):
    return admin("GET", f"{_prop(property_id)}/conversionEvents", account, {"pageSize": 200}).get("conversionEvents", [])


# ------------------------------------------------------------- Data API completa
def run_report_raw(property_id, body, account=None):
    """Cuerpo completo de runReport (dimensionFilter, metricFilter, orderBys, cohortSpec, comparisons...)."""
    return data("POST", f"{_prop(property_id)}:runReport", account, body=body)


def run_pivot_report(property_id, body, account=None):
    return data("POST", f"{_prop(property_id)}:runPivotReport", account, body=body)


def batch_run_reports(property_id, requests_list, account=None):
    return data("POST", f"{_prop(property_id)}:batchRunReports", account, body={"requests": requests_list})


def run_funnel_report(property_id, body, account=None):
    return data("POST", f"{_prop(property_id)}:runFunnelReport", account, body=body, version="v1alpha")


def check_compatibility(property_id, body, account=None):
    return data("POST", f"{_prop(property_id)}:checkCompatibility", account, body=body)


def create_audience_export(property_id, audience_name, dimensions, account=None):
    body = {"audience": audience_name, "dimension": [{"dimensionName": d} for d in dimensions]}
    return data("POST", f"{_prop(property_id)}/audienceExports", account, body=body)


def query_audience_export(export_name, offset=0, limit=1000, account=None):
    return data("POST", f"{export_name}:query", account, body={"offset": offset, "limit": limit})


def list_audience_exports(property_id, account=None):
    return data("GET", f"{_prop(property_id)}/audienceExports", account)


def property_quotas(property_id, account=None):
    return data("GET", f"{_prop(property_id)}/propertyQuotasSnapshot", account)


# ------------------------------------------------------------- escape hatches
def admin_request(method, path, params=None, body=None, version=None, account=None):
    return admin(method, path, account, params, body, version)


def data_request(method, path, params=None, body=None, version=None, account=None):
    return data(method, path, account, params, body, version)


# ------------------------------------------------------------- tools
_AC = "Etiqueta de cuenta de login del .env (bryan | academy). Opcional si solo hay una."
_S = {"type": "string"}
_B = {"type": "boolean"}
_I = {"type": "integer"}
_O = {"type": "object"}
_LS = {"type": "array", "items": {"type": "string"}}
_PID = {"property_id": {"type": "string", "description": "Número o 'properties/123'."}}
_ENT = {"entity": {"type": "string", "description": "'accounts/123' o 'properties/123'."}}


def _t(name, desc, props=None, req=None):
    p = dict(props or {})
    p["account"] = {"type": "string", "description": _AC}
    return {"name": name, "description": desc, "inputSchema": {"type": "object", "properties": p, "required": req or []}}


TOOLS = [
    _t("list_account_summaries", "Todas las cuentas GA4 con sus propiedades (visión rápida)."),
    _t("update_account", "ESCRITURA: modifica una cuenta (displayName, regionCode).", {"account_id": _S, "body": _O}, ["account_id", "body"]),
    _t("create_property", "ESCRITURA: crea una propiedad GA4 en una cuenta.",
       {"account_id": _S, "display_name": _S, "time_zone": _S, "currency_code": _S, "industry_category": _S,
        "property_type": _S}, ["account_id", "display_name"]),
    _t("update_property", "ESCRITURA: modifica una propiedad (displayName, timeZone, currencyCode, industryCategory).",
       dict(_PID, body=_O), ["property_id", "body"]),
    _t("delete_property", "ESCRITURA: manda una propiedad a la papelera (recuperable 35 días).", _PID, ["property_id"]),
    _t("run_access_report", "Informe de acceso de datos (quién consultó qué).", dict(_ENT, body=_O), ["entity", "body"]),
    _t("search_change_history", "Historial de cambios de una cuenta (body opcional: property, resourceType, action, earliestChangeTime...).",
       {"account_id": _S, "body": _O}, ["account_id"]),
    _t("create_data_stream", "ESCRITURA: crea un flujo de datos (WEB_DATA_STREAM con default_uri, ANDROID_APP_DATA_STREAM, IOS_APP_DATA_STREAM).",
       dict(_PID, display_name=_S, stream_type=_S, default_uri=_S, package_name=_S, bundle_id=_S), ["property_id", "display_name"]),
    _t("update_data_stream", "ESCRITURA: modifica un flujo (name completo properties/1/dataStreams/2).", {"stream_name": _S, "body": _O}, ["stream_name", "body"]),
    _t("delete_data_stream", "ESCRITURA: borra un flujo de datos.", {"stream_name": _S}, ["stream_name"]),
    _t("get_enhanced_measurement", "Medición mejorada de un flujo web (scrolls, outbound clicks, site search, video, downloads, forms).",
       {"stream_name": _S}, ["stream_name"]),
    _t("update_enhanced_measurement", "ESCRITURA: cambia la medición mejorada. body p.ej. {streamEnabled:true, scrollsEnabled:true, formInteractionsEnabled:true}.",
       {"stream_name": _S, "body": _O}, ["stream_name", "body"]),
    _t("create_key_event", "ESCRITURA: marca un evento como evento clave (conversión). counting_method: ONCE_PER_EVENT | ONCE_PER_SESSION.",
       dict(_PID, event_name=_S, counting_method=_S, default_value=_O), ["property_id", "event_name"]),
    _t("update_key_event", "ESCRITURA: modifica un evento clave (countingMethod, defaultValue).", {"key_event_name": _S, "body": _O}, ["key_event_name", "body"]),
    _t("delete_key_event", "ESCRITURA: deja de tratar un evento como clave.", {"key_event_name": _S}, ["key_event_name"]),
    _t("list_custom_dimensions", "Dimensiones personalizadas.", _PID, ["property_id"]),
    _t("create_custom_dimension", "ESCRITURA: crea una dimensión personalizada. scope: EVENT | USER | ITEM.",
       dict(_PID, parameter_name=_S, display_name=_S, scope=_S, description=_S), ["property_id", "parameter_name", "display_name"]),
    _t("archive_custom_dimension", "ESCRITURA: archiva una dimensión personalizada.", {"name": _S}, ["name"]),
    _t("list_custom_metrics", "Métricas personalizadas.", _PID, ["property_id"]),
    _t("create_custom_metric", "ESCRITURA: crea una métrica personalizada. measurement_unit: STANDARD | CURRENCY | FEET | METERS | ... ",
       dict(_PID, parameter_name=_S, display_name=_S, measurement_unit=_S, scope=_S, description=_S),
       ["property_id", "parameter_name", "display_name"]),
    _t("archive_custom_metric", "ESCRITURA: archiva una métrica personalizada.", {"name": _S}, ["name"]),
    _t("list_google_ads_links", "Vínculos con Google Ads.", _PID, ["property_id"]),
    _t("create_google_ads_link", "ESCRITURA: vincula una cuenta de Google Ads (customer_id) a la propiedad.",
       dict(_PID, customer_id=_S, ads_personalization=_B), ["property_id", "customer_id"]),
    _t("delete_google_ads_link", "ESCRITURA: elimina un vínculo con Google Ads (name completo).", {"link_name": _S}, ["link_name"]),
    _t("get_data_retention", "Retención de datos de eventos.", _PID, ["property_id"]),
    _t("update_data_retention", "ESCRITURA: retención TWO_MONTHS | FOURTEEN_MONTHS (26/38/50 meses solo en 360).",
       dict(_PID, event_retention=_S, reset_on_activity=_B), ["property_id"]),
    _t("get_attribution_settings", "Modelo de atribución y ventanas de conversión.", _PID, ["property_id"]),
    _t("update_attribution_settings", "ESCRITURA: body p.ej. {reportingAttributionModel:'PAID_AND_ORGANIC_CHANNELS_DATA_DRIVEN', acquisitionConversionEventLookbackWindow:'ACQUISITION_CONVERSION_EVENT_LOOKBACK_WINDOW_30_DAYS'}.",
       dict(_PID, body=_O), ["property_id", "body"]),
    _t("get_google_signals", "Estado de Google Signals.", _PID, ["property_id"]),
    _t("update_google_signals", "ESCRITURA: activa/desactiva Google Signals (state GOOGLE_SIGNALS_ENABLED | GOOGLE_SIGNALS_DISABLED).",
       dict(_PID, state=_S, consent=_S), ["property_id"]),
    _t("list_audiences", "Audiencias de la propiedad.", _PID, ["property_id"]),
    _t("create_audience", "ESCRITURA: crea una audiencia (body con displayName, description, membershipDurationDays, filterClauses).",
       dict(_PID, body=_O), ["property_id", "body"]),
    _t("archive_audience", "ESCRITURA: archiva una audiencia.", {"audience_name": _S}, ["audience_name"]),
    _t("list_access_bindings", "Usuarios y roles de una cuenta o propiedad.", _ENT, ["entity"]),
    _t("create_access_binding", "ESCRITURA: da acceso a un usuario. roles: ['predefinedRoles/viewer'|'analyst'|'editor'|'admin'].",
       dict(_ENT, user_email=_S, roles=_LS), ["entity", "user_email", "roles"]),
    _t("update_access_binding", "ESCRITURA: cambia los roles de un usuario (binding_name completo).", {"binding_name": _S, "roles": _LS}, ["binding_name", "roles"]),
    _t("delete_access_binding", "ESCRITURA: quita el acceso de un usuario.", {"binding_name": _S}, ["binding_name"]),
    _t("list_measurement_protocol_secrets", "Secretos de Measurement Protocol de un flujo.", {"stream_name": _S}, ["stream_name"]),
    _t("create_measurement_protocol_secret", "ESCRITURA: crea un secreto de Measurement Protocol.", {"stream_name": _S, "display_name": _S}, ["stream_name", "display_name"]),
    _t("list_firebase_links", "Vínculos con Firebase.", _PID, ["property_id"]),
    _t("list_conversion_events", "Eventos de conversión (API antigua; equivale a key events).", _PID, ["property_id"]),
    _t("run_report_raw", "Informe con el cuerpo COMPLETO de runReport (filtros, cohortes, comparaciones, keepEmptyRows...).",
       dict(_PID, body=_O), ["property_id", "body"]),
    _t("run_pivot_report", "Informe pivote (body: dimensions, metrics, dateRanges, pivots).", dict(_PID, body=_O), ["property_id", "body"]),
    _t("batch_run_reports", "Hasta 5 informes en una llamada (lista de cuerpos de runReport).",
       dict(_PID, requests={"type": "array", "items": _O}), ["property_id", "requests"]),
    _t("run_funnel_report", "Informe de embudo (alpha): body con funnel.steps, dateRanges, funnelBreakdown...", dict(_PID, body=_O), ["property_id", "body"]),
    _t("check_compatibility", "Comprueba si dimensiones/métricas son compatibles antes de un informe.", dict(_PID, body=_O), ["property_id", "body"]),
    _t("create_audience_export", "ESCRITURA: exporta usuarios de una audiencia (dimensions p.ej. ['deviceId']).",
       dict(_PID, audience_name=_S, dimensions=_LS), ["property_id", "audience_name", "dimensions"]),
    _t("query_audience_export", "Lee los usuarios de una exportación de audiencia.", {"export_name": _S, "offset": _I, "limit": _I}, ["export_name"]),
    _t("list_audience_exports", "Exportaciones de audiencia de la propiedad.", _PID, ["property_id"]),
    _t("property_quotas", "Cuota de la Data API de la propiedad.", _PID, ["property_id"]),
    _t("admin_request", ("Llamada cruda a la Admin API (cualquier recurso: subpropiedades, rollups, eventCreateRules, "
                         "channelGroups, calculatedMetrics, skAdNetwork, expandedDataSets, bigQueryLinks, dataRedaction...). "
                         "path relativo a la versión, p.ej. 'properties/123/channelGroups'. version: v1beta (defecto, con fallback a v1alpha) | v1alpha."),
       {"method": _S, "path": _S, "params": _O, "body": _O, "version": _S}, ["method", "path"]),
    _t("data_request", "Llamada cruda a la Data API (runRealtimeReport, recurringAudienceLists, etc.). path relativo a la versión.",
       {"method": _S, "path": _S, "params": _O, "body": _O, "version": _S}, ["method", "path"]),
]

HANDLERS = {
    "list_account_summaries": lambda a: list_account_summaries(a.get("account")),
    "update_account": lambda a: update_account(a["account_id"], a["body"], a.get("account")),
    "create_property": lambda a: create_property(a["account_id"], a["display_name"], a.get("time_zone", "Europe/Madrid"),
                                                 a.get("currency_code", "EUR"), a.get("industry_category"),
                                                 a.get("property_type", "PROPERTY_TYPE_ORDINARY"), a.get("account")),
    "update_property": lambda a: update_property(a["property_id"], a["body"], a.get("account")),
    "delete_property": lambda a: delete_property(a["property_id"], a.get("account")),
    "run_access_report": lambda a: run_access_report(a["entity"], a["body"], a.get("account")),
    "search_change_history": lambda a: search_change_history(a["account_id"], a.get("body"), a.get("account")),
    "create_data_stream": lambda a: create_data_stream(a["property_id"], a["display_name"], a.get("stream_type", "WEB_DATA_STREAM"),
                                                       a.get("default_uri"), a.get("package_name"), a.get("bundle_id"), a.get("account")),
    "update_data_stream": lambda a: update_data_stream(a["stream_name"], a["body"], a.get("account")),
    "delete_data_stream": lambda a: delete_data_stream(a["stream_name"], a.get("account")),
    "get_enhanced_measurement": lambda a: get_enhanced_measurement(a["stream_name"], a.get("account")),
    "update_enhanced_measurement": lambda a: update_enhanced_measurement(a["stream_name"], a["body"], a.get("account")),
    "create_key_event": lambda a: create_key_event(a["property_id"], a["event_name"], a.get("counting_method", "ONCE_PER_EVENT"),
                                                   a.get("default_value"), a.get("account")),
    "update_key_event": lambda a: update_key_event(a["key_event_name"], a["body"], a.get("account")),
    "delete_key_event": lambda a: delete_key_event(a["key_event_name"], a.get("account")),
    "list_custom_dimensions": lambda a: list_custom_dimensions(a["property_id"], a.get("account")),
    "create_custom_dimension": lambda a: create_custom_dimension(a["property_id"], a["parameter_name"], a["display_name"],
                                                                 a.get("scope", "EVENT"), a.get("description"), a.get("account")),
    "archive_custom_dimension": lambda a: archive_custom_dimension(a["name"], a.get("account")),
    "list_custom_metrics": lambda a: list_custom_metrics(a["property_id"], a.get("account")),
    "create_custom_metric": lambda a: create_custom_metric(a["property_id"], a["parameter_name"], a["display_name"],
                                                           a.get("measurement_unit", "STANDARD"), a.get("scope", "EVENT"),
                                                           a.get("description"), a.get("account")),
    "archive_custom_metric": lambda a: archive_custom_metric(a["name"], a.get("account")),
    "list_google_ads_links": lambda a: list_google_ads_links(a["property_id"], a.get("account")),
    "create_google_ads_link": lambda a: create_google_ads_link(a["property_id"], a["customer_id"], a.get("ads_personalization", True), a.get("account")),
    "delete_google_ads_link": lambda a: delete_google_ads_link(a["link_name"], a.get("account")),
    "get_data_retention": lambda a: get_data_retention(a["property_id"], a.get("account")),
    "update_data_retention": lambda a: update_data_retention(a["property_id"], a.get("event_retention", "FOURTEEN_MONTHS"),
                                                             a.get("reset_on_activity", True), a.get("account")),
    "get_attribution_settings": lambda a: get_attribution_settings(a["property_id"], a.get("account")),
    "update_attribution_settings": lambda a: update_attribution_settings(a["property_id"], a["body"], a.get("account")),
    "get_google_signals": lambda a: get_google_signals(a["property_id"], a.get("account")),
    "update_google_signals": lambda a: update_google_signals(a["property_id"], a.get("state", "GOOGLE_SIGNALS_ENABLED"),
                                                             a.get("consent", "GOOGLE_SIGNALS_CONSENT_CONSENTED"), a.get("account")),
    "list_audiences": lambda a: list_audiences(a["property_id"], a.get("account")),
    "create_audience": lambda a: create_audience(a["property_id"], a["body"], a.get("account")),
    "archive_audience": lambda a: archive_audience(a["audience_name"], a.get("account")),
    "list_access_bindings": lambda a: list_access_bindings(a["entity"], a.get("account")),
    "create_access_binding": lambda a: create_access_binding(a["entity"], a["user_email"], a["roles"], a.get("account")),
    "update_access_binding": lambda a: update_access_binding(a["binding_name"], a["roles"], a.get("account")),
    "delete_access_binding": lambda a: delete_access_binding(a["binding_name"], a.get("account")),
    "list_measurement_protocol_secrets": lambda a: list_measurement_protocol_secrets(a["stream_name"], a.get("account")),
    "create_measurement_protocol_secret": lambda a: create_measurement_protocol_secret(a["stream_name"], a["display_name"], a.get("account")),
    "list_firebase_links": lambda a: list_firebase_links(a["property_id"], a.get("account")),
    "list_conversion_events": lambda a: list_conversion_events(a["property_id"], a.get("account")),
    "run_report_raw": lambda a: run_report_raw(a["property_id"], a["body"], a.get("account")),
    "run_pivot_report": lambda a: run_pivot_report(a["property_id"], a["body"], a.get("account")),
    "batch_run_reports": lambda a: batch_run_reports(a["property_id"], a["requests"], a.get("account")),
    "run_funnel_report": lambda a: run_funnel_report(a["property_id"], a["body"], a.get("account")),
    "check_compatibility": lambda a: check_compatibility(a["property_id"], a["body"], a.get("account")),
    "create_audience_export": lambda a: create_audience_export(a["property_id"], a["audience_name"], a["dimensions"], a.get("account")),
    "query_audience_export": lambda a: query_audience_export(a["export_name"], a.get("offset", 0), a.get("limit", 1000), a.get("account")),
    "list_audience_exports": lambda a: list_audience_exports(a["property_id"], a.get("account")),
    "property_quotas": lambda a: property_quotas(a["property_id"], a.get("account")),
    "admin_request": lambda a: admin_request(a["method"], a["path"], a.get("params"), a.get("body"), a.get("version"), a.get("account")),
    "data_request": lambda a: data_request(a["method"], a["path"], a.get("params"), a.get("body"), a.get("version"), a.get("account")),
}
