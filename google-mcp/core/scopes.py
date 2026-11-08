"""Todos los permisos (scopes) que pide el MCP unificado. Un solo login por cuenta
= acceso a todo el ecosistema de Google de esa cuenta."""

SCOPES = [
    # Identidad (necesario para comprobar que el token es de bryan@ / academy@)
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    # Google Ads
    "https://www.googleapis.com/auth/adwords",
    # Google Analytics 4 (Data + Admin)
    "https://www.googleapis.com/auth/analytics",
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/analytics.edit",
    "https://www.googleapis.com/auth/analytics.manage.users",
    "https://www.googleapis.com/auth/analytics.provision",
    # Google Tag Manager
    "https://www.googleapis.com/auth/tagmanager.readonly",
    "https://www.googleapis.com/auth/tagmanager.edit.containers",
    "https://www.googleapis.com/auth/tagmanager.edit.containerversions",
    "https://www.googleapis.com/auth/tagmanager.publish",
    "https://www.googleapis.com/auth/tagmanager.delete.containers",
    "https://www.googleapis.com/auth/tagmanager.manage.accounts",
    "https://www.googleapis.com/auth/tagmanager.manage.users",
    # Search Console + Indexing API + Site Verification
    "https://www.googleapis.com/auth/webmasters",
    "https://www.googleapis.com/auth/indexing",
    "https://www.googleapis.com/auth/siteverification",
    # Merchant Center
    "https://www.googleapis.com/auth/content",
    # Google Business Profile (fichas de Google Maps, reseñas, posts)
    "https://www.googleapis.com/auth/business.manage",
    # YouTube (canal, vídeos, playlists, comentarios) + YouTube Analytics
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/yt-analytics-monetary.readonly",
    # Gmail
    "https://mail.google.com/",
    "https://www.googleapis.com/auth/gmail.settings.basic",
    "https://www.googleapis.com/auth/gmail.settings.sharing",
    "https://www.googleapis.com/auth/postmaster.readonly",
    # Drive / Docs / Sheets / Slides / Forms
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/presentations",
    "https://www.googleapis.com/auth/forms.body",
    "https://www.googleapis.com/auth/forms.responses.readonly",
    # Calendar / Tasks / Contactos
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/tasks",
    "https://www.googleapis.com/auth/contacts",
    # Looker Studio
    "https://www.googleapis.com/auth/datastudio",
    # Google Cloud completo (BigQuery, activar APIs, Cloud Storage, Vertex, etc.)
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/bigquery",
    # Apps Script
    "https://www.googleapis.com/auth/script.projects",
    "https://www.googleapis.com/auth/script.deployments",
    # AdSense
    "https://www.googleapis.com/auth/adsense",
    # Marketing Platform: Campaign Manager 360, DV360, Search Ads 360
    "https://www.googleapis.com/auth/dfatrafficking",
    "https://www.googleapis.com/auth/dfareporting",
    "https://www.googleapis.com/auth/ddmconversions",
    "https://www.googleapis.com/auth/display-video",
    "https://www.googleapis.com/auth/doubleclicksearch",
]


# Grupos que se pueden EXCLUIR (GOOGLE_MCP_EXCLUDE=gmail,drive,docs,calendar en el .env).
# Un token generado sin esos permisos NO puede tocar esos datos aunque alguien lo intente.
GROUPS = {
    "gmail": {"scopes": ["https://mail.google.com/",
                         "https://www.googleapis.com/auth/gmail.settings.basic",
                         "https://www.googleapis.com/auth/gmail.settings.sharing",
                         "https://www.googleapis.com/auth/postmaster.readonly"],
              "tools": ["gmail_", "postmaster_"],
              "hosts": ["gmail.googleapis.com", "gmailpostmastertools.googleapis.com"], "paths": ["/gmail/"]},
    "drive": {"scopes": ["https://www.googleapis.com/auth/drive"],
              "tools": ["drive_"], "hosts": ["drive.googleapis.com"], "paths": ["/drive/", "/upload/drive/"]},
    "docs": {"scopes": ["https://www.googleapis.com/auth/documents",
                        "https://www.googleapis.com/auth/spreadsheets",
                        "https://www.googleapis.com/auth/presentations",
                        "https://www.googleapis.com/auth/forms.body",
                        "https://www.googleapis.com/auth/forms.responses.readonly"],
             "tools": ["docs_", "sheets_", "slides_", "forms_"],
             "hosts": ["docs.googleapis.com", "sheets.googleapis.com", "slides.googleapis.com", "forms.googleapis.com"], "paths": []},
    "calendar": {"scopes": ["https://www.googleapis.com/auth/calendar",
                            "https://www.googleapis.com/auth/tasks",
                            "https://www.googleapis.com/auth/contacts"],
                 "tools": ["calendar_", "tasks_", "contacts_"],
                 "hosts": ["calendar.googleapis.com", "tasks.googleapis.com", "people.googleapis.com"], "paths": ["/calendar/"]},
}


def excluded(env=None):
    import os
    raw = (env if env is not None else os.environ.get("GOOGLE_MCP_EXCLUDE", "")).lower()
    return [g.strip() for g in raw.replace(";", ",").split(",") if g.strip() in GROUPS]


def active_scopes(exclude=None):
    ex = excluded() if exclude is None else exclude
    drop = {s for g in ex for s in GROUPS[g]["scopes"]}
    return [s for s in SCOPES if s not in drop]
