# Instalador del MCP de Google UNIFICADO para Windows (un solo servidor "google").
# Uso: doble clic en install.bat  (o en PowerShell:  powershell -ExecutionPolicy Bypass -File install.ps1)
$ErrorActionPreference = "Continue"
$HERE = Split-Path -Parent $MyInvocation.MyCommand.Path
$DEST = Join-Path $env:USERPROFILE "google-mcp"

Write-Host "== 1/5 Python"
$PY = $null
foreach ($cand in @("py -3", "python", "python3")) {
    try {
        $parts = $cand.Split(" ")
        $exe = & $parts[0] ($parts | Select-Object -Skip 1) -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $exe -and (Test-Path $exe.Trim())) { $PY = $exe.Trim(); break }
    } catch { }
}
if (-not $PY) {
    Write-Host "[X] No hay Python 3. Instalalo desde https://www.python.org/downloads/windows/"
    Write-Host "    (marca 'Add python.exe to PATH' durante la instalacion) y vuelve a ejecutar."
    Read-Host "Pulsa Enter para salir"; exit 1
}
Write-Host "    usando $PY ($(& $PY --version 2>&1))"

Write-Host "== 2/5 Dependencias (requests, python-dotenv)"
& $PY -m pip install --user -q requests python-dotenv
& $PY -c "import requests, dotenv"
if ($LASTEXITCODE -ne 0) { Write-Host "[X] No se pudieron instalar las dependencias"; exit 1 }
Write-Host "    ok"

Write-Host "== 3/5 Copiando a $DEST"
$OLDENV = $null
if ((Resolve-Path $HERE).Path -ne $DEST) {
    if (Test-Path $DEST) {
        $BAK = "$DEST.bak-$(Get-Date -Format yyyyMMddHHmmss)"
        Copy-Item $DEST $BAK -Recurse
        if (Test-Path (Join-Path $BAK ".env")) { $OLDENV = Join-Path $BAK ".env" }
        Remove-Item $DEST -Recurse -Force
        Write-Host "    ya existia -> copia de seguridad en $BAK"
    }
    Copy-Item $HERE $DEST -Recurse
} else { Write-Host "    ya estas en $DEST, no se copia nada" }
$ENVF = Join-Path $DEST ".env"
if (-not (Test-Path $ENVF)) { Copy-Item (Join-Path $DEST ".env.example") $ENVF }

$tmp = Join-Path $env:TEMP "google-mcp-setup.py"
@'
import json, os, re, sys, shutil, datetime
home, py, dest, oldenv = (sys.argv[1:] + ["", "", "", ""])[:4]
# conserva los tokens unificados de la instalacion anterior
if oldenv and os.path.exists(oldenv):
    ov = dict(re.findall(r"^([A-Z0-9_]+)=(.+)$", open(oldenv, encoding="utf-8").read(), flags=re.M))
    p = os.path.join(dest, ".env"); txt = open(p, encoding="utf-8").read()
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
    open(p, "w", encoding="utf-8", newline="\n").write(txt)
    print("    tokens de la instalacion anterior conservados")
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
servers["google"] = {"type": "stdio", "command": py, "args": [os.path.join(dest, "server.py")],
                     "env": {"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}}
with open(cfg, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
print("    registrado: google ->", cfg)
'@ | Set-Content -Path $tmp -Encoding UTF8

Write-Host "== 4/5 Registrando el MCP 'google' en $env:USERPROFILE\.claude.json (y quitando los 6 antiguos)"
if ($OLDENV) { & $PY $tmp $env:USERPROFILE $PY $DEST $OLDENV } else { & $PY $tmp $env:USERPROFILE $PY $DEST }
Remove-Item $tmp

# .env solo legible por tu usuario
try { icacls $ENVF /inheritance:r /grant:r "$($env:USERNAME):(M)" | Out-Null } catch { }

Write-Host "== 5/5 Conectar cuentas (un login por cuenta = TODOS los servicios de Google)"
Set-Location $DEST
$labels = (& $PY -c "import sys; sys.path.insert(0, '.'); from core import accounts; accounts.bootstrap(verify=False); print(' '.join(accounts.ALLOWED))").Split(" ")
foreach ($acc in $labels) {
    $key = "GOOGLE_REFRESH_TOKEN_" + $acc.ToUpper()
    if (Select-String -Path $ENVF -Pattern "^$key=." -Quiet) {
        Write-Host "    $acc ya conectada (para renovarla: cd $DEST ; python get_refresh_token.py $acc)"
    } else {
        $ans = Read-Host "    Conectar ahora '$acc'? Se abrira el navegador [S/n]"
        if ($ans -eq "" -or $ans -match "^[sSyY]") {
            & $PY get_refresh_token.py $acc
            if ($LASTEXITCODE -ne 0) { Write-Host "    [!] $acc no se conecto; repitelo luego." }
        }
    }
}

Write-Host ""
Write-Host "== Comprobacion"
$req = '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' + "`n" + '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'
$out = $req | & $PY (Join-Path $DEST "server.py") 2>$null | Out-String
$n = ([regex]::Matches($out, '"inputSchema"')).Count
Write-Host "    google -> $n herramientas"
Write-Host ""
Write-Host "LISTO. Reinicia Claude. En Claude pide: 'usa google_whoami' para ver las cuentas conectadas."
Read-Host "Pulsa Enter para cerrar"
