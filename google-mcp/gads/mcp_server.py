"""
Servidor MCP de Google Ads (stdio, JSON-RPC 2.0) — Python puro, sin SDK externo.
Expone el motor gads/ads.py como herramientas nativas de Claude Code.

Se lanza con:  python3 /ruta/gads/mcp_server.py
Las credenciales salen del .env del repo (via gads/ads.py).
"""
import os
import sys
import json

# Permite importar el paquete 'gads' sin importar desde dónde se lance
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gads import ads  # noqa: E402
from gads import extra  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "googleads", "version": "3.0.0"}

# Sub-esquemas reutilizables -------------------------------------------------
_BIDDING = {
    "type": "object",
    "description": ("Estrategia de puja. strategy: MANUAL_CPC | MAXIMIZE_CLICKS | "
                    "MAXIMIZE_CONVERSIONS | MAXIMIZE_CONVERSION_VALUE | TARGET_CPA | "
                    "TARGET_ROAS. Opcionales: target_cpa_eur, target_roas, "
                    "cpc_ceiling_eur (tope CPC para Max clics), enhanced_cpc."),
    "properties": {
        "strategy": {"type": "string", "enum": [
            "MANUAL_CPC", "MAXIMIZE_CLICKS", "MAXIMIZE_CONVERSIONS",
            "MAXIMIZE_CONVERSION_VALUE", "TARGET_CPA", "TARGET_ROAS"]},
        "target_cpa_eur": {"type": "number"},
        "target_roas": {"type": "number"},
        "cpc_ceiling_eur": {"type": "number"},
        "enhanced_cpc": {"type": "boolean"},
    },
}
_NETWORKS = {
    "type": "object",
    "description": "Red. search_partners: socios de búsqueda. content: red de Display. Google Search siempre ON.",
    "properties": {"search_partners": {"type": "boolean"}, "content": {"type": "boolean"}},
}
_GEO = {
    "type": "object",
    "description": ("Segmentación geográfica. locations: lista de IDs (geo target constant, "
                    "p.ej. 2724=España, 1005402=provincia de Málaga) o de objetos "
                    "{id, bid_modifier} para modificar puja (1.25 = +25%). presence: "
                    "PRESENCE (personas EN la ubicación) | PRESENCE_OR_INTEREST."),
    "properties": {
        "locations": {"type": "array", "items": {"type": ["number", "integer", "object"]}},
        "presence": {"type": "string", "enum": ["PRESENCE", "PRESENCE_OR_INTEREST"]},
    },
}

# ----------------------------------------------------------------------------
# Definición de herramientas
# ----------------------------------------------------------------------------
TOOLS = [
    {
        "name": "list_login_accounts",
        "description": "Lista las cuentas de login (tokens) configuradas en el .env (bryan, academy).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_accounts",
        "description": ("Lista las cuentas de Google Ads accesibles (fusiona TODOS los logins configurados "
                        "y deduplica; cada fila indica su 'account'). id, nombre, si es manager."),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_campaigns",
        "description": "Devuelve las campañas de una cuenta con métricas. Opcionalmente en un rango de fechas (YYYY-MM-DD).",
        "inputSchema": {"type": "object", "properties": {
            "customer_id": {"type": "string", "description": "ID de la cuenta (10 dígitos, con o sin guiones)."},
            "date_from": {"type": "string"},
            "date_to": {"type": "string"},
        }, "required": ["customer_id"]},
    },
    {
        "name": "run_gaql",
        "description": "Ejecuta una consulta GAQL (Google Ads Query Language) de SOLO LECTURA sobre una cuenta y devuelve las filas.",
        "inputSchema": {"type": "object", "properties": {
            "customer_id": {"type": "string"},
            "query": {"type": "string", "description": "Consulta GAQL, p.ej. 'SELECT campaign.name FROM campaign'."},
        }, "required": ["customer_id", "query"]},
    },
    {
        "name": "create_search_campaign",
        "description": ("Crea una campaña de BÚSQUEDA con su presupuesto. Por defecto nace EN PAUSA. "
                        "Acepta puja, red, geo (ubicaciones + Presencia + modificador), idiomas y fechas. "
                        "Devuelve resource names (budget, campaign, criteria)."),
        "inputSchema": {"type": "object", "properties": {
            "customer_id": {"type": "string"},
            "name": {"type": "string"},
            "daily_eur": {"type": "number", "description": "Presupuesto diario en euros."},
            "budget_name": {"type": "string"},
            "bidding": _BIDDING,
            "networks": _NETWORKS,
            "geo": _GEO,
            "languages": {"type": "array", "items": {"type": ["number", "integer"]},
                          "description": "IDs de idioma (1003 = español)."},
            "start_date": {"type": "string", "description": "YYYY-MM-DD"},
            "end_date": {"type": "string", "description": "YYYY-MM-DD"},
            "status": {"type": "string", "enum": ["PAUSED", "ENABLED"], "description": "Por defecto PAUSED."},
        }, "required": ["customer_id", "name", "daily_eur"]},
    },
    {
        "name": "create_ad_group",
        "description": "Crea un grupo de anuncios dentro de una campaña (por su resource name).",
        "inputSchema": {"type": "object", "properties": {
            "customer_id": {"type": "string"},
            "campaign_resource_name": {"type": "string"},
            "name": {"type": "string"},
            "cpc_eur": {"type": "number"},
        }, "required": ["customer_id", "campaign_resource_name", "name"]},
    },
    {
        "name": "add_keywords",
        "description": "Añade keywords (positivas) a un grupo de anuncios. match: EXACT | PHRASE | BROAD.",
        "inputSchema": {"type": "object", "properties": {
            "customer_id": {"type": "string"},
            "ad_group_resource_name": {"type": "string"},
            "keywords": {"type": "array", "items": {"type": "string"}},
            "match": {"type": "string", "enum": ["EXACT", "PHRASE", "BROAD"]},
        }, "required": ["customer_id", "ad_group_resource_name", "keywords"]},
    },
    {
        "name": "add_campaign_negative_keywords",
        "description": "Añade keywords NEGATIVAS a nivel de campaña. match: EXACT | PHRASE | BROAD.",
        "inputSchema": {"type": "object", "properties": {
            "customer_id": {"type": "string"},
            "campaign_resource_name": {"type": "string"},
            "keywords": {"type": "array", "items": {"type": "string"}},
            "match": {"type": "string", "enum": ["EXACT", "PHRASE", "BROAD"]},
        }, "required": ["customer_id", "campaign_resource_name", "keywords"]},
    },
    {
        "name": "create_rsa_ad",
        "description": ("Crea un anuncio RSA (por defecto EN PAUSA). headlines: 3-15 (max 30 car.), "
                        "descriptions: 2-4 (max 90 car.). Cada headline/description puede ser un string "
                        "o un objeto {text, pin} con pin 1|2|3 para FIJAR la posición. path1/path2: rutas visibles."),
        "inputSchema": {"type": "object", "properties": {
            "customer_id": {"type": "string"},
            "ad_group_resource_name": {"type": "string"},
            "final_url": {"type": "string"},
            "headlines": {"type": "array", "items": {"type": ["string", "object"]}},
            "descriptions": {"type": "array", "items": {"type": ["string", "object"]}},
            "path1": {"type": "string"},
            "path2": {"type": "string"},
            "status": {"type": "string", "enum": ["PAUSED", "ENABLED"]},
        }, "required": ["customer_id", "ad_group_resource_name", "final_url", "headlines", "descriptions"]},
    },
    {
        "name": "update_campaign_bidding",
        "description": "Cambia la estrategia de puja de una campaña existente (mismo formato 'bidding' que en la creación).",
        "inputSchema": {"type": "object", "properties": {
            "customer_id": {"type": "string"},
            "campaign_id": {"type": "string"},
            "bidding": _BIDDING,
        }, "required": ["customer_id", "campaign_id", "bidding"]},
    },
    {
        "name": "update_campaign_budget",
        "description": "Cambia el presupuesto diario (por el resource name del presupuesto, p.ej. customers/X/campaignBudgets/Y).",
        "inputSchema": {"type": "object", "properties": {
            "customer_id": {"type": "string"},
            "budget_resource_name": {"type": "string"},
            "daily_eur": {"type": "number"},
        }, "required": ["customer_id", "budget_resource_name", "daily_eur"]},
    },
    {
        "name": "add_campaign_locations",
        "description": "Añade ubicaciones a una campaña existente. locations: lista de IDs o {id, bid_modifier}. presence opcional.",
        "inputSchema": {"type": "object", "properties": {
            "customer_id": {"type": "string"},
            "campaign_resource_name": {"type": "string"},
            "locations": {"type": "array", "items": {"type": ["number", "integer", "object"]}},
            "presence": {"type": "string", "enum": ["PRESENCE", "PRESENCE_OR_INTEREST"]},
        }, "required": ["customer_id", "campaign_resource_name", "locations"]},
    },
    {
        "name": "add_campaign_languages",
        "description": "Añade idiomas a una campaña existente. language_ids: p.ej. [1003] para español.",
        "inputSchema": {"type": "object", "properties": {
            "customer_id": {"type": "string"},
            "campaign_resource_name": {"type": "string"},
            "language_ids": {"type": "array", "items": {"type": ["number", "integer"]}},
        }, "required": ["customer_id", "campaign_resource_name", "language_ids"]},
    },
    {
        "name": "update_campaign_geo_type",
        "description": "Cambia el tipo de segmentación geográfica de una campaña. presence: PRESENCE | PRESENCE_OR_INTEREST.",
        "inputSchema": {"type": "object", "properties": {
            "customer_id": {"type": "string"},
            "campaign_id": {"type": "string"},
            "presence": {"type": "string", "enum": ["PRESENCE", "PRESENCE_OR_INTEREST"]},
        }, "required": ["customer_id", "campaign_id", "presence"]},
    },
    {
        "name": "set_resource_status",
        "description": ("Cambia el estado (ENABLED|PAUSED) o elimina (REMOVED) un recurso suelto. "
                        "service: adGroups | adGroupCriteria | adGroupAds. resource_name: el resource name completo."),
        "inputSchema": {"type": "object", "properties": {
            "customer_id": {"type": "string"},
            "service": {"type": "string", "enum": ["adGroups", "adGroupCriteria", "adGroupAds", "campaigns"]},
            "resource_name": {"type": "string"},
            "status": {"type": "string", "enum": ["ENABLED", "PAUSED", "REMOVED"]},
        }, "required": ["customer_id", "service", "resource_name", "status"]},
    },
    {
        "name": "add_sitelinks",
        "description": ("Crea sitelinks y los enlaza a la campaña. sitelinks: lista de "
                        "{link_text, description1, description2, final_url}."),
        "inputSchema": {"type": "object", "properties": {
            "customer_id": {"type": "string"},
            "campaign_resource_name": {"type": "string"},
            "sitelinks": {"type": "array", "items": {"type": "object"}},
        }, "required": ["customer_id", "campaign_resource_name", "sitelinks"]},
    },
    {
        "name": "add_callouts",
        "description": "Crea textos destacados (callouts, max 25 car.) y los enlaza a la campaña. callouts: lista de strings.",
        "inputSchema": {"type": "object", "properties": {
            "customer_id": {"type": "string"},
            "campaign_resource_name": {"type": "string"},
            "callouts": {"type": "array", "items": {"type": "string"}},
        }, "required": ["customer_id", "campaign_resource_name", "callouts"]},
    },
    {
        "name": "add_structured_snippet",
        "description": ("Crea un extracto de sitio (structured snippet) y lo enlaza a la campaña. "
                        "header: cabecera válida (p.ej. 'Servicios', 'Tipos'). values: >=3 strings (max 25 car.)."),
        "inputSchema": {"type": "object", "properties": {
            "customer_id": {"type": "string"},
            "campaign_resource_name": {"type": "string"},
            "header": {"type": "string"},
            "values": {"type": "array", "items": {"type": "string"}},
        }, "required": ["customer_id", "campaign_resource_name", "header", "values"]},
    },
    {
        "name": "add_call_asset",
        "description": "Crea una extensión de LLAMADA y la enlaza a la campaña. phone_number sin prefijo, country_code (por defecto ES).",
        "inputSchema": {"type": "object", "properties": {
            "customer_id": {"type": "string"},
            "campaign_resource_name": {"type": "string"},
            "phone_number": {"type": "string"},
            "country_code": {"type": "string"},
        }, "required": ["customer_id", "campaign_resource_name", "phone_number"]},
    },
    {
        "name": "create_custom_conversion_goal",
        "description": ("Crea un OBJETIVO DE CONVERSIÓN PERSONALIZADO que agrupa conversiones concretas "
                        "(por sus IDs). Útil para agrupar solo las conversiones deseadas (p.ej. las 'Nexor'). "
                        "La asignación del objetivo a cada campaña se hace luego en la interfaz."),
        "inputSchema": {"type": "object", "properties": {
            "customer_id": {"type": "string"},
            "name": {"type": "string"},
            "conversion_action_ids": {"type": "array", "items": {"type": "string"}},
        }, "required": ["customer_id", "name", "conversion_action_ids"]},
    },
    {
        "name": "add_ad_schedule",
        "description": ("Horario de anuncios (dayparting) en una campaña. schedules: lista de "
                        "{day (MONDAY..SUNDAY), start_hour, end_hour, start_minute?, end_minute?, bid_modifier?}."),
        "inputSchema": {"type": "object", "properties": {
            "customer_id": {"type": "string"},
            "campaign_resource_name": {"type": "string"},
            "schedules": {"type": "array", "items": {"type": "object"}},
        }, "required": ["customer_id", "campaign_resource_name", "schedules"]},
    },
    {
        "name": "set_device_bid_modifiers",
        "description": ("Modificadores de puja por dispositivo. devices: lista de "
                        "{device: MOBILE|DESKTOP|TABLET, bid_modifier} (1.15=+15%, 0=excluir)."),
        "inputSchema": {"type": "object", "properties": {
            "customer_id": {"type": "string"},
            "campaign_resource_name": {"type": "string"},
            "devices": {"type": "array", "items": {"type": "object"}},
        }, "required": ["customer_id", "campaign_resource_name", "devices"]},
    },
    {
        "name": "add_audiences",
        "description": ("Añade audiencias a un grupo (por defecto OBSERVACIÓN, solo puja). "
                        "audiences: lista de {type: USER_LIST|USER_INTEREST|CUSTOM_AUDIENCE|AUDIENCE, "
                        "id, bid_modifier?}. observation: true|false."),
        "inputSchema": {"type": "object", "properties": {
            "customer_id": {"type": "string"},
            "ad_group_resource_name": {"type": "string"},
            "audiences": {"type": "array", "items": {"type": "object"}},
            "observation": {"type": "boolean"},
        }, "required": ["customer_id", "ad_group_resource_name", "audiences"]},
    },
    {
        "name": "create_shared_negative_list",
        "description": ("Crea una lista COMPARTIDA de negativas a nivel de cuenta. keywords: strings "
                        "(usan 'match') o {text, match}. Luego enlázala con attach_shared_set."),
        "inputSchema": {"type": "object", "properties": {
            "customer_id": {"type": "string"},
            "name": {"type": "string"},
            "keywords": {"type": "array", "items": {"type": ["string", "object"]}},
            "match": {"type": "string", "enum": ["EXACT", "PHRASE", "BROAD"]},
        }, "required": ["customer_id", "name"]},
    },
    {
        "name": "add_shared_list_keywords",
        "description": "Añade negativas a una lista compartida existente (por su shared_set_resource_name).",
        "inputSchema": {"type": "object", "properties": {
            "customer_id": {"type": "string"},
            "shared_set_resource_name": {"type": "string"},
            "keywords": {"type": "array", "items": {"type": ["string", "object"]}},
            "match": {"type": "string", "enum": ["EXACT", "PHRASE", "BROAD"]},
        }, "required": ["customer_id", "shared_set_resource_name", "keywords"]},
    },
    {
        "name": "attach_shared_set",
        "description": "Enlaza una lista compartida (shared set) a una campaña.",
        "inputSchema": {"type": "object", "properties": {
            "customer_id": {"type": "string"},
            "campaign_resource_name": {"type": "string"},
            "shared_set_resource_name": {"type": "string"},
        }, "required": ["customer_id", "campaign_resource_name", "shared_set_resource_name"]},
    },
    {
        "name": "add_business_name",
        "description": ("Añade el nombre de negocio a una campaña (asset de texto). "
                        "Requiere verificación del anunciante en la cuenta."),
        "inputSchema": {"type": "object", "properties": {
            "customer_id": {"type": "string"},
            "campaign_resource_name": {"type": "string"},
            "business_name": {"type": "string"},
        }, "required": ["customer_id", "campaign_resource_name", "business_name"]},
    },
    {
        "name": "add_image_asset",
        "description": ("Añade una imagen/logo a una campaña. image: ruta local o URL. "
                        "field_type: MARKETING_IMAGE (1.91:1) | SQUARE_MARKETING_IMAGE (1:1) | "
                        "PORTRAIT_MARKETING_IMAGE (4:5) | LOGO (1:1) | LANDSCAPE_LOGO (4:1)."),
        "inputSchema": {"type": "object", "properties": {
            "customer_id": {"type": "string"},
            "campaign_resource_name": {"type": "string"},
            "image": {"type": "string"},
            "asset_name": {"type": "string"},
            "field_type": {"type": "string"},
        }, "required": ["customer_id", "campaign_resource_name", "image", "asset_name"]},
    },
    {
        "name": "set_campaign_ai_max",
        "description": ("Activa/desactiva AI Max for Search en una campaña. Nota: una vez activo, "
                        "la API suele bloquear apagarlo (AI_MAX_MUST_BE_ENABLED); para neutralizar la "
                        "expansión usa set_ad_group_search_term_matching(enabled=false) en cada grupo."),
        "inputSchema": {"type": "object", "properties": {
            "customer_id": {"type": "string"},
            "campaign_id": {"type": "string"},
            "enable": {"type": "boolean"},
        }, "required": ["customer_id", "campaign_id", "enable"]},
    },
    {
        "name": "set_ad_group_search_term_matching",
        "description": ("AI Max: activa/desactiva la coincidencia de términos de búsqueda en un grupo. "
                        "enabled=false la DESACTIVA (Fase 1 del workbook = sin expansión). ad_group: id o resource name."),
        "inputSchema": {"type": "object", "properties": {
            "customer_id": {"type": "string"},
            "ad_group": {"type": "string"},
            "enabled": {"type": "boolean"},
        }, "required": ["customer_id", "ad_group", "enabled"]},
    },
    {
        "name": "set_campaign_status",
        "description": "Cambia el estado de una campaña. status: ENABLED (activar, ¡empieza a gastar!) | PAUSED | REMOVED (borrar).",
        "inputSchema": {"type": "object", "properties": {
            "customer_id": {"type": "string"},
            "campaign_id": {"type": "string"},
            "status": {"type": "string", "enum": ["ENABLED", "PAUSED", "REMOVED"]},
        }, "required": ["customer_id", "campaign_id", "status"]},
    },
]


# ----------------------------------------------------------------------------
# Ejecución de cada herramienta
# ----------------------------------------------------------------------------
TOOLS.extend(extra.TOOLS)


def call_tool(name, args):
    if name == "list_login_accounts":
        return ads.list_login_accounts()
    if name == "list_accounts":
        return ads.list_accounts()
    if name == "get_campaigns":
        return ads.get_campaigns(args["customer_id"], args.get("date_from"), args.get("date_to"))
    if name == "run_gaql":
        return ads.search(args["query"], args["customer_id"])
    if name == "create_search_campaign":
        return ads.create_search_campaign(
            args["customer_id"], args["name"], args["daily_eur"],
            budget_name=args.get("budget_name"), bidding=args.get("bidding"),
            networks=args.get("networks"), geo=args.get("geo"),
            languages=args.get("languages"), start_date=args.get("start_date"),
            end_date=args.get("end_date"), status=args.get("status", "PAUSED"))
    if name == "create_ad_group":
        return ads.create_ad_group(args["customer_id"], args["campaign_resource_name"],
                                   args["name"], args.get("cpc_eur", 0.5))
    if name == "add_keywords":
        return ads.add_keywords(args["customer_id"], args["ad_group_resource_name"],
                                args["keywords"], args.get("match", "PHRASE"))
    if name == "add_campaign_negative_keywords":
        return ads.add_campaign_negative_keywords(
            args["customer_id"], args["campaign_resource_name"],
            args["keywords"], args.get("match", "PHRASE"))
    if name == "create_rsa_ad":
        return ads.create_rsa_ad(args["customer_id"], args["ad_group_resource_name"],
                                 args["final_url"], args["headlines"], args["descriptions"],
                                 path1=args.get("path1"), path2=args.get("path2"),
                                 status=args.get("status", "PAUSED"))
    if name == "update_campaign_bidding":
        return ads.update_campaign_bidding(args["customer_id"], args["campaign_id"], args["bidding"])
    if name == "update_campaign_budget":
        return ads.update_campaign_budget(args["customer_id"], args["budget_resource_name"], args["daily_eur"])
    if name == "add_campaign_locations":
        return ads.add_campaign_locations(args["customer_id"], args["campaign_resource_name"],
                                          args["locations"], args.get("presence"))
    if name == "add_campaign_languages":
        return ads.add_campaign_languages(args["customer_id"], args["campaign_resource_name"], args["language_ids"])
    if name == "update_campaign_geo_type":
        return ads.update_campaign_geo_type(args["customer_id"], args["campaign_id"], args["presence"])
    if name == "set_resource_status":
        return ads.set_resource_status(args["customer_id"], args["service"],
                                       args["resource_name"], args["status"])
    if name == "add_sitelinks":
        return ads.add_sitelinks(args["customer_id"], args["campaign_resource_name"], args["sitelinks"])
    if name == "add_callouts":
        return ads.add_callouts(args["customer_id"], args["campaign_resource_name"], args["callouts"])
    if name == "add_structured_snippet":
        return ads.add_structured_snippet(args["customer_id"], args["campaign_resource_name"],
                                          args["header"], args["values"])
    if name == "add_call_asset":
        return ads.add_call_asset(args["customer_id"], args["campaign_resource_name"],
                                  args["phone_number"], args.get("country_code", "ES"))
    if name == "create_custom_conversion_goal":
        return ads.create_custom_conversion_goal(args["customer_id"], args["name"],
                                                 args["conversion_action_ids"])
    if name == "add_ad_schedule":
        return ads.add_ad_schedule(args["customer_id"], args["campaign_resource_name"], args["schedules"])
    if name == "set_device_bid_modifiers":
        return ads.set_device_bid_modifiers(args["customer_id"], args["campaign_resource_name"], args["devices"])
    if name == "add_audiences":
        return ads.add_audiences(args["customer_id"], args["ad_group_resource_name"],
                                 args["audiences"], args.get("observation", True))
    if name == "create_shared_negative_list":
        return ads.create_shared_negative_list(args["customer_id"], args["name"],
                                               args.get("keywords"), args.get("match", "PHRASE"))
    if name == "add_shared_list_keywords":
        return ads.add_shared_list_keywords(args["customer_id"], args["shared_set_resource_name"],
                                            args["keywords"], args.get("match", "PHRASE"))
    if name == "attach_shared_set":
        return ads.attach_shared_set(args["customer_id"], args["campaign_resource_name"],
                                     args["shared_set_resource_name"])
    if name == "add_business_name":
        return ads.add_business_name(args["customer_id"], args["campaign_resource_name"], args["business_name"])
    if name == "add_image_asset":
        return ads.add_image_asset(args["customer_id"], args["campaign_resource_name"], args["image"],
                                   args["asset_name"], args.get("field_type", "MARKETING_IMAGE"))
    if name == "set_campaign_ai_max":
        return ads.set_campaign_ai_max(args["customer_id"], args["campaign_id"], args["enable"])
    if name == "set_ad_group_search_term_matching":
        return ads.set_ad_group_search_term_matching(args["customer_id"], args["ad_group"], args["enabled"])
    if name == "set_campaign_status":
        return ads.set_campaign_status(args["customer_id"], args["campaign_id"], args["status"])
    if name in extra.HANDLERS:
        return extra.HANDLERS[name](args)
    raise ValueError(f"Herramienta desconocida: {name}")


# ----------------------------------------------------------------------------
# Bucle JSON-RPC por stdio
# ----------------------------------------------------------------------------
def send(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def handle(req):
    method = req.get("method")
    rid = req.get("id")

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = req.get("params", {})
        tname = params.get("name")
        targs = params.get("arguments", {}) or {}
        try:
            result = call_tool(tname, targs)
            text = json.dumps(result, ensure_ascii=False, indent=2)
            return {"jsonrpc": "2.0", "id": rid,
                    "result": {"content": [{"type": "text", "text": text}], "isError": False}}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": rid,
                    "result": {"content": [{"type": "text", "text": f"ERROR: {e}"}], "isError": True}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}
    # Notificaciones (sin id) u otros métodos: no responder
    return None


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle(req)
        if resp is not None:
            send(resp)


if __name__ == "__main__":
    main()
