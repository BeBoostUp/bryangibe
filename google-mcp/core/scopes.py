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
