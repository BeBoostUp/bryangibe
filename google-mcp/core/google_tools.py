"""
Herramientas transversales del MCP unificado:
  - google_api_request: llamada a CUALQUIER API de Google (*.googleapis.com) con el
    token de bryan@ o academy@. Es la red de seguridad: si algo no tiene herramienta
    propia, se hace con esto.
  - google_api_discovery: busca APIs y métodos (documentación oficial en vivo).
  - Atajos para servicios nuevos: YouTube, Business Profile, Sheets, Docs, Slides,
    Calendar, Tasks, Contactos, Forms, BigQuery, Cloud, Looker Studio, Indexing,
    Site Verification, PageSpeed, CrUX, AdSense, Apps Script.
"""
import json
import mimetypes
import os
import urllib.parse

import requests

from core import accounts

_ACC = {"type": "string", "description": "Cuenta: 'bryan' (bryan@bryangibe.com, por defecto) o 'academy' (academy@bryangibe.com)."}
_S, _I, _B, _O, _A = ({"type": "string"}, {"type": "integer"}, {"type": "boolean"},
                      {"type": "object"}, {"type": "array", "items": {"type": "string"}})


def _check_host(url):
    u = urllib.parse.urlparse(url)
    host = (u.hostname or "").lower()
    if u.scheme != "https" or not (host == "googleapis.com" or host.endswith(".googleapis.com")):
        raise ValueError("Por seguridad solo se permiten URLs https://*.googleapis.com "
                         "(el token nunca se envía a otros dominios).")


def request(method, url, account=None, params=None, body=None, headers=None,
            upload_file=None, save_to=None, raw_body=None, content_type=None):
    if not url.startswith("http"):
        url = "https://" + url.lstrip("/")
    _check_host(url)
    h = {"Authorization": "Bearer " + accounts.access_token(account)}
    if headers:
        h.update({k: v for k, v in headers.items() if k.lower() != "authorization"})
    kw = {"params": params, "headers": h, "timeout": 300}
    if upload_file:
        path = os.path.expanduser(upload_file)
        mime = content_type or mimetypes.guess_type(path)[0] or "application/octet-stream"
        data = open(path, "rb").read()
        if body is not None:  # multipart: metadatos + archivo
            boundary = "mcp_google_boundary"
            payload = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
                       f"{json.dumps(body)}\r\n--{boundary}\r\nContent-Type: {mime}\r\n\r\n").encode() \
                + data + f"\r\n--{boundary}--".encode()
            h["Content-Type"] = f"multipart/related; boundary={boundary}"
            kw["data"] = payload
        else:
            h["Content-Type"] = mime
            kw["data"] = data
    elif raw_body is not None:
        h["Content-Type"] = content_type or "text/plain"
        kw["data"] = raw_body.encode("utf-8")
    elif body is not None:
        kw["json"] = body
    r = requests.request(method.upper(), url, **kw)
    if save_to:
        path = os.path.expanduser(save_to)
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "wb") as f:
            f.write(r.content)
        return {"status": r.status_code, "saved_to": os.path.abspath(path), "bytes": len(r.content),
                "content_type": r.headers.get("Content-Type")}
    try:
        data = r.json() if r.content else {}
    except ValueError:
        data = r.text[:200000]
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code}: {json.dumps(data, ensure_ascii=False)[:4000]}")
    return data


def _g(url, account=None, params=None):
    return request("GET", url, account, params=params)


def _p(url, body=None, account=None, params=None, method="POST"):
    return request(method, url, account, params=params, body=body)


# ---------------------------------------------------------------- discovery
def discovery(api=None, version=None, filter=None, discovery_url=None):
    if not api and not discovery_url:
        d = requests.get("https://www.googleapis.com/discovery/v1/apis", params={"preferred": "true"}, timeout=60).json()
        items = [{"name": i["name"], "version": i["version"], "title": i.get("title")}
                 for i in d.get("items", [])]
        if filter:
            f = filter.lower()
            items = [i for i in items if f in json.dumps(i).lower()]
        return {"apis": items, "tip": "Pasa api+version para ver sus métodos."}
    url = discovery_url or f"https://www.googleapis.com/discovery/v1/apis/{api}/{version}/rest"
    d = requests.get(url, timeout=60)
    if d.status_code == 404 and api:
        d = requests.get(f"https://{api}.googleapis.com/$discovery/rest", params={"version": version}, timeout=60)
    d = d.json()
    root = d.get("rootUrl", "") + d.get("servicePath", "")
    out = []

    def walk(res, prefix):
        for name, m in (res.get("methods") or {}).items():
            row = {"id": m.get("id"), "http": m.get("httpMethod"), "url": root + (m.get("flatPath") or m.get("path", "")),
                   "desc": (m.get("description") or "")[:200],
                   "params": {k: v.get("location") for k, v in (m.get("parameters") or {}).items()}}
            if not filter or filter.lower() in json.dumps(row).lower():
                out.append(row)
        for rn, r in (res.get("resources") or {}).items():
            walk(r, prefix + rn + ".")
    walk(d, "")
    return {"api": d.get("name"), "version": d.get("version"), "rootUrl": root,
            "n_methods": len(out), "methods": out[:400]}


# ---------------------------------------------------------------- Cloud
def cloud_list_projects(account=None):
    return _g("https://cloudresourcemanager.googleapis.com/v1/projects", account)


def cloud_list_enabled_apis(project, account=None):
    return _g(f"https://serviceusage.googleapis.com/v1/projects/{project}/services", account,
              {"filter": "state:ENABLED", "pageSize": 200})


def cloud_enable_api(project, service, account=None):
    return _p(f"https://serviceusage.googleapis.com/v1/projects/{project}/services/{service}:enable", {}, account)


def bigquery_query(project, query, account=None, use_legacy_sql=False, max_results=1000):
    r = _p(f"https://bigquery.googleapis.com/bigquery/v2/projects/{project}/queries",
           {"query": query, "useLegacySql": use_legacy_sql, "maxResults": max_results, "timeoutMs": 120000}, account)
    fields = [f["name"] for f in r.get("schema", {}).get("fields", [])]
    rows = [{fields[i]: c.get("v") for i, c in enumerate(row.get("f", []))} for row in r.get("rows", [])]
    return {"totalRows": r.get("totalRows"), "jobComplete": r.get("jobComplete"), "rows": rows,
            "jobReference": r.get("jobReference")}


# ---------------------------------------------------------------- YouTube
YT = "https://youtube.googleapis.com/youtube/v3"


def youtube_my_channels(account=None):
    return _g(f"{YT}/channels", account, {"part": "snippet,statistics,contentDetails,brandingSettings", "mine": "true"})


def youtube_list_videos(account=None, max_results=50, page_token=None):
    ch = youtube_my_channels(account).get("items", [])
    if not ch:
        return {"items": [], "note": "Esta cuenta no tiene canal de YouTube."}
    up = ch[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    pl = _g(f"{YT}/playlistItems", account, {"part": "contentDetails", "playlistId": up,
                                              "maxResults": max_results, "pageToken": page_token})
    ids = ",".join(i["contentDetails"]["videoId"] for i in pl.get("items", []))
    vids = _g(f"{YT}/videos", account, {"part": "snippet,statistics,status,contentDetails", "id": ids}) if ids else {}
    return {"items": vids.get("items", []), "nextPageToken": pl.get("nextPageToken")}


def youtube_upload_video(file_path, title, description="", tags=None, privacy="private", category_id="22", account=None):
    meta = {"snippet": {"title": title, "description": description, "tags": tags or [], "categoryId": category_id},
            "status": {"privacyStatus": privacy}}
    return request("POST", "https://www.googleapis.com/upload/youtube/v3/videos", account,
                   params={"uploadType": "multipart", "part": "snippet,status"}, body=meta, upload_file=file_path)


def youtube_analytics(start_date, end_date, metrics="views,estimatedMinutesWatched,averageViewDuration,subscribersGained,likes",
                      dimensions=None, filters=None, sort=None, max_results=None, account=None):
    return _g("https://youtubeanalytics.googleapis.com/v2/reports", account, {
        "ids": "channel==MINE", "startDate": start_date, "endDate": end_date, "metrics": metrics,
        "dimensions": dimensions, "filters": filters, "sort": sort, "maxResults": max_results})


# ---------------------------------------------------------------- Business Profile
def gbp_list_accounts(account=None):
    return _g("https://mybusinessaccountmanagement.googleapis.com/v1/accounts", account)


def gbp_list_locations(gbp_account, account=None, read_mask=None):
    return _g(f"https://mybusinessbusinessinformation.googleapis.com/v1/{gbp_account}/locations", account,
              {"readMask": read_mask or "name,title,storefrontAddress,phoneNumbers,websiteUri,categories,regularHours,metadata",
               "pageSize": 100})


def gbp_list_reviews(gbp_account, location, account=None):
    loc = location.split("/")[-1]
    return _g(f"https://mybusiness.googleapis.com/v4/{gbp_account}/locations/{loc}/reviews", account, {"pageSize": 50})


def gbp_reply_review(review_name, comment, account=None):
    return _p(f"https://mybusiness.googleapis.com/v4/{review_name}/reply", {"comment": comment}, account, method="PUT")


def gbp_performance(location, metrics, start_date, end_date, account=None):
    loc = location if location.startswith("locations/") else "locations/" + location.split("/")[-1]
    s, e = start_date.split("-"), end_date.split("-")
    params = [("dailyMetrics", m) for m in metrics] + [
        ("dailyRange.startDate.year", s[0]), ("dailyRange.startDate.month", s[1]), ("dailyRange.startDate.day", s[2]),
        ("dailyRange.endDate.year", e[0]), ("dailyRange.endDate.month", e[1]), ("dailyRange.endDate.day", e[2])]
    return _g(f"https://businessprofileperformance.googleapis.com/v1/{loc}:fetchMultiDailyMetricsTimeSeries", account, params)


# ---------------------------------------------------------------- Sheets / Docs / Slides / Forms
def sheets_get(spreadsheet_id, account=None):
    return _g(f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}", account,
              {"fields": "spreadsheetId,properties,sheets.properties,spreadsheetUrl"})


def sheets_read(spreadsheet_id, range, account=None):
    return _g(f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{urllib.parse.quote(range)}", account)


def sheets_write(spreadsheet_id, range, values, append=False, account=None):
    rng = urllib.parse.quote(range)
    base = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{rng}"
    if append:
        return _p(base + ":append", {"values": values}, account, {"valueInputOption": "USER_ENTERED"})
    return _p(base, {"values": values}, account, {"valueInputOption": "USER_ENTERED"}, method="PUT")


def sheets_create(title, account=None):
    return _p("https://sheets.googleapis.com/v4/spreadsheets", {"properties": {"title": title}}, account)


def sheets_batch_update(spreadsheet_id, requests_, account=None):
    return _p(f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}:batchUpdate", {"requests": requests_}, account)


def docs_get_text(document_id, account=None):
    d = _g(f"https://docs.googleapis.com/v1/documents/{document_id}", account)
    txt = []
    for el in d.get("body", {}).get("content", []):
        for pe in (el.get("paragraph") or {}).get("elements", []):
            txt.append((pe.get("textRun") or {}).get("content", ""))
    return {"title": d.get("title"), "documentId": d.get("documentId"), "text": "".join(txt)}


def docs_create(title, text=None, account=None):
    d = _p("https://docs.googleapis.com/v1/documents", {"title": title}, account)
    if text:
        _p(f"https://docs.googleapis.com/v1/documents/{d['documentId']}:batchUpdate",
           {"requests": [{"insertText": {"location": {"index": 1}, "text": text}}]}, account)
    return {"documentId": d["documentId"], "url": f"https://docs.google.com/document/d/{d['documentId']}/edit"}


def docs_batch_update(document_id, requests_, account=None):
    return _p(f"https://docs.googleapis.com/v1/documents/{document_id}:batchUpdate", {"requests": requests_}, account)


def slides_get(presentation_id, account=None):
    return _g(f"https://slides.googleapis.com/v1/presentations/{presentation_id}", account)


def slides_batch_update(presentation_id, requests_, account=None):
    return _p(f"https://slides.googleapis.com/v1/presentations/{presentation_id}:batchUpdate", {"requests": requests_}, account)


def forms_get(form_id, account=None):
    return _g(f"https://forms.googleapis.com/v1/forms/{form_id}", account)


def forms_responses(form_id, account=None):
    return _g(f"https://forms.googleapis.com/v1/forms/{form_id}/responses", account)


# ---------------------------------------------------------------- Calendar / Tasks / Contacts
CAL = "https://www.googleapis.com/calendar/v3"


def calendar_list(account=None):
    return _g(f"{CAL}/users/me/calendarList", account)


def calendar_events(calendar_id="primary", time_min=None, time_max=None, q=None, max_results=100, account=None):
    return _g(f"{CAL}/calendars/{urllib.parse.quote(calendar_id)}/events", account, {
        "timeMin": time_min, "timeMax": time_max, "q": q, "maxResults": max_results,
        "singleEvents": "true", "orderBy": "startTime"})


def calendar_create_event(event, calendar_id="primary", send_updates="none", account=None):
    return _p(f"{CAL}/calendars/{urllib.parse.quote(calendar_id)}/events", event, account,
              {"sendUpdates": send_updates, "conferenceDataVersion": 1})


def tasks_list(account=None):
    lists = _g("https://tasks.googleapis.com/tasks/v1/users/@me/lists", account).get("items", [])
    for l in lists:
        l["tasks"] = _g(f"https://tasks.googleapis.com/tasks/v1/lists/{l['id']}/tasks", account,
                        {"showCompleted": "false"}).get("items", [])
    return lists


def contacts_search(query, account=None):
    return _g("https://people.googleapis.com/v1/people:searchContacts", account,
              {"query": query, "readMask": "names,emailAddresses,phoneNumbers,organizations"})


# ---------------------------------------------------------------- SEO extra
def indexing_publish(url, type="URL_UPDATED", account=None):
    return _p("https://indexing.googleapis.com/v3/urlNotifications:publish", {"url": url, "type": type}, account)


def site_verification_token(site, method="DNS_TXT", account=None):
    t = "INET_DOMAIN" if method.startswith("DNS") else "SITE"
    return _p("https://www.googleapis.com/siteVerification/v1/token",
              {"site": {"type": t, "identifier": site}, "verificationMethod": method}, account)


def site_verification_verify(site, method="DNS_TXT", account=None):
    t = "INET_DOMAIN" if method.startswith("DNS") else "SITE"
    return _p("https://www.googleapis.com/siteVerification/v1/webResource",
              {"site": {"type": t, "identifier": site}}, account, {"verificationMethod": method})


def pagespeed(url, strategy="mobile", account=None):
    params = [("url", url), ("strategy", strategy)] + [("category", c) for c in
                                                        ("performance", "accessibility", "best-practices", "seo")]
    if os.environ.get("GOOGLE_API_KEY"):
        params.append(("key", os.environ["GOOGLE_API_KEY"]))
    r = _g("https://pagespeedonline.googleapis.com/pagespeedonline/v5/runPagespeed", account, params)
    lh = r.get("lighthouseResult", {})
    audits = lh.get("audits", {})
    return {"url": r.get("id"), "strategy": strategy,
            "scores": {k: v.get("score") for k, v in lh.get("categories", {}).items()},
            "core_web_vitals_field": r.get("loadingExperience", {}).get("metrics"),
            "lab": {k: audits.get(k, {}).get("displayValue") for k in
                    ("first-contentful-paint", "largest-contentful-paint", "total-blocking-time",
                     "cumulative-layout-shift", "speed-index", "interactive")},
            "opportunities": [{"id": k, "title": a.get("title"), "saving": a.get("displayValue")}
                              for k, a in audits.items()
                              if (a.get("details") or {}).get("type") == "opportunity" and (a.get("score") or 1) < 0.9]}


def crux(origin_or_url, form_factor=None, account=None):
    key = "url" if "/" in origin_or_url.split("://", 1)[-1].rstrip("/") else "origin"
    body = {key: origin_or_url}
    if form_factor:
        body["formFactor"] = form_factor
    params = {"key": os.environ["GOOGLE_API_KEY"]} if os.environ.get("GOOGLE_API_KEY") else None
    return _p("https://chromeuxreport.googleapis.com/v1/records:queryRecord", body, account, params)


# ---------------------------------------------------------------- Otros
def looker_studio_search(asset_type="REPORT", title=None, account=None):
    return _g("https://datastudio.googleapis.com/v1/assets:search", account, {"assetTypes": asset_type, "title": title})


def adsense_accounts(account=None):
    return _g("https://adsense.googleapis.com/v2/accounts", account)


def postmaster_domains(account=None):
    return _g("https://gmailpostmastertools.googleapis.com/v1/domains", account)


# ---------------------------------------------------------------- Definición de herramientas
def _t(name, desc, props=None, req=None):
    p = dict(props or {})
    p["account"] = _ACC
    return {"name": name, "description": desc,
            "inputSchema": {"type": "object", "properties": p, "required": req or []}}


TOOLS = [
    _t("google_whoami", "Estado de las cuentas permitidas (bryan@ y academy@): email verificado, nº de permisos, origen del token. Este MCP NO puede usar ninguna otra cuenta."),
    _t("google_inventory", "Inventario de TODO lo accesible en las dos cuentas: cuentas de Google Ads, propiedades GA4, contenedores GTM, propiedades de Search Console, Merchant Center, canales de YouTube, fichas de Business Profile, proyectos de Cloud.",
       {"services": dict(_A, description="Opcional: limita a ads, ga4, gtm, gsc, merchant, youtube, gbp, cloud.")}),
    _t("google_api_request",
       "UNIVERSAL: llama a CUALQUIER endpoint de una API de Google (https://*.googleapis.com) con el token de la cuenta. "
       "Úsalo para todo lo que no tenga herramienta propia (cualquier método de Ads, GA4, GTM, GSC, Merchant, YouTube, "
       "Business Profile, Drive, Sheets, Cloud, BigQuery, Looker Studio, CM360, DV360, SA360...). "
       "Usa google_api_discovery para encontrar la URL y los parámetros. Para Google Ads añade en headers "
       "'login-customer-id' (y 'developer-token' si hace falta) o usa ads_api_call.",
       {"method": dict(_S, description="GET | POST | PUT | PATCH | DELETE"),
        "url": dict(_S, description="URL completa, p.ej. https://analyticsadmin.googleapis.com/v1beta/accountSummaries"),
        "params": dict(_O, description="Query params."),
        "body": dict(_O, description="Cuerpo JSON (o metadatos si hay upload_file)."),
        "headers": dict(_O, description="Cabeceras extra."),
        "upload_file": dict(_S, description="Ruta local de un archivo a subir (media/multipart upload)."),
        "save_to": dict(_S, description="Ruta local donde guardar la respuesta (descargas binarias, exportaciones)."),
        "raw_body": dict(_S, description="Cuerpo de texto crudo (p.ej. XML)."),
        "content_type": _S}, ["method", "url"]),
    _t("google_api_discovery",
       "Busca APIs de Google y sus métodos (documentación oficial en vivo). Sin 'api': lista todas las APIs (filtra con 'filter'). "
       "Con api+version (p.ej. 'mybusinessbusinessinformation','v1' o 'googleads','v25'): lista métodos con URL, verbo y parámetros.",
       {"api": _S, "version": _S, "filter": dict(_S, description="Texto para filtrar."), "discovery_url": _S}),
    _t("cloud_list_projects", "Lista los proyectos de Google Cloud accesibles."),
    _t("cloud_list_enabled_apis", "APIs activadas en un proyecto de Cloud (p.ej. gads-be-boost-up).", {"project": _S}, ["project"]),
    _t("cloud_enable_api", "ESCRITURA: activa una API en un proyecto de Cloud (p.ej. service='mybusinessbusinessinformation.googleapis.com'). Úsalo cuando una llamada devuelva 'API has not been used in project'.",
       {"project": _S, "service": _S}, ["project", "service"]),
    _t("bigquery_query", "Ejecuta SQL en BigQuery (incluye exportaciones de GA4 / Ads / GSC a BigQuery).",
       {"project": _S, "query": _S, "use_legacy_sql": _B, "max_results": _I}, ["project", "query"]),
    _t("youtube_my_channels", "Canales de YouTube de la cuenta (estadísticas, branding)."),
    _t("youtube_list_videos", "Vídeos subidos al canal con estadísticas.", {"max_results": _I, "page_token": _S}),
    _t("youtube_upload_video", "ESCRITURA: sube un vídeo desde disco (privado por defecto).",
       {"file_path": _S, "title": _S, "description": _S, "tags": _A,
        "privacy": {"type": "string", "enum": ["private", "unlisted", "public"]}, "category_id": _S}, ["file_path", "title"]),
    _t("youtube_analytics", "Informe de YouTube Analytics del canal (métricas/dimensiones de la API v2).",
       {"start_date": _S, "end_date": _S, "metrics": _S, "dimensions": _S, "filters": _S, "sort": _S, "max_results": _I},
       ["start_date", "end_date"]),
    _t("gbp_list_accounts", "Google Business Profile: cuentas (accounts/...)."),
    _t("gbp_list_locations", "Google Business Profile: fichas de una cuenta.", {"gbp_account": dict(_S, description="accounts/123"), "read_mask": _S}, ["gbp_account"]),
    _t("gbp_list_reviews", "Google Business Profile: reseñas de una ficha.", {"gbp_account": _S, "location": _S}, ["gbp_account", "location"]),
    _t("gbp_reply_review", "ESCRITURA: responde una reseña (review_name = accounts/x/locations/y/reviews/z).", {"review_name": _S, "comment": _S}, ["review_name", "comment"]),
    _t("gbp_performance", "Google Business Profile: métricas diarias (BUSINESS_IMPRESSIONS_DESKTOP_MAPS, CALL_CLICKS, WEBSITE_CLICKS, BUSINESS_DIRECTION_REQUESTS...).",
       {"location": _S, "metrics": _A, "start_date": _S, "end_date": _S}, ["location", "metrics", "start_date", "end_date"]),
    _t("sheets_get", "Google Sheets: info y pestañas de una hoja.", {"spreadsheet_id": _S}, ["spreadsheet_id"]),
    _t("sheets_read", "Google Sheets: lee un rango (p.ej. 'Hoja1!A1:F200').", {"spreadsheet_id": _S, "range": _S}, ["spreadsheet_id", "range"]),
    _t("sheets_write", "ESCRITURA: escribe (o añade con append=true) filas en un rango.",
       {"spreadsheet_id": _S, "range": _S, "values": {"type": "array", "items": {"type": "array"}}, "append": _B},
       ["spreadsheet_id", "range", "values"]),
    _t("sheets_create", "ESCRITURA: crea una hoja de cálculo nueva.", {"title": _S}, ["title"]),
    _t("sheets_batch_update", "ESCRITURA: batchUpdate de Sheets (formato, pestañas, gráficos...).", {"spreadsheet_id": _S, "requests": {"type": "array", "items": _O}}, ["spreadsheet_id", "requests"]),
    _t("docs_get_text", "Google Docs: texto de un documento.", {"document_id": _S}, ["document_id"]),
    _t("docs_create", "ESCRITURA: crea un Google Doc (con texto opcional).", {"title": _S, "text": _S}, ["title"]),
    _t("docs_batch_update", "ESCRITURA: batchUpdate de Docs.", {"document_id": _S, "requests": {"type": "array", "items": _O}}, ["document_id", "requests"]),
    _t("slides_get", "Google Slides: estructura de una presentación.", {"presentation_id": _S}, ["presentation_id"]),
    _t("slides_batch_update", "ESCRITURA: batchUpdate de Slides.", {"presentation_id": _S, "requests": {"type": "array", "items": _O}}, ["presentation_id", "requests"]),
    _t("forms_get", "Google Forms: estructura de un formulario.", {"form_id": _S}, ["form_id"]),
    _t("forms_responses", "Google Forms: respuestas.", {"form_id": _S}, ["form_id"]),
    _t("calendar_list", "Google Calendar: calendarios."),
    _t("calendar_events", "Google Calendar: eventos (time_min/time_max en RFC3339).",
       {"calendar_id": _S, "time_min": _S, "time_max": _S, "q": _S, "max_results": _I}),
    _t("calendar_create_event", "ESCRITURA: crea un evento (objeto Event de la API).",
       {"event": _O, "calendar_id": _S, "send_updates": {"type": "string", "enum": ["all", "externalOnly", "none"]}}, ["event"]),
    _t("tasks_list", "Google Tasks: listas y tareas pendientes."),
    _t("contacts_search", "Google Contacts: busca contactos.", {"query": _S}, ["query"]),
    _t("indexing_publish", "ESCRITURA: Indexing API, notifica URL_UPDATED o URL_DELETED.",
       {"url": _S, "type": {"type": "string", "enum": ["URL_UPDATED", "URL_DELETED"]}}, ["url"]),
    _t("site_verification_token", "Site Verification: obtiene el token (DNS_TXT, META, FILE...) para verificar un dominio/URL.",
       {"site": _S, "method": _S}, ["site"]),
    _t("site_verification_verify", "ESCRITURA: verifica la propiedad de un dominio/URL tras poner el token.", {"site": _S, "method": _S}, ["site"]),
    _t("pagespeed", "PageSpeed Insights: puntuaciones Lighthouse, Core Web Vitals reales y oportunidades.",
       {"url": _S, "strategy": {"type": "string", "enum": ["mobile", "desktop"]}}, ["url"]),
    _t("crux", "Chrome UX Report: Core Web Vitals reales de un origen o URL.",
       {"origin_or_url": _S, "form_factor": {"type": "string", "enum": ["PHONE", "DESKTOP", "TABLET"]}}, ["origin_or_url"]),
    _t("looker_studio_search", "Looker Studio: busca informes/fuentes de datos.",
       {"asset_type": {"type": "string", "enum": ["REPORT", "DATA_SOURCE"]}, "title": _S}),
    _t("adsense_accounts", "AdSense: cuentas."),
    _t("postmaster_domains", "Gmail Postmaster Tools: dominios (reputación de envío)."),
]


def _a(a):
    return a.get("account")


HANDLERS = {
    "google_whoami": lambda a: accounts.whoami(),
    "google_api_request": lambda a: request(a["method"], a["url"], _a(a), a.get("params"), a.get("body"),
                                            a.get("headers"), a.get("upload_file"), a.get("save_to"),
                                            a.get("raw_body"), a.get("content_type")),
    "google_api_discovery": lambda a: discovery(a.get("api"), a.get("version"), a.get("filter"), a.get("discovery_url")),
    "cloud_list_projects": lambda a: cloud_list_projects(_a(a)),
    "cloud_list_enabled_apis": lambda a: cloud_list_enabled_apis(a["project"], _a(a)),
    "cloud_enable_api": lambda a: cloud_enable_api(a["project"], a["service"], _a(a)),
    "bigquery_query": lambda a: bigquery_query(a["project"], a["query"], _a(a), a.get("use_legacy_sql", False), a.get("max_results", 1000)),
    "youtube_my_channels": lambda a: youtube_my_channels(_a(a)),
    "youtube_list_videos": lambda a: youtube_list_videos(_a(a), a.get("max_results", 50), a.get("page_token")),
    "youtube_upload_video": lambda a: youtube_upload_video(a["file_path"], a["title"], a.get("description", ""), a.get("tags"),
                                                           a.get("privacy", "private"), a.get("category_id", "22"), _a(a)),
    "youtube_analytics": lambda a: youtube_analytics(a["start_date"], a["end_date"], a.get("metrics") or
                                                     "views,estimatedMinutesWatched,averageViewDuration,subscribersGained,likes",
                                                     a.get("dimensions"), a.get("filters"), a.get("sort"), a.get("max_results"), _a(a)),
    "gbp_list_accounts": lambda a: gbp_list_accounts(_a(a)),
    "gbp_list_locations": lambda a: gbp_list_locations(a["gbp_account"], _a(a), a.get("read_mask")),
    "gbp_list_reviews": lambda a: gbp_list_reviews(a["gbp_account"], a["location"], _a(a)),
    "gbp_reply_review": lambda a: gbp_reply_review(a["review_name"], a["comment"], _a(a)),
    "gbp_performance": lambda a: gbp_performance(a["location"], a["metrics"], a["start_date"], a["end_date"], _a(a)),
    "sheets_get": lambda a: sheets_get(a["spreadsheet_id"], _a(a)),
    "sheets_read": lambda a: sheets_read(a["spreadsheet_id"], a["range"], _a(a)),
    "sheets_write": lambda a: sheets_write(a["spreadsheet_id"], a["range"], a["values"], a.get("append", False), _a(a)),
    "sheets_create": lambda a: sheets_create(a["title"], _a(a)),
    "sheets_batch_update": lambda a: sheets_batch_update(a["spreadsheet_id"], a["requests"], _a(a)),
    "docs_get_text": lambda a: docs_get_text(a["document_id"], _a(a)),
    "docs_create": lambda a: docs_create(a["title"], a.get("text"), _a(a)),
    "docs_batch_update": lambda a: docs_batch_update(a["document_id"], a["requests"], _a(a)),
    "slides_get": lambda a: slides_get(a["presentation_id"], _a(a)),
    "slides_batch_update": lambda a: slides_batch_update(a["presentation_id"], a["requests"], _a(a)),
    "forms_get": lambda a: forms_get(a["form_id"], _a(a)),
    "forms_responses": lambda a: forms_responses(a["form_id"], _a(a)),
    "calendar_list": lambda a: calendar_list(_a(a)),
    "calendar_events": lambda a: calendar_events(a.get("calendar_id", "primary"), a.get("time_min"), a.get("time_max"),
                                                 a.get("q"), a.get("max_results", 100), _a(a)),
    "calendar_create_event": lambda a: calendar_create_event(a["event"], a.get("calendar_id", "primary"),
                                                             a.get("send_updates", "none"), _a(a)),
    "tasks_list": lambda a: tasks_list(_a(a)),
    "contacts_search": lambda a: contacts_search(a["query"], _a(a)),
    "indexing_publish": lambda a: indexing_publish(a["url"], a.get("type", "URL_UPDATED"), _a(a)),
    "site_verification_token": lambda a: site_verification_token(a["site"], a.get("method", "DNS_TXT"), _a(a)),
    "site_verification_verify": lambda a: site_verification_verify(a["site"], a.get("method", "DNS_TXT"), _a(a)),
    "pagespeed": lambda a: pagespeed(a["url"], a.get("strategy", "mobile"), _a(a)),
    "crux": lambda a: crux(a["origin_or_url"], a.get("form_factor"), _a(a)),
    "looker_studio_search": lambda a: looker_studio_search(a.get("asset_type", "REPORT"), a.get("title"), _a(a)),
    "adsense_accounts": lambda a: adsense_accounts(_a(a)),
    "postmaster_domains": lambda a: postmaster_domains(_a(a)),
}
