"""
Motor de Google Workspace para Bryan — Gmail (borradores + envio con adjuntos)
y Drive (subida de archivos y carpetas).

Reutiliza el MISMO cliente OAuth del proyecto gads-be-boost-up, con un refresh
token por cuenta en el .env:   WS_REFRESH_TOKEN_<ETIQUETA>=...

Clave del diseno: los adjuntos y las subidas se leen DEL DISCO. El contenido del
archivo nunca pasa por el modelo, asi que no hay riesgo de corromper un PDF.
"""
import os
import base64
import mimetypes
import time
from email.message import EmailMessage
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

CLIENT_ID = os.environ.get("WS_CLIENT_ID", "").strip()
CLIENT_SECRET = os.environ.get("WS_CLIENT_SECRET", "").strip()
_PREFIX = "WS_REFRESH_TOKEN_"

GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
DRIVE = "https://www.googleapis.com/drive/v3"
DRIVE_UP = "https://www.googleapis.com/upload/drive/v3/files"

_token_cache = {}


class WsError(Exception):
    pass


def _accounts():
    a = {k[len(_PREFIX):].lower(): v.strip()
         for k, v in os.environ.items() if k.startswith(_PREFIX) and v.strip()}
    if not a:
        raise WsError("No hay ninguna cuenta configurada. Genera un refresh token: "
                      "python3 get_refresh_token.py bryan")
    return a


def _pick(account=None):
    a = _accounts()
    if account:
        if account.lower() not in a:
            raise WsError("Cuenta '%s' no configurada. Disponibles: %s"
                          % (account, ", ".join(a)))
        return account.lower(), a[account.lower()]
    if "bryan" in a:
        return "bryan", a["bryan"]
    k = sorted(a)[0]
    return k, a[k]


def _token(account=None):
    label, refresh = _pick(account)
    c = _token_cache.get(label)
    if c and time.time() < c["exp"] - 60:
        return c["tok"]
    if not (CLIENT_ID and CLIENT_SECRET):
        raise WsError("Faltan WS_CLIENT_ID / WS_CLIENT_SECRET en el .env.")
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
        "refresh_token": refresh, "grant_type": "refresh_token"}, timeout=30)
    d = r.json()
    if "access_token" not in d:
        raise WsError("No se pudo refrescar el token de '%s': %s" % (label, d))
    _token_cache[label] = {"tok": d["access_token"],
                           "exp": time.time() + d.get("expires_in", 3600)}
    return d["access_token"]


def _hdr(account=None):
    return {"Authorization": "Bearer " + _token(account)}


def _check(r):
    if r.status_code >= 400:
        raise WsError("HTTP %s: %s" % (r.status_code, r.text[:600]))
    return r.json() if r.content else {}


# ---------------------------------------------------------------- Gmail
def _build(to, subject, body, attachments=None, cc=None, bcc=None, html=None):
    msg = EmailMessage()
    msg["To"] = ", ".join(to if isinstance(to, list) else [to])
    if cc:
        msg["Cc"] = ", ".join(cc if isinstance(cc, list) else [cc])
    if bcc:
        msg["Bcc"] = ", ".join(bcc if isinstance(bcc, list) else [bcc])
    msg["Subject"] = subject or ""
    msg.set_content(body or "")
    if html:
        msg.add_alternative(html, subtype="html")
    for p in (attachments or []):
        path = Path(p).expanduser()
        if not path.is_file():
            raise WsError("No existe el adjunto: %s" % path)
        mime, _ = mimetypes.guess_type(path.name)
        maj, _, minr = (mime or "application/octet-stream").partition("/")
        msg.add_attachment(path.read_bytes(), maintype=maj,
                           subtype=minr or "octet-stream", filename=path.name)
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


def send_email(to, subject, body, attachments=None, cc=None, bcc=None,
               html=None, account=None):
    """Envia un correo. `attachments` = rutas locales; se leen del disco."""
    raw = _build(to, subject, body, attachments, cc, bcc, html)
    r = requests.post(GMAIL + "/messages/send", headers=_hdr(account),
                      json={"raw": raw}, timeout=120)
    d = _check(r)
    return {"ok": True, "id": d.get("id"), "threadId": d.get("threadId"),
            "to": to, "subject": subject,
            "adjuntos": [Path(p).name for p in (attachments or [])]}


def create_draft(to, subject, body, attachments=None, cc=None, bcc=None,
                 html=None, account=None):
    raw = _build(to, subject, body, attachments, cc, bcc, html)
    r = requests.post(GMAIL + "/drafts", headers=_hdr(account),
                      json={"message": {"raw": raw}}, timeout=120)
    d = _check(r)
    return {"ok": True, "draftId": d.get("id"), "to": to, "subject": subject,
            "adjuntos": [Path(p).name for p in (attachments or [])]}


def send_draft(draft_id, account=None):
    r = requests.post(GMAIL + "/drafts/send", headers=_hdr(account),
                      json={"id": draft_id}, timeout=120)
    out = {"ok": True}
    out.update(_check(r))
    return out


# ---------------------------------------------------------------- Drive
def drive_list(parent_id=None, name_contains=None, page_size=100, account=None):
    q = ["trashed = false"]
    if parent_id:
        q.append("'%s' in parents" % parent_id)
    if name_contains:
        q.append("name contains '%s'" % name_contains)
    r = requests.get(DRIVE + "/files", headers=_hdr(account), timeout=60, params={
        "q": " and ".join(q), "pageSize": page_size,
        "fields": "files(id,name,mimeType,size,modifiedTime,parents)",
        "supportsAllDrives": True, "includeItemsFromAllDrives": True})
    return _check(r).get("files", [])


def drive_create_folder(name, parent_id=None, account=None):
    existing = [f for f in drive_list(parent_id, name, account=account)
                if f["name"] == name and f["mimeType"].endswith("folder")]
    if existing:
        return {"ok": True, "id": existing[0]["id"], "name": name, "ya_existia": True}
    meta = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        meta["parents"] = [parent_id]
    r = requests.post(DRIVE + "/files", headers=_hdr(account), json=meta,
                      params={"supportsAllDrives": True}, timeout=60)
    d = _check(r)
    return {"ok": True, "id": d.get("id"), "name": name, "ya_existia": False}


def drive_upload(local_path, parent_id=None, name=None, account=None, overwrite=True):
    """Sube un archivo local a Drive. Lee del disco: no pasa por el modelo."""
    import json as _json
    path = Path(local_path).expanduser()
    if not path.is_file():
        raise WsError("No existe el archivo: %s" % path)
    name = name or path.name
    mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
    data = path.read_bytes()

    if overwrite and parent_id:
        dup = [f for f in drive_list(parent_id, name, account=account) if f["name"] == name]
        if dup:
            r = requests.patch(DRIVE_UP + "/" + dup[0]["id"], headers=_hdr(account),
                               params={"uploadType": "media", "supportsAllDrives": True},
                               data=data, timeout=300)
            d = _check(r)
            return {"ok": True, "id": d.get("id"), "name": name,
                    "bytes": len(data), "accion": "reemplazado"}

    meta = {"name": name}
    if parent_id:
        meta["parents"] = [parent_id]
    b = "===bgb==="
    body = ("--%s\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n%s\r\n"
            "--%s\r\nContent-Type: %s\r\n\r\n" % (b, _json.dumps(meta), b, mime)).encode()
    body += data + ("\r\n--%s--" % b).encode()
    h = _hdr(account)
    h["Content-Type"] = "multipart/related; boundary=%s" % b
    r = requests.post(DRIVE_UP, headers=h, data=body, timeout=300,
                      params={"uploadType": "multipart", "supportsAllDrives": True})
    d = _check(r)
    return {"ok": True, "id": d.get("id"), "name": name,
            "bytes": len(data), "accion": "creado"}


def whoami(account=None):
    r = requests.get(DRIVE + "/about", headers=_hdr(account),
                     params={"fields": "user(displayName,emailAddress)"}, timeout=30)
    return _check(r)
