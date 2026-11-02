"""Conexión inicial de TikTok (una sola vez, la dispara el responsable con tiktok-conectar.yml).
Recibe el código de autorización de OAuth (TIKTOK_CODIGO) y la URI de redirección registrada (TIKTOK_REDIRECT), canjea
el código por tokens y los guarda cifrados en estado/tiktok_token.enc. El código caduca en minutos y es de un solo uso.
No imprime tokens."""
import json, os, sys, urllib.parse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import tiktok

if __name__ == "__main__":
    env = os.environ
    faltan = [k for k in tiktok.SECRETOS + ("TIKTOK_CODIGO", "TIKTOK_REDIRECT") if not env.get(k)]
    if faltan: sys.exit(f"faltan: {', '.join(faltan)}")
    codigo = urllib.parse.unquote(env["TIKTOK_CODIGO"].strip())
    if "code=" in codigo:                      # se pegó la dirección completa de la barra del navegador
        codigo = urllib.parse.parse_qs(urllib.parse.urlparse(codigo).query).get("code", [""])[0]
    r = tiktok.canjear_codigo(env, codigo, env["TIKTOK_REDIRECT"].strip())
    print(json.dumps({"conectado": True, "alcances": r.get("alcances")}, ensure_ascii=False))
    if "video.upload" not in (r.get("alcances") or ""): sys.exit("la autorización no incluye video.upload")
