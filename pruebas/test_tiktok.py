"""TikTok: borrador en la bandeja; solo simula sin condiciones; tokens cifrados y renovados (se guarda la clave nueva);
idempotente; un envío sin confirmación no se repite; respeta aprobación exacta y plazo de veto."""
import json, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sistema"))
import publicador, publicar, tiktok

REAL = {"PUBLICAR": "1", "LANZAMIENTO_AUTORIZADO": "SI", "META_PAGE_ID": "1", "META_PAGE_TOKEN": "t", "TIKTOK": "1",
        "TIKTOK_CLIENT_KEY": "k", "TIKTOK_CLIENT_SECRET": "s", "TIKTOK_CLAVE": "clave-secreta"}
AHORA = datetime(2026, 12, 11, 3, tzinfo=timezone.utc)


@pytest.fixture
def ent(tmp_path, monkeypatch):
    monkeypatch.setattr(publicar, "LIBRO", tmp_path / "ops.jsonl")
    monkeypatch.setattr(tiktok, "TOKENS", tmp_path / "tt.enc")
    monkeypatch.setattr(publicador, "PAUSA", tmp_path / "pausa.json")
    tiktok.guardar_tokens("clave-secreta", {"access_token": "A1", "refresh_token": "R1", "open_id": "o",
                                            "expira": (AHORA + timedelta(hours=10)).isoformat(),
                                            "renovacion_expira": (AHORA + timedelta(days=300)).isoformat()})
    f = tmp_path / "r.mp4"; f.write_bytes(b"video")
    return f


class Http:
    def __init__(self, estado_final="SEND_TO_USER_INBOX", put=None):
        self.llamadas = []; self.estado_final = estado_final; self.put = put
    def __call__(self, metodo, url, cab=None, datos=None, timeout=60):
        self.llamadas.append((metodo, url, cab, datos))
        if url == tiktok.TOKEN_URL:
            return 200, json.dumps({"access_token": "A2", "refresh_token": "R2", "expires_in": 86400, "refresh_expires_in": 31536000, "open_id": "o"}).encode()
        if url.endswith("/inbox/video/init/"):
            return 200, json.dumps({"data": {"publish_id": "P1", "upload_url": "https://subida/x"}, "error": {"code": "ok"}}).encode()
        if metodo == "PUT":
            if self.put: raise self.put
            return 201, b""
        if url.endswith("/status/fetch/"):
            return 200, json.dumps({"data": {"status": self.estado_final}, "error": {"code": "ok"}}).encode()
        raise AssertionError(url)


def test_sin_condiciones_simula(ent):
    for env, motivo in [({**REAL, "TIKTOK": "0"}, "TIKTOK"), ({**REAL, "TIKTOK_CLAVE": ""}, "TIKTOK_CLAVE"), ({**REAL, "PUBLICAR": "0"}, "PUBLICAR")]:
        h = Http(); r = tiktok.enviar_a_bandeja("R1", ent, "v1", env=env, http=h, ahora=AHORA)
        assert r["estado"] == "SIMULADO" and motivo in r["motivo"] and not h.llamadas


def test_envia_a_la_bandeja_y_no_repite(ent):
    h = Http(); r = tiktok.enviar_a_bandeja("R1", ent, "v1", env=REAL, http=h, ahora=AHORA, dormir=lambda s: None)
    assert r["estado"] == "EN_BANDEJA" and r["publish_id"] == "P1"
    ini = json.loads(h.llamadas[0][3]); assert ini["source_info"] == {"source": "FILE_UPLOAD", "video_size": 5, "chunk_size": 5, "total_chunk_count": 1}
    assert h.llamadas[0][2]["Authorization"] == "Bearer A1" and h.llamadas[1][2]["Content-Range"] == "bytes 0-4/5"
    h2 = Http(); assert tiktok.enviar_a_bandeja("R1", ent, "v1", env=REAL, http=h2, ahora=AHORA)["origen"] == "libro" and not h2.llamadas


def test_renueva_y_guarda_la_clave_nueva_cifrada(ent):
    h = Http(); tiktok.enviar_a_bandeja("R1", ent, "v1", env=REAL, http=h, ahora=AHORA + timedelta(hours=9, minutes=30), dormir=lambda s: None)
    assert h.llamadas[0][1] == tiktok.TOKEN_URL and b"refresh_token=R1" in h.llamadas[0][3]
    t = tiktok.leer_tokens("clave-secreta"); assert t["refresh_token"] == "R2" and t["access_token"] == "A2"
    cifrado = tiktok.TOKENS.read_bytes()                                # nunca en claro: se busca el JSON en claro, no
    assert b'"R2"' not in cifrado and b"refresh_token" not in cifrado  # «R2» suelto (un token Fernet en base64 puede contenerlo por azar: ciclo 41964418538, 5-11)


def test_envio_sin_confirmacion_no_se_repite(ent):
    with pytest.raises(tiktok.TikTokAmbigua):
        tiktok.enviar_a_bandeja("R1", ent, "v1", env=REAL, http=Http(put=publicar.SinRed("corte")), ahora=AHORA)
    h = Http()
    with pytest.raises(tiktok.TikTokAmbigua): tiktok.enviar_a_bandeja("R1", ent, "v1", env=REAL, http=h, ahora=AHORA)
    assert not h.llamadas


def test_rechazo_de_tiktok_queda_registrado(ent):
    with pytest.raises(tiktok.ErrorTikTok):
        tiktok.enviar_a_bandeja("R1", ent, "v1", env=REAL, http=Http(estado_final="FAILED"), ahora=AHORA, dormir=lambda s: None)
    assert publicar.operacion(publicar.marca("R1", "v1") + "-tt", "real")["fase"] == "FALLIDA"


def test_ejecutar_exige_aprobacion_y_respeta_el_veto(ent, monkeypatch):
    cal = json.loads(publicador.CAL.read_text()); dia = cal["dias"][0]
    def bajar(e, carpeta, env): return ent
    r = tiktok.ejecutar(dia["fecha"], env={}, bajar=bajar, ahora=AHORA)
    assert r["estado"] == "NO_APROBADA"                                   # el archivo falso no es el aprobado
    monkeypatch.setattr(publicador, "comprobar", lambda e, f, ahora=None: (_ for _ in ()).throw(publicador.EnPlazoDeVeto("veto")))
    assert tiktok.ejecutar(dia["fecha"], env={}, bajar=bajar, ahora=AHORA)["estado"] == "EN_PLAZO_DE_VETO"
    monkeypatch.setattr(publicador, "comprobar", lambda e, f, ahora=None: True)
    r = tiktok.ejecutar(dia["fecha"], env={}, bajar=bajar, ahora=AHORA)
    assert r["estado"] == "SIMULADO" and r["copy"]
    assert tiktok.ejecutar("2030-01-01", env={}, bajar=bajar, ahora=AHORA)["estado"] == "SIN_REEL_EN_CALENDARIO"
