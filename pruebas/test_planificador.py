"""Planificador: una sola solicitud activa por fecha y formato, idempotencia entre ejecuciones, consolidación de los
duplicados históricos sin borrar nada y recuperación tras fallas (escritura interrumpida, archivo dañado)."""
import json, shutil, sys
from collections import Counter
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sistema"))
import planificador

ORIG = Path(__file__).resolve().parent.parent


@pytest.fixture
def raiz(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir(); shutil.copy(ORIG / "data" / "catalogo.csv", tmp_path / "data" / "catalogo.csv")
    (tmp_path / "piezas").mkdir(); (tmp_path / "estado" / "solicitudes").mkdir(parents=True)
    monkeypatch.setattr(planificador, "RAIZ", tmp_path)
    monkeypatch.setattr(planificador, "CATALOGO", tmp_path / "data" / "catalogo.csv")
    monkeypatch.setattr(planificador, "SOLICITUDES", tmp_path / "estado" / "solicitudes")
    return tmp_path


D0 = date(2026, 10, 26)


def activas(raiz):
    return Counter((d["fecha"], d["formato"]) for _, d in planificador.solicitudes() if d["estado"] in planificador.ACTIVAS)


def test_tres_ejecuciones_seguidas_no_duplican(raiz):
    for _ in range(3):
        planificador.planificar(dias=7, desde=D0, env={}, escribir=True)
    c = activas(raiz)
    assert len(c) == 14 and set(c.values()) == {1}          # 7 días × (reel + imagen), una de cada
    assert len(list(planificador.SOLICITUDES.glob("*.json"))) == 14


def test_ventana_movil_solo_agrega_los_dias_nuevos(raiz):
    planificador.planificar(dias=7, desde=D0, env={}, escribir=True)
    antes = {f.name for f in planificador.SOLICITUDES.glob("*.json")}
    planificador.planificar(dias=7, desde=date(2026, 10, 27), env={}, escribir=True)
    nuevos = {f.name for f in planificador.SOLICITUDES.glob("*.json")} - antes
    assert {n[:10] for n in nuevos} == {"2026-11-02"} and len(nuevos) == 2
    assert set(activas(raiz).values()) == {1}


def test_consolida_duplicados_historicos_sin_borrar(raiz):
    for tid in ("T019", "T060", "T071"):                     # como el defecto real: varias solicitudes del mismo día
        (planificador.SOLICITUDES / f"2026-10-26_reel_{tid}.json").write_text(json.dumps(
            {"fecha": "2026-10-26", "formato": "reel", "tema_id": tid, "titulo": tid, "carril": "A", "estado": "PENDIENTE_GUION"}))
    planificador.planificar(dias=1, desde=D0, env={}, escribir=True)
    todas = [d for _, d in planificador.solicitudes() if d["formato"] == "reel"]
    assert len(todas) == 3                                   # nada se borra
    sup = [d for d in todas if d["estado"] == "SUPERSEDIDA"]
    assert len(sup) == 2 and all(d["supersedida_por"] and d["motivo_cierre"] and d["historial"] for d in sup)
    assert activas(raiz)[("2026-10-26", "reel")] == 1


def test_conserva_la_que_ya_tiene_guion(raiz):
    for tid, est in (("T019", "PENDIENTE_GUION"), ("T060", "GUION_LISTO")):
        (planificador.SOLICITUDES / f"2026-10-26_reel_{tid}.json").write_text(json.dumps(
            {"fecha": "2026-10-26", "formato": "reel", "tema_id": tid, "titulo": tid, "carril": "A", "estado": est}))
    planificador.consolidar()
    est = {d["tema_id"]: d["estado"] for _, d in planificador.solicitudes()}
    assert est == {"T019": "SUPERSEDIDA", "T060": "GUION_LISTO"}


def test_descartada_se_reemplaza_una_sola_vez(raiz):
    planificador.planificar(dias=1, desde=D0, env={}, escribir=True)
    f, d = next((f, d) for f, d in planificador.solicitudes() if d["formato"] == "reel")
    d["estado"] = "DESCARTADA"; f.write_text(json.dumps(d))
    for _ in range(3):
        planificador.planificar(dias=1, desde=D0, env={}, escribir=True)
    reels = [d for _, d in planificador.solicitudes() if d["formato"] == "reel"]
    assert len(reels) == 2 and activas(raiz)[("2026-10-26", "reel")] == 1
    assert {x["tema_id"] for x in reels if x["estado"] == "PENDIENTE_GUION"} != {d["tema_id"]}   # otro tema


def test_supersedida_libera_su_tema(raiz):
    (planificador.SOLICITUDES / "2026-10-20_reel_T019.json").write_text(json.dumps(
        {"fecha": "2026-10-20", "formato": "reel", "tema_id": "T019", "titulo": "x", "carril": "A", "estado": "SUPERSEDIDA"}))
    assert "T019" not in planificador.usados()


def test_recupera_escritura_interrumpida_y_archivo_danado(raiz):
    (planificador.SOLICITUDES / "2026-10-26_reel_T999.tmp").write_text('{"fecha": "2026-10-26", "form')   # proceso muerto
    (planificador.SOLICITUDES / "2026-10-25_reel_T998.json").write_text("{dañado")
    planificador.planificar(dias=2, desde=D0, env={}, escribir=True)
    assert not list(planificador.SOLICITUDES.glob("*.tmp"))
    assert set(activas(raiz).values()) == {1} and len(activas(raiz)) == 4


def test_falla_a_mitad_de_la_escritura_no_deja_duplicados(raiz, monkeypatch):
    real = planificador._escribir; n = {"i": 0}
    def falla(f, d):
        n["i"] += 1
        if n["i"] == 4: raise OSError("disco lleno (simulado)")
        real(f, d)
    monkeypatch.setattr(planificador, "_escribir", falla)
    with pytest.raises(OSError):
        planificador.planificar(dias=7, desde=D0, env={}, escribir=True)
    monkeypatch.setattr(planificador, "_escribir", real)
    planificador.planificar(dias=7, desde=D0, env={}, escribir=True)        # reintento
    c = activas(raiz)
    assert len(c) == 14 and set(c.values()) == {1}


def test_imagen_complementa_el_reel_ya_planificado(raiz):
    planificador.planificar(dias=7, desde=D0, env={}, escribir=True)
    sol = {(d["fecha"], d["formato"]): d for _, d in planificador.solicitudes()}
    # martes 27-10: la imagen complementa el Reel del lunes 26-10
    assert sol[("2026-10-27", "imagen")]["relacion"] == "complemento"
    assert sol[("2026-10-27", "imagen")]["tema_id"] == sol[("2026-10-26", "reel")]["tema_id"]
