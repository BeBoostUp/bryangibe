#!/bin/bash
# Instalador del MCP de Google UNIFICADO (un solo servidor "google").
# Uso: cd a la carpeta descomprimida y ejecuta:  bash install.sh
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/google-mcp"

echo "== 1/5 Python"
PY="$(command -v python3 || true)"
if [ -z "$PY" ]; then echo "[X] No hay python3. Instala Xcode Command Line Tools:  xcode-select --install"; exit 1; fi
echo "    usando $PY ($($PY --version 2>&1))"

echo "== 2/5 Dependencias (requests, python-dotenv)"
"$PY" -m pip install --user -q requests python-dotenv 2>/dev/null || "$PY" -m pip install --user -q --break-system-packages requests python-dotenv
"$PY" -c "import requests, dotenv" && echo "    ok"

echo "== 3/5 Copiando a $DEST"
if [ "$HERE" = "$DEST" ]; then
  echo "    ya estas en $DEST, no se copia nada"
else
  OLDENV=""
  if [ -d "$DEST" ]; then
    BAK="$DEST.bak-$(date +%Y%m%d%H%M%S)"
    cp -a "$DEST" "$BAK"
    [ -f "$BAK/.env" ] && OLDENV="$BAK/.env"
    echo "    ya existia -> copia de seguridad en $BAK"
  fi
  rm -rf "$DEST"; cp -a "$HERE" "$DEST"
  [ -f "$DEST/.env" ] || cp "$DEST/.env.example" "$DEST/.env"
  # conserva los tokens unificados ya generados en la instalacion anterior
  if [ -n "$OLDENV" ]; then
    "$PY" - "$OLDENV" "$DEST/.env" <<'PY'
import re, sys
old, new = sys.argv[1], sys.argv[2]
ov = dict(re.findall(r"^([A-Z0-9_]+)=(.+)$", open(old).read(), flags=re.M))
txt = open(new).read()
if ov.get("GOOGLE_MCP_ACCOUNTS") and "GOOGLE_MCP_ACCOUNTS=" in txt:  # une las cuentas de antes con las del paquete
    m = re.search(r"^GOOGLE_MCP_ACCOUNTS=(.*)$", txt, flags=re.M)
    cur = [x for x in (m.group(1) if m else "").split(",") if x]
    merged = ",".join(cur + [x for x in ov["GOOGLE_MCP_ACCOUNTS"].split(",") if x and x.split("=")[0] not in [c.split("=")[0] for c in cur]])
    txt = re.sub(r"^GOOGLE_MCP_ACCOUNTS=.*$", "GOOGLE_MCP_ACCOUNTS=" + merged, txt, flags=re.M) if m else txt + "\nGOOGLE_MCP_ACCOUNTS=" + merged + "\n"
for k, v in ov.items():
    if k.startswith(("GOOGLE_REFRESH_TOKEN_", "GOOGLE_ADS_LOGIN_CUSTOMER_ID_", "GOOGLE_API_KEY")):
        if re.search(rf"^{k}=$", txt, flags=re.M):
            txt = re.sub(rf"^{k}=$", f"{k}={v}", txt, flags=re.M)
        elif not re.search(rf"^{k}=", txt, flags=re.M):
            txt += f"\n{k}={v}\n"
open(new, "w").write(txt)
print("    tokens de la instalacion anterior conservados")
PY
  fi
fi
chmod 600 "$DEST/.env"

echo "== 4/5 Registrando el MCP 'google' en ~/.claude.json (y quitando los 6 antiguos)"
"$PY" - "$HOME" "$PY" "$DEST" <<'PY'
import json, os, sys, shutil, datetime
home, py, dest = sys.argv[1:4]
cfg = os.path.join(home, ".claude.json")
data = {}
if os.path.exists(cfg):
    shutil.copy(cfg, cfg + ".bak-" + datetime.datetime.now().strftime("%Y%m%d%H%M%S"))
    with open(cfg, encoding="utf-8") as f:
        data = json.load(f)
servers = data.setdefault("mcpServers", {})
import re as _re
_envtxt = open(os.path.join(dest, ".env"), encoding="utf-8").read() if os.path.exists(os.path.join(dest, ".env")) else ""
if _re.search(r"^GOOGLE_MCP_OPEN=1", _envtxt, flags=_re.M):
    print("    modo 'todas las cuentas': los MCP antiguos se CONSERVAN (no se quita ningun acceso)")
else:
    for old in ("googleads", "searchconsole", "tagmanager", "ga4", "merchantcenter", "gmail", "workspace"):
        if servers.pop(old, None) is not None:
            print("    quitado antiguo:", old)
servers["google"] = {"type": "stdio", "command": py, "args": [os.path.join(dest, "server.py")], "env": {}}
with open(cfg, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
print("    registrado: google")
PY

echo "== 5/5 Conectar cuentas (un login por cuenta = TODOS los servicios de Google)"
cd "$DEST"
for acc in $("$PY" -c "import sys; sys.path.insert(0, '.'); from core import accounts; accounts.bootstrap(verify=False); print(' '.join(accounts.ALLOWED))"); do
  if grep -q "^GOOGLE_REFRESH_TOKEN_$(echo $acc | tr a-z A-Z)=." .env; then
    echo "    $acc ya conectada (para renovarla: cd ~/google-mcp && python3 get_refresh_token.py $acc)"
  else
    read -r -p "    ¿Conectar ahora '$acc'? Se abrira el navegador [S/n] " ans
    if [ -z "$ans" ] || [[ "$ans" =~ ^[sSyY] ]]; then "$PY" get_refresh_token.py "$acc" || echo "    [!] $acc no se conecto; repitelo luego."; fi
  fi
done

echo
echo "== Comprobacion"
n=$(printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' | "$PY" "$DEST/server.py" 2>/dev/null | grep -o '"inputSchema"' | wc -l | tr -d ' ')
echo "    google -> $n herramientas"
echo
echo "LISTO. Reinicia Claude. En Claude pide: 'usa google_whoami' para ver las cuentas conectadas."
