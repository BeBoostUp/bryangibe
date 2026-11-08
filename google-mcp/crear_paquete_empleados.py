"""
Crea el zip del MCP de Google para tus EMPLEADOS: ya conectado a bryan@bryangibe.com y
academy@bryangibe.com, sin que ellos tengan que iniciar sesión ni conocer tus contraseñas.

Lo ejecutas TÚ, una vez, en tu ordenador:
    cd ~/google-mcp && python3 crear_paquete_empleados.py

Qué hace:
  1. Te pregunta qué servicios personales quieres DEJAR FUERA (Gmail, Drive, Docs/Sheets,
     Calendar). Lo que dejes fuera no se pide a Google: los tokens del paquete no tienen
     ese permiso, así que nadie puede leer tu correo con ellos aunque lo intente.
  2. Abre el navegador dos veces: inicias sesión con bryan@ y con academy@. Se crean
     tokens NUEVOS solo para el paquete (no se tocan los tuyos ni tu .env).
  3. Deja el zip en tu Escritorio. Tus empleados lo descomprimen y ejecutan
     install.sh (Mac) o install.bat (Windows). Sin login.

Para cortarles el acceso:  python3 revocar_paquete_empleados.py <zip del paquete>
"""
import datetime
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

CODE = ["core", "gads", "ga4", "gtm", "mc", "gsc", "ws", "server.py", "get_refresh_token.py",
        "install.sh", "install.ps1", "install.bat", "conectar-bryan.bat", "conectar-academy.bat", "requirements.txt", ".env.example", ".gitignore",
        "LEEME.md"]
# Lo único que se copia de tu .env (configuración, no tokens)
KEEP = ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_ADS_API_VERSION", "GOOGLE_ADS_DEVELOPER_TOKEN",
        "GOOGLE_ADS_CUSTOMER_ID", "GOOGLE_API_KEY"]
QUESTIONS = [
    ("gmail", "Gmail (leer y enviar correos de bryan@ / academy@)"),
    ("drive", "Google Drive (todos los archivos)"),
    ("docs", "Docs, Sheets, Slides y Forms"),
    ("calendar", "Calendar, Tasks y Contactos"),
]


def ask(q, default_yes):
    d = "S/n" if default_yes else "s/N"
    a = input(f"  {q} [{d}] ").strip().lower()
    return default_yes if not a else a.startswith(("s", "y"))


def read_env(path):
    if not os.path.exists(path):
        return {}
    return dict(re.findall(r"^([A-Z0-9_]+)=(.*)$", open(path, encoding="utf-8").read(), flags=re.M))


def main():
    mine = read_env(os.path.join(ROOT, ".env"))
    if not mine.get("GOOGLE_CLIENT_ID"):
        print("[X] No encuentro GOOGLE_CLIENT_ID en tu .env. Ejecuta esto dentro de ~/google-mcp.")
        sys.exit(1)

    print("=" * 64)
    print("Paquete para empleados: cuentas bryan@bryangibe.com y academy@bryangibe.com")
    print("Siempre incluye Ads, GA4, Tag Manager, Search Console, Merchant, Business Profile,")
    print("YouTube, Looker Studio, Cloud/BigQuery, PageSpeed, etc.")
    print("\nServicios PERSONALES. ¿Quieres que tus empleados tengan acceso a...?")
    exclude = []
    for key, label in QUESTIONS:
        if not ask(label, default_yes=(key == "docs")):
            exclude.append(key)
    print("\n  Fuera del paquete:", ", ".join(exclude) or "nada")

    tmp = tempfile.mkdtemp(prefix="google-mcp-empleados-")
    pkg = os.path.join(tmp, "google-mcp")
    os.makedirs(pkg)
    for item in CODE:
        src = os.path.join(ROOT, item)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(pkg, item), ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        elif os.path.exists(src):
            shutil.copy2(src, os.path.join(pkg, item))

    # paquete CERRADO: solo bryan@ y academy@, sin preguntas al instalar
    with open(os.path.join(pkg, "LOCKED"), "w", encoding="utf-8") as f:
        f.write("Paquete cerrado: solo bryan@bryangibe.com y academy@bryangibe.com.\n")
    env_path = os.path.join(pkg, ".env")
    lines = ["# MCP de Google — paquete para empleados (" + datetime.date.today().isoformat() + ")",
             "# Contiene tokens de bryan@bryangibe.com y academy@bryangibe.com: no lo compartas fuera.",
             "# Solo admite esas dos cuentas. Servicios excluidos (sin permiso en el token):",
             "GOOGLE_MCP_EXCLUDE=" + ",".join(exclude), ""]
    lines += [f"{k}={mine.get(k, '')}" for k in KEEP]
    lines += ["GOOGLE_REFRESH_TOKEN_BRYAN=", "GOOGLE_REFRESH_TOKEN_ACADEMY=",
              "GOOGLE_ADS_LOGIN_CUSTOMER_ID_BRYAN=" + mine.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID_BRYAN", ""),
              "GOOGLE_ADS_LOGIN_CUSTOMER_ID_ACADEMY=" + mine.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID_ACADEMY", "")]
    with open(env_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")

    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("GOOGLE_", "GA4_", "GTM_", "MC_", "GSC_", "WS_"))}
    env["GOOGLE_MCP_ENV_PATH"] = env_path
    for acc in ("bryan", "academy"):
        print(f"\n== Inicia sesion con {acc}@bryangibe.com en el navegador que se abre")
        r = subprocess.run([sys.executable, os.path.join(ROOT, "get_refresh_token.py"), acc], env=env)
        if r.returncode != 0:
            print(f"[X] No se conecto {acc}. Paquete cancelado.")
            shutil.rmtree(tmp, ignore_errors=True)
            sys.exit(1)

    dest_dir = os.path.join(os.path.expanduser("~"), "Desktop")
    if not os.path.isdir(dest_dir):
        dest_dir = os.path.expanduser("~")
    name = os.path.join(dest_dir, "mcp-bryan-gibe-" + datetime.date.today().isoformat())
    os.rename(pkg, os.path.join(tmp, "mcp-bryan-gibe"))
    zip_path = shutil.make_archive(name, "zip", tmp, "mcp-bryan-gibe")
    shutil.rmtree(tmp, ignore_errors=True)
    print("\n" + "=" * 64)
    print("[OK] Paquete creado:", zip_path)
    print("     Tus empleados: descomprimir y ejecutar install.sh (Mac) o install.bat (Windows).")
    print("     No tienen que iniciar sesion.")
    print("     Para cortarles el acceso: python3 revocar_paquete_empleados.py \"" + zip_path + "\"")


if __name__ == "__main__":
    main()
