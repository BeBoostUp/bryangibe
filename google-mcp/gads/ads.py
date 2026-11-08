"""
Motor de Google Ads API (v25 por defecto; GOOGLE_ADS_API_VERSION en .env) para Bryan — LECTURA + ESCRITURA.
Reutiliza el OAuth probado del dashboard. Todas las credenciales salen del .env.

SEGURIDAD:
  - Las campañas se crean SIEMPRE en PAUSA (status=PAUSED). Nada gasta hasta activarlo.
  - Las escrituras aceptan validate_only=True (dry-run): Google valida SIN crear nada.

Uso como librería:  from gads.ads import get_campaigns, create_search_campaign, ...
Uso por CLI:        python3 gads/ads.py <comando> [args]
"""
import os
import sys
import json
import time
import base64
import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

DEV_TOKEN = os.environ.get("GOOGLE_ADS_DEVELOPER_TOKEN", "").strip()
CLIENT_ID = os.environ.get("GOOGLE_ADS_CLIENT_ID", "").strip()
CLIENT_SECRET = os.environ.get("GOOGLE_ADS_CLIENT_SECRET", "").strip()
DEFAULT_CID = os.environ.get("GOOGLE_ADS_CUSTOMER_ID", "").replace("-", "").strip()
API = os.environ.get("GOOGLE_ADS_API_VERSION", "v25").strip() or "v25"
BASE = f"https://googleads.googleapis.com/{API}"


# ----------------------------------------------------------------------------
# MULTI-CUENTA: cada cuenta = un email de Google con su propio refresh token y
# su MCC (login-customer-id). Mismo patrón que el MCP de Search Console.
#   .env:  GOOGLE_ADS_REFRESH_TOKEN_CUENTA1  + GOOGLE_ADS_LOGIN_CUSTOMER_ID_CUENTA1
#          GOOGLE_ADS_REFRESH_TOKEN_CUENTA2  + GOOGLE_ADS_LOGIN_CUSTOMER_ID_CUENTA2
# Compat: si solo existen las variables antiguas sin sufijo, se usan como cuenta1.
# ----------------------------------------------------------------------------
def _load_accounts():
    """Cada GOOGLE_ADS_REFRESH_TOKEN_<label> (+ GOOGLE_ADS_LOGIN_CUSTOMER_ID_<label>)
    es una cuenta de login. Etiquetas libres (p.ej. BRYAN, MARKETING).
    Compat: variables sin sufijo -> 'default'."""
    accts = {}
    prefix = "GOOGLE_ADS_REFRESH_TOKEN_"
    for k, v in os.environ.items():
        if k.startswith(prefix) and v.strip():
            label = k[len(prefix):].lower()
            lc = os.environ.get(f"GOOGLE_ADS_LOGIN_CUSTOMER_ID_{label.upper()}", "").replace("-", "").strip()
            accts[label] = {"refresh_token": v.strip(), "login_cid": lc}
    legacy_rt = os.environ.get("GOOGLE_ADS_REFRESH_TOKEN", "").strip()
    legacy_lc = os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID", "").replace("-", "").strip()
    if legacy_rt and not accts:
        accts["default"] = {"refresh_token": legacy_rt, "login_cid": legacy_lc}
    return accts


def list_login_accounts():
    """Etiquetas de cuenta de login configuradas en el .env."""
    return list(_load_accounts().keys())


ACCOUNTS = _load_accounts()
DEFAULT_ACCOUNT = next(iter(ACCOUNTS), None)
# MCC de la cuenta por defecto (compat con el antiguo LOGIN_CID)
LOGIN_CID = ACCOUNTS.get(DEFAULT_ACCOUNT, {}).get("login_cid", "") if DEFAULT_ACCOUNT else ""

_token_cache = {}   # label -> {"token":..., "expires":...}
_owner_cache = {}   # customer_id (cliente o MCC) -> label de la cuenta que lo posee


def _acct(account=None):
    """Devuelve (label, dict) de una cuenta. account puede ser None (por defecto)."""
    label = (account or DEFAULT_ACCOUNT)
    if label not in ACCOUNTS:
        raise AdsError(f"Cuenta desconocida '{account}'. Disponibles: {list(ACCOUNTS)}")
    return label, ACCOUNTS[label]


def get_access_token(account=None):
    label, acct = _acct(account)
    now = time.time()
    cached = _token_cache.get(label)
    if cached and now < cached["expires"] - 60:
        return cached["token"]
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
        "refresh_token": acct["refresh_token"], "grant_type": "refresh_token",
    })
    r.raise_for_status()
    data = r.json()
    _token_cache[label] = {"token": data["access_token"],
                           "expires": now + data.get("expires_in", 3600)}
    return data["access_token"]


def _headers(account=None):
    label, acct = _acct(account)
    h = {
        "Authorization": f"Bearer {get_access_token(label)}",
        "login-customer-id": acct["login_cid"],
        "Content-Type": "application/json",
    }
    # Desde el 9-sep-2026 el developer token es opcional (el acceso lo da el proyecto Cloud).
    if DEV_TOKEN:
        h["developer-token"] = DEV_TOKEN
    return h


def _cid(customer_id=None, account=None):
    if customer_id:
        return str(customer_id).replace("-", "").strip()
    _, acct = _acct(account)
    return str(DEFAULT_CID or acct["login_cid"]).replace("-", "").strip()


def _owner_of(customer_id):
    """Averigua qué cuenta (label) posee un customer_id de cliente. Cachea el mapa."""
    cid = str(customer_id).replace("-", "").strip()
    if cid in _owner_cache:
        return _owner_cache[cid]
    for label, acct in ACCOUNTS.items():
        if acct["login_cid"]:
            _owner_cache.setdefault(acct["login_cid"], label)
        try:
            for c in _list_client_ids(label):
                _owner_cache.setdefault(c, label)
        except Exception:
            pass  # si una cuenta falla, seguimos con las demás
    return _owner_cache.get(cid, DEFAULT_ACCOUNT)


class AdsError(Exception):
    pass


def search(query, customer_id=None, account=None):
    """Lee datos con GAQL. Devuelve lista de filas (dicts).
    Si no se indica account, se resuelve por la cuenta dueña del customer_id."""
    cid = _cid(customer_id, account)
    if account is None and customer_id:
        account = _owner_of(cid)
    url = f"{BASE}/customers/{cid}/googleAds:searchStream"
    r = requests.post(url, headers=_headers(account), json={"query": query})
    if r.status_code != 200:
        raise AdsError(f"search HTTP {r.status_code}: {r.text}")
    rows = []
    for batch in r.json():
        rows.extend(batch.get("results", []))
    return rows


def mutate(service, operations, customer_id=None, validate_only=False, account=None):
    """Escritura genérica. service p.ej. 'campaigns', 'adGroups', 'campaignBudgets'."""
    cid = _cid(customer_id, account)
    if account is None and customer_id:
        account = _owner_of(cid)
    url = f"{BASE}/customers/{cid}/{service}:mutate"
    body = {"operations": operations, "validateOnly": validate_only}
    if service in ("campaigns", "adGroups", "adGroupCriteria", "adGroupAds"):
        body["partialFailure"] = False
    r = requests.post(url, headers=_headers(account), json=body)
    if r.status_code != 200:
        raise AdsError(f"{service}:mutate HTTP {r.status_code}: {r.text}")
    return r.json()


def list_accessible_customers(account=None):
    """Customers a los que el usuario de la cuenta accede directamente (raíz del
    árbol). No requiere login-customer-id. Útil para descubrir el MCC."""
    label, acct = _acct(account)
    h = {"Authorization": f"Bearer {get_access_token(label)}", "Content-Type": "application/json"}
    if DEV_TOKEN:
        h["developer-token"] = DEV_TOKEN
    r = requests.get(f"{BASE}/customers:listAccessibleCustomers", headers=h)
    if r.status_code != 200:
        raise AdsError(f"listAccessibleCustomers HTTP {r.status_code}: {r.text}")
    ids = [rn.split("/")[-1] for rn in r.json().get("resourceNames", [])]
    out = []
    for cid in ids:
        # login-customer-id = el propio cid (aún no conocemos el MCC de la cuenta)
        hq = {"Authorization": f"Bearer {get_access_token(label)}",
              "developer-token": DEV_TOKEN, "login-customer-id": cid,
              "Content-Type": "application/json"}
        try:
            rr = requests.post(f"{BASE}/customers/{cid}/googleAds:searchStream",
                               headers=hq, json={"query": "SELECT customer.id, "
                               "customer.descriptive_name, customer.manager FROM customer LIMIT 1"})
            c = rr.json()[0]["results"][0]["customer"] if rr.status_code == 200 else {}
            out.append({"id": cid, "name": c.get("descriptiveName", ""),
                        "manager": c.get("manager", False)})
        except Exception:
            out.append({"id": cid, "name": "", "manager": None})
    return out


def micros(euros):
    """Convierte euros a micros (unidad de la API)."""
    return int(round(float(euros) * 1_000_000))


# ----------------------------------------------------------------------------
# LECTURA
# ----------------------------------------------------------------------------
_CLIENTS_Q = ("SELECT customer_client.id, customer_client.descriptive_name, "
              "customer_client.manager, customer_client.status "
              "FROM customer_client WHERE customer_client.status = 'ENABLED'")


def _list_client_ids(account):
    """IDs de cliente (str) accesibles bajo el MCC de una cuenta concreta."""
    _, acct = _acct(account)
    if not acct["login_cid"]:
        return []
    ids = []
    for row in search(_CLIENTS_Q, acct["login_cid"], account=account):
        cid = row["customerClient"].get("id")
        if cid:
            ids.append(str(cid))
    return ids


def list_accounts(account=None):
    """Lista las cuentas cliente. Sin 'account' fusiona TODAS las cuentas
    conectadas (bryan + academy) y deduplica por id de cliente."""
    labels = [account] if account else list(ACCOUNTS)
    seen = {}
    for label in labels:
        _, acct = _acct(label)
        if not acct["login_cid"]:
            continue
        try:
            for row in search(_CLIENTS_Q, acct["login_cid"], account=label):
                c = row["customerClient"]
                cid = str(c.get("id"))
                if cid in seen:
                    continue
                seen[cid] = {"id": c.get("id"), "name": c.get("descriptiveName", ""),
                             "manager": c.get("manager", False), "account": label}
        except AdsError:
            continue  # una cuenta caída no debe tumbar la fusión
    return list(seen.values())


def get_campaigns(customer_id, date_from=None, date_to=None):
    seg = (f"WHERE segments.date BETWEEN '{date_from}' AND '{date_to}' "
           if date_from and date_to else "WHERE campaign.status != 'REMOVED' ")
    q = ("SELECT campaign.id, campaign.name, campaign.status, "
         "campaign.advertising_channel_type, campaign_budget.amount_micros, "
         "metrics.impressions, metrics.clicks, metrics.cost_micros, "
         "metrics.conversions, metrics.conversions_value "
         f"FROM campaign {seg}ORDER BY metrics.cost_micros DESC")
    return search(q, customer_id)


def get_ad_groups(customer_id, campaign_id=None):
    where = f"WHERE campaign.id = {campaign_id} " if campaign_id else "WHERE ad_group.status != 'REMOVED' "
    q = ("SELECT ad_group.id, ad_group.name, ad_group.status, campaign.id "
         f"FROM ad_group {where}")
    return search(q, customer_id)


# ----------------------------------------------------------------------------
# ESCRITURA (siempre segura: campañas nacen en PAUSA)
# ----------------------------------------------------------------------------
def create_campaign_budget(customer_id, name, daily_eur, validate_only=False):
    op = [{"create": {"name": name, "amountMicros": micros(daily_eur),
                      "deliveryMethod": "STANDARD", "explicitlyShared": False}}]
    res = mutate("campaignBudgets", op, customer_id, validate_only)
    return None if validate_only else res["results"][0]["resourceName"]


# --- Estrategias de puja -----------------------------------------------------
# Para el updateMask del PATCH hay que apuntar al SUBCAMPO HOJA (no al mensaje).
# Con mensaje vacío + esta hoja, la API cambia de estrategia igualmente (verificado).
_BID_LEAF = {
    "manualCpc": "manual_cpc.enhanced_cpc_enabled",
    "targetSpend": "target_spend.cpc_bid_ceiling_micros",
    "maximizeConversions": "maximize_conversions.target_cpa_micros",
    "maximizeConversionValue": "maximize_conversion_value.target_roas",
}


def _bidding_payload(bidding):
    """Devuelve el dict de estrategia de puja para el create/update de campaña.

    bidding = {"strategy": ..., "target_cpa_eur":..., "target_roas":...,
               "cpc_ceiling_eur":..., "enhanced_cpc": bool}
    strategy: MANUAL_CPC | MAXIMIZE_CLICKS | MAXIMIZE_CONVERSIONS |
              MAXIMIZE_CONVERSION_VALUE | TARGET_CPA | TARGET_ROAS
    """
    if not bidding:
        return {"manualCpc": {}}
    s = (bidding.get("strategy") or "MANUAL_CPC").upper()
    if s == "MANUAL_CPC":
        return {"manualCpc": {"enhancedCpcEnabled": bool(bidding.get("enhanced_cpc", False))}}
    if s == "MAXIMIZE_CLICKS":
        ts = {}
        if bidding.get("cpc_ceiling_eur"):
            ts["cpcBidCeilingMicros"] = micros(bidding["cpc_ceiling_eur"])
        return {"targetSpend": ts}
    if s == "MAXIMIZE_CONVERSIONS":
        mc = {}
        if bidding.get("target_cpa_eur"):
            mc["targetCpaMicros"] = micros(bidding["target_cpa_eur"])
        return {"maximizeConversions": mc}
    if s == "MAXIMIZE_CONVERSION_VALUE":
        mcv = {}
        if bidding.get("target_roas"):
            mcv["targetRoas"] = float(bidding["target_roas"])
        return {"maximizeConversionValue": mcv}
    if s == "TARGET_CPA":
        # Google ya no permite tCPA "puro": es Max. conversiones + CPA objetivo.
        return {"maximizeConversions": {"targetCpaMicros": micros(bidding.get("target_cpa_eur", 0))}}
    if s == "TARGET_ROAS":
        # tROAS "puro" tampoco: es Max. valor de conv. + ROAS objetivo.
        return {"maximizeConversionValue": {"targetRoas": float(bidding.get("target_roas", 0))}}
    raise AdsError(f"Estrategia de puja desconocida: {s}")


def _geo_type_setting(presence):
    """positive: PRESENCE (personas EN la ubicación) | PRESENCE_OR_INTEREST | SEARCH_INTEREST."""
    p = (presence or "PRESENCE").upper()
    return {"positiveGeoTargetType": p, "negativeGeoTargetType": "PRESENCE"}


def create_search_campaign(customer_id, name, daily_eur, budget_name=None,
                           bidding=None, networks=None, geo=None, languages=None,
                           start_date=None, end_date=None, status="PAUSED",
                           validate_only=False):
    """Crea presupuesto + campaña de BÚSQUEDA (por defecto EN PAUSA).

    Opcionales:
      bidding   -> ver _bidding_payload (por defecto Manual CPC)
      networks  -> {"search_partners": bool, "content": bool}
      geo       -> {"locations": [id | {"id":.., "bid_modifier":..}],
                    "presence": "PRESENCE" | "PRESENCE_OR_INTEREST"}
      languages -> [id, ...]  (ej. 1003 = español)
      start_date/end_date -> "YYYY-MM-DD"
      status    -> PAUSED (recomendado) | ENABLED
    """
    budget_rn = create_campaign_budget(
        customer_id, budget_name or f"{name} - Budget", daily_eur, validate_only)
    net = networks or {}
    camp = {
        "name": name,
        "status": status if status in ("PAUSED", "ENABLED") else "PAUSED",
        "advertisingChannelType": "SEARCH",
        "containsEuPoliticalAdvertising": "DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING",
        "campaignBudget": budget_rn or "customers/X/campaignBudgets/0",
        "networkSettings": {
            "targetGoogleSearch": True,
            "targetSearchNetwork": bool(net.get("search_partners", False)),
            "targetContentNetwork": bool(net.get("content", False)),
        },
    }
    camp.update(_bidding_payload(bidding))
    if geo and geo.get("presence"):
        camp["geoTargetTypeSetting"] = _geo_type_setting(geo.get("presence"))
    if start_date:
        camp["startDate"] = start_date
    if end_date:
        camp["endDate"] = end_date
    res = mutate("campaigns", [{"create": camp}], customer_id, validate_only)
    campaign_rn = None if validate_only else res["results"][0]["resourceName"]
    out = {"budget": budget_rn, "campaign": campaign_rn}

    # Criterios de campaña: ubicaciones (con modificador) e idiomas
    crit_ops = []
    if geo and geo.get("locations"):
        for loc in geo["locations"]:
            lid = loc.get("id") if isinstance(loc, dict) else loc
            bm = loc.get("bid_modifier") if isinstance(loc, dict) else None
            c = {"campaign": campaign_rn or "customers/X/campaigns/0",
                 "location": {"geoTargetConstant": f"geoTargetConstants/{lid}"}}
            if bm:
                c["bidModifier"] = float(bm)
            crit_ops.append({"create": c})
    if languages:
        for lang in languages:
            crit_ops.append({"create": {
                "campaign": campaign_rn or "customers/X/campaigns/0",
                "language": {"languageConstant": f"languageConstants/{lang}"}}})
    if crit_ops:
        cres = mutate("campaignCriteria", crit_ops, customer_id, validate_only)
        out["criteria"] = ([] if validate_only
                           else [r["resourceName"] for r in cres.get("results", [])])
    return out


def update_campaign_bidding(customer_id, campaign_id, bidding, validate_only=False):
    """Cambia la estrategia de puja de una campaña existente."""
    rn = f"customers/{_cid(customer_id)}/campaigns/{campaign_id}"
    payload = _bidding_payload(bidding)
    field = next(iter(payload))
    op = [{"update": {"resourceName": rn, **payload}, "updateMask": _BID_LEAF[field]}]
    return mutate("campaigns", op, customer_id, validate_only)


def update_campaign_budget(customer_id, budget_resource_name, daily_eur, validate_only=False):
    """Cambia el presupuesto diario (por el resource name del presupuesto)."""
    op = [{"update": {"resourceName": budget_resource_name, "amountMicros": micros(daily_eur)},
           "updateMask": "amount_micros"}]
    return mutate("campaignBudgets", op, customer_id, validate_only)


def add_campaign_negative_keywords(customer_id, campaign_rn, keywords, match="PHRASE",
                                   validate_only=False):
    """Añade keywords NEGATIVAS a nivel de campaña. match: EXACT | PHRASE | BROAD."""
    ops = [{"create": {"campaign": campaign_rn, "negative": True,
                       "keyword": {"text": kw, "matchType": match}}} for kw in keywords]
    res = mutate("campaignCriteria", ops, customer_id, validate_only)
    return [] if validate_only else [r["resourceName"] for r in res["results"]]


def add_campaign_locations(customer_id, campaign_rn, locations, presence=None,
                           validate_only=False):
    """Añade ubicaciones a una campaña existente. locations: [id | {id, bid_modifier}].
    presence: si se pasa, ajusta el tipo de segmentación geográfica de la campaña."""
    if presence:
        cid = campaign_rn.split("/")[-1]
        update_campaign_geo_type(customer_id, cid, presence, validate_only)
    ops = []
    for loc in locations:
        lid = loc.get("id") if isinstance(loc, dict) else loc
        bm = loc.get("bid_modifier") if isinstance(loc, dict) else None
        c = {"campaign": campaign_rn,
             "location": {"geoTargetConstant": f"geoTargetConstants/{lid}"}}
        if bm:
            c["bidModifier"] = float(bm)
        ops.append({"create": c})
    res = mutate("campaignCriteria", ops, customer_id, validate_only)
    return [] if validate_only else [r["resourceName"] for r in res["results"]]


def update_campaign_geo_type(customer_id, campaign_id, presence, validate_only=False):
    rn = f"customers/{_cid(customer_id)}/campaigns/{campaign_id}"
    op = [{"update": {"resourceName": rn, "geoTargetTypeSetting": _geo_type_setting(presence)},
           "updateMask": "geo_target_type_setting.positive_geo_target_type,"
                         "geo_target_type_setting.negative_geo_target_type"}]
    return mutate("campaigns", op, customer_id, validate_only)


def add_campaign_languages(customer_id, campaign_rn, language_ids, validate_only=False):
    ops = [{"create": {"campaign": campaign_rn,
                       "language": {"languageConstant": f"languageConstants/{l}"}}}
           for l in language_ids]
    res = mutate("campaignCriteria", ops, customer_id, validate_only)
    return [] if validate_only else [r["resourceName"] for r in res["results"]]


def create_ad_group(customer_id, campaign_rn, name, cpc_eur=0.5, validate_only=False):
    op = [{"create": {"name": name, "campaign": campaign_rn, "status": "ENABLED",
                      "type": "SEARCH_STANDARD", "cpcBidMicros": micros(cpc_eur)}}]
    res = mutate("adGroups", op, customer_id, validate_only)
    return None if validate_only else res["results"][0]["resourceName"]


def add_keywords(customer_id, ad_group_rn, keywords, match="PHRASE", validate_only=False):
    """keywords: lista de strings. match: EXACT | PHRASE | BROAD."""
    ops = [{"create": {"adGroup": ad_group_rn, "status": "ENABLED",
                       "keyword": {"text": kw, "matchType": match}}} for kw in keywords]
    res = mutate("adGroupCriteria", ops, customer_id, validate_only)
    return [] if validate_only else [r["resourceName"] for r in res["results"]]


_PIN_H = {1: "HEADLINE_1", 2: "HEADLINE_2", 3: "HEADLINE_3"}
_PIN_D = {1: "DESCRIPTION_1", 2: "DESCRIPTION_2"}


def _ad_text_assets(items, pin_map):
    """items: lista de strings o de {"text":..., "pin": 1|2|3}. Devuelve AdTextAsset[]."""
    out = []
    for it in items:
        if isinstance(it, dict):
            a = {"text": it["text"]}
            if it.get("pin"):
                a["pinnedField"] = pin_map.get(int(it["pin"]))
            out.append(a)
        else:
            out.append({"text": it})
    return out


def create_rsa_ad(customer_id, ad_group_rn, final_url, headlines, descriptions,
                  path1=None, path2=None, status="PAUSED", validate_only=False):
    """Anuncio de búsqueda responsivo (por defecto EN PAUSA).
    headlines/descriptions: strings o {"text":.., "pin": 1|2|3} para fijar posición.
    path1/path2: rutas visibles de la URL (max 15 car.)."""
    rsa = {"headlines": _ad_text_assets(headlines, _PIN_H),
           "descriptions": _ad_text_assets(descriptions, _PIN_D)}
    if path1:
        rsa["path1"] = path1
    if path2:
        rsa["path2"] = path2
    op = [{"create": {
        "adGroup": ad_group_rn,
        "status": status if status in ("PAUSED", "ENABLED") else "PAUSED",
        "ad": {"finalUrls": [final_url], "responsiveSearchAd": rsa},
    }}]
    res = mutate("adGroupAds", op, customer_id, validate_only)
    return None if validate_only else res["results"][0]["resourceName"]


def set_resource_status(customer_id, service, resource_name, status, id_field=None,
                        validate_only=False):
    """Cambia el estado (ENABLED|PAUSED) o elimina (REMOVED) un recurso cualquiera.
    service: 'adGroups' | 'adGroupCriteria' | 'adGroupAds' | 'campaigns'."""
    if status == "REMOVED":
        op = [{"remove": resource_name}]
    else:
        op = [{"update": {"resourceName": resource_name, "status": status},
               "updateMask": "status"}]
    return mutate(service, op, customer_id, validate_only)


# ----------------------------------------------------------------------------
# EXTENSIONES (assets) — se crean y se enlazan a la campaña
# ----------------------------------------------------------------------------
def _link_assets_to_campaign(customer_id, campaign_rn, asset_rns, field_type,
                             validate_only=False):
    ops = [{"create": {"campaign": campaign_rn, "asset": rn, "fieldType": field_type}}
           for rn in asset_rns]
    res = mutate("campaignAssets", ops, customer_id, validate_only)
    return [] if validate_only else [r["resourceName"] for r in res["results"]]


def add_sitelinks(customer_id, campaign_rn, sitelinks, validate_only=False):
    """sitelinks: [{"link_text":.., "description1":.., "description2":.., "final_url":..}]."""
    aops = []
    for s in sitelinks:
        sl = {"linkText": s["link_text"]}
        if s.get("description1"):
            sl["description1"] = s["description1"]
        if s.get("description2"):
            sl["description2"] = s["description2"]
        create = {"sitelinkAsset": sl}
        if s.get("final_url"):
            create["finalUrls"] = [s["final_url"]]
        aops.append({"create": create})
    res = mutate("assets", aops, customer_id, validate_only)
    if validate_only:
        return {"assets": [], "links": []}
    asset_rns = [r["resourceName"] for r in res["results"]]
    links = _link_assets_to_campaign(customer_id, campaign_rn, asset_rns, "SITELINK")
    return {"assets": asset_rns, "links": links}


def add_callouts(customer_id, campaign_rn, callouts, validate_only=False):
    """callouts: lista de strings (max 25 car.)."""
    aops = [{"create": {"calloutAsset": {"calloutText": c}}} for c in callouts]
    res = mutate("assets", aops, customer_id, validate_only)
    if validate_only:
        return {"assets": [], "links": []}
    asset_rns = [r["resourceName"] for r in res["results"]]
    links = _link_assets_to_campaign(customer_id, campaign_rn, asset_rns, "CALLOUT")
    return {"assets": asset_rns, "links": links}


def add_structured_snippet(customer_id, campaign_rn, header, values, validate_only=False):
    """header: p.ej. 'Servicios'. values: lista de strings (max 25 car. cada uno)."""
    aops = [{"create": {"structuredSnippetAsset": {"header": header, "values": values}}}]
    res = mutate("assets", aops, customer_id, validate_only)
    if validate_only:
        return {"assets": [], "links": []}
    asset_rns = [r["resourceName"] for r in res["results"]]
    links = _link_assets_to_campaign(customer_id, campaign_rn, asset_rns, "STRUCTURED_SNIPPET")
    return {"assets": asset_rns, "links": links}


def add_call_asset(customer_id, campaign_rn, phone_number, country_code="ES",
                   validate_only=False):
    """Extensión de llamada. phone_number: p.ej. '691874961'."""
    aops = [{"create": {"callAsset": {"countryCode": country_code,
                                      "phoneNumber": phone_number}}}]
    res = mutate("assets", aops, customer_id, validate_only)
    if validate_only:
        return {"assets": [], "links": []}
    asset_rns = [r["resourceName"] for r in res["results"]]
    links = _link_assets_to_campaign(customer_id, campaign_rn, asset_rns, "CALL")
    return {"assets": asset_rns, "links": links}


# ----------------------------------------------------------------------------
# CONVERSIONES — grupo de conversiones personalizado (custom goal)
# ----------------------------------------------------------------------------
def create_custom_conversion_goal(customer_id, name, conversion_action_ids,
                                  validate_only=False):
    """Crea un OBJETIVO PERSONALIZADO que agrupa conversiones concretas (por su id).
    Devuelve el resource name del custom goal."""
    cid = _cid(customer_id)
    actions = [f"customers/{cid}/conversionActions/{a}" for a in conversion_action_ids]
    op = [{"create": {"name": name, "conversionActions": actions}}]
    res = mutate("customConversionGoals", op, customer_id, validate_only)
    return None if validate_only else res["results"][0]["resourceName"]


# NOTA: asignar el custom goal / conversiones concretas a UNA campaña
# (campaign.selective_optimization) está obsoleto en la API y el modelo de
# "objetivos de campaña" para custom goals no es escribible de forma fiable aquí.
# create_custom_conversion_goal() SÍ crea el grupo (visible en la cuenta); la
# asignación del objetivo a la campaña se hace en la interfaz (1 clic). Pendiente
# de investigar en Fase 2 (campaign_conversion_goal / customer-specific goals).


def set_campaign_status(customer_id, campaign_id, status):
    """status: ENABLED | PAUSED | REMOVED (REMOVED borra la campaña)."""
    rn = f"customers/{_cid(customer_id)}/campaigns/{campaign_id}"
    if status == "REMOVED":
        op = [{"remove": rn}]
    else:
        op = [{"update": {"resourceName": rn, "status": status},
               "updateMask": "status"}]
    return mutate("campaigns", op, customer_id)


# ----------------------------------------------------------------------------
# HORARIO (dayparting) y MODIFICADORES POR DISPOSITIVO
# ----------------------------------------------------------------------------
_MINUTE = {0: "ZERO", 15: "FIFTEEN", 30: "THIRTY", 45: "FORTY_FIVE"}


def add_ad_schedule(customer_id, campaign_rn, schedules, validate_only=False):
    """Franjas horarias. schedules: [{day, start_hour, end_hour,
    start_minute?, end_minute?, bid_modifier?}]. day: MONDAY..SUNDAY. horas 0-24."""
    ops = []
    for s in schedules:
        sch = {"dayOfWeek": s["day"].upper(),
               "startHour": int(s["start_hour"]), "endHour": int(s["end_hour"]),
               "startMinute": _MINUTE.get(int(s.get("start_minute", 0)), "ZERO"),
               "endMinute": _MINUTE.get(int(s.get("end_minute", 0)), "ZERO")}
        c = {"campaign": campaign_rn, "adSchedule": sch}
        if s.get("bid_modifier"):
            c["bidModifier"] = float(s["bid_modifier"])
        ops.append({"create": c})
    res = mutate("campaignCriteria", ops, customer_id, validate_only)
    return [] if validate_only else [r["resourceName"] for r in res["results"]]


def set_device_bid_modifiers(customer_id, campaign_rn, devices, validate_only=False):
    """Modificadores por dispositivo. devices: [{device: MOBILE|DESKTOP|TABLET,
    bid_modifier}]. Para excluir un dispositivo usa bid_modifier 0 (=-100%)."""
    ops = [{"create": {"campaign": campaign_rn,
                       "device": {"type": d["device"].upper()},
                       "bidModifier": float(d["bid_modifier"])}} for d in devices]
    res = mutate("campaignCriteria", ops, customer_id, validate_only)
    return [] if validate_only else [r["resourceName"] for r in res["results"]]


# ----------------------------------------------------------------------------
# AUDIENCIAS (a nivel de grupo, por defecto en OBSERVACIÓN)
# ----------------------------------------------------------------------------
def add_audiences(customer_id, ad_group_rn, audiences, observation=True,
                  validate_only=False):
    """audiences: [{type, id, bid_modifier?}]. type: USER_LIST | USER_INTEREST |
    CUSTOM_AUDIENCE | AUDIENCE. observation=True -> solo puja (no restringe alcance)."""
    cid = _cid(customer_id)
    if observation:
        # bid_only=True => "observación" (solo modificadores de puja, target-all).
        # El updateMask reemplaza toda la lista, así que hay que enviar TODAS las
        # dimensiones en True para no cambiar las demográficas a targetAll=false.
        ag = [{"update": {"resourceName": ad_group_rn, "targetingSetting": {
            "targetRestrictions": [
                {"targetingDimension": "AUDIENCE", "bidOnly": True},
                {"targetingDimension": "AGE_RANGE", "bidOnly": True},
                {"targetingDimension": "GENDER", "bidOnly": True},
                {"targetingDimension": "PARENTAL_STATUS", "bidOnly": True},
                {"targetingDimension": "INCOME_RANGE", "bidOnly": True},
            ]}},
            "updateMask": "targeting_setting.target_restrictions"}]
        mutate("adGroups", ag, customer_id, validate_only)
    ops = []
    for a in audiences:
        t = a["type"].upper()
        crit = {"adGroup": ad_group_rn}
        if t == "USER_LIST":
            crit["userList"] = {"userList": f"customers/{cid}/userLists/{a['id']}"}
        elif t == "USER_INTEREST":
            crit["userInterest"] = {"userInterestCategory": f"userInterests/{a['id']}"}
        elif t == "CUSTOM_AUDIENCE":
            crit["customAudience"] = {"customAudience": f"customers/{cid}/customAudiences/{a['id']}"}
        elif t == "AUDIENCE":
            crit["audience"] = {"audience": f"customers/{cid}/audiences/{a['id']}"}
        else:
            raise AdsError(f"Tipo de audiencia desconocido: {t}")
        if a.get("bid_modifier"):
            crit["bidModifier"] = float(a["bid_modifier"])
        ops.append({"create": crit})
    res = mutate("adGroupCriteria", ops, customer_id, validate_only)
    return [] if validate_only else [r["resourceName"] for r in res["results"]]


# ----------------------------------------------------------------------------
# LISTAS DE NEGATIVAS COMPARTIDAS (a nivel de cuenta) + enlace a campaña
# ----------------------------------------------------------------------------
def create_shared_negative_list(customer_id, name, keywords=None, match="PHRASE",
                                validate_only=False):
    """Crea una lista compartida de negativas. keywords: lista de strings (usan
    'match') o de {text, match}. Devuelve el sharedSet y sus criterios."""
    res = mutate("sharedSets", [{"create": {"name": name, "type": "NEGATIVE_KEYWORDS"}}],
                 customer_id, validate_only)
    if validate_only:
        return {"sharedSet": None, "criteria": []}
    ss = res["results"][0]["resourceName"]
    crit = []
    if keywords:
        ops = []
        for kw in keywords:
            text = kw["text"] if isinstance(kw, dict) else kw
            m = kw.get("match", match) if isinstance(kw, dict) else match
            ops.append({"create": {"sharedSet": ss, "keyword": {"text": text, "matchType": m}}})
        cres = mutate("sharedCriteria", ops, customer_id, validate_only)
        crit = [r["resourceName"] for r in cres["results"]]
    return {"sharedSet": ss, "criteria": crit}


def add_shared_list_keywords(customer_id, shared_set_rn, keywords, match="PHRASE",
                             validate_only=False):
    """Añade más negativas a una lista compartida existente."""
    ops = []
    for kw in keywords:
        text = kw["text"] if isinstance(kw, dict) else kw
        m = kw.get("match", match) if isinstance(kw, dict) else match
        ops.append({"create": {"sharedSet": shared_set_rn, "keyword": {"text": text, "matchType": m}}})
    res = mutate("sharedCriteria", ops, customer_id, validate_only)
    return [] if validate_only else [r["resourceName"] for r in res["results"]]


def attach_shared_set(customer_id, campaign_rn, shared_set_rn, validate_only=False):
    """Enlaza una lista compartida a una campaña."""
    res = mutate("campaignSharedSets",
                 [{"create": {"campaign": campaign_rn, "sharedSet": shared_set_rn}}],
                 customer_id, validate_only)
    return None if validate_only else res["results"][0]["resourceName"]


# ----------------------------------------------------------------------------
# ASSETS de IMAGEN / LOGO / NOMBRE DE NEGOCIO
# ----------------------------------------------------------------------------
def _load_image_b64(path_or_url):
    if path_or_url.startswith(("http://", "https://")):
        r = requests.get(path_or_url, timeout=30)
        r.raise_for_status()
        raw = r.content
    else:
        with open(path_or_url, "rb") as f:
            raw = f.read()
    return base64.b64encode(raw).decode("ascii")


def add_business_name(customer_id, campaign_rn, business_name, validate_only=False):
    """Nombre de negocio (para anuncios de búsqueda). Text asset enlazado como BUSINESS_NAME."""
    res = mutate("assets", [{"create": {"textAsset": {"text": business_name}}}],
                 customer_id, validate_only)
    if validate_only:
        return {"asset": None, "links": []}
    asset = res["results"][0]["resourceName"]
    links = _link_assets_to_campaign(customer_id, campaign_rn, [asset], "BUSINESS_NAME")
    return {"asset": asset, "links": links}


# field_type: MARKETING_IMAGE (1.91:1) | SQUARE_MARKETING_IMAGE (1:1) |
#             PORTRAIT_MARKETING_IMAGE (4:5) | LOGO (1:1) | LANDSCAPE_LOGO (4:1)
def add_image_asset(customer_id, campaign_rn, image, asset_name,
                    field_type="MARKETING_IMAGE", validate_only=False):
    """image: ruta local o URL. asset_name: nombre único del asset."""
    data = _load_image_b64(image)
    res = mutate("assets", [{"create": {"name": asset_name, "imageAsset": {"data": data}}}],
                 customer_id, validate_only)
    if validate_only:
        return {"asset": None, "links": []}
    asset = res["results"][0]["resourceName"]
    links = _link_assets_to_campaign(customer_id, campaign_rn, [asset], field_type)
    return {"asset": asset, "links": links}


# ----------------------------------------------------------------------------
# ASIGNAR conversiones concretas (grupo Nexor) A UNA CAMPAÑA
# ----------------------------------------------------------------------------
def set_campaign_conversion_actions(customer_id, campaign_id, conversion_action_ids,
                                    validate_only=False):
    """NO DISPONIBLE por API en v23: campaign.selective_optimization está obsoleto
    y el modelo de objetivos de campaña para custom goals no es escribible aquí.
    Crea el grupo con create_custom_conversion_goal() y asígnalo en la interfaz."""
    raise AdsError(
        "Asignar conversiones/custom goal a una campaña no está disponible por API "
        "(selective_optimization obsoleto desde v23). Crea el grupo con "
        "create_custom_conversion_goal y asígnalo a la campaña en la interfaz "
        "(Configuración > Objetivos de conversión de la campaña).")


# ----------------------------------------------------------------------------
# AI MAX FOR SEARCH
# ----------------------------------------------------------------------------
def set_campaign_ai_max(customer_id, campaign_id, enable, validate_only=False):
    """Activa (True) o desactiva (False) AI Max for Search en una campaña.
    En este vertical sensible el workbook lo quiere OFF en Fase 1."""
    rn = f"customers/{_cid(customer_id)}/campaigns/{campaign_id}"
    op = [{"update": {"resourceName": rn, "aiMaxSetting": {"enableAiMax": bool(enable)}},
           "updateMask": "ai_max_setting.enable_ai_max"}]
    return mutate("campaigns", op, customer_id, validate_only)


def set_ad_group_search_term_matching(customer_id, ad_group, enabled, validate_only=False):
    """AI Max: coincidencia de términos de búsqueda en un grupo. enabled=False la
    DESACTIVA (disable_search_term_matching=True). ad_group: id o resource name."""
    rn = ad_group if "/" in str(ad_group) else f"customers/{_cid(customer_id)}/adGroups/{ad_group}"
    op = [{"update": {"resourceName": rn,
                      "aiMaxAdGroupSetting": {"disableSearchTermMatching": (not enabled)}},
           "updateMask": "ai_max_ad_group_setting.disable_search_term_matching"}]
    return mutate("adGroups", op, customer_id, validate_only)


# ----------------------------------------------------------------------------
# CLI mínimo para inspección rápida
# ----------------------------------------------------------------------------
def _main(argv):
    if not argv:
        print("Comandos: accounts | campaigns <cid> | adgroups <cid> [campaign_id] | gaql <cid> <query>")
        return
    cmd = argv[0]
    if cmd == "accounts":
        for a in list_accounts():
            tag = "MANAGER" if a["manager"] else "cuenta"
            print(f"[{a['id']}] {a['name']} ({tag})")
    elif cmd == "campaigns":
        print(json.dumps(get_campaigns(argv[1]), indent=2, ensure_ascii=False))
    elif cmd == "adgroups":
        cid = argv[1]
        camp = argv[2] if len(argv) > 2 else None
        print(json.dumps(get_ad_groups(cid, camp), indent=2, ensure_ascii=False))
    elif cmd == "gaql":
        print(json.dumps(search(argv[2], argv[1]), indent=2, ensure_ascii=False))
    else:
        print("Comando desconocido:", cmd)


if __name__ == "__main__":
    _main(sys.argv[1:])
