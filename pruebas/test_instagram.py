"""Instagram (Content Publishing): el contenedor no publica; solo media_publish; sin duplicados ante respuestas ambiguas;
la imagen se aloja como foto NO publicada de la Página; el texto público no lleva etiquetas internas."""
import json, sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sistema"))
import instagram, publicar

ENV = {"PUBLICAR": "1", "LANZAMIENTO_AUTORIZADO": "SI", "META_PAGE_ID": "P1", "META_PAGE_TOKEN": "TOK", "META_IG_ID": "IG1"}


class IGFalso:
    def __init__(self):
        self.publicados, self.contenedores, self.fotos, self.fallar_publish = [], {}, [], []
    def __call__(self, metodo, url, cab=None, datos=None, timeout=60):
        assert cab.get("Authorization") == "OAuth TOK"
        u = urlparse(url); q = {k: v[0] for k, v in parse_qs(u.query).items()}
        campos = {k: v[0] for k, v in parse_qs(datos.decode()).items()} if datos and cab.get("Content-Type", "").startswith("application/x-www") else {}
        r = lambda d: (200, json.dumps(d).encode())
        p = u.path
        if p.endswith("/P1/photos"):
            assert b'name="published"\r\n\r\nfalse' in datos; self.fotos.append(1); return r({"id": "F1"})
        if p.endswith("/F1"): return r({"images": [{"width": 1080, "source": "https://scontent.example/f1.png"}]})
        if p.endswith("/IG1/media") and metodo == "POST":
            cid = f"C{len(self.contenedores) + 1}"; self.contenedores[cid] = campos
            return r({"id": cid, "uri": f"https://rupload.facebook.com/ig-api-upload/v26.0/{cid}"})
        if "ig-api-upload" in url: return r({"success": True})
        if p.endswith("/IG1/media") and metodo == "GET":
            return r({"data": [{"id": m, "caption": c} for m, c in self.publicados]})
        if p.split("/")[-1] in self.contenedores: return r({"status_code": "FINISHED"})
        if p.endswith("/IG1/media_publish"):
            if self.fallar_publish:
                self.fallar_publish.pop(0); cid = campos["creation_id"]
                self.publicados.append((f"M{len(self.publicados) + 1}", self.contenedores[cid]["caption"]))
                raise publicar.SinRed("tiempo agotado tras enviar")
            cid = campos["creation_id"]; mid = f"M{len(self.publicados) + 1}"
            self.publicados.append((mid, self.contenedores[cid]["caption"])); return r({"id": mid})
        raise AssertionError(f"ruta inesperada {metodo} {url}")


@pytest.fixture
def entorno(tmp_path):
    img = tmp_path / "i.png"; img.write_bytes(b"\x89PNG..."); mp4 = tmp_path / "r.mp4"; mp4.write_bytes(b"\x00" * 100)
    return {"ig": IGFalso(), "libro": tmp_path / "ops.jsonl", "img": img, "mp4": mp4}


def test_imagen_se_publica_una_vez_con_foto_no_publicada(entorno):
    f = entorno["ig"]
    r = instagram.publicar_ig("I1", "imagen", entorno["img"], "Texto aprobado", "h" * 16, env=ENV, http=f, libro=entorno["libro"], dormir=lambda s: None)
    assert r["estado"] == "PUBLICADO" and len(f.publicados) == 1 and f.fotos == [1]
    assert f.contenedores["C1"]["image_url"].startswith("https://") and f.contenedores["C1"]["caption"] == "Texto aprobado"
    r2 = instagram.publicar_ig("I1", "imagen", entorno["img"], "Texto aprobado", "h" * 16, env=ENV, http=f, libro=entorno["libro"], dormir=lambda s: None)
    assert r2["origen"] == "libro" and len(f.publicados) == 1


def test_reel_con_carga_reanudable(entorno):
    f = entorno["ig"]
    r = instagram.publicar_ig("R1", "reel", entorno["mp4"], "Reel aprobado", "h" * 16, env=ENV, http=f, libro=entorno["libro"], dormir=lambda s: None)
    assert r["estado"] == "PUBLICADO" and f.contenedores["C1"]["media_type"] == "REELS" and f.contenedores["C1"]["upload_type"] == "resumable"


def test_respuesta_ambigua_no_duplica(entorno):
    f = entorno["ig"]; f.fallar_publish.append(1)
    with pytest.raises(publicar.PublicacionAmbigua):
        instagram.publicar_ig("I1", "imagen", entorno["img"], "Texto aprobado", "h" * 16, env=ENV, http=f, libro=entorno["libro"], dormir=lambda s: None)
    r = instagram.publicar_ig("I1", "imagen", entorno["img"], "Texto aprobado", "h" * 16, env=ENV, http=f, libro=entorno["libro"], dormir=lambda s: None)
    assert r["origen"] == "recuperada_por_texto" and len(f.publicados) == 1


def test_sin_autorizacion_solo_simula(entorno):
    f = entorno["ig"]
    r = instagram.publicar_ig("I1", "imagen", entorno["img"], "Texto", "h" * 16, env={**ENV, "PUBLICAR": "0"}, http=f, libro=entorno["libro"])
    assert r["estado"] == "SIMULADO" and not f.contenedores and not f.publicados


def test_texto_publico_sin_etiqueta_interna(tmp_path):
    r = publicar.publicar_imagen("I1", tmp_path / "x.png", "Texto aprobado", "h" * 16, modo="simulacion", libro=tmp_path / "l.jsonl")
    assert "#dpt" not in r["descripcion"] and r["descripcion"] == "Texto aprobado"
