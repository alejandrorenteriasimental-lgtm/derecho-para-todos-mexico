"""Publicador del calendario: solo versiones aprobadas exactas; Facebook programado, Instagram a la hora; paro de
emergencia ante archivos no aprobados o errores no transitorios; sin autorización solo simula."""
import hashlib, json, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sistema"))
import publicador, publicar

CAL = json.loads((Path(__file__).resolve().parent.parent / "data" / "calendario_lanzamiento.json").read_text())


@pytest.fixture
def ent(tmp_path, monkeypatch):
    monkeypatch.setattr(publicador, "PAUSA", tmp_path / "pausa.json")
    monkeypatch.setattr(publicar, "LIBRO", tmp_path / "ops.jsonl")
    archivos = {}
    def bajar(e, carpeta, env):
        f = tmp_path / e["archivo"]
        if not f.exists(): f.write_bytes(archivos.get(e["pieza"], b"falso"))
        return f
    return {"tmp": tmp_path, "bajar": bajar, "archivos": archivos}


def test_aprobaciones_del_calendario_coinciden_con_el_registro():
    for d in CAL["dias"]:
        for fmt in ("imagen", "reel"):
            e = d[fmt]; a = publicador.ultima_decision(e["pieza"])
            assert a["decision"] == "APROBADA" and a["version"] == e["version"] and a["huella_archivo"] == e["sha256"], e["pieza"]


def test_archivo_distinto_al_aprobado_detiene_todo(ent):
    r = publicador.ejecutar(datetime(2026, 11, 1, tzinfo=timezone.utc), env={}, bajar=ent["bajar"])
    assert r["pausa"] and "no es el aprobado" in r["pausa"] and publicador.PAUSA.exists()
    r2 = publicador.ejecutar(datetime(2026, 11, 1, tzinfo=timezone.utc), env={}, bajar=ent["bajar"])
    assert r2["pausa"] and not r2["acciones"]                         # pausado: no se envía nada hasta revisarlo


def test_sin_autorizacion_simula_con_archivos_aprobados(ent, monkeypatch):
    monkeypatch.setattr(publicador, "comprobar", lambda e, f, ahora=None: True)
    r = publicador.ejecutar(datetime(2026, 11, 3, tzinfo=timezone.utc), env={}, bajar=ent["bajar"])   # todo el calendario cae dentro de 28 días
    assert r["modo"] == "simulacion" and not r.get("pausa")
    ahora = datetime(2026, 11, 3, tzinfo=timezone.utc)
    esperadas = sum(1 for d in CAL["dias"] for f in ("imagen", "reel")
                    if timedelta(minutes=20) < publicador.hora_utc(d["fecha"], d[f]["hora"]) - ahora < timedelta(days=28))
    assert {a.get("facebook") for a in r["acciones"]} == {"SIMULADO"} and len(r["acciones"]) == esperadas >= 14


def test_instagram_solo_en_su_ventana(ent, monkeypatch):
    monkeypatch.setattr(publicador, "comprobar", lambda e, f, ahora=None: True)
    hora = publicador.hora_utc("2026-11-23", "09:00")
    r = publicador.ejecutar(hora.replace(minute=5), env={}, bajar=ent["bajar"])
    ig = [a for a in r["acciones"] if "instagram" in a]
    assert len(ig) == 1 and ig[0]["pieza"] == "I20261123-T084" and ig[0]["instagram"] == "SIMULADO"


def test_pausa_por_variable(ent):
    r = publicador.ejecutar(datetime(2026, 11, 1, tzinfo=timezone.utc), env={"PAUSA_PUBLICACION": "1"}, bajar=ent["bajar"])
    assert r["pausa"] and not r["acciones"]


def test_reel_de_instagram_en_espera_no_detiene_lo_demas(ent, monkeypatch):
    """28-10: la carga de Reels a IG aún falla; sin IG_REELS=1 el Reel no se intenta en IG y nada se pausa."""
    monkeypatch.setattr(publicador, "comprobar", lambda e, f, ahora=None: True)
    hora = publicador.hora_utc("2026-11-23", "19:00")
    r = publicador.ejecutar(hora.replace(minute=5), env={}, bajar=ent["bajar"])
    ig = [a for a in r["acciones"] if "instagram" in a]
    assert len(ig) == 1 and ig[0]["pieza"] == "R20261123-T031" and ig[0]["instagram"] == "REEL_IG_EN_ESPERA" and not r.get("pausa")
    r2 = publicador.ejecutar(hora.replace(minute=5), env={"IG_REELS": "1"}, bajar=ent["bajar"])
    assert [a["instagram"] for a in r2["acciones"] if "instagram" in a] == ["SIMULADO"]


def test_autorizacion_registrada_y_variable_tiene_prioridad(tmp_path):
    a = tmp_path / "l.json"; a.write_text(json.dumps({"PUBLICAR": "1", "LANZAMIENTO_AUTORIZADO": "SI", "IG_REELS": "0"}))
    e = publicador.con_autorizacion({"META_PAGE_ID": "P", "META_PAGE_TOKEN": "T"}, a)
    assert publicar.modo_operacion(e)[0] == "real"
    assert publicar.modo_operacion(publicador.con_autorizacion({"PUBLICAR": "0", "META_PAGE_ID": "P", "META_PAGE_TOKEN": "T"}, a))[0] == "simulacion"


def test_aprobacion_delegada_respeta_72_horas_de_veto(monkeypatch):
    """29-10-2026: el responsable delegó la aprobación en Claude con 72 h de aviso para vetar."""
    ahora = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)
    d = {"decision": "APROBADA", "canal": "delegada", "fecha": "2026-11-09T12:00:00+00:00"}
    assert publicador.plazo_de_veto(d, ahora) is not None                       # 24 h después: aún en plazo
    assert publicador.plazo_de_veto(d, ahora + timedelta(hours=48)) is None     # 72 h cumplidas
    assert publicador.plazo_de_veto({**d, "canal": "chat"}, ahora) is None      # aprobación directa del responsable
    e = {"pieza": "X", "version": "v", "sha256": "h"}
    monkeypatch.setattr(publicador, "ultima_decision", lambda p: {**d, "version": "v", "huella_archivo": "h"})
    with pytest.raises(publicador.EnPlazoDeVeto):
        publicador.comprobar(e, __file__, ahora)
    monkeypatch.setattr(publicador, "ultima_decision", lambda p: {**d, "decision": "RECHAZADA"})   # vetada
    with pytest.raises(publicador.NoAprobada):
        publicador.comprobar(e, __file__, ahora + timedelta(days=5))


def test_reels_de_ig_solo_cortos(ent, monkeypatch):
    """IG_REELS=corto: solo Reels de duración ≤ IG_REEL_MAX_S (2-11: 38 s pasa, 58 s falla con 2207076)."""
    assert publicador.reel_ig_permitido({"IG_REELS": "corto", "IG_REEL_MAX_S": "38"}, f="x", medir=lambda f: 37.9)
    assert not publicador.reel_ig_permitido({"IG_REELS": "corto", "IG_REEL_MAX_S": "38"}, f="x", medir=lambda f: 58.1)
    assert not publicador.reel_ig_permitido({"IG_REELS": "corto"}, f="x", medir=lambda f: None)
    assert not publicador.reel_ig_permitido({"IG_REELS": "0"}, f="x", medir=lambda f: 10)
    assert publicador.reel_ig_permitido({"IG_REELS": "1"})
    monkeypatch.setattr(publicador, "comprobar", lambda e, f, ahora=None: True)
    monkeypatch.setattr(publicador, "duracion", lambda f: 30.0)
    hora = publicador.hora_utc("2026-11-23", "19:00")
    r = publicador.ejecutar(hora.replace(minute=5), env={"IG_REELS": "corto"}, bajar=ent["bajar"])
    assert [a["instagram"] for a in r["acciones"] if "instagram" in a] == ["SIMULADO"]
    monkeypatch.setattr(publicador, "duracion", lambda f: 58.0)
    r = publicador.ejecutar(hora.replace(minute=5), env={"IG_REELS": "corto"}, bajar=ent["bajar"])
    assert [a["instagram"] for a in r["acciones"] if "instagram" in a] == ["REEL_IG_EN_ESPERA"]


def test_publicar_hasta_no_programa_fechas_posteriores(ent, monkeypatch):
    # 3-11-2026: la aprobación no equivale a autorización de publicación; solo se programa hasta PUBLICAR_HASTA
    monkeypatch.setattr(publicador, "comprobar", lambda e, f, ahora=None: True)
    r = publicador.ejecutar(datetime(2026, 11, 20, tzinfo=timezone.utc), env={"PUBLICAR_HASTA": "2026-11-25"}, bajar=ent["bajar"])
    assert r["acciones"] and all(a["fecha"] <= "2026-11-25" for a in r["acciones"])
    r2 = publicador.ejecutar(datetime(2026, 11, 20, tzinfo=timezone.utc), env={}, bajar=ent["bajar"])
    assert any(a["fecha"] > "2026-11-25" for a in r2["acciones"])
