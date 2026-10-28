"""La prueba de Meta solo lee (GET) y reconoce Página, Instagram y permisos de publicación no autorizados."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sistema"))
import meta_prueba as M


def falso(perms):
    def http(ruta, tok, **p):
        if ruta == "me": return {"id": M.PAGINA_ESPERADA, "name": "Aquí Dice la Ley"}
        if ruta == "me/permissions": return {"data": [{"permission": x, "status": "granted"} for x in perms]}
        return {"name": "Aquí Dice la Ley", "username": "aquidicelaley", "followers_count": 0,
                "instagram_business_account": {"username": "aquidicelaley", "followers_count": 0, "media_count": 0}}
    return http


def test_permisos_de_publicacion_pasan():
    """Desde el 28-10 el lanzamiento requiere los permisos de publicación (autorizados por el responsable)."""
    assert M.probar("t", http=falso(["pages_show_list", "pages_read_engagement", "instagram_basic", "pages_manage_posts", "instagram_content_publish"]))["ok"]


def test_falta_de_permiso_de_publicacion_se_senala():
    r = M.probar("t", http=falso(["pages_show_list", "pages_read_engagement", "instagram_basic"]))
    assert not r["ok"] and any(c["resultado"] == "FALLA" and "publicación" in c["prueba"] for c in r["comprobaciones"])


def test_token_invalido():
    assert not M.probar("t", http=lambda ruta, tok, **p: {"error": {"message": "Invalid OAuth"}})["ok"]
