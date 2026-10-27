"""Revisión humana por el chat (sin Telegram): la decisión solo se registra y se aplica para la versión exacta revisada,
y queda anotado quién, cuándo y qué versión."""
import json, sys
from pathlib import Path
import pytest

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / "sistema")); sys.path.insert(0, str(AQUI))
import ciclo, cola, decidir, revision
from test_ciclo import raiz, raiz_vacia, fuentes_ok, _sim_dos_formatos, sim_ultimo   # noqa: F401 (fixtures)


@pytest.fixture
def en_revision(raiz_vacia):
    base = _sim_dos_formatos(); env = {}                                # sin TELEGRAM_TOKEN
    def sim(rol, sistema, usuario):
        sim_ultimo[0] = usuario; return base(rol, sistema, usuario)
    ciclo._rutas(); ciclo.ciclo("t", fuentes_ok, env=env, simulador=sim)
    c = cola.cargar(); ps = decidir.pendientes(c)
    assert len(ps) == 2 and all((t.get("revision") or {}).get("canal") == "chat" for t in ps)
    return env, sim, c, ps


def test_sin_telegram_se_fija_la_version_para_revision(en_revision):
    env, sim, c, ps = en_revision
    for t in ps:
        assert t["revision"]["version"] == revision.version(t["id"], t["formato"])[0]


def test_aprobar_y_rechazar_por_chat(en_revision):
    env, sim, c, ps = en_revision
    a, r = ps
    decidir.decidir(c, a["id"], "APROBADA", a["revision"]["version"], "Alejandro Rentería (chat)")
    decidir.decidir(c, r["id"], "RECHAZADA", r["revision"]["version"], "Alejandro Rentería (chat)", "la conclusión es imprecisa")
    ciclo.ciclo("t", fuentes_ok, env=env, simulador=sim)
    t = cola.cargar()["trabajos"]
    assert t[a["id"]]["estado"] == "SIMULADO" and t[r["id"]]["estado"] == "RETENIDO"
    for d in (json.loads(l) for l in revision.REGISTRO.read_text().splitlines()):
        assert d["canal"] == "chat" and d["por"]["nombre"] == "Alejandro Rentería (chat)" and d["fecha"] and len(d["version"]) == 16


def test_version_equivocada_no_se_registra(en_revision):
    env, sim, c, ps = en_revision
    with pytest.raises(decidir.VersionDistinta):
        decidir.decidir(c, ps[0]["id"], "APROBADA", "0" * 16, "Alejandro (chat)")
    assert not revision.REGISTRO.exists()


def test_si_la_pieza_cambia_despues_de_revisarla_no_se_aplica(en_revision):
    env, sim, c, ps = en_revision
    pid, ver = ps[0]["id"], ps[0]["revision"]["version"]
    decidir.decidir(c, pid, "APROBADA", ver, "Alejandro (chat)")
    gp = revision.RAIZ / "piezas" / pid / "guion.json"
    g = json.loads(gp.read_text()); g["titulo"] += " (editado)"; gp.write_text(json.dumps(g, ensure_ascii=False))
    c = cola.cargar(); revision.aplicar(c)
    assert c["trabajos"][pid]["estado"] == "REVISION_HUMANA"


def test_rechazo_sin_motivo_no_se_registra(en_revision):
    env, sim, c, ps = en_revision
    with pytest.raises(ValueError):
        decidir.decidir(c, ps[0]["id"], "RECHAZADA", ps[0]["revision"]["version"], "Alejandro (chat)")
