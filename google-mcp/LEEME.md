# MCP de Google unificado (`google`)

Un solo servidor MCP con **todo** el ecosistema de Google. Sustituye a los 6 anteriores
(`googleads`, `ga4`, `tagmanager`, `merchantcenter`, `searchconsole`, `gmail`), que
quedan integrados dentro sin perder ninguna herramienta.

## Cuentas: solo dos

| Etiqueta | Email |
|---|---|
| `bryan` (por defecto) | bryan@bryangibe.com |
| `academy` | academy@bryangibe.com |

Todo lo que tengan esas dos cuentas (cuentas de Ads, propiedades de GA4, contenedores de
GTM, propiedades de Search Console, Merchant Center, canales de YouTube, fichas de Business
Profile, Drive, proyectos de Cloud...) es accesible. **Nada más.** El límite se aplica en
tres capas:

1. Al arrancar, cualquier token de otra etiqueta (`marketing`, `gmail`, ...) se anula aunque
   siga en el `.env`.
2. Cada token unificado se comprueba con Google: si su email no es el esperado, la cuenta se
   bloquea.
3. `get_refresh_token.py` rechaza (y revoca) el login si inicias sesión con otro email.

Además, `google_api_request` solo envía el token a `https://*.googleapis.com`.

## Modo "todas las cuentas" (ordenador principal)

Si el `.env` tiene `GOOGLE_MCP_OPEN=1`, la lista de cuentas sale de `GOOGLE_MCP_ACCOUNTS`
(pares `etiqueta=email` separados por comas) y puedes añadir cuentas nuevas cuando quieras:

```bash
cd ~/google-mcp && python3 get_refresh_token.py sockdata
```

Inicias sesión con la cuenta que quieras: su email queda registrado y fijado a esa etiqueta.
En este modo el instalador NO quita los 6 MCP antiguos.

Sin `GOOGLE_MCP_OPEN`, el MCP solo admite bryan@ y academy@ (modo restringido).

## Instalar

**Mac:** abre Terminal en la carpeta descomprimida y ejecuta `bash install.sh`.

**Windows:** haz doble clic en `install.bat`. Necesitas Python 3 de
https://www.python.org/downloads/windows/ (marca "Add python.exe to PATH" al instalarlo).

El instalador copia la carpeta a tu carpeta de usuario (`~/google-mcp` o
`C:\Users\<tu usuario>\google-mcp`), registra el servidor `google` en `.claude.json`
(quitando los 6 antiguos, con copia de seguridad) y te ofrece conectar `bryan` y
`academy`. Reinicia Claude.

## Conectar o renovar una cuenta

```bash
cd ~/google-mcp && python3 get_refresh_token.py bryan
cd ~/google-mcp && python3 get_refresh_token.py academy
```

En Windows (PowerShell): `cd ~\google-mcp; python get_refresh_token.py academy`

Un login pide todos los permisos de una vez (Ads, GA4, GTM, Search Console, Indexing, Site
Verification, Merchant, Business Profile, YouTube y YouTube Analytics, Gmail, Drive, Docs,
Sheets, Slides, Forms, Calendar, Tasks, Contactos, Looker Studio, Cloud/BigQuery, Apps
Script, AdSense, CM360/DV360/SA360). Así no hay que volver a añadir nada.

Hasta que generes el token unificado de `bryan`, siguen funcionando sus tokens antiguos
por servicio (Ads, GA4, GTM, Merchant, Search Console, Gmail/Drive).

## Herramientas (351)

| Prefijo | Servicio | Nº |
|---|---|---|
| `ads_` | Google Ads (API v25): GAQL, mutate, campañas Search/PMax, keywords, assets, recomendaciones, Keyword Planner... | 54 |
| `ga4_` | Analytics 4: Data API (informes, realtime, funnels, pivots) y Admin API completa | 61 |
| `gtm_` | Tag Manager: cuentas, contenedores, workspaces, tags, triggers, variables, versiones, publicar, permisos | 59 |
| `merchant_` | Merchant Center (Merchant API): productos, feeds, inventarios, promociones, envío, informes | 68 |
| `gsc_` | Search Console: rendimiento, URL Inspection, sitemaps, propiedades | 13 |
| `gmail_` / `drive_` | Gmail completo y Drive | 54 |
| `youtube_` | Canales, vídeos, subida de vídeos, YouTube Analytics | 4 |
| `gbp_` | Business Profile: cuentas, fichas, reseñas (y responderlas), métricas | 5 |
| `sheets_` `docs_` `slides_` `forms_` | Google Sheets, Docs, Slides y Forms | 12 |
| `calendar_` `tasks_` `contacts_` | Calendar, Tasks y Contactos | 5 |
| `cloud_` `bigquery_` | Proyectos de Cloud, activar APIs, SQL en BigQuery | 4 |
| `indexing_` `site_verification_` `pagespeed` `crux` | Indexing API, verificación de dominios, PageSpeed y Core Web Vitals | 5 |
| `looker_studio_` `adsense_` `postmaster_` | Looker Studio, AdSense y Gmail Postmaster | 3 |
| `google_` | `google_whoami`, `google_inventory`, `google_api_request`, `google_api_discovery` | 4 |

**`google_api_request` es la red de seguridad:** llama a cualquier endpoint de cualquier API
de Google con el token de la cuenta. Junto a `google_api_discovery` (que busca la URL y los
parámetros en la documentación oficial) y `cloud_enable_api` (que activa la API en el
proyecto si hace falta), cubre lo que no tenga herramienta propia.

Para ver todo lo accesible en las dos cuentas: `google_inventory`.

## Paquete para empleados (sin contraseñas)

Para que tu equipo use bryan@ y academy@ sin iniciar sesión ni saber tus contraseñas:

```bash
cd ~/google-mcp && python3 crear_paquete_empleados.py
```

1. Eliges qué servicios personales dejar fuera (Gmail, Drive, Docs/Sheets, Calendar). Lo que
   dejes fuera no se pide a Google: esos tokens no pueden leer tu correo aunque lo intenten.
2. Inicias sesión tú con bryan@ y con academy@ (tokens nuevos solo para el paquete).
3. El zip queda en tu Escritorio. Ellos ejecutan `install.sh` o `install.bat`, sin login.

Para cortarles el acceso: `python3 revocar_paquete_empleados.py <zip>`. Google puede
desconectar también tus propios tokens de esa cuenta; si pasa, vuelve a ejecutar
`python3 get_refresh_token.py bryan`.

## Seguridad

El `.env` contiene el client secret de OAuth y los refresh tokens: equivalen a tus
contraseñas de Google. No lo subas a Git ni lo compartas. Si se filtra, revoca el acceso en
https://myaccount.google.com/permissions (app "Gads Be Boost Up") y vuelve a generar los tokens.
