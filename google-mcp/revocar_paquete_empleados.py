"""
Corta el acceso de un paquete de empleados: revoca en Google sus tokens.

    python3 revocar_paquete_empleados.py ~/Desktop/mcp-google-empleados-2026-11-08.zip
    python3 revocar_paquete_empleados.py /ruta/a/google-mcp/.env

AVISO: Google puede revocar a la vez todos los tokens de esa cuenta para esta app,
incluidos los tuyos. Si después tu MCP da error de token, vuelve a conectarte con:
    python3 get_refresh_token.py bryan   (y/o academy)
"""
import re
import sys
import zipfile

import requests


def tokens_from(path):
    if path.endswith(".zip"):
        with zipfile.ZipFile(path) as z:
            name = next(n for n in z.namelist() if n.endswith("/.env") or n == ".env")
            text = z.read(name).decode("utf-8")
    else:
        text = open(path, encoding="utf-8").read()
    return re.findall(r"^(GOOGLE_REFRESH_TOKEN_[A-Z0-9_]+)=(.+)$", text, flags=re.M)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    toks = tokens_from(sys.argv[1])
    if not toks:
        print("[X] No hay tokens en ese paquete.")
        sys.exit(1)
    for key, tok in toks:
        r = requests.post("https://oauth2.googleapis.com/revoke", params={"token": tok.strip()}, timeout=30)
        print(f"  {key}: {'revocado' if r.status_code == 200 else 'ya no era valido / error ' + str(r.status_code)}")
    print("Listo. Ese paquete ya no tiene acceso.")


if __name__ == "__main__":
    main()
