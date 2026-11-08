"""
Extensión Google Ads: cobertura COMPLETA de la API (v25).
  - mutate genérico sobre CUALQUIER recurso (campaigns, adGroups, assetGroups, labels,
    conversionActions, experiments, biddingStrategies...)
  - mutate_multi atómico (googleAds:mutate con ids temporales)
  - api_call genérico para cualquier servicio REST (keywordPlanIdeas, recommendations, reachPlan,
    audienceInsights, batchJobs, geoTargetConstants...)
  - GoogleAdsFieldService (descubrir campos/segmentos/métricas)
  - atajos: ideas de keywords, métricas históricas, previsión, geo suggest, recomendaciones
    (listar/aplicar/descartar), acciones de conversión, PMax + asset groups, etiquetas,
    edición de campañas/grupos/keywords, borrado, historial de cambios.
"""
import requests
from gads import ads


def _post(url_path, body, customer_id=None, account=None, method="POST", params=None):
    cid = ads._cid(customer_id, account)
    if account is None and customer_id:
        account = ads._owner_of(cid)
    url = f"{ads.BASE}/{url_path.lstrip('/')}"
    r = requests.request(method, url, headers=ads._headers(account), json=body, params=params, timeout=180)
    if r.status_code >= 300:
        raise ads.AdsError(f"{method} {url_path} HTTP {r.status_code}: {r.text[:1500]}")
    return r.json() if r.text.strip() else {"ok": True}


def api_call(method, path, body=None, params=None, customer_id=None, account=None):
    """path relativo a la versión, p.ej. 'customers/123:generateKeywordIdeas'
    o 'googleAdsFields:search' o 'customers:listAccessibleCustomers'."""
    return _post(path, body, customer_id, account, method.upper(), params)


def mutate(customer_id, service, operations, validate_only=False, partial_failure=False, account=None):
    """service: campaigns | adGroups | adGroupAds | adGroupCriteria | campaignCriteria | assets |
    assetGroups | assetGroupAssets | assetGroupSignals | campaignAssets | conversionActions |
    labels | campaignLabels | biddingStrategies | campaignBudgets | sharedSets | experiments | ...
    operations: [{create:{...}} | {update:{resourceName,...}, updateMask:'a,b'} | {remove:'resourceName'}]"""
    body = {"operations": operations, "validateOnly": bool(validate_only), "partialFailure": bool(partial_failure)}
    return _post(f"customers/{ads._cid(customer_id)}/{service}:mutate", body, customer_id, account)


def mutate_multi(customer_id, mutate_operations, validate_only=False, partial_failure=False, account=None):
    """googleAds:mutate: varias entidades en una sola transacción atómica. mutate_operations:
    [{campaignBudgetOperation:{create:{...}}}, {campaignOperation:{create:{...}}}] (permite temp ids -1, -2...)."""
    body = {"mutateOperations": mutate_operations, "validateOnly": bool(validate_only),
            "partialFailure": bool(partial_failure)}
    return _post(f"customers/{ads._cid(customer_id)}/googleAds:mutate", body, customer_id, account)


def search_paged(customer_id, query, page_token=None, summary_row=False, account=None):
    """googleAds:search: páginas fijas de 10.000 filas; devuelve nextPageToken y (opcional) fila resumen."""
    body = {"query": query}
    if page_token:
        body["pageToken"] = page_token
    if summary_row:
        body["summaryRowSetting"] = "SUMMARY_ROW_WITH_RESULTS"
    return _post(f"customers/{ads._cid(customer_id)}/googleAds:search", body, customer_id, account)


def google_ads_fields(query, account=None):
    """GoogleAdsFieldService. query p.ej. "SELECT name, category, selectable, filterable, data_type,
    selectable_with WHERE name LIKE 'campaign.%'"."""
    label = account or ads.DEFAULT_ACCOUNT
    r = requests.post(f"{ads.BASE}/googleAdsFields:search", headers=ads._headers(label),
                      json={"query": query, "pageSize": 5000}, timeout=120)
    if r.status_code >= 300:
        raise ads.AdsError(f"googleAdsFields HTTP {r.status_code}: {r.text[:800]}")
    return r.json().get("results", [])


# ------------------------------------------------------------- planificación
def generate_keyword_ideas(customer_id, keywords=None, page_url=None, language_id=1003, geo_ids=(2724,),
                           network="GOOGLE_SEARCH", include_adult=False, page_size=200, account=None):
    body = {"language": f"languageConstants/{language_id}",
            "geoTargetConstants": [f"geoTargetConstants/{g}" for g in geo_ids],
            "keywordPlanNetwork": network, "includeAdultKeywords": include_adult, "pageSize": page_size}
    if keywords and page_url:
        body["keywordAndUrlSeed"] = {"keywords": keywords, "url": page_url}
    elif keywords:
        body["keywordSeed"] = {"keywords": keywords}
    elif page_url:
        body["urlSeed"] = {"url": page_url}
    else:
        raise ads.AdsError("Indica keywords y/o page_url.")
    return _post(f"customers/{ads._cid(customer_id)}:generateKeywordIdeas", body, customer_id, account)


def keyword_historical_metrics(customer_id, keywords, language_id=1003, geo_ids=(2724,),
                               network="GOOGLE_SEARCH", account=None):
    body = {"keywords": keywords, "language": f"languageConstants/{language_id}",
            "geoTargetConstants": [f"geoTargetConstants/{g}" for g in geo_ids], "keywordPlanNetwork": network}
    return _post(f"customers/{ads._cid(customer_id)}:generateKeywordHistoricalMetrics",
                 body, customer_id, account)


def keyword_forecast(customer_id, campaign_to_forecast, forecast_period=None, account=None):
    body = {"campaign": campaign_to_forecast}
    if forecast_period:
        body["forecastPeriod"] = forecast_period
    return _post(f"customers/{ads._cid(customer_id)}:generateKeywordForecastMetrics",
                 body, customer_id, account)


def suggest_geo_targets(location_names, locale="es", country_code="ES", account=None):
    body = {"locale": locale, "countryCode": country_code, "locationNames": {"names": location_names}}
    label = account or ads.DEFAULT_ACCOUNT
    r = requests.post(f"{ads.BASE}/geoTargetConstants:suggest", headers=ads._headers(label), json=body, timeout=60)
    if r.status_code >= 300:
        raise ads.AdsError(f"geoTargetConstants:suggest HTTP {r.status_code}: {r.text[:800]}")
    return r.json().get("geoTargetConstantSuggestions", [])


# ------------------------------------------------------------- recomendaciones
def list_recommendations(customer_id, types=None, campaign_id=None, account=None):
    where = ["recommendation.dismissed = FALSE"]
    if types:
        where.append("recommendation.type IN (" + ",".join(f"'{t}'" for t in types) + ")")
    if campaign_id:
        where.append(f"campaign.id = {campaign_id}")
    q = ("SELECT recommendation.resource_name, recommendation.type, recommendation.campaign, "
         "recommendation.ad_group, recommendation.dismissed, campaign.name "
         "FROM recommendation WHERE " + " AND ".join(where))
    return ads.search(q, customer_id, account)


def apply_recommendations(customer_id, resource_names, partial_failure=True, account=None):
    body = {"operations": [{"resourceName": rn} for rn in resource_names], "partialFailure": partial_failure}
    return _post(f"customers/{ads._cid(customer_id)}/recommendations:apply", body, customer_id, account)


def dismiss_recommendations(customer_id, resource_names, partial_failure=True, account=None):
    body = {"operations": [{"resourceName": rn} for rn in resource_names], "partialFailure": partial_failure}
    return _post(f"customers/{ads._cid(customer_id)}/recommendations:dismiss", body, customer_id, account)


# ------------------------------------------------------------- acciones de conversión
def create_conversion_action(customer_id, name, category="LEAD", type_="WEBPAGE", default_value_eur=None,
                             counting="ONE_PER_CLICK", primary=True, click_window_days=30,
                             view_window_days=1, attribution="DATA_DRIVEN", validate_only=False, account=None):
    """category: LEAD | SUBMIT_LEAD_FORM | PURCHASE | SIGNUP | PHONE_CALL_LEAD | BOOK_APPOINTMENT | CONTACT...
    type_: WEBPAGE | UPLOAD_CLICKS | UPLOAD_CALLS | GOOGLE_ANALYTICS_4_CUSTOM | ..."""
    ca = {"name": name, "category": category, "type": type_, "status": "ENABLED",
          "countingType": counting, "primaryForGoal": primary,
          "clickThroughLookbackWindowDays": click_window_days, "viewThroughLookbackWindowDays": view_window_days,
          "attributionModelSettings": {"attributionModel": attribution}}
    if default_value_eur is not None:
        ca["valueSettings"] = {"defaultValue": float(default_value_eur), "defaultCurrencyCode": "EUR",
                               "alwaysUseDefaultValue": False}
    return ads.mutate("conversionActions", [{"create": ca}], customer_id, validate_only, account)


# ------------------------------------------------------------- Performance Max
def create_pmax_campaign(customer_id, name, daily_eur, target_roas=None, target_cpa_eur=None,
                         final_url_expansion=True, merchant_id=None, sales_country="ES",
                         geo_ids=None, language_ids=(1003,), start_date=None, end_date=None,
                         status="PAUSED", validate_only=False, account=None):
    cid = ads._cid(customer_id)
    ops = [{"campaignBudgetOperation": {"create": {
        "resourceName": f"customers/{cid}/campaignBudgets/-1", "name": f"{name} - presupuesto",
        "amountMicros": ads.micros(daily_eur), "deliveryMethod": "STANDARD", "explicitlyShared": False}}}]
    camp = {"resourceName": f"customers/{cid}/campaigns/-2", "name": name, "status": status,
            "advertisingChannelType": "PERFORMANCE_MAX", "campaignBudget": f"customers/{cid}/campaignBudgets/-1",
            "urlExpansionOptOut": (not final_url_expansion)}
    if target_roas:
        camp["maximizeConversionValue"] = {"targetRoas": float(target_roas)}
    elif target_cpa_eur:
        camp["maximizeConversions"] = {"targetCpaMicros": ads.micros(target_cpa_eur)}
    else:
        camp["maximizeConversions"] = {}
    if merchant_id:
        camp["shoppingSetting"] = {"merchantId": str(merchant_id), "feedLabel": sales_country}
    if start_date:
        camp["startDate"] = start_date.replace("-", "")
    if end_date:
        camp["endDate"] = end_date.replace("-", "")
    ops.append({"campaignOperation": {"create": camp}})
    for g in (geo_ids or []):
        ops.append({"campaignCriterionOperation": {"create": {
            "campaign": f"customers/{cid}/campaigns/-2", "location": {"geoTargetConstant": f"geoTargetConstants/{g}"}}}})
    for l in (language_ids or []):
        ops.append({"campaignCriterionOperation": {"create": {
            "campaign": f"customers/{cid}/campaigns/-2", "language": {"languageConstant": f"languageConstants/{l}"}}}})
    return mutate_multi(customer_id, ops, validate_only, False, account)


def create_asset_group(customer_id, campaign_rn, name, final_urls, headlines, long_headlines, descriptions,
                       business_name, images, logos, square_images=None, videos=None, path1=None, path2=None,
                       status="PAUSED", validate_only=False, account=None):
    """images/square_images/logos: rutas locales o URLs. videos: ids de YouTube."""
    cid = ads._cid(customer_id)
    ag_rn = f"customers/{cid}/assetGroups/-1"
    ag = {"resourceName": ag_rn, "campaign": campaign_rn, "name": name, "finalUrls": final_urls, "status": status}
    if path1:
        ag["path1"] = path1
    if path2:
        ag["path2"] = path2
    ops = [{"assetGroupOperation": {"create": ag}}]
    tmp = [-2]

    def add_text(text, field):
        tmp[0] -= 1
        rn = f"customers/{cid}/assets/{tmp[0]}"
        ops.append({"assetOperation": {"create": {"resourceName": rn, "textAsset": {"text": text}}}})
        ops.append({"assetGroupAssetOperation": {"create": {"assetGroup": ag_rn, "asset": rn, "fieldType": field}}})

    def add_image(src, field, idx):
        tmp[0] -= 1
        rn = f"customers/{cid}/assets/{tmp[0]}"
        ops.append({"assetOperation": {"create": {"resourceName": rn, "name": f"{name} {field} {idx}",
                                                  "imageAsset": {"data": ads._load_image_b64(src)}}}})
        ops.append({"assetGroupAssetOperation": {"create": {"assetGroup": ag_rn, "asset": rn, "fieldType": field}}})

    for h in headlines:
        add_text(h, "HEADLINE")
    for h in long_headlines:
        add_text(h, "LONG_HEADLINE")
    for d in descriptions:
        add_text(d, "DESCRIPTION")
    add_text(business_name, "BUSINESS_NAME")
    for i, im in enumerate(images):
        add_image(im, "MARKETING_IMAGE", i)
    for i, im in enumerate(square_images or []):
        add_image(im, "SQUARE_MARKETING_IMAGE", i)
    for i, im in enumerate(logos):
        add_image(im, "LOGO", i)
    for i, v in enumerate(videos or []):
        tmp[0] -= 1
        rn = f"customers/{cid}/assets/{tmp[0]}"
        ops.append({"assetOperation": {"create": {"resourceName": rn, "name": f"{name} video {i}",
                                                  "youtubeVideoAsset": {"youtubeVideoId": v}}}})
        ops.append({"assetGroupAssetOperation": {"create": {"assetGroup": ag_rn, "asset": rn, "fieldType": "YOUTUBE_VIDEO"}}})
    return mutate_multi(customer_id, ops, validate_only, False, account)


# ------------------------------------------------------------- etiquetas y ediciones rápidas
def create_label(customer_id, name, description=None, color=None, validate_only=False, account=None):
    lb = {"name": name}
    if description:
        lb["description"] = description
    if color:
        lb["textLabel"] = {"backgroundColor": color}
    return ads.mutate("labels", [{"create": lb}], customer_id, validate_only, account)


def apply_label(customer_id, label_rn, campaign_rns=None, ad_group_rns=None, ad_group_ad_rns=None,
                criterion_rns=None, validate_only=False, account=None):
    out = {}
    if campaign_rns:
        out["campaigns"] = ads.mutate("campaignLabels", [{"create": {"campaign": c, "label": label_rn}} for c in campaign_rns],
                                      customer_id, validate_only, account)
    if ad_group_rns:
        out["adGroups"] = ads.mutate("adGroupLabels", [{"create": {"adGroup": c, "label": label_rn}} for c in ad_group_rns],
                                     customer_id, validate_only, account)
    if ad_group_ad_rns:
        out["ads"] = ads.mutate("adGroupAdLabels", [{"create": {"adGroupAd": c, "label": label_rn}} for c in ad_group_ad_rns],
                                customer_id, validate_only, account)
    if criterion_rns:
        out["criteria"] = ads.mutate("adGroupCriterionLabels", [{"create": {"adGroupCriterion": c, "label": label_rn}} for c in criterion_rns],
                                     customer_id, validate_only, account)
    return out


def _snake(k):
    out = ""
    for ch in k:
        out += "_" + ch.lower() if ch.isupper() else ch
    return out


def update_resource(customer_id, service, resource_name, fields, validate_only=False, account=None):
    """Actualiza cualquier recurso: fields = {campo_json: valor} (camelCase; el updateMask se deriva).
    Ej. service='adGroups', fields={'name':'Nuevo','cpcBidMicros':'800000'}."""
    op = {"update": {"resourceName": resource_name, **fields}, "updateMask": ",".join(_snake(k) for k in fields)}
    return ads.mutate(service, [op], customer_id, validate_only, account)


def update_campaign(customer_id, campaign_id, name=None, status=None, start_date=None, end_date=None,
                    validate_only=False, account=None):
    f = {}
    if name is not None:
        f["name"] = name
    if status is not None:
        f["status"] = status
    if start_date:
        f["startDate"] = start_date.replace("-", "")
    if end_date:
        f["endDate"] = end_date.replace("-", "")
    return update_resource(customer_id, "campaigns", f"customers/{ads._cid(customer_id)}/campaigns/{campaign_id}", f, validate_only, account)


def update_ad_group(customer_id, ad_group_id, name=None, status=None, cpc_eur=None, validate_only=False, account=None):
    f = {}
    if name is not None:
        f["name"] = name
    if status is not None:
        f["status"] = status
    if cpc_eur is not None:
        f["cpcBidMicros"] = str(ads.micros(cpc_eur))
    return update_resource(customer_id, "adGroups", f"customers/{ads._cid(customer_id)}/adGroups/{ad_group_id}", f, validate_only, account)


def update_keyword(customer_id, criterion_rn, status=None, cpc_eur=None, final_url=None, validate_only=False, account=None):
    f = {}
    if status is not None:
        f["status"] = status
    if cpc_eur is not None:
        f["cpcBidMicros"] = str(ads.micros(cpc_eur))
    if final_url:
        f["finalUrls"] = [final_url]
    return update_resource(customer_id, "adGroupCriteria", criterion_rn, f, validate_only, account)


def remove_resources(customer_id, service, resource_names, validate_only=False, account=None):
    return ads.mutate(service, [{"remove": rn} for rn in resource_names], customer_id, validate_only, account)


def list_change_history(customer_id, days=7, account=None):
    import datetime as _dt
    end = _dt.date.today() + _dt.timedelta(days=1)
    start = _dt.date.today() - _dt.timedelta(days=min(max(int(days), 1), 29))
    q = ("SELECT change_event.change_date_time, change_event.change_resource_type, change_event.change_resource_name, "
         "change_event.user_email, change_event.client_type, change_event.resource_change_operation, "
         "change_event.changed_fields, campaign.name FROM change_event "
         f"WHERE change_event.change_date_time >= '{start.isoformat()}' AND change_event.change_date_time <= '{end.isoformat()}' "
         "ORDER BY change_event.change_date_time DESC LIMIT 500")
    return ads.search(q, customer_id, account)


# ------------------------------------------------------------- tools
_S = {"type": "string"}
_B = {"type": "boolean"}
_I = {"type": "integer"}
_N = {"type": "number"}
_O = {"type": "object"}
_LS = {"type": "array", "items": {"type": "string"}}
_LO = {"type": "array", "items": {"type": "object"}}
_LI = {"type": "array", "items": {"type": "integer"}}
_CID = {"customer_id": {"type": "string", "description": "ID de la cuenta cliente (10 dígitos)."}}


def _t(name, desc, props=None, req=None):
    p = dict(props or {})
    p["account"] = {"type": "string", "description": "Etiqueta de login (opcional; se resuelve sola por customer_id)."}
    return {"name": name, "description": desc, "inputSchema": {"type": "object", "properties": p, "required": req or []}}


TOOLS = [
    _t("mutate", ("ESCRITURA GENÉRICA sobre CUALQUIER recurso de Google Ads. service p.ej. campaigns, adGroups, adGroupAds, "
                  "adGroupCriteria, campaignCriteria, assets, campaignAssets, assetGroups, assetGroupAssets, assetGroupSignals, "
                  "conversionActions, conversionValueRules, labels, biddingStrategies, campaignBudgets, sharedSets, "
                  "experiments, experimentArms, customerNegativeCriteria, adParameters... operations en JSON camelCase: "
                  "[{create:{...}} | {update:{resourceName,...}, updateMask:'a,b'} | {remove:'rn'}]. validate_only = dry-run."),
       dict(_CID, service=_S, operations=_LO, validate_only=_B, partial_failure=_B), ["customer_id", "service", "operations"]),
    _t("mutate_multi", ("ESCRITURA ATÓMICA multi-entidad (googleAds:mutate) con ids temporales -1,-2... "
                        "mutate_operations: [{campaignBudgetOperation:{create:{}}}, {campaignOperation:{create:{}}}, ...]"),
       dict(_CID, mutate_operations=_LO, validate_only=_B, partial_failure=_B), ["customer_id", "mutate_operations"]),
    _t("api_call", ("Llamada cruda a CUALQUIER servicio REST de la Google Ads API (versión actual). path relativo, p.ej. "
                    "'customers/123:generateKeywordIdeas', 'customers/123:generateReachForecast', 'customers/123:uploadClickConversions', 'customers/123/audienceInsights:generateAudienceCompositionInsights', "
                    "'customers/123/batchJobs:mutate', 'customers/123/invoices:list' (GET con params), 'customers/123/paymentsAccounts:list'."),
       dict(_CID, method=_S, path=_S, body=_O, params=_O), ["method", "path"]),
    _t("search_paged", "GAQL con paginación (googleAds:search): páginas de 10.000 filas con page_token y fila resumen opcional.",
       dict(_CID, query=_S, page_token=_S, summary_row=_B), ["customer_id", "query"]),
    _t("google_ads_fields", "Descubre campos/segmentos/métricas (GoogleAdsFieldService). query: SELECT name, category, selectable_with WHERE name LIKE 'campaign.%'",
       {"query": _S}, ["query"]),
    _t("generate_keyword_ideas", "Keyword Planner: ideas por keywords y/o URL (volumen, competencia, pujas). geo_ids p.ej. [2724]=España; language_id 1003=español.",
       dict(_CID, keywords=_LS, page_url=_S, language_id=_I, geo_ids=_LI, network=_S, include_adult=_B, page_size=_I), ["customer_id"]),
    _t("keyword_historical_metrics", "Keyword Planner: métricas históricas de una lista de keywords.",
       dict(_CID, keywords=_LS, language_id=_I, geo_ids=_LI, network=_S), ["customer_id", "keywords"]),
    _t("keyword_forecast", "Keyword Planner: previsión (campaign_to_forecast en formato CampaignToForecast de la API).",
       dict(_CID, campaign_to_forecast=_O, forecast_period=_O), ["customer_id", "campaign_to_forecast"]),
    _t("suggest_geo_targets", "Busca IDs de ubicación por nombre (p.ej. ['Málaga','Marbella']).",
       {"location_names": _LS, "locale": _S, "country_code": _S}, ["location_names"]),
    _t("list_recommendations", "Recomendaciones activas (opcional filtrar por tipos o campaña). El detalle de impacto se lee con run_gaql sobre recommendation.<tipo>_recommendation.",
       dict(_CID, types=_LS, campaign_id=_S), ["customer_id"]),
    _t("apply_recommendations", "ESCRITURA: aplica recomendaciones por resource name.", dict(_CID, resource_names=_LS, partial_failure=_B),
       ["customer_id", "resource_names"]),
    _t("dismiss_recommendations", "ESCRITURA: descarta recomendaciones por resource name.", dict(_CID, resource_names=_LS, partial_failure=_B),
       ["customer_id", "resource_names"]),
    _t("create_conversion_action", ("ESCRITURA: crea una acción de conversión. category: LEAD|SUBMIT_LEAD_FORM|PURCHASE|SIGNUP|PHONE_CALL_LEAD|"
                                    "BOOK_APPOINTMENT|CONTACT|... type: WEBPAGE|UPLOAD_CLICKS|UPLOAD_CALLS. Devuelve el resource name "
                                    "(el id/label del tag se lee con GAQL: conversion_action.tag_snippets)."),
       dict(_CID, name=_S, category=_S, type=_S, default_value_eur=_N, counting=_S, primary=_B, click_window_days=_I,
            view_window_days=_I, attribution=_S, validate_only=_B), ["customer_id", "name"]),
    _t("create_pmax_campaign", ("ESCRITURA: crea presupuesto + campaña Performance Max (EN PAUSA por defecto) con geo/idiomas; "
                                "tROAS o tCPA opcional; merchant_id para retail. Después usa create_asset_group."),
       dict(_CID, name=_S, daily_eur=_N, target_roas=_N, target_cpa_eur=_N, final_url_expansion=_B, merchant_id=_S, sales_country=_S,
            geo_ids=_LI, language_ids=_LI, start_date=_S, end_date=_S, status=_S, validate_only=_B), ["customer_id", "name", "daily_eur"]),
    _t("create_asset_group", ("ESCRITURA: asset group PMax completo (títulos, títulos largos, descripciones, nombre de negocio, "
                              "imágenes 1.91:1, cuadradas 1:1, logos, vídeos YouTube). Mínimos: 3 headlines, 1 long headline, 2 descriptions, "
                              "1 imagen horizontal, 1 cuadrada, 1 logo."),
       dict(_CID, campaign_resource_name=_S, name=_S, final_urls=_LS, headlines=_LS, long_headlines=_LS, descriptions=_LS,
            business_name=_S, images=_LS, logos=_LS, square_images=_LS, videos=_LS, path1=_S, path2=_S, status=_S, validate_only=_B),
       ["customer_id", "campaign_resource_name", "name", "final_urls", "headlines", "long_headlines", "descriptions", "business_name", "images", "logos"]),
    _t("create_label", "ESCRITURA: crea una etiqueta (color hex opcional).", dict(_CID, name=_S, description=_S, color=_S, validate_only=_B), ["customer_id", "name"]),
    _t("apply_label", "ESCRITURA: aplica una etiqueta a campañas / grupos / anuncios / criterios (resource names).",
       dict(_CID, label_rn=_S, campaign_rns=_LS, ad_group_rns=_LS, ad_group_ad_rns=_LS, criterion_rns=_LS, validate_only=_B), ["customer_id", "label_rn"]),
    _t("update_resource", "ESCRITURA: actualiza CUALQUIER recurso: service + resource_name + fields {campoCamelCase: valor} (updateMask automático).",
       dict(_CID, service=_S, resource_name=_S, fields=_O, validate_only=_B), ["customer_id", "service", "resource_name", "fields"]),
    _t("update_campaign", "ESCRITURA: nombre, estado o fechas de una campaña.", dict(_CID, campaign_id=_S, name=_S, status=_S, start_date=_S, end_date=_S, validate_only=_B),
       ["customer_id", "campaign_id"]),
    _t("update_ad_group", "ESCRITURA: nombre, estado o CPC por defecto de un grupo.", dict(_CID, ad_group_id=_S, name=_S, status=_S, cpc_eur=_N, validate_only=_B),
       ["customer_id", "ad_group_id"]),
    _t("update_keyword", "ESCRITURA: estado, puja o URL final de una keyword (criterion resource name).",
       dict(_CID, criterion_rn=_S, status=_S, cpc_eur=_N, final_url=_S, validate_only=_B), ["customer_id", "criterion_rn"]),
    _t("remove_resources", "ESCRITURA: elimina recursos por resource name (service + lista).", dict(_CID, service=_S, resource_names=_LS, validate_only=_B),
       ["customer_id", "service", "resource_names"]),
    _t("list_change_history", "Historial de cambios de la cuenta (days: 1-29, máximo que permite la API).", dict(_CID, days=_I), ["customer_id"]),
]

HANDLERS = {
    "mutate": lambda a: mutate(a["customer_id"], a["service"], a["operations"], a.get("validate_only", False), a.get("partial_failure", False), a.get("account")),
    "mutate_multi": lambda a: mutate_multi(a["customer_id"], a["mutate_operations"], a.get("validate_only", False), a.get("partial_failure", False), a.get("account")),
    "api_call": lambda a: api_call(a["method"], a["path"], a.get("body"), a.get("params"), a.get("customer_id"), a.get("account")),
    "search_paged": lambda a: search_paged(a["customer_id"], a["query"], a.get("page_token"), a.get("summary_row", False), a.get("account")),
    "google_ads_fields": lambda a: google_ads_fields(a["query"], a.get("account")),
    "generate_keyword_ideas": lambda a: generate_keyword_ideas(a["customer_id"], a.get("keywords"), a.get("page_url"), a.get("language_id", 1003),
                                                               a.get("geo_ids") or [2724], a.get("network", "GOOGLE_SEARCH"), a.get("include_adult", False),
                                                               a.get("page_size", 200), a.get("account")),
    "keyword_historical_metrics": lambda a: keyword_historical_metrics(a["customer_id"], a["keywords"], a.get("language_id", 1003), a.get("geo_ids") or [2724],
                                                                       a.get("network", "GOOGLE_SEARCH"), a.get("account")),
    "keyword_forecast": lambda a: keyword_forecast(a["customer_id"], a["campaign_to_forecast"], a.get("forecast_period"), a.get("account")),
    "suggest_geo_targets": lambda a: suggest_geo_targets(a["location_names"], a.get("locale", "es"), a.get("country_code", "ES"), a.get("account")),
    "list_recommendations": lambda a: list_recommendations(a["customer_id"], a.get("types"), a.get("campaign_id"), a.get("account")),
    "apply_recommendations": lambda a: apply_recommendations(a["customer_id"], a["resource_names"], a.get("partial_failure", True), a.get("account")),
    "dismiss_recommendations": lambda a: dismiss_recommendations(a["customer_id"], a["resource_names"], a.get("partial_failure", True), a.get("account")),
    "create_conversion_action": lambda a: create_conversion_action(a["customer_id"], a["name"], a.get("category", "LEAD"), a.get("type", "WEBPAGE"),
                                                                   a.get("default_value_eur"), a.get("counting", "ONE_PER_CLICK"), a.get("primary", True),
                                                                   a.get("click_window_days", 30), a.get("view_window_days", 1), a.get("attribution", "DATA_DRIVEN"),
                                                                   a.get("validate_only", False), a.get("account")),
    "create_pmax_campaign": lambda a: create_pmax_campaign(a["customer_id"], a["name"], a["daily_eur"], a.get("target_roas"), a.get("target_cpa_eur"),
                                                           a.get("final_url_expansion", True), a.get("merchant_id"), a.get("sales_country", "ES"),
                                                           a.get("geo_ids"), a.get("language_ids") or [1003], a.get("start_date"), a.get("end_date"),
                                                           a.get("status", "PAUSED"), a.get("validate_only", False), a.get("account")),
    "create_asset_group": lambda a: create_asset_group(a["customer_id"], a["campaign_resource_name"], a["name"], a["final_urls"], a["headlines"],
                                                       a["long_headlines"], a["descriptions"], a["business_name"], a["images"], a["logos"],
                                                       a.get("square_images"), a.get("videos"), a.get("path1"), a.get("path2"), a.get("status", "PAUSED"),
                                                       a.get("validate_only", False), a.get("account")),
    "create_label": lambda a: create_label(a["customer_id"], a["name"], a.get("description"), a.get("color"), a.get("validate_only", False), a.get("account")),
    "apply_label": lambda a: apply_label(a["customer_id"], a["label_rn"], a.get("campaign_rns"), a.get("ad_group_rns"), a.get("ad_group_ad_rns"),
                                         a.get("criterion_rns"), a.get("validate_only", False), a.get("account")),
    "update_resource": lambda a: update_resource(a["customer_id"], a["service"], a["resource_name"], a["fields"], a.get("validate_only", False), a.get("account")),
    "update_campaign": lambda a: update_campaign(a["customer_id"], a["campaign_id"], a.get("name"), a.get("status"), a.get("start_date"), a.get("end_date"),
                                                 a.get("validate_only", False), a.get("account")),
    "update_ad_group": lambda a: update_ad_group(a["customer_id"], a["ad_group_id"], a.get("name"), a.get("status"), a.get("cpc_eur"), a.get("validate_only", False), a.get("account")),
    "update_keyword": lambda a: update_keyword(a["customer_id"], a["criterion_rn"], a.get("status"), a.get("cpc_eur"), a.get("final_url"), a.get("validate_only", False), a.get("account")),
    "remove_resources": lambda a: remove_resources(a["customer_id"], a["service"], a["resource_names"], a.get("validate_only", False), a.get("account")),
    "list_change_history": lambda a: list_change_history(a["customer_id"], a.get("days", 7), a.get("account")),
}
