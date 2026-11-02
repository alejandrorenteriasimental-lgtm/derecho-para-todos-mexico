"""YouTube (Shorts): solo simula sin YOUTUBE=1 y sus secretos; programa con publishAt; idempotente por el libro;
una carga sin confirmación no se reintenta; sus errores no detienen Facebook ni Instagram."""
import json, sys
from datetime import datetime, timezone
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sistema"))
import publicador, publicar, youtube

REAL = {"PUBLICAR": "1", "LANZAMIENTO_AUTORIZADO": "SI", "META_PAGE_ID": "1", "META_PAGE_TOKEN": "t",
        "YOUTUBE": "1", "YT_CLIENT_ID": "c", "YT_CLIENT_SECRET": "s", "YT_REFRESH_TOKEN": "r"}
CUANDO = datetime(2026, 12, 13, 1, 0, tzinfo=timezone.utc)


@pytest.fixture
def libro(tmp_path, monkeypatch):
    monkeypatch.setattr(publicar, "LIBRO", tmp_path / "ops.jsonl")
    f = tmp_path / "r.mp4"; f.write_bytes(b"video")
    return f


class Http:
    def __init__(self, fallar_put=None): self.llamadas = []; self.fallar_put = fallar_put
    def __call__(self, metodo, url, cab=None, datos=None, timeout=60):
        self.llamadas.append((metodo, url, cab, datos))
        if url == youtube.TOKEN_URL: return 200, b'{"access_token": "A"}'
        if metodo == "POST": return 200, json.dumps({"location": "https://subida/1"}).encode()
        if self.fallar_put: raise self.fallar_put
        return 200, json.dumps({"id": "VID1", "status": {"privacyStatus": "private", "publishAt": "2026-12-13T01:00:00Z"}}).encode()


def test_sin_condiciones_solo_simula(libro):
    for env, motivo in [({**REAL, "YOUTUBE": "0"}, "YOUTUBE"), ({**REAL, "YT_REFRESH_TOKEN": ""}, "YT_REFRESH_TOKEN"),
                        ({**REAL, "PUBLICAR": "0"}, "PUBLICAR")]:
        h = Http(); r = youtube.publicar_yt("R1", libro, "¿T?", "copy", "v1", CUANDO, env=env, http=h)
        assert r["estado"] == "SIMULADO" and motivo in r["motivo"] and not h.llamadas


def test_programa_con_publish_at_y_no_repite(libro):
    h = Http()
    r = youtube.publicar_yt("R1", libro, "¿Pregunta?", "copy", "v1", CUANDO, env=REAL, http=h)
    assert r == {"estado": "PROGRAMADO", "video_id": "VID1", "marca": r["marca"], "origen": "videos.insert"}
    meta = json.loads(h.llamadas[1][3])
    assert meta["status"] == {"privacyStatus": "private", "publishAt": "2026-12-13T01:00:00Z", "selfDeclaredMadeForKids": False, "embeddable": True}
    assert meta["snippet"]["title"] == "¿Pregunta?" and meta["snippet"]["categoryId"] == "27"
    assert h.llamadas[2][0] == "PUT" and h.llamadas[2][3] == b"video"
    h2 = Http(); r2 = youtube.publicar_yt("R1", libro, "¿Pregunta?", "copy", "v1", CUANDO, env=REAL, http=h2)
    assert r2["origen"] == "libro" and not h2.llamadas


def test_carga_sin_confirmacion_no_se_reintenta(libro):
    with pytest.raises(youtube.YouTubeAmbigua):
        youtube.publicar_yt("R1", libro, "t", "c", "v1", CUANDO, env=REAL, http=Http(fallar_put=publicar.SinRed("corte")))
    h = Http()
    with pytest.raises(youtube.YouTubeAmbigua):
        youtube.publicar_yt("R1", libro, "t", "c", "v1", CUANDO, env=REAL, http=h)
    assert not h.llamadas


def test_titulo_respeta_limites_de_youtube():
    assert youtube.titulo_yt("a<b>" + "x" * 200).startswith("ab") and len(youtube.titulo_yt("x" * 200)) == 100


def test_error_de_youtube_no_detiene_facebook(tmp_path, monkeypatch):
    monkeypatch.setattr(publicador, "PAUSA", tmp_path / "pausa.json")
    monkeypatch.setattr(publicar, "LIBRO", tmp_path / "ops.jsonl")
    monkeypatch.setattr(publicador, "comprobar", lambda e, f, ahora=None: True)
    def bajar(e, carpeta, env):
        f = tmp_path / e["archivo"]; f.write_bytes(b"x"); return f
    def yt_falla(*a, **k): raise youtube.ErrorYouTube(403, "quotaExceeded")
    monkeypatch.setattr(youtube, "publicar_yt", yt_falla)
    r = publicador.ejecutar(datetime(2026, 11, 2, 12, tzinfo=timezone.utc), env={}, bajar=bajar)
    reels = [a for a in r["acciones"] if a["formato"] == "reel"]
    assert reels and not r.get("pausa")
    assert all(a["facebook"] == "SIMULADO" and a["youtube"].startswith("ERROR") for a in reels)
