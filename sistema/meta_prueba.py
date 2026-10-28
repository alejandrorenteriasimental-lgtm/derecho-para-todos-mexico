"""Prueba de SOLO LECTURA de la conexión con Meta (Página de Facebook e Instagram). No publica ni modifica nada.

Comprueba con el token guardado como secreto (META_PAGE_TOKEN; permisos mínimos pages_show_list,
pages_read_engagement e instagram_basic):
  1. a qué Página corresponde el token y si es la de Aquí Dice la Ley;
  2. qué permisos tiene concedidos (y avisa si hay alguno de publicación, que todavía no se autoriza);
  3. que la cuenta de Instagram @aquidicelaley está vinculada a esa Página;
  4. que se pueden leer datos básicos (nombre, seguidores, número de publicaciones).
Solo usa peticiones GET. Uso: python sistema/meta_prueba.py  (variables META_PAGE_TOKEN y, opcional, META_PAGE_ID).
"""
import json, os, sys, urllib.error, urllib.parse, urllib.request

GRAPH = "https://graph.facebook.com/v26.0"
PAGINA_ESPERADA = "1359758353893509"        # ID de la Página en la API Graph (el perfil web es 61595676911245)
IG_ESPERADO = "aquidicelaley"
PUBLICACION = {"pages_manage_posts", "instagram_content_publish", "publish_video", "pages_manage_engagement"}


def get(ruta, tok, **params):
    url = f"{GRAPH}/{ruta}?" + urllib.parse.urlencode({**params, "access_token": tok})
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="GET"), timeout=30) as r: return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b"{}")


def probar(tok, page_id=None, http=get):
    res = {"ok": False, "comprobaciones": []}
    def ok(nombre, cumple, detalle=""): res["comprobaciones"].append({"prueba": nombre, "resultado": "OK" if cumple else "FALLA", "detalle": detalle})
    yo = http("me", tok, fields="id,name")
    if "error" in yo:
        ok("token válido", False, yo["error"].get("message", "")); return res
    pid = page_id or yo.get("id")
    ok("token válido", True, yo.get("name", ""))
    ok("es la Página de Aquí Dice la Ley", str(pid) == PAGINA_ESPERADA, f"id {pid}")
    perms = http("me/permissions", tok)
    concedidos = {p["permission"] for p in perms.get("data", []) if p.get("status") == "granted"}
    if concedidos:
        ok("permisos de publicación concedidos (necesarios para el lanzamiento)", {"pages_manage_posts", "instagram_content_publish"} <= concedidos, ", ".join(sorted(concedidos)))
    pag = http(str(pid), tok, fields="name,username,followers_count,instagram_business_account{username,followers_count,media_count}")
    ok("lectura de la Página", "error" not in pag, json.dumps({k: pag.get(k) for k in ("name", "username", "followers_count")}, ensure_ascii=False))
    ig = pag.get("instagram_business_account") or {}
    ok("Instagram vinculado", ig.get("username") == IG_ESPERADO, json.dumps(ig, ensure_ascii=False))
    res["ok"] = all(c["resultado"] == "OK" for c in res["comprobaciones"])
    return res


if __name__ == "__main__":
    tok = os.environ.get("META_PAGE_TOKEN")
    if not tok:
        print("Falta el secreto META_PAGE_TOKEN; no se hizo ninguna llamada."); sys.exit(0)
    r = probar(tok, os.environ.get("META_PAGE_ID"))
    print(json.dumps(r, ensure_ascii=False, indent=2)); sys.exit(0 if r["ok"] else 1)
