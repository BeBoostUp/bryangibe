"""
Control de cuentas del MCP de Google unificado.

REGLA DE ORO: este MCP SOLO puede usar las cuentas de la lista ALLOWED.
  bryan   -> bryan@bryangibe.com
  academy -> academy@bryangibe.com

Cómo se garantiza:
  1. bootstrap() se ejecuta ANTES de importar ningún módulo (Ads, GA4, GTM, ...).
     Pone a "" en os.environ cualquier refresh token cuya etiqueta no esté en
     ALLOWED (marketing, gmail, default, ...), así los módulos no lo ven aunque
     siga escrito en el .env.
  2. El token unificado GOOGLE_REFRESH_TOKEN_<ETIQUETA> incluye el scope 'email':
     al arrancar se comprueba con Google a qué email pertenece. Si no coincide
     con el esperado, esa etiqueta se desactiva por completo.
  3. get_refresh_token.py se niega a guardar un token de un email no permitido.
"""
import os
import time

import requests
from dotenv import dotenv_values

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(ROOT, ".env")

ALLOWED = {
    "bryan": "bryan@bryangibe.com",
    "academy": "academy@bryangibe.com",
}

# Prefijos de refresh token de cada módulo heredado
MODULE_PREFIXES = {
    "ads": "GOOGLE_ADS_REFRESH_TOKEN_",
    "ga4": "GA4_REFRESH_TOKEN_",
    "gtm": "GTM_REFRESH_TOKEN_",
    "merchant": "MC_REFRESH_TOKEN_",
    "gsc": "GSC_REFRESH_TOKEN_",
    "gmail": "WS_REFRESH_TOKEN_",
}
UNIFIED_PREFIX = "GOOGLE_REFRESH_TOKEN_"
ALL_PREFIXES = list(MODULE_PREFIXES.values()) + [UNIFIED_PREFIX]
# Variables sin sufijo (modo 'default' antiguo): se anulan siempre
LEGACY_SINGLE = [p[:-1] for p in ALL_PREFIXES] + ["GOOGLE_ADS_LOGIN_CUSTOMER_ID"]
CLIENT_PREFIXES = ["GOOGLE_ADS", "GA4", "GTM", "MC", "GSC", "WS"]

STATUS = {}        # label -> {"email":..., "verified":bool, "source":..., "scopes":[...], "note":...}
_token_cache = {}  # label -> {"token":..., "exp":...}


class AccountError(Exception):
    pass


def client_id():
    return os.environ.get("GOOGLE_CLIENT_ID", "").strip()


def client_secret():
    return os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()


def _label_of(key):
    for p in ALL_PREFIXES + ["GOOGLE_ADS_LOGIN_CUSTOMER_ID_"]:
        if key.startswith(p):
            return key[len(p):].lower()
    return None


def _refresh(refresh_token):
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": client_id(), "client_secret": client_secret(),
        "refresh_token": refresh_token, "grant_type": "refresh_token"}, timeout=20)
    d = r.json()
    if "access_token" not in d:
        raise AccountError(d.get("error_description") or d.get("error") or str(d))
    return d


def token_email(access_token):
    """(email, scopes) del access token según Google."""
    r = requests.get("https://oauth2.googleapis.com/tokeninfo",
                     params={"access_token": access_token}, timeout=20)
    d = r.json()
    return (d.get("email") or "").lower(), (d.get("scope") or "").split()


def bootstrap(verify=True):
    """Prepara os.environ para que los módulos solo vean cuentas permitidas."""
    file_vals = dotenv_values(ENV_PATH) if os.path.exists(ENV_PATH) else {}
    for k, v in file_vals.items():
        if k not in os.environ and v is not None:
            os.environ[k] = v

    # 1) Cliente OAuth común para todos los módulos
    cid, csec = client_id(), client_secret()
    if not cid:  # compat: toma el de cualquier módulo
        for p in CLIENT_PREFIXES:
            if os.environ.get(p + "_CLIENT_ID"):
                os.environ["GOOGLE_CLIENT_ID"] = os.environ[p + "_CLIENT_ID"]
                os.environ["GOOGLE_CLIENT_SECRET"] = os.environ.get(p + "_CLIENT_SECRET", "")
                break
        cid, csec = client_id(), client_secret()
    for p in CLIENT_PREFIXES:
        os.environ.setdefault(p + "_CLIENT_ID", cid)
        os.environ.setdefault(p + "_CLIENT_SECRET", csec)

    # 2) Anula todo lo que no sea una cuenta permitida
    for k in list(os.environ.keys()):
        lab = _label_of(k)
        if lab is not None and lab not in ALLOWED:
            os.environ[k] = ""
    for k in LEGACY_SINGLE:
        os.environ[k] = ""

    # 3) Token unificado (todos los scopes) -> se inyecta en cada módulo
    for label, email in ALLOWED.items():
        unified = os.environ.get(UNIFIED_PREFIX + label.upper(), "").strip()
        legacy = [p for p in MODULE_PREFIXES.values() if os.environ.get(p + label.upper(), "").strip()]
        st = {"expected_email": email, "email": None, "verified": False, "scopes": [],
              "source": None, "note": ""}
        if unified:
            st["source"] = "unificado"
            ok = True
            if verify:
                try:
                    d = _refresh(unified)
                    _token_cache[label] = {"token": d["access_token"],
                                           "exp": time.time() + d.get("expires_in", 3600)}
                    got, scopes = token_email(d["access_token"])
                    st["email"], st["scopes"] = got, scopes
                    if got == email:
                        st["verified"] = True
                    else:
                        ok = False
                        st["note"] = (f"BLOQUEADA: el token pertenece a '{got or 'desconocido'}', "
                                      f"no a {email}.")
                except Exception as e:  # sin red: no se bloquea, se reintenta en whoami
                    st["note"] = f"No se pudo verificar ahora ({e}). Se reintentará."
            if ok:
                for p in MODULE_PREFIXES.values():
                    os.environ[p + label.upper()] = unified
            else:
                for p in ALL_PREFIXES:
                    os.environ[p + label.upper()] = ""
                os.environ["GOOGLE_ADS_LOGIN_CUSTOMER_ID_" + label.upper()] = ""
        elif legacy:
            st["source"] = "tokens antiguos por servicio (" + ", ".join(
                n for n, p in MODULE_PREFIXES.items() if p in legacy) + ")"
            st["note"] = ("Funciona solo en esos servicios. Para tenerlo TODO (YouTube, Business "
                          f"Profile, Sheets, Cloud...) ejecuta: python3 get_refresh_token.py {label}")
        else:
            st["note"] = f"Sin conectar. Ejecuta: python3 get_refresh_token.py {label}"
        STATUS[label] = st
    return STATUS


def active_labels():
    return [l for l in ALLOWED if os.environ.get(UNIFIED_PREFIX + l.upper(), "").strip()]


def default_label():
    labs = active_labels()
    if not labs:
        raise AccountError("No hay ninguna cuenta con token unificado. Ejecuta: "
                           "python3 get_refresh_token.py bryan  (y luego academy)")
    return "bryan" if "bryan" in labs else labs[0]


def resolve(account=None):
    label = (account or default_label()).lower().strip()
    # se aceptan también los emails
    for l, e in ALLOWED.items():
        if label == e:
            label = l
    if label not in ALLOWED:
        raise AccountError(f"Cuenta '{account}' NO permitida. Este MCP solo usa: "
                           + ", ".join(f"{l} ({e})" for l, e in ALLOWED.items()))
    if label not in active_labels():
        raise AccountError(f"La cuenta '{label}' no tiene token unificado válido. "
                           f"Ejecuta: python3 get_refresh_token.py {label}")
    return label


def access_token(account=None):
    label = resolve(account)
    c = _token_cache.get(label)
    if c and time.time() < c["exp"] - 60:
        return c["token"]
    d = _refresh(os.environ[UNIFIED_PREFIX + label.upper()])
    st = STATUS.get(label, {})
    if not st.get("verified"):
        got, scopes = token_email(d["access_token"])
        if got != ALLOWED[label]:
            for p in ALL_PREFIXES:
                os.environ[p + label.upper()] = ""
            raise AccountError(f"Token de '{label}' pertenece a '{got}', no a {ALLOWED[label]}. Bloqueado.")
        st.update(email=got, scopes=scopes, verified=True, note="")
    _token_cache[label] = {"token": d["access_token"], "exp": time.time() + d.get("expires_in", 3600)}
    return d["access_token"]


def whoami():
    out = {}
    for label in ALLOWED:
        st = dict(STATUS.get(label, {}))
        if label in active_labels():
            try:
                access_token(label)
                st = dict(STATUS.get(label, {}))
            except Exception as e:
                st["note"] = str(e)
        st["n_scopes"] = len(st.get("scopes") or [])
        out[label] = st
    return out
