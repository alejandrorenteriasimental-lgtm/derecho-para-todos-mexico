"""Revisión humana por Telegram y respaldo persistente, con Telegram y GitHub simulados (sin red).
Lo esencial: solo decide la persona vinculada, la decisión se aplica solo a la versión exacta que se le envió, y queda
registrado quién, cuándo y qué versión."""
import hashlib, json, sys
from pathlib import Path
import pytest

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / "sistema")); sys.path.insert(0, str(AQUI))
import ciclo, cola, revision, respaldo
from test_ciclo import raiz, raiz_vacia, fuentes_ok, _sim_dos_formatos, sim_ultimo   # noqa: F401 (fixtures)

YO, OTRO = 111, 999


class TelegramFalso:
    def __init__(self): self.enviados, self.pendientes, self.uid = [], [], 1
    def __call__(self, metodo, tok, campos=None, archivo=None):
        self.enviados.append((metodo, campos, archivo))
        if metodo == "getUpdates":
            r, self.pendientes = self.pendientes, []; return {"ok": True, "result": r}
        return {"ok": True, "result": {"message_id": len(self.enviados)}}
    def _u(self, **x): self.uid += 1; self.pendientes.append({"update_id": self.uid, **x})
    def mensaje(self, texto, de=YO): self._u(message={"text": texto, "chat": {"id": de, "type": "private"}, "from": {"id": de, "username": "responsable" if de == YO else "intruso"}})
    def boton(self, data, de=YO): self._u(callback_query={"id": "q", "data": data, "from": {"id": de, "username": "responsable" if de == YO else "intruso", "first_name": "Alejandro"},
                                                           "message": {"message_id": 1, "chat": {"id": de}}})
    def botones(self): return [json.loads(c["reply_markup"])["inline_keyboard"][0] for m, c, a in self.enviados if m in ("sendPhoto", "sendVideo")]


@pytest.fixture
def en_revision(raiz_vacia, monkeypatch):
    base = _sim_dos_formatos()
    def sim(rol, sistema, usuario):
        sim_ultimo[0] = usuario; return base(rol, sistema, usuario)
    tg = TelegramFalso(); env = {"TELEGRAM_TOKEN": "x"}
    monkeypatch.setattr(revision, "http_real", tg)
    ciclo._rutas(); cod = revision.nuevo_codigo()
    tg.mensaje(f"/vincular {cod}")
    ciclo.ciclo("t", fuentes_ok, env=env, simulador=sim)              # vincula, redacta, produce, respalda y envía
    c = cola.cargar()
    assert all(t["estado"] == "REVISION_HUMANA" for t in c["trabajos"].values())
    return tg, env, sim, c


def test_vinculo_envio_y_ambas_decisiones(en_revision):
    tg, env, sim, c = en_revision
    assert revision.estado_tg()["chat_id"] == YO and "vinculo_sha256" not in revision.estado_tg()
    envs = [x for x in tg.enviados if x[0] in ("sendPhoto", "sendVideo")]
    assert sorted(m for m, _, _ in envs) == ["sendPhoto", "sendVideo"] and all(a and Path(a[1]).exists() for _, _, a in envs)
    (a1, r1), (a2, r2) = tg.botones()
    tg.boton(a1["callback_data"]); tg.boton(r2["callback_data"])     # aprueba una y rechaza la otra
    ciclo.ciclo("t", fuentes_ok, env=env, simulador=sim)
    est = {k: v["estado"] for k, v in cola.cargar()["trabajos"].items()}
    pid_a, pid_r = a1["callback_data"].split("|")[1], r2["callback_data"].split("|")[1]
    assert est[pid_a] == "SIMULADO" and est[pid_r] == "RETENIDO", est
    reg = [json.loads(l) for l in (revision.REGISTRO).read_text().splitlines()]
    assert {(d["pieza"], d["decision"]) for d in reg} == {(pid_a, "APROBADA"), (pid_r, "RECHAZADA")}
    for d in reg:
        assert d["por"]["telegram_id"] == YO and d["por"]["usuario"] == "responsable" and d["fecha"] and d["canal"] == "telegram"
        assert d["version"] == revision.version(d["pieza"], cola.cargar()["trabajos"][d["pieza"]]["formato"])[0]
        assert len(d["huella_guion"]) == 64 and len(d["huella_archivo"]) == 64


def test_boton_de_otra_persona_no_cuenta(en_revision):
    tg, env, sim, c = en_revision
    (a1, _), _ = tg.botones()
    tg.boton(a1["callback_data"], de=OTRO)
    ciclo.ciclo("t", fuentes_ok, env=env, simulador=sim)
    assert all(t["estado"] == "REVISION_HUMANA" for t in cola.cargar()["trabajos"].values())
    assert not revision.REGISTRO.exists()


def test_aprobacion_de_una_version_anterior_no_se_aplica(en_revision):
    tg, env, sim, c = en_revision
    (a1, _), _ = tg.botones(); pid = a1["callback_data"].split("|")[1]
    gp = revision.RAIZ / "piezas" / pid / "guion.json"
    g = json.loads(gp.read_text()); g["titulo"] += " (editado)"; gp.write_text(json.dumps(g, ensure_ascii=False))
    tg.boton(a1["callback_data"])
    c = cola.cargar(); revision.recoger(c, env); revision.aplicar(c)
    assert c["trabajos"][pid]["estado"] == "REVISION_HUMANA" and not revision.REGISTRO.exists()


def test_codigo_incorrecto_no_vincula(raiz_vacia, monkeypatch):
    tg = TelegramFalso(); monkeypatch.setattr(revision, "http_real", tg); ciclo._rutas()
    revision.nuevo_codigo(); tg.mensaje("/vincular ADL-00000000", de=OTRO)
    revision.recoger({"trabajos": {}}, {"TELEGRAM_TOKEN": "x"})
    assert "chat_id" not in revision.estado_tg()


def test_respaldo_es_idempotente_y_la_descarga_verifica_la_huella(tmp_path, monkeypatch):
    monkeypatch.setattr(respaldo, "MANIFIESTO", tmp_path / "respaldo.json")
    sal = tmp_path / "salida"; sal.mkdir(); (sal / "X.png").write_bytes(b"png-1"); (sal / "auditoria.json").write_text("{}")
    assets, subidas = {}, []
    def gh(metodo, url, token, datos=None, tipo=None):
        if "/releases/tags/" in url: return (200, {"upload_url": "https://u/{?name}", "assets": list(assets.values())}) if assets else (404, {})
        if url.endswith("/releases"): return 201, {"upload_url": "https://u/{?name}", "assets": []}
        nombre = url.split("name=")[1]; a = {"id": len(assets) + 1, "name": nombre}; assets[nombre] = a; subidas.append(nombre); return 201, a
    env = {"GITHUB_REPOSITORY": "o/r", "GITHUB_TOKEN": "t"}
    r1 = respaldo.respaldar("X", sal, env, gh, "piezas-prueba"); n = len(subidas)
    respaldo.respaldar("X", sal, env, gh, "piezas-prueba")
    assert n == 2 and len(subidas) == 2 and r1["X.png"]["sha256"] == hashlib.sha256(b"png-1").hexdigest()
    (sal / "X.png").write_bytes(b"png-2"); respaldo.respaldar("X", sal, env, gh, "piezas-prueba")
    assert len(subidas) == 3                                        # versión nueva = asset nuevo; el anterior se conserva


def test_respaldo_usa_el_siguiente_release_cuando_el_mes_esta_lleno(tmp_path, monkeypatch):
    """20-11-2026: «piezas-2026-11» llegó a 1,000 assets (límite de GitHub) y cada subida respondía HTTP 422."""
    monkeypatch.setattr(respaldo, "MANIFIESTO", tmp_path / "respaldo.json")
    sal = tmp_path / "salida"; sal.mkdir(); (sal / "X.png").write_bytes(b"png-1"); (sal / "auditoria.json").write_text("{}")
    lleno = [{"id": 10_000 + i, "name": f"otro__{i}"} for i in range(respaldo.LIMITE_ASSETS)]
    previo = hashlib.sha256(b"{}").hexdigest()[:12]
    lleno[0] = {"id": 77, "name": f"X__{previo}__auditoria.json"}   # ya respaldado en el release lleno
    rels = {"piezas-prueba": {"upload_url": "https://lleno/{?name}", "assets": lleno}}
    subidas = []
    def gh(metodo, url, token, datos=None, tipo=None):
        if "/releases/tags/" in url:
            t = url.rsplit("/", 1)[1]; return (200, rels[t]) if t in rels else (404, {})
        if url.endswith("/releases"):
            import json as _j; t = _j.loads(datos)["tag_name"]; rels[t] = {"upload_url": f"https://{t}/{{?name}}", "assets": []}; return 201, rels[t]
        if url.startswith("https://lleno/"): return 422, {"message": "Validation Failed"}
        nombre = url.split("name=")[1]; a = {"id": len(subidas) + 1, "name": nombre}; subidas.append(url); return 201, a
    env = {"GITHUB_REPOSITORY": "o/r", "GITHUB_TOKEN": "t"}
    r = respaldo.respaldar("X", sal, env, gh, "piezas-prueba")
    assert r["X.png"]["release"] == "piezas-prueba-2" and subidas and all(u.startswith("https://piezas-prueba-2/") for u in subidas)
    assert r["auditoria.json"] == {**r["auditoria.json"], "asset_id": 77, "release": "piezas-prueba"}   # no se duplica
    assert len(subidas) == 1
