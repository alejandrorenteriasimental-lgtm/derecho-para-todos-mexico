"""Transporte de fuentes oficiales con reintentos y copia de respaldo (falla real del 26-10-2026: diputados.gob.mx sin
respuesta desde GitHub dos ciclos seguidos)."""
import hashlib, json, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sistema"))
import verificador as v

URL = "https://www.diputados.gob.mx/LeyesBiblio/pdf/LFPC.pdf"
T0 = datetime(2026, 10, 26, 12, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(v, "CACHE_FUENTES", tmp_path / "cache")
    v.RESPALDOS_USADOS.clear()
    yield tmp_path / "cache"


def caido(url, timeout=60):
    raise v.SinConexion("timed out")


def bien(url, timeout=60):
    return 200, "application/pdf", b"%PDF texto oficial"


def test_reintenta_y_luego_descarga():
    n = []
    def a_la_tercera(url, timeout=60):
        n.append(timeout)
        if len(n) < 3: raise v.SinConexion("timed out")
        return bien(url)
    r = v.transporte_resiliente(URL, base=a_la_tercera, dormir=lambda s: None, ahora=T0)
    assert r[0] == 200 and n == [60, 120, 180] and not v.RESPALDOS_USADOS


def test_sin_conexion_usa_copia_reciente_y_lo_anota():
    v.transporte_resiliente(URL, base=bien, ahora=T0)
    r = v.transporte_resiliente(URL, base=caido, dormir=lambda s: None, ahora=T0 + timedelta(days=2))
    assert r == (200, "application/pdf", b"%PDF texto oficial")
    assert v.RESPALDOS_USADOS and v.RESPALDOS_USADOS[0]["url"] == URL and v.RESPALDOS_USADOS[0]["descargado"].startswith("2026-10-26")


def test_copia_vieja_no_se_usa():
    v.transporte_resiliente(URL, base=bien, ahora=T0)
    with pytest.raises(v.SinConexion):
        v.transporte_resiliente(URL, base=caido, dormir=lambda s: None, ahora=T0 + timedelta(days=v.RESPALDO_DIAS + 1))


def test_copia_alterada_no_se_usa(cache):
    v.transporte_resiliente(URL, base=bien, ahora=T0)
    next(cache.glob("*.bin")).write_bytes(b"%PDF texto cambiado")
    with pytest.raises(v.SinConexion):
        v.transporte_resiliente(URL, base=caido, dormir=lambda s: None, ahora=T0)


def test_sin_copia_sigue_fallando():
    with pytest.raises(v.SinConexion):
        v.transporte_resiliente(URL, base=caido, dormir=lambda s: None, ahora=T0)


def test_respuesta_de_error_no_se_guarda(cache):
    v.transporte_resiliente(URL, base=lambda u, timeout=60: (404, "text/html", b"no"), ahora=T0)
    assert not list(cache.glob("*.bin"))
