"""
Extensión Merchant Center: sub-APIs no cubiertas por el motor base
(regiones, info de negocio, homepage, programas, autofeed, políticas de devolución,
fuentes de conversión, notificaciones, resolución de incidencias, reseñas, LFP,
señales de pedidos, alta masiva de productos) + api_request con v1/v1beta/v1alpha.
"""
import requests
from mc import engine as mc


def _call(method, sub, path, account=None, params=None, body=None, versions=("v1", "v1beta", "v1alpha")):
    last = None
    for ver in versions:
        r = mc._raw(method, f"{mc.BASE}/{sub}/{ver}/{path.lstrip('/')}", account, params, body)
        if r.status_code < 300:
            return r.json() if r.text.strip() else {"ok": True}
        last = r
        if r.status_code not in (404, 409):
            break
    raise mc.McError(f"{method} {sub}/{path} HTTP {last.status_code}: {last.text[:900]}")


def _acc(a):
    return mc._acc(a)


# ---------------------------------------------------------------- accounts sub-API
def list_regions(account_id, account=None):
    return _call("GET", "accounts", f"{_acc(account_id)}/regions", account, {"pageSize": 200}).get("regions", [])


def create_region(account_id, region_id, display_name, postal_codes=None, geotarget_ids=None, account=None):
    """postal_codes: [{begin:'29600', end:'29699'}]  |  geotarget_ids: [2724]"""
    body = {"displayName": display_name}
    if postal_codes:
        body["postalCodeArea"] = {"regionCode": "ES", "postalCodes": postal_codes}
    if geotarget_ids:
        body["geotargetArea"] = {"geotargetCriteriaIds": [str(g) for g in geotarget_ids]}
    return _call("POST", "accounts", f"{_acc(account_id)}/regions", account, {"regionId": region_id}, body)


def delete_region(account_id, region_id, account=None):
    return _call("DELETE", "accounts", f"{_acc(account_id)}/regions/{region_id}", account)


def get_business_info(account_id, account=None):
    return _call("GET", "accounts", f"{_acc(account_id)}/businessInfo", account)


def update_business_info(account_id, body, account=None):
    """body: {address:{...}, phone:{e164Number}, customerService:{uri,email,phone}, koreanBusinessRegistrationNumber}"""
    return _call("PATCH", "accounts", f"{_acc(account_id)}/businessInfo", account, {"updateMask": ",".join(body)}, body)


def get_homepage(account_id, account=None):
    return _call("GET", "accounts", f"{_acc(account_id)}/homepage", account)


def update_homepage(account_id, uri, account=None):
    return _call("PATCH", "accounts", f"{_acc(account_id)}/homepage", account, {"updateMask": "uri"}, {"uri": uri})


def claim_homepage(account_id, overwrite=False, account=None):
    return _call("POST", "accounts", f"{_acc(account_id)}/homepage:claim", account, None, {"overwrite": overwrite})


def unclaim_homepage(account_id, account=None):
    return _call("POST", "accounts", f"{_acc(account_id)}/homepage:unclaim", account, None, {})


def list_programs(account_id, account=None):
    return _call("GET", "accounts", f"{_acc(account_id)}/programs", account).get("programs", [])


def enable_program(account_id, program, enable=True, account=None):
    """program: free-listings | shopping-ads | ... (ver list_programs)"""
    act = "enable" if enable else "disable"
    return _call("POST", "accounts", f"{_acc(account_id)}/programs/{program}:{act}", account, None, {})


def get_autofeed(account_id, account=None):
    return _call("GET", "accounts", f"{_acc(account_id)}/autofeedSettings", account)


def update_autofeed(account_id, enable_products, account=None):
    return _call("PATCH", "accounts", f"{_acc(account_id)}/autofeedSettings", account,
                 {"updateMask": "enableProducts"}, {"enableProducts": bool(enable_products)})


def get_email_preferences(account_id, account=None):
    return _call("GET", "accounts", f"{_acc(account_id)}/users/me/emailPreferences", account)


def list_return_policies(account_id, account=None):
    return _call("GET", "accounts", f"{_acc(account_id)}/onlineReturnPolicies", account).get("onlineReturnPolicies", [])


def create_return_policy(account_id, body, account=None):
    return _call("POST", "accounts", f"{_acc(account_id)}/onlineReturnPolicies", account, None, body)


def delete_return_policy(policy_name, account=None):
    return _call("DELETE", "accounts", policy_name, account)


def get_terms_of_service_state(account_id, region="ES", account=None):
    return _call("GET", "accounts", f"{_acc(account_id)}/termsOfServiceAgreementStates/MERCHANT_CENTER-{region}", account)


def list_users(account_id, account=None):
    return _call("GET", "accounts", f"{_acc(account_id)}/users", account).get("users", [])


def list_gbp_accounts(account_id, account=None):
    return _call("GET", "accounts", f"{_acc(account_id)}/gbpAccounts", account).get("gbpAccounts", [])


def list_shipping_settings(account_id, account=None):
    return _call("GET", "accounts", f"{_acc(account_id)}/shippingSettings", account)


# ---------------------------------------------------------------- conversions / notifications
def list_conversion_sources(account_id, account=None):
    return _call("GET", "conversions", f"{_acc(account_id)}/conversionSources", account).get("conversionSources", [])


def create_conversion_source(account_id, body, account=None):
    """body p.ej. {googleAnalyticsLink:{propertyId:'123'}} o {merchantCenterDestination:{displayName,currencyCode,attributionSettings}}"""
    return _call("POST", "conversions", f"{_acc(account_id)}/conversionSources", account, None, body)


def delete_conversion_source(source_name, account=None):
    return _call("DELETE", "conversions", source_name, account)


def list_notification_subscriptions(account_id, account=None):
    return _call("GET", "notifications", f"{_acc(account_id)}/notificationsubscriptions", account).get("notificationSubscriptions", [])


def create_notification_subscription(account_id, callback_uri, event="PRODUCT_STATUS_CHANGE", all_managed=True, account=None):
    body = {"registeredEvent": event, "callbackUri": callback_uri}
    if all_managed:
        body["allManagedAccounts"] = True
    return _call("POST", "notifications", f"{_acc(account_id)}/notificationsubscriptions", account, None, body)


def delete_notification_subscription(sub_name, account=None):
    return _call("DELETE", "notifications", sub_name, account)


# ---------------------------------------------------------------- issue resolution
def render_account_issues(account_id, language="es-ES", account=None):
    return _call("POST", "issueresolution", f"{_acc(account_id)}:renderaccountissues", account,
                 {"languageCode": language}, {})


def render_product_issues(account_id, product_id, language="es-ES", account=None):
    return _call("POST", "issueresolution", f"{_acc(account_id)}/products/{product_id}:renderproductissues", account,
                 {"languageCode": language}, {})


def trigger_action(account_id, action_context, user_input=None, language="es-ES", account=None):
    body = {"actionContext": action_context}
    if user_input:
        body["actionInput"] = user_input
    return _call("POST", "issueresolution", f"{_acc(account_id)}:triggeraction", account, {"languageCode": language}, body)


def aggregate_product_statuses(account_id, filter_=None, account=None):
    params = {"pageSize": 200}
    if filter_:
        params["filter"] = filter_
    return _call("GET", "issueresolution", f"{_acc(account_id)}/aggregateProductStatuses", account, params)


# ---------------------------------------------------------------- reviews
def list_reviews(account_id, kind="productReviews", page_size=100, page_token=None, account=None):
    """kind: productReviews | merchantReviews"""
    params = {"pageSize": page_size}
    if page_token:
        params["pageToken"] = page_token
    return _call("GET", "reviews", f"{_acc(account_id)}/{kind}", account, params)


def insert_review(account_id, kind, data_source, body, account=None):
    return _call("POST", "reviews", f"{_acc(account_id)}/{kind}:insert", account, {"dataSource": data_source}, body)


def delete_review(review_name, account=None):
    sub = "reviews"
    return _call("DELETE", sub, review_name, account)


# ---------------------------------------------------------------- LFP / order tracking
def lfp_insert_inventory(account_id, target_account, body, account=None):
    """body LfpInventory: {offerId, regionCode, contentLanguage, storeCode, availability, price..., feedLabel}"""
    return _call("POST", "lfp", f"{_acc(account_id)}/lfpInventories:insert", account, None,
                 dict(body, targetAccount=str(target_account)))


def lfp_insert_sale(account_id, target_account, body, account=None):
    return _call("POST", "lfp", f"{_acc(account_id)}/lfpSales:insert", account, None,
                 dict(body, targetAccount=str(target_account)))


def create_order_tracking_signal(account_id, body, account=None):
    return _call("POST", "ordertracking", f"{_acc(account_id)}/ordertrackingsignals", account, None, body)


# ---------------------------------------------------------------- productos en bloque
def insert_products_bulk(account_id, data_source, product_inputs, stop_on_error=False, account=None):
    """Alta/actualización masiva secuencial. product_inputs: lista de ProductInput completos."""
    out = {"ok": [], "errors": []}
    for pi in product_inputs:
        try:
            r = mc.insert_product_input(account_id, data_source, pi, account)
            out["ok"].append(r.get("name") or pi.get("offerId"))
        except Exception as e:
            out["errors"].append({"offerId": pi.get("offerId"), "error": str(e)[:400]})
            if stop_on_error:
                break
    out["summary"] = {"inserted": len(out["ok"]), "failed": len(out["errors"])}
    return out


def api_request_any(method, sub_api, path, params=None, body=None, version=None, account=None):
    versions = (version,) if version else ("v1", "v1beta", "v1alpha")
    return _call(method.upper(), sub_api, path, account, params, body, versions)


# ---------------------------------------------------------------- tools
_AC = "Etiqueta de cuenta de LOGIN del .env (bryan | academy). Opcional si solo hay una."
_S = {"type": "string"}
_B = {"type": "boolean"}
_I = {"type": "integer"}
_O = {"type": "object"}
_LO = {"type": "array", "items": {"type": "object"}}
_LI = {"type": "array", "items": {"type": "integer"}}
_AID = {"account_id": {"type": "string", "description": "ID de la cuenta de Merchant Center."}}


def _t(name, desc, props=None, req=None):
    p = dict(props or {})
    p["account"] = {"type": "string", "description": _AC}
    return {"name": name, "description": desc, "inputSchema": {"type": "object", "properties": p, "required": req or []}}


TOOLS = [
    _t("list_regions", "Regiones definidas (para envíos/inventario regional).", _AID, ["account_id"]),
    _t("create_region", "ESCRITURA: crea una región por códigos postales [{begin,end}] o geotarget_ids.",
       dict(_AID, region_id=_S, display_name=_S, postal_codes=_LO, geotarget_ids=_LI), ["account_id", "region_id", "display_name"]),
    _t("delete_region", "ESCRITURA: borra una región.", dict(_AID, region_id=_S), ["account_id", "region_id"]),
    _t("get_business_info", "Información de negocio (dirección, teléfono, atención al cliente).", _AID, ["account_id"]),
    _t("update_business_info", "ESCRITURA: modifica la información de negocio (body con address / phone / customerService).",
       dict(_AID, body=_O), ["account_id", "body"]),
    _t("get_homepage", "Página principal y estado de reclamación.", _AID, ["account_id"]),
    _t("update_homepage", "ESCRITURA: cambia la URL de la página principal.", dict(_AID, uri=_S), ["account_id", "uri"]),
    _t("claim_homepage", "ESCRITURA: reclama la página principal (verificación previa necesaria).", dict(_AID, overwrite=_B), ["account_id"]),
    _t("unclaim_homepage", "ESCRITURA: libera la reclamación de la página principal.", _AID, ["account_id"]),
    _t("list_programs", "Programas (free-listings, shopping-ads...) y su estado / requisitos.", _AID, ["account_id"]),
    _t("enable_program", "ESCRITURA: activa (enable=true) o desactiva un programa.", dict(_AID, program=_S, enable=_B), ["account_id", "program"]),
    _t("get_autofeed", "Ajustes de autofeed (rastreo automático de la web).", _AID, ["account_id"]),
    _t("update_autofeed", "ESCRITURA: activa/desactiva el autofeed de productos.", dict(_AID, enable_products=_B), ["account_id", "enable_products"]),
    _t("get_email_preferences", "Preferencias de email del usuario actual en la cuenta.", _AID, ["account_id"]),
    _t("list_return_policies", "Políticas de devolución online.", _AID, ["account_id"]),
    _t("create_return_policy", "ESCRITURA: crea una política de devolución (body OnlineReturnPolicy).", dict(_AID, body=_O), ["account_id", "body"]),
    _t("delete_return_policy", "ESCRITURA: borra una política de devolución (name completo).", {"policy_name": _S}, ["policy_name"]),
    _t("get_terms_of_service_state", "Estado de aceptación de los términos de servicio.", dict(_AID, region=_S), ["account_id"]),
    _t("list_users", "Usuarios de la cuenta y sus roles.", _AID, ["account_id"]),
    _t("list_gbp_accounts", "Perfiles de Google Business vinculables/vinculados.", _AID, ["account_id"]),
    _t("list_shipping_settings", "Configuración de envíos completa.", _AID, ["account_id"]),
    _t("list_conversion_sources", "Fuentes de conversión (GA4, destino Merchant Center).", _AID, ["account_id"]),
    _t("create_conversion_source", "ESCRITURA: crea fuente de conversión (body: googleAnalyticsLink | merchantCenterDestination).",
       dict(_AID, body=_O), ["account_id", "body"]),
    _t("delete_conversion_source", "ESCRITURA: archiva una fuente de conversión.", {"source_name": _S}, ["source_name"]),
    _t("list_notification_subscriptions", "Suscripciones a notificaciones (webhooks).", _AID, ["account_id"]),
    _t("create_notification_subscription", "ESCRITURA: webhook para PRODUCT_STATUS_CHANGE.",
       dict(_AID, callback_uri=_S, event=_S, all_managed=_B), ["account_id", "callback_uri"]),
    _t("delete_notification_subscription", "ESCRITURA: borra una suscripción.", {"sub_name": _S}, ["sub_name"]),
    _t("render_account_issues", "Incidencias de CUENTA con explicación y acciones disponibles.", dict(_AID, language=_S), ["account_id"]),
    _t("render_product_issues", "Incidencias de un PRODUCTO con explicación y acciones.", dict(_AID, product_id=_S, language=_S), ["account_id", "product_id"]),
    _t("trigger_action", "ESCRITURA: ejecuta una acción de resolución (action_context de render_*_issues).",
       dict(_AID, action_context=_S, user_input=_O, language=_S), ["account_id", "action_context"]),
    _t("aggregate_product_statuses", "Estados agregados de productos por país/canal/destino (filter opcional).", dict(_AID, filter=_S), ["account_id"]),
    _t("list_reviews", "Reseñas: kind = productReviews | merchantReviews.", dict(_AID, kind=_S, page_size=_I, page_token=_S), ["account_id"]),
    _t("insert_review", "ESCRITURA: inserta una reseña (kind, data_source, body de la API).",
       dict(_AID, kind=_S, data_source=_S, body=_O), ["account_id", "kind", "data_source", "body"]),
    _t("delete_review", "ESCRITURA: borra una reseña (name completo).", {"review_name": _S}, ["review_name"]),
    _t("lfp_insert_inventory", "ESCRITURA (LFP): inventario local de un comercio (body LfpInventory).",
       dict(_AID, target_account=_S, body=_O), ["account_id", "target_account", "body"]),
    _t("lfp_insert_sale", "ESCRITURA (LFP): venta local (body LfpSale).", dict(_AID, target_account=_S, body=_O), ["account_id", "target_account", "body"]),
    _t("create_order_tracking_signal", "ESCRITURA: señal de seguimiento de pedido (body OrderTrackingSignal).", dict(_AID, body=_O), ["account_id", "body"]),
    _t("insert_products_bulk", "ESCRITURA: alta/actualización masiva de productos (lista de ProductInput) en una fuente API.",
       dict(_AID, data_source=_S, product_inputs=_LO, stop_on_error=_B), ["account_id", "data_source", "product_inputs"]),
    _t("api_request_any", ("Llamada cruda a cualquier sub-API de Merchant API probando v1 -> v1beta -> v1alpha (o version fija). "
                           "sub_api: accounts | products | inventories | datasources | reports | promotions | quota | conversions | "
                           "notifications | lfp | issueresolution | ordertracking | reviews | productstudio."),
       {"method": _S, "sub_api": _S, "path": _S, "params": _O, "body": _O, "version": _S}, ["method", "sub_api", "path"]),
]

HANDLERS = {
    "list_regions": lambda a: list_regions(a["account_id"], a.get("account")),
    "create_region": lambda a: create_region(a["account_id"], a["region_id"], a["display_name"], a.get("postal_codes"), a.get("geotarget_ids"), a.get("account")),
    "delete_region": lambda a: delete_region(a["account_id"], a["region_id"], a.get("account")),
    "get_business_info": lambda a: get_business_info(a["account_id"], a.get("account")),
    "update_business_info": lambda a: update_business_info(a["account_id"], a["body"], a.get("account")),
    "get_homepage": lambda a: get_homepage(a["account_id"], a.get("account")),
    "update_homepage": lambda a: update_homepage(a["account_id"], a["uri"], a.get("account")),
    "claim_homepage": lambda a: claim_homepage(a["account_id"], a.get("overwrite", False), a.get("account")),
    "unclaim_homepage": lambda a: unclaim_homepage(a["account_id"], a.get("account")),
    "list_programs": lambda a: list_programs(a["account_id"], a.get("account")),
    "enable_program": lambda a: enable_program(a["account_id"], a["program"], a.get("enable", True), a.get("account")),
    "get_autofeed": lambda a: get_autofeed(a["account_id"], a.get("account")),
    "update_autofeed": lambda a: update_autofeed(a["account_id"], a["enable_products"], a.get("account")),
    "get_email_preferences": lambda a: get_email_preferences(a["account_id"], a.get("account")),
    "list_return_policies": lambda a: list_return_policies(a["account_id"], a.get("account")),
    "create_return_policy": lambda a: create_return_policy(a["account_id"], a["body"], a.get("account")),
    "delete_return_policy": lambda a: delete_return_policy(a["policy_name"], a.get("account")),
    "get_terms_of_service_state": lambda a: get_terms_of_service_state(a["account_id"], a.get("region", "ES"), a.get("account")),
    "list_users": lambda a: list_users(a["account_id"], a.get("account")),
    "list_gbp_accounts": lambda a: list_gbp_accounts(a["account_id"], a.get("account")),
    "list_shipping_settings": lambda a: list_shipping_settings(a["account_id"], a.get("account")),
    "list_conversion_sources": lambda a: list_conversion_sources(a["account_id"], a.get("account")),
    "create_conversion_source": lambda a: create_conversion_source(a["account_id"], a["body"], a.get("account")),
    "delete_conversion_source": lambda a: delete_conversion_source(a["source_name"], a.get("account")),
    "list_notification_subscriptions": lambda a: list_notification_subscriptions(a["account_id"], a.get("account")),
    "create_notification_subscription": lambda a: create_notification_subscription(a["account_id"], a["callback_uri"], a.get("event", "PRODUCT_STATUS_CHANGE"),
                                                                                   a.get("all_managed", True), a.get("account")),
    "delete_notification_subscription": lambda a: delete_notification_subscription(a["sub_name"], a.get("account")),
    "render_account_issues": lambda a: render_account_issues(a["account_id"], a.get("language", "es-ES"), a.get("account")),
    "render_product_issues": lambda a: render_product_issues(a["account_id"], a["product_id"], a.get("language", "es-ES"), a.get("account")),
    "trigger_action": lambda a: trigger_action(a["account_id"], a["action_context"], a.get("user_input"), a.get("language", "es-ES"), a.get("account")),
    "aggregate_product_statuses": lambda a: aggregate_product_statuses(a["account_id"], a.get("filter"), a.get("account")),
    "list_reviews": lambda a: list_reviews(a["account_id"], a.get("kind", "productReviews"), a.get("page_size", 100), a.get("page_token"), a.get("account")),
    "insert_review": lambda a: insert_review(a["account_id"], a["kind"], a["data_source"], a["body"], a.get("account")),
    "delete_review": lambda a: delete_review(a["review_name"], a.get("account")),
    "lfp_insert_inventory": lambda a: lfp_insert_inventory(a["account_id"], a["target_account"], a["body"], a.get("account")),
    "lfp_insert_sale": lambda a: lfp_insert_sale(a["account_id"], a["target_account"], a["body"], a.get("account")),
    "create_order_tracking_signal": lambda a: create_order_tracking_signal(a["account_id"], a["body"], a.get("account")),
    "insert_products_bulk": lambda a: insert_products_bulk(a["account_id"], a["data_source"], a["product_inputs"], a.get("stop_on_error", False), a.get("account")),
    "api_request_any": lambda a: api_request_any(a["method"], a["sub_api"], a["path"], a.get("params"), a.get("body"), a.get("version"), a.get("account")),
}
