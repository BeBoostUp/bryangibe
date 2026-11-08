"""
Conecta UNA cuenta al MCP de Google unificado (un solo login = todos los servicios).

    python3 get_refresh_token.py bryan      -> inicia sesión con bryan@bryangibe.com
    python3 get_refresh_token.py academy    -> inicia sesión con academy@bryangibe.com

Solo se aceptan esas dos cuentas: si inicias sesión con otro email, el token se
DESCARTA y no se guarda nada.

Guarda en el .env:
    GOOGLE_REFRESH_TOKEN_<ETIQUETA>
    GOOGLE_ADS_LOGIN_CUSTOMER_ID_<ETIQUETA>  (MCC de Google Ads, autodescubierto)
"""
import os
import re
import sys
import urllib.parse
import webbrowser
import http.server

import requests

try:  # consola de Windows
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from core import accounts  # noqa: E402
from core.scopes import SCOPES  # noqa: E402

accounts.bootstrap(verify=False)

LABEL = (sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
NEW_LABEL = False
if not re.fullmatch(r"[a-z0-9_]+", LABEL or "-"):
    print("Uso: python3 get_refresh_token.py <" + "|".join(accounts.ALLOWED) + ">")
    sys.exit(1)
if LABEL not in accounts.ALLOWED:
    if not accounts.open_mode():
        print("Uso: python3 get_refresh_token.py <" + "|".join(accounts.ALLOWED) + ">")
        print("Este MCP solo admite: " + ", ".join(accounts.ALLOWED.values()))
        sys.exit(1)
    NEW_LABEL = True  # modo abierto: se registra el email con el que inicies sesion
EMAIL = accounts.ALLOWED.get(LABEL)
CLIENT_ID, CLIENT_SECRET = accounts.client_id(), accounts.client_secret()
REDIRECT_URI = "http://127.0.0.1:8787/oauth2callback"
if not CLIENT_ID or not CLIENT_SECRET:
    print("[X] Falta GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET en el .env")
    sys.exit(1)

auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
    "client_id": CLIENT_ID,
    "redirect_uri": REDIRECT_URI,
    "response_type": "code",
    "scope": " ".join(SCOPES),
    "access_type": "offline",
    "prompt": "consent select_account",
    "include_granted_scopes": "true",
    **({"login_hint": EMAIL} if EMAIL else {}),
})

result = {"refresh_token": None, "access_token": None, "error": None}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if not parsed.path.startswith("/oauth2callback"):
            self.send_response(404)
            self.end_headers()
            return
        params = urllib.parse.parse_qs(parsed.query)
        if params.get("error"):
            result["error"] = params["error"][0]
            return self._reply("Error de autorizacion: " + result["error"])
        r = requests.post("https://oauth2.googleapis.com/token", data={
            "code": params.get("code", [""])[0], "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET, "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code"}, timeout=30)
        d = r.json()
        if not d.get("refresh_token"):
            result["error"] = d.get("error_description") or str(d)
            return self._reply("No se recibio refresh_token: " + result["error"])
        got, scopes = accounts.token_email(d["access_token"])
        if NEW_LABEL and got:
            result["email"] = got
        elif got != EMAIL:
            # revoca el token para no dejar nada colgando
            requests.post("https://oauth2.googleapis.com/revoke",
                          params={"token": d["refresh_token"]}, timeout=20)
            result["error"] = f"Has iniciado sesion con '{got}', pero '{LABEL}' debe ser {EMAIL}. Token descartado."
            return self._reply(result["error"])
        missing = [s for s in SCOPES if s not in scopes and s != "openid"]
        result.update(refresh_token=d["refresh_token"], access_token=d["access_token"], missing=missing)
        self._reply(f"Listo: {got} conectado a TODO el ecosistema de Google. Cierra esta pestana.")

    def _reply(self, msg):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(("<html><body style='font-family:sans-serif;background:#0f1117;color:#fff;"
                          f"padding:48px;text-align:center'><h1>{msg}</h1></body></html>").encode("utf-8"))

    def log_message(self, *a):
        pass


def write_env(key, value):
    content = open(accounts.ENV_PATH, encoding="utf-8").read() if os.path.exists(accounts.ENV_PATH) else ""
    if re.search(rf"^{key}=.*$", content, flags=re.M):
        content = re.sub(rf"^{key}=.*$", f"{key}={value}", content, flags=re.M)
    else:
        content = content.rstrip("\n") + f"\n{key}={value}\n"
    with open(accounts.ENV_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    try:
        os.chmod(accounts.ENV_PATH, 0o600)
    except OSError:
        pass


def discover_ads_login_cid(access_token):
    """Busca el MCC (o la primera cuenta) de Google Ads de este login."""
    ver = os.environ.get("GOOGLE_ADS_API_VERSION", "v25") or "v25"
    h = {"Authorization": "Bearer " + access_token}
    dev = os.environ.get("GOOGLE_ADS_DEVELOPER_TOKEN", "").strip()
    if dev:
        h["developer-token"] = dev
    r = requests.get(f"https://googleads.googleapis.com/{ver}/customers:listAccessibleCustomers",
                     headers=h, timeout=30)
    ids = [x.split("/")[-1] for x in r.json().get("resourceNames", [])] if r.ok else []
    for cid in ids:
        q = {"query": "SELECT customer.id, customer.manager FROM customer LIMIT 1"}
        rr = requests.post(f"https://googleads.googleapis.com/{ver}/customers/{cid}/googleAds:search",
                           headers=dict(h, **{"login-customer-id": cid}), json=q, timeout=30)
        if rr.ok and rr.json().get("results", [{}])[0].get("customer", {}).get("manager"):
            return cid
    return ids[0] if ids else ""


print("=" * 64)
print(f"Cuenta: {LABEL}  ->  inicia sesion con {EMAIL or 'la cuenta de Google que quieras anadir'}")
print(f"Se piden {len(SCOPES)} permisos (Ads, GA4, GTM, Search Console, Merchant, Business")
print("Profile, YouTube, Gmail, Drive, Docs, Sheets, Calendar, Cloud/BigQuery, Looker Studio...)")
print("Si no se abre el navegador, copia esta URL:\n")
print(auth_url)
print("=" * 64)
try:
    webbrowser.open(auth_url)
except Exception:
    pass

server = http.server.HTTPServer(("127.0.0.1", 8787), Handler)
server.timeout = 300
while result["refresh_token"] is None and result["error"] is None:
    server.handle_request()

if not result["refresh_token"]:
    print("\n[X]", result["error"])
    sys.exit(1)

if NEW_LABEL:
    EMAIL = result["email"]
    pairs = dict(accounts.ALLOWED, **{LABEL: EMAIL})
    write_env("GOOGLE_MCP_ACCOUNTS", ",".join(f"{l}={e}" for l, e in pairs.items()))
    print(f"[OK] Cuenta nueva registrada: {LABEL} = {EMAIL}")
write_env(f"GOOGLE_REFRESH_TOKEN_{LABEL.upper()}", result["refresh_token"])
print(f"\n[OK] GOOGLE_REFRESH_TOKEN_{LABEL.upper()} guardado ({EMAIL}).")
if result.get("missing"):
    print("[!] Google no concedio estos permisos (desmarcados en la pantalla de consentimiento):")
    for s in result["missing"]:
        print("    -", s)
cid = ""
try:
    cid = discover_ads_login_cid(result["access_token"])
except Exception as e:
    print("[i] No se pudo autodescubrir la cuenta de Google Ads:", e)
if cid:
    write_env(f"GOOGLE_ADS_LOGIN_CUSTOMER_ID_{LABEL.upper()}", cid)
    print(f"[OK] Google Ads login-customer-id = {cid}")
else:
    print("[i] Esta cuenta no tiene acceso a Google Ads (o no se pudo detectar).")
print("\nReinicia Claude para que el MCP 'google' use el nuevo token.")
