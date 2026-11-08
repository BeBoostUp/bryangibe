"""
Gmail COMPLETO (leer, buscar, responder, reenviar un mensaje, etiquetas,
borradores, adjuntos, papelera, ajustes: vacaciones, filtros de etiquetado,
firmas/alias, IMAP/POP/idioma) + Drive ampliado (descargar, mover, renombrar,
compartir, borrar).

Requiere scopes: https://mail.google.com/  gmail.settings.basic  drive
(regenera el token con: python3 get_refresh_token.py bryan)

Todo el binario (adjuntos, descargas) va por disco, nunca por el modelo.
"""
import base64
import mimetypes
import os
import re
from email.message import EmailMessage
from email.utils import parseaddr, getaddresses
from pathlib import Path

import requests
from ws import engine as ws

GMAIL = ws.GMAIL
DRIVE = ws.DRIVE
DOWNLOADS = os.path.expanduser("~/Downloads/gmail-adjuntos")


# ---------------------------------------------------------------- helpers
def _req(method, url, account=None, params=None, body=None, timeout=120, raw=False):
    r = requests.request(method.upper(), url, headers=ws._hdr(account), params=params,
                         json=body, timeout=timeout)
    if r.status_code >= 400:
        raise ws.WsError("HTTP %s %s: %s" % (r.status_code, url.replace(GMAIL, ""), r.text[:700]))
    if raw:
        return r
    return r.json() if r.content else {"ok": True}


def _b64d(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _hdrs(payload):
    return {h["name"].lower(): h["value"] for h in (payload or {}).get("headers", [])}


def _walk(part, out):
    """Recorre el árbol MIME: rellena out['text'], out['html'], out['attachments']."""
    mime = part.get("mimeType", "")
    body = part.get("body", {}) or {}
    fname = part.get("filename")
    if fname:
        out["attachments"].append({"filename": fname, "mimeType": mime,
                                   "size": body.get("size"), "attachmentId": body.get("attachmentId"),
                                   "partId": part.get("partId")})
    elif body.get("data"):
        txt = _b64d(body["data"]).decode("utf-8", "replace")
        if mime == "text/plain" and not out["text"]:
            out["text"] = txt
        elif mime == "text/html" and not out["html"]:
            out["html"] = txt
    for p in part.get("parts", []) or []:
        _walk(p, out)


def _parse(msg, max_chars=20000, include_html=False):
    payload = msg.get("payload", {}) or {}
    h = _hdrs(payload)
    out = {"text": "", "html": "", "attachments": []}
    _walk(payload, out)
    text = out["text"]
    if not text and out["html"]:
        text = re.sub(r"<(script|style).*?</\1>", "", out["html"], flags=re.S | re.I)
        text = re.sub(r"<br\s*/?>|</p>|</div>|</tr>", "\n", text, flags=re.I)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
    res = {"id": msg.get("id"), "threadId": msg.get("threadId"), "labelIds": msg.get("labelIds", []),
           "date": h.get("date"), "from": h.get("from"), "to": h.get("to"), "cc": h.get("cc"),
           "bcc": h.get("bcc"), "reply_to": h.get("reply-to"), "subject": h.get("subject"),
           "message_id_header": h.get("message-id"), "snippet": msg.get("snippet"),
           "internalDate": msg.get("internalDate"),
           "body_text": text[:max_chars] + ("...[truncado]" if len(text) > max_chars else ""),
           "attachments": out["attachments"]}
    if include_html:
        res["body_html"] = out["html"][:max_chars]
    return res


def _summary(msg):
    h = _hdrs(msg.get("payload", {}))
    return {"id": msg.get("id"), "threadId": msg.get("threadId"), "date": h.get("date"),
            "from": h.get("from"), "to": h.get("to"), "subject": h.get("subject"),
            "snippet": msg.get("snippet"), "labelIds": msg.get("labelIds", [])}


# ---------------------------------------------------------------- lectura
def get_profile(account=None):
    return _req("GET", GMAIL + "/profile", account)


def search_messages(q=None, label_ids=None, max_results=20, page_token=None,
                    include_spam_trash=False, account=None):
    """Busca con la sintaxis de Gmail (from:, to:, subject:, newer_than:7d, has:attachment, is:unread...)."""
    params = {"maxResults": min(int(max_results or 20), 100), "includeSpamTrash": include_spam_trash}
    if q:
        params["q"] = q
    if label_ids:
        params["labelIds"] = label_ids
    if page_token:
        params["pageToken"] = page_token
    d = _req("GET", GMAIL + "/messages", account, params)
    items = []
    for m in d.get("messages", []) or []:
        full = _req("GET", GMAIL + "/messages/" + m["id"], account,
                    {"format": "metadata", "metadataHeaders": ["From", "To", "Subject", "Date"]})
        items.append(_summary(full))
    return {"count": len(items), "nextPageToken": d.get("nextPageToken"),
            "resultSizeEstimate": d.get("resultSizeEstimate"), "messages": items}


def list_threads(q=None, label_ids=None, max_results=20, page_token=None, account=None):
    params = {"maxResults": min(int(max_results or 20), 100)}
    if q:
        params["q"] = q
    if label_ids:
        params["labelIds"] = label_ids
    if page_token:
        params["pageToken"] = page_token
    return _req("GET", GMAIL + "/threads", account, params)


def get_message(message_id, max_chars=20000, include_html=False, account=None):
    msg = _req("GET", GMAIL + "/messages/" + message_id, account, {"format": "full"})
    return _parse(msg, max_chars, include_html)


def get_thread(thread_id, max_chars=8000, account=None):
    t = _req("GET", GMAIL + "/threads/" + thread_id, account, {"format": "full"})
    return {"id": t.get("id"), "historyId": t.get("historyId"),
            "messages": [_parse(m, max_chars) for m in t.get("messages", [])]}


def save_attachment(message_id, attachment_id, filename, save_dir=None, account=None):
    """Descarga un adjunto a disco. Devuelve la ruta local."""
    d = _req("GET", GMAIL + "/messages/%s/attachments/%s" % (message_id, attachment_id), account)
    folder = Path(save_dir or DOWNLOADS).expanduser()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (filename or ("adjunto_" + attachment_id[:12]))
    path.write_bytes(_b64d(d["data"]))
    return {"ok": True, "path": str(path), "bytes": path.stat().st_size}


def save_all_attachments(message_id, save_dir=None, account=None):
    parsed = get_message(message_id, max_chars=10, account=account)
    saved = []
    for a in parsed["attachments"]:
        if a.get("attachmentId"):
            saved.append(save_attachment(message_id, a["attachmentId"], a["filename"], save_dir, account))
    return {"count": len(saved), "files": saved}


def save_raw_message(message_id, save_path=None, account=None):
    """Guarda el .eml completo en disco."""
    d = _req("GET", GMAIL + "/messages/" + message_id, account, {"format": "raw"})
    path = Path(save_path or os.path.join(DOWNLOADS, message_id + ".eml")).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_b64d(d["raw"]))
    return {"ok": True, "path": str(path)}


# ---------------------------------------------------------------- envío
def _build(to, subject, body, attachments=None, cc=None, bcc=None, html=None,
           headers=None, from_addr=None, attachment_bytes=None):
    msg = EmailMessage()
    if to:
        msg["To"] = ", ".join(to if isinstance(to, list) else [to])
    if cc:
        msg["Cc"] = ", ".join(cc if isinstance(cc, list) else [cc])
    if bcc:
        msg["Bcc"] = ", ".join(bcc if isinstance(bcc, list) else [bcc])
    if from_addr:
        msg["From"] = from_addr
    msg["Subject"] = subject or ""
    for k, v in (headers or {}).items():
        if v:
            msg[k] = v
    msg.set_content(body or "")
    if html:
        msg.add_alternative(html, subtype="html")
    for p in (attachments or []):
        path = Path(p).expanduser()
        if not path.is_file():
            raise ws.WsError("No existe el adjunto: %s" % path)
        mime, _ = mimetypes.guess_type(path.name)
        maj, _, minr = (mime or "application/octet-stream").partition("/")
        msg.add_attachment(path.read_bytes(), maintype=maj, subtype=minr or "octet-stream",
                           filename=path.name)
    for name, data, mime in (attachment_bytes or []):
        maj, _, minr = (mime or "application/octet-stream").partition("/")
        msg.add_attachment(data, maintype=maj, subtype=minr or "octet-stream", filename=name)
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


def send_message(to, subject, body, attachments=None, cc=None, bcc=None, html=None,
                 thread_id=None, in_reply_to=None, references=None, from_addr=None, account=None):
    """Envío completo: admite hilo (thread_id + in_reply_to), alias 'from' (sendAs) y adjuntos."""
    hdr = {"In-Reply-To": in_reply_to, "References": references or in_reply_to}
    raw = _build(to, subject, body, attachments, cc, bcc, html, hdr, from_addr)
    payload = {"raw": raw}
    if thread_id:
        payload["threadId"] = thread_id
    d = _req("POST", GMAIL + "/messages/send", account, body=payload)
    return {"ok": True, "id": d.get("id"), "threadId": d.get("threadId"), "to": to, "subject": subject}


def reply(message_id, body, html=None, attachments=None, reply_all=False, cc=None,
          bcc=None, quote_original=True, account=None):
    """Responde a un mensaje manteniendo el hilo (In-Reply-To / References / threadId)."""
    orig = _req("GET", GMAIL + "/messages/" + message_id, account, {"format": "full"})
    p = _parse(orig, 6000)
    me = get_profile(account).get("emailAddress", "").lower()
    to_addr = p["reply_to"] or p["from"]
    to = [to_addr]
    cc_list = list(cc or [])
    if reply_all:
        for _, addr in getaddresses([p.get("to") or "", p.get("cc") or ""]):
            if addr and addr.lower() != me and addr.lower() != parseaddr(to_addr)[1].lower():
                cc_list.append(addr)
    subj = p["subject"] or ""
    if not subj.lower().startswith("re:"):
        subj = "Re: " + subj
    text = body
    if quote_original and p["body_text"]:
        quoted = "\n".join("> " + l for l in p["body_text"].splitlines())
        text = "%s\n\nEl %s, %s escribió:\n%s" % (body, p["date"], p["from"], quoted)
    h = _hdrs(orig.get("payload", {}))
    refs = (h.get("references", "") + " " + (h.get("message-id") or "")).strip()
    return send_message(to, subj, text, attachments, cc_list or None, bcc, html,
                        thread_id=orig.get("threadId"), in_reply_to=h.get("message-id"),
                        references=refs, account=account)


def forward_message(message_id, to, body="", include_attachments=True, cc=None, account=None):
    """Reenvía UN mensaje concreto a alguien (texto citado + adjuntos originales). Acción puntual."""
    orig = _req("GET", GMAIL + "/messages/" + message_id, account, {"format": "full"})
    p = _parse(orig, 50000, include_html=True)
    subj = p["subject"] or ""
    if not subj.lower().startswith("fwd:") and not subj.lower().startswith("fw:"):
        subj = "Fwd: " + subj
    text = ("%s\n\n---------- Mensaje reenviado ----------\nDe: %s\nFecha: %s\nAsunto: %s\nPara: %s\n\n%s"
            % (body, p["from"], p["date"], p["subject"], p["to"], p["body_text"]))
    blobs = []
    if include_attachments:
        for a in p["attachments"]:
            if a.get("attachmentId"):
                d = _req("GET", GMAIL + "/messages/%s/attachments/%s" % (message_id, a["attachmentId"]), account)
                blobs.append((a["filename"], _b64d(d["data"]), a["mimeType"]))
    raw = _build(to, subj, text, None, cc, None, None, None, None, blobs)
    d = _req("POST", GMAIL + "/messages/send", account, body={"raw": raw})
    return {"ok": True, "id": d.get("id"), "threadId": d.get("threadId"), "to": to,
            "subject": subj, "adjuntos": [b[0] for b in blobs]}


# ---------------------------------------------------------------- borradores
def list_drafts(max_results=20, q=None, account=None):
    params = {"maxResults": max_results}
    if q:
        params["q"] = q
    d = _req("GET", GMAIL + "/drafts", account, params)
    out = []
    for dr in d.get("drafts", []) or []:
        full = _req("GET", GMAIL + "/drafts/" + dr["id"], account, {"format": "metadata"})
        s = _summary(full.get("message", {}))
        s["draftId"] = dr["id"]
        out.append(s)
    return {"count": len(out), "drafts": out, "nextPageToken": d.get("nextPageToken")}


def get_draft(draft_id, account=None):
    d = _req("GET", GMAIL + "/drafts/" + draft_id, account, {"format": "full"})
    r = _parse(d.get("message", {}))
    r["draftId"] = d.get("id")
    return r


def update_draft(draft_id, to, subject, body, attachments=None, cc=None, bcc=None, html=None,
                 thread_id=None, account=None):
    raw = _build(to, subject, body, attachments, cc, bcc, html)
    m = {"raw": raw}
    if thread_id:
        m["threadId"] = thread_id
    d = _req("PUT", GMAIL + "/drafts/" + draft_id, account, body={"message": m})
    return {"ok": True, "draftId": d.get("id")}


def delete_draft(draft_id, account=None):
    _req("DELETE", GMAIL + "/drafts/" + draft_id, account)
    return {"ok": True, "deleted": draft_id}


# ---------------------------------------------------------------- etiquetas / estado
def list_labels(account=None, compact=True):
    labels = _req("GET", GMAIL + "/labels", account).get("labels", [])
    if not compact:
        return labels
    return sorted([{"id": l["id"], "name": l["name"], "type": l.get("type")} for l in labels],
                  key=lambda x: (x["type"] != "system", x["name"].lower()))


def create_label(name, label_list_visibility="labelShow", message_list_visibility="show",
                 color=None, account=None):
    body = {"name": name, "labelListVisibility": label_list_visibility,
            "messageListVisibility": message_list_visibility}
    if color:
        body["color"] = color
    return _req("POST", GMAIL + "/labels", account, body=body)


def update_label(label_id, body, account=None):
    return _req("PATCH", GMAIL + "/labels/" + label_id, account, body=body)


def delete_label(label_id, account=None):
    _req("DELETE", GMAIL + "/labels/" + label_id, account)
    return {"ok": True, "deleted": label_id}


_SYSTEM = ("INBOX", "UNREAD", "STARRED", "IMPORTANT", "SPAM", "TRASH", "SENT", "DRAFT", "CHAT")


def _label_id(name_or_id, account=None):
    if name_or_id.startswith(("Label_", "CATEGORY_")):
        return name_or_id
    if name_or_id.upper() in _SYSTEM:
        return name_or_id.upper()
    for l in list_labels(account):
        if l["name"].lower() == name_or_id.lower():
            return l["id"]
    raise ws.WsError("Etiqueta no encontrada: %s" % name_or_id)


def modify_messages(message_ids, add_labels=None, remove_labels=None, account=None):
    """add/remove por nombre o id. Para >1 id usa batchModify."""
    ids = message_ids if isinstance(message_ids, list) else [message_ids]
    add = [_label_id(x, account) for x in (add_labels or [])]
    rem = [_label_id(x, account) for x in (remove_labels or [])]
    if len(ids) == 1:
        d = _req("POST", GMAIL + "/messages/%s/modify" % ids[0], account,
                 body={"addLabelIds": add, "removeLabelIds": rem})
        return {"ok": True, "id": d.get("id"), "labelIds": d.get("labelIds")}
    _req("POST", GMAIL + "/messages/batchModify", account,
         body={"ids": ids, "addLabelIds": add, "removeLabelIds": rem})
    return {"ok": True, "modified": len(ids)}


def modify_thread(thread_id, add_labels=None, remove_labels=None, account=None):
    add = [_label_id(x, account) for x in (add_labels or [])]
    rem = [_label_id(x, account) for x in (remove_labels or [])]
    d = _req("POST", GMAIL + "/threads/%s/modify" % thread_id, account,
             body={"addLabelIds": add, "removeLabelIds": rem})
    return {"ok": True, "id": d.get("id")}


def archive(message_ids, account=None):
    return modify_messages(message_ids, remove_labels=["INBOX"], account=account)


def mark_read(message_ids, read=True, account=None):
    if read:
        return modify_messages(message_ids, remove_labels=["UNREAD"], account=account)
    return modify_messages(message_ids, add_labels=["UNREAD"], account=account)


def star(message_ids, starred=True, account=None):
    if starred:
        return modify_messages(message_ids, add_labels=["STARRED"], account=account)
    return modify_messages(message_ids, remove_labels=["STARRED"], account=account)


def trash(message_id=None, thread_id=None, untrash=False, account=None):
    act = "untrash" if untrash else "trash"
    if thread_id:
        d = _req("POST", GMAIL + "/threads/%s/%s" % (thread_id, act), account)
    else:
        d = _req("POST", GMAIL + "/messages/%s/%s" % (message_id, act), account)
    return {"ok": True, "action": act, "id": d.get("id")}


def spam(message_id, is_spam=True, account=None):
    if is_spam:
        return modify_messages(message_id, add_labels=["SPAM"], remove_labels=["INBOX"], account=account)
    return modify_messages(message_id, add_labels=["INBOX"], remove_labels=["SPAM"], account=account)


# ---------------------------------------------------------------- ajustes
def get_vacation(account=None):
    return _req("GET", GMAIL + "/settings/vacation", account)


def set_vacation(enable, subject=None, body_plain=None, body_html=None, start_time_ms=None,
                 end_time_ms=None, contacts_only=False, domain_only=False, account=None):
    body = {"enableAutoReply": bool(enable), "restrictToContacts": contacts_only,
            "restrictToDomain": domain_only}
    if subject is not None:
        body["responseSubject"] = subject
    if body_plain is not None:
        body["responseBodyPlainText"] = body_plain
    if body_html is not None:
        body["responseBodyHtml"] = body_html
    if start_time_ms:
        body["startTime"] = str(start_time_ms)
    if end_time_ms:
        body["endTime"] = str(end_time_ms)
    return _req("PUT", GMAIL + "/settings/vacation", account, body=body)


def list_filters(account=None):
    return _req("GET", GMAIL + "/settings/filters", account).get("filter", [])


def create_label_filter(criteria, add_labels=None, remove_labels=None, account=None):
    """Filtro de ORGANIZACIÓN (etiquetar / archivar / marcar leído). criteria:
    {from, to, subject, query, negatedQuery, hasAttachment}."""
    action = {}
    if add_labels:
        action["addLabelIds"] = [_label_id(x, account) for x in add_labels]
    if remove_labels:
        action["removeLabelIds"] = [_label_id(x, account) for x in remove_labels]
    return _req("POST", GMAIL + "/settings/filters", account, body={"criteria": criteria, "action": action})


def delete_filter(filter_id, account=None):
    _req("DELETE", GMAIL + "/settings/filters/" + filter_id, account)
    return {"ok": True, "deleted": filter_id}


def list_send_as(account=None):
    return _req("GET", GMAIL + "/settings/sendAs", account).get("sendAs", [])


def update_signature(send_as_email, signature_html=None, display_name=None, is_default=None, account=None):
    """Firma / nombre visible / alias por defecto de una dirección de envío ya existente."""
    body = {}
    if signature_html is not None:
        body["signature"] = signature_html
    if display_name is not None:
        body["displayName"] = display_name
    if is_default is not None:
        body["isDefault"] = bool(is_default)
    return _req("PATCH", GMAIL + "/settings/sendAs/" + send_as_email, account, body=body)


def get_setting(kind, account=None):
    """kind: imap | pop | language | vacation"""
    return _req("GET", GMAIL + "/settings/" + kind, account)


def update_setting(kind, body, account=None):
    """kind: imap | pop | language"""
    if kind not in ("imap", "pop", "language"):
        raise ws.WsError("kind debe ser imap | pop | language")
    return _req("PUT", GMAIL + "/settings/" + kind, account, body=body)


def gmail_request(method, path, params=None, body=None, account=None):
    """Llamada cruda de lectura/escritura sobre mensajes, hilos, etiquetas y borradores.
    path relativo a /gmail/v1/users/me/, p.ej. 'messages', 'threads/{id}', 'labels'."""
    p = path.lstrip("/")
    if p.startswith("settings/") and method.upper() != "GET":
        raise ws.WsError("Los ajustes se cambian con las herramientas dedicadas (vacation, filtros, firma, imap/pop).")
    return _req(method, GMAIL + "/" + p, account, params, body)


# ---------------------------------------------------------------- Drive ampliado
def drive_get(file_id, account=None):
    return _req("GET", DRIVE + "/files/" + file_id, account,
                {"fields": "id,name,mimeType,size,modifiedTime,createdTime,parents,webViewLink,owners,shared,trashed",
                 "supportsAllDrives": True})


def drive_search(q, page_size=50, page_token=None, order_by=None, account=None):
    """q en sintaxis de Drive: name contains 'x' and mimeType='application/pdf' and trashed=false"""
    params = {"q": q, "pageSize": page_size, "supportsAllDrives": True, "includeItemsFromAllDrives": True,
              "fields": "nextPageToken,files(id,name,mimeType,size,modifiedTime,parents,webViewLink)"}
    if page_token:
        params["pageToken"] = page_token
    if order_by:
        params["orderBy"] = order_by
    return _req("GET", DRIVE + "/files", account, params)


_EXPORT = {"application/vnd.google-apps.document": ("application/pdf", ".pdf"),
           "application/vnd.google-apps.spreadsheet": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"),
           "application/vnd.google-apps.presentation": ("application/pdf", ".pdf"),
           "application/vnd.google-apps.drawing": ("image/png", ".png")}


def drive_download(file_id, save_path=None, export_mime=None, account=None):
    """Descarga a disco. Los Google Docs/Sheets/Slides se exportan (por defecto pdf/xlsx/pdf)."""
    meta = drive_get(file_id, account)
    mime = meta.get("mimeType", "")
    name = meta.get("name", file_id)
    if mime.startswith("application/vnd.google-apps."):
        exp, ext = _EXPORT.get(mime, ("application/pdf", ".pdf"))
        exp = export_mime or exp
        r = _req("GET", DRIVE + "/files/%s/export" % file_id, account, {"mimeType": exp}, raw=True, timeout=300)
        if not save_path:
            name = name + (ext if not name.endswith(ext) else "")
    else:
        r = _req("GET", DRIVE + "/files/" + file_id, account, {"alt": "media", "supportsAllDrives": True},
                 raw=True, timeout=300)
    path = Path(save_path or os.path.join(DOWNLOADS, name)).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(r.content)
    return {"ok": True, "path": str(path), "bytes": len(r.content), "mimeType": mime}


def drive_update(file_id, name=None, description=None, add_parents=None, remove_parents=None,
                 starred=None, trashed=None, account=None):
    body = {}
    if name is not None:
        body["name"] = name
    if description is not None:
        body["description"] = description
    if starred is not None:
        body["starred"] = starred
    if trashed is not None:
        body["trashed"] = trashed
    params = {"supportsAllDrives": True, "fields": "id,name,parents,trashed,starred"}
    if add_parents:
        params["addParents"] = add_parents
    if remove_parents:
        params["removeParents"] = remove_parents
    return _req("PATCH", DRIVE + "/files/" + file_id, account, params, body)


def drive_move(file_id, new_parent_id, account=None):
    meta = drive_get(file_id, account)
    return drive_update(file_id, add_parents=new_parent_id,
                        remove_parents=",".join(meta.get("parents", [])), account=account)


def drive_copy(file_id, name=None, parent_id=None, account=None):
    body = {}
    if name:
        body["name"] = name
    if parent_id:
        body["parents"] = [parent_id]
    return _req("POST", DRIVE + "/files/%s/copy" % file_id, account, {"supportsAllDrives": True}, body)


def drive_trash(file_id, restore=False, account=None):
    return drive_update(file_id, trashed=(not restore), account=account)


def drive_share(file_id, email=None, role="reader", perm_type="user", notify=True, message=None, account=None):
    """role: reader|commenter|writer. perm_type: user|group|anyone."""
    if role not in ("reader", "commenter", "writer"):
        raise ws.WsError("role debe ser reader | commenter | writer")
    body = {"role": role, "type": perm_type}
    if email:
        body["emailAddress"] = email
    params = {"supportsAllDrives": True, "sendNotificationEmail": notify}
    if message:
        params["emailMessage"] = message
    return _req("POST", DRIVE + "/files/%s/permissions" % file_id, account, params, body)


def drive_list_permissions(file_id, account=None):
    return _req("GET", DRIVE + "/files/%s/permissions" % file_id, account,
                {"supportsAllDrives": True, "fields": "permissions(id,type,role,emailAddress,domain,displayName)"}).get("permissions", [])


def drive_delete_permission(file_id, permission_id, account=None):
    _req("DELETE", DRIVE + "/files/%s/permissions/%s" % (file_id, permission_id), account, {"supportsAllDrives": True})
    return {"ok": True, "removed": permission_id}


def drive_request(method, path, params=None, body=None, account=None):
    """Llamada cruda a Drive v3 (archivos, carpetas, unidades compartidas, cambios, comentarios)."""
    return _req(method, DRIVE + "/" + path.lstrip("/"), account, params, body)


# ---------------------------------------------------------------- MCP tools
_A = {"account": {"type": "string", "description": "Etiqueta de cuenta (opcional, por defecto 'bryan')."}}
_S = {"type": "string"}
_B = {"type": "boolean"}
_I = {"type": "integer"}
_O = {"type": "object"}
_LS = {"type": "array", "items": {"type": "string"}}


def _t(name, desc, props=None, req=None):
    p = dict(props or {})
    p.update(_A)
    return {"name": name, "description": desc,
            "inputSchema": {"type": "object", "properties": p, "required": req or []}}


TOOLS = [
    _t("gmail_profile", "Perfil de la cuenta: email, nº mensajes/hilos, historyId."),
    _t("gmail_search", ("Busca correos con la sintaxis de Gmail (from:, to:, subject:, newer_than:7d, "
                        "has:attachment, is:unread, label:X, after:2026/09/01...). Devuelve resumen por mensaje."),
       {"q": _S, "label_ids": _LS, "max_results": _I, "page_token": _S, "include_spam_trash": _B}),
    _t("gmail_list_threads", "Lista hilos (ids + snippet) con filtro q/labels.",
       {"q": _S, "label_ids": _LS, "max_results": _I, "page_token": _S}),
    _t("gmail_get_message", "Lee un correo completo: cabeceras, cuerpo en texto, lista de adjuntos.",
       {"message_id": _S, "max_chars": _I, "include_html": _B}, ["message_id"]),
    _t("gmail_get_thread", "Lee un hilo completo (todos sus mensajes parseados).",
       {"thread_id": _S, "max_chars": _I}, ["thread_id"]),
    _t("gmail_save_attachment", "Descarga UN adjunto a disco (por attachmentId de gmail_get_message).",
       {"message_id": _S, "attachment_id": _S, "filename": _S, "save_dir": _S}, ["message_id", "attachment_id"]),
    _t("gmail_save_all_attachments", "Descarga TODOS los adjuntos de un mensaje a disco (~/Downloads/gmail-adjuntos por defecto).",
       {"message_id": _S, "save_dir": _S}, ["message_id"]),
    _t("gmail_save_raw", "Guarda el .eml completo de un mensaje en disco.",
       {"message_id": _S, "save_path": _S}, ["message_id"]),
    _t("gmail_send", ("ENVÍA DE VERDAD un correo. Admite adjuntos (rutas locales), HTML, hilo (thread_id + in_reply_to) "
                      "y alias remitente (from_addr de gmail_list_send_as). Usar solo con confirmación explícita."),
       {"to": _LS, "subject": _S, "body": _S, "html": _S, "attachments": _LS, "cc": _LS, "bcc": _LS,
        "thread_id": _S, "in_reply_to": _S, "references": _S, "from_addr": _S}, ["to", "subject", "body"]),
    _t("gmail_reply", ("ENVÍA DE VERDAD una respuesta en el mismo hilo (cita el original). reply_all responde a todos. "
                       "Usar solo con confirmación explícita."),
       {"message_id": _S, "body": _S, "html": _S, "attachments": _LS, "reply_all": _B, "cc": _LS, "bcc": _LS,
        "quote_original": _B}, ["message_id", "body"]),
    _t("gmail_forward_message", "ENVÍA DE VERDAD un correo concreto a otra persona (texto original + adjuntos). Solo con confirmación explícita.",
       {"message_id": _S, "to": _LS, "body": _S, "include_attachments": _B, "cc": _LS}, ["message_id", "to"]),
    _t("gmail_list_drafts", "Lista borradores con resumen.", {"max_results": _I, "q": _S}),
    _t("gmail_get_draft", "Lee un borrador completo.", {"draft_id": _S}, ["draft_id"]),
    _t("gmail_update_draft", "Reemplaza el contenido de un borrador.",
       {"draft_id": _S, "to": _LS, "subject": _S, "body": _S, "html": _S, "attachments": _LS, "cc": _LS,
        "bcc": _LS, "thread_id": _S}, ["draft_id", "to", "subject", "body"]),
    _t("gmail_delete_draft", "Borra un borrador.", {"draft_id": _S}, ["draft_id"]),
    _t("gmail_list_labels", "Lista etiquetas (sistema y personalizadas) con ids. compact=false devuelve todos los campos.", {"compact": _B}),
    _t("gmail_create_label", "Crea una etiqueta. Anidada: 'Clientes/Nexor'. color: {backgroundColor, textColor} (paleta Gmail).",
       {"name": _S, "label_list_visibility": _S, "message_list_visibility": _S, "color": _O}, ["name"]),
    _t("gmail_update_label", "Modifica una etiqueta (name, color, visibilidad).", {"label_id": _S, "body": _O}, ["label_id", "body"]),
    _t("gmail_delete_label", "Borra una etiqueta (los correos no se borran).", {"label_id": _S}, ["label_id"]),
    _t("gmail_modify_messages", ("Añade/quita etiquetas a uno o varios mensajes (por nombre o id; INBOX, UNREAD, STARRED, "
                                 "SPAM, IMPORTANT o etiquetas propias)."),
       {"message_ids": _LS, "add_labels": _LS, "remove_labels": _LS}, ["message_ids"]),
    _t("gmail_modify_thread", "Añade/quita etiquetas a un hilo entero.",
       {"thread_id": _S, "add_labels": _LS, "remove_labels": _LS}, ["thread_id"]),
    _t("gmail_archive", "Archiva mensajes (quita INBOX).", {"message_ids": _LS}, ["message_ids"]),
    _t("gmail_mark_read", "Marca leído (read=true) o no leído (read=false).", {"message_ids": _LS, "read": _B}, ["message_ids"]),
    _t("gmail_star", "Destaca (starred=true) o quita destacado.", {"message_ids": _LS, "starred": _B}, ["message_ids"]),
    _t("gmail_spam", "Marca como spam (is_spam=true) o lo saca de spam.", {"message_id": _S, "is_spam": _B}, ["message_id"]),
    _t("gmail_trash", "Envía a la papelera un mensaje o un hilo (untrash=true lo recupera). Nada se borra definitivamente.",
       {"message_id": _S, "thread_id": _S, "untrash": _B}),
    _t("gmail_get_vacation", "Respuesta automática (vacaciones) actual."),
    _t("gmail_set_vacation", "Configura la respuesta automática. Tiempos en epoch ms.",
       {"enable": _B, "subject": _S, "body_plain": _S, "body_html": _S, "start_time_ms": _I, "end_time_ms": _I,
        "contacts_only": _B, "domain_only": _B}, ["enable"]),
    _t("gmail_list_filters", "Lista filtros de la cuenta."),
    _t("gmail_create_label_filter", ("Crea un filtro de ORGANIZACIÓN: criteria {from,to,subject,query,negatedQuery,hasAttachment}; "
                                     "add_labels/remove_labels por nombre o id (remove ['INBOX'] = archivar, ['UNREAD'] = marcar leído)."),
       {"criteria": _O, "add_labels": _LS, "remove_labels": _LS}, ["criteria"]),
    _t("gmail_delete_filter", "Borra un filtro.", {"filter_id": _S}, ["filter_id"]),
    _t("gmail_list_send_as", "Direcciones de envío (alias) con sus firmas."),
    _t("gmail_update_signature", "Cambia la firma (HTML), el nombre visible o el alias por defecto de una dirección de envío existente.",
       {"send_as_email": _S, "signature_html": _S, "display_name": _S, "is_default": _B}, ["send_as_email"]),
    _t("gmail_get_setting", "Lee ajustes: kind = imap | pop | language | vacation.", {"kind": _S}, ["kind"]),
    _t("gmail_update_setting", "Escribe ajustes: kind = imap | pop | language (body según API).", {"kind": _S, "body": _O}, ["kind", "body"]),
    _t("gmail_request", ("Llamada cruda a Gmail API sobre mensajes/hilos/etiquetas/borradores. path relativo a "
                         "/gmail/v1/users/me/, p.ej. 'messages', 'threads/{id}', 'history'."),
       {"method": _S, "path": _S, "params": _O, "body": _O}, ["method", "path"]),
    _t("drive_get", "Metadatos de un archivo/carpeta de Drive.", {"file_id": _S}, ["file_id"]),
    _t("drive_search", "Busca en Drive con la sintaxis q (name contains 'x' and mimeType='application/pdf').",
       {"q": _S, "page_size": _I, "page_token": _S, "order_by": _S}, ["q"]),
    _t("drive_download", "Descarga a disco (Docs/Sheets/Slides se exportan a pdf/xlsx/pdf o export_mime).",
       {"file_id": _S, "save_path": _S, "export_mime": _S}, ["file_id"]),
    _t("drive_update", "Renombra, describe, destaca o mueve (add/remove_parents) un archivo.",
       {"file_id": _S, "name": _S, "description": _S, "add_parents": _S, "remove_parents": _S, "starred": _B}, ["file_id"]),
    _t("drive_move", "Mueve un archivo a otra carpeta.", {"file_id": _S, "new_parent_id": _S}, ["file_id", "new_parent_id"]),
    _t("drive_copy", "Copia un archivo (opcional nuevo nombre/carpeta).", {"file_id": _S, "name": _S, "parent_id": _S}, ["file_id"]),
    _t("drive_trash", "Envía a la papelera de Drive (restore=true lo recupera).", {"file_id": _S, "restore": _B}, ["file_id"]),
    _t("drive_share", "Comparte un archivo: role reader|commenter|writer; perm_type user|group|anyone.",
       {"file_id": _S, "email": _S, "role": _S, "perm_type": _S, "notify": _B, "message": _S}, ["file_id"]),
    _t("drive_list_permissions", "Con quién está compartido un archivo.", {"file_id": _S}, ["file_id"]),
    _t("drive_delete_permission", "Deja de compartir con un permiso concreto.", {"file_id": _S, "permission_id": _S},
       ["file_id", "permission_id"]),
    _t("drive_request", "Llamada cruda a Drive v3 (path relativo a /drive/v3/, p.ej. 'files', 'drives', 'changes').",
       {"method": _S, "path": _S, "params": _O, "body": _O}, ["method", "path"]),
]


def _ac(a):
    return a.get("account")


HANDLERS = {
    "gmail_profile": lambda a: get_profile(_ac(a)),
    "gmail_search": lambda a: search_messages(a.get("q"), a.get("label_ids"), a.get("max_results", 20),
                                              a.get("page_token"), a.get("include_spam_trash", False), _ac(a)),
    "gmail_list_threads": lambda a: list_threads(a.get("q"), a.get("label_ids"), a.get("max_results", 20),
                                                 a.get("page_token"), _ac(a)),
    "gmail_get_message": lambda a: get_message(a["message_id"], a.get("max_chars", 20000), a.get("include_html", False), _ac(a)),
    "gmail_get_thread": lambda a: get_thread(a["thread_id"], a.get("max_chars", 8000), _ac(a)),
    "gmail_save_attachment": lambda a: save_attachment(a["message_id"], a["attachment_id"], a.get("filename"), a.get("save_dir"), _ac(a)),
    "gmail_save_all_attachments": lambda a: save_all_attachments(a["message_id"], a.get("save_dir"), _ac(a)),
    "gmail_save_raw": lambda a: save_raw_message(a["message_id"], a.get("save_path"), _ac(a)),
    "gmail_send": lambda a: send_message(a["to"], a["subject"], a["body"], a.get("attachments"), a.get("cc"), a.get("bcc"),
                                         a.get("html"), a.get("thread_id"), a.get("in_reply_to"), a.get("references"),
                                         a.get("from_addr"), _ac(a)),
    "gmail_reply": lambda a: reply(a["message_id"], a["body"], a.get("html"), a.get("attachments"), a.get("reply_all", False),
                                   a.get("cc"), a.get("bcc"), a.get("quote_original", True), _ac(a)),
    "gmail_forward_message": lambda a: forward_message(a["message_id"], a["to"], a.get("body", ""),
                                                       a.get("include_attachments", True), a.get("cc"), _ac(a)),
    "gmail_list_drafts": lambda a: list_drafts(a.get("max_results", 20), a.get("q"), _ac(a)),
    "gmail_get_draft": lambda a: get_draft(a["draft_id"], _ac(a)),
    "gmail_update_draft": lambda a: update_draft(a["draft_id"], a["to"], a["subject"], a["body"], a.get("attachments"),
                                                 a.get("cc"), a.get("bcc"), a.get("html"), a.get("thread_id"), _ac(a)),
    "gmail_delete_draft": lambda a: delete_draft(a["draft_id"], _ac(a)),
    "gmail_list_labels": lambda a: list_labels(_ac(a), a.get("compact", True)),
    "gmail_create_label": lambda a: create_label(a["name"], a.get("label_list_visibility", "labelShow"),
                                                 a.get("message_list_visibility", "show"), a.get("color"), _ac(a)),
    "gmail_update_label": lambda a: update_label(a["label_id"], a["body"], _ac(a)),
    "gmail_delete_label": lambda a: delete_label(a["label_id"], _ac(a)),
    "gmail_modify_messages": lambda a: modify_messages(a["message_ids"], a.get("add_labels"), a.get("remove_labels"), _ac(a)),
    "gmail_modify_thread": lambda a: modify_thread(a["thread_id"], a.get("add_labels"), a.get("remove_labels"), _ac(a)),
    "gmail_archive": lambda a: archive(a["message_ids"], _ac(a)),
    "gmail_mark_read": lambda a: mark_read(a["message_ids"], a.get("read", True), _ac(a)),
    "gmail_star": lambda a: star(a["message_ids"], a.get("starred", True), _ac(a)),
    "gmail_spam": lambda a: spam(a["message_id"], a.get("is_spam", True), _ac(a)),
    "gmail_trash": lambda a: trash(a.get("message_id"), a.get("thread_id"), a.get("untrash", False), _ac(a)),
    "gmail_get_vacation": lambda a: get_vacation(_ac(a)),
    "gmail_set_vacation": lambda a: set_vacation(a["enable"], a.get("subject"), a.get("body_plain"), a.get("body_html"),
                                                 a.get("start_time_ms"), a.get("end_time_ms"), a.get("contacts_only", False),
                                                 a.get("domain_only", False), _ac(a)),
    "gmail_list_filters": lambda a: list_filters(_ac(a)),
    "gmail_create_label_filter": lambda a: create_label_filter(a["criteria"], a.get("add_labels"), a.get("remove_labels"), _ac(a)),
    "gmail_delete_filter": lambda a: delete_filter(a["filter_id"], _ac(a)),
    "gmail_list_send_as": lambda a: list_send_as(_ac(a)),
    "gmail_update_signature": lambda a: update_signature(a["send_as_email"], a.get("signature_html"), a.get("display_name"),
                                                         a.get("is_default"), _ac(a)),
    "gmail_get_setting": lambda a: get_setting(a["kind"], _ac(a)),
    "gmail_update_setting": lambda a: update_setting(a["kind"], a["body"], _ac(a)),
    "gmail_request": lambda a: gmail_request(a["method"], a["path"], a.get("params"), a.get("body"), _ac(a)),
    "drive_get": lambda a: drive_get(a["file_id"], _ac(a)),
    "drive_search": lambda a: drive_search(a["q"], a.get("page_size", 50), a.get("page_token"), a.get("order_by"), _ac(a)),
    "drive_download": lambda a: drive_download(a["file_id"], a.get("save_path"), a.get("export_mime"), _ac(a)),
    "drive_update": lambda a: drive_update(a["file_id"], a.get("name"), a.get("description"), a.get("add_parents"),
                                           a.get("remove_parents"), a.get("starred"), None, _ac(a)),
    "drive_move": lambda a: drive_move(a["file_id"], a["new_parent_id"], _ac(a)),
    "drive_copy": lambda a: drive_copy(a["file_id"], a.get("name"), a.get("parent_id"), _ac(a)),
    "drive_trash": lambda a: drive_trash(a["file_id"], a.get("restore", False), _ac(a)),
    "drive_share": lambda a: drive_share(a["file_id"], a.get("email"), a.get("role", "reader"), a.get("perm_type", "user"),
                                         a.get("notify", True), a.get("message"), _ac(a)),
    "drive_list_permissions": lambda a: drive_list_permissions(a["file_id"], _ac(a)),
    "drive_delete_permission": lambda a: drive_delete_permission(a["file_id"], a["permission_id"], _ac(a)),
    "drive_request": lambda a: drive_request(a["method"], a["path"], a.get("params"), a.get("body"), _ac(a)),
}
