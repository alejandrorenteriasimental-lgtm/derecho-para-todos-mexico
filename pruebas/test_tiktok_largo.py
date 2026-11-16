"""Versión larga SOLO para TikTok (decisión del responsable, 16-11-2026): rango propio de 60 a 75 s sin tocar el del Reel,
ampliación anclada en el texto oficial de los mismos artículos con todos los controles, pieza derivada con su propia
aprobación (veto de 72 h), entrada opcional en el calendario y envío a la bandeja con regreso al Reel normal."""
import copy, json, sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sistema"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import auditoria, decidir, esquema, publicador, publicar, redactor, revision, tiktok, tiktok_largo, verificador
from test_redactor import BORRADOR, SOL, simulador_con, transporte

AHORA = datetime(2026, 12, 11, 3, tzinfo=timezone.utc)


# ── esquema y auditoría técnica ──────────────────────────────────────────────────────────────────────────────────
def _guion_con(n):
    g = copy.deepcopy(_base()); relleno = n - sum(len(e["texto"]) for e in g["escenas"])
    g["escenas"][1]["texto"] += " " + ("x" * (relleno - 1)) if relleno > 0 else ""
    return g


def test_rango_propio_de_la_variante_sin_tocar_el_del_reel():
    assert esquema.MAX_NARRACION == 620 and (esquema.MIN_NARRACION_TIKTOK, esquema.MAX_NARRACION_TIKTOK) == (930, 1040)
    largo = _guion_con(980)
    assert any("narración de 980" in e and "620" in e for e in esquema.validar(largo))          # como Reel normal, no pasa
    assert not any("narración" in e for e in esquema.validar({**largo, "variante": "tiktok"}))  # como variante, sí
    corto = {**_base(), "variante": "tiktok"}
    assert any("faltan" in e and "930" in e for e in esquema.validar(corto))
    assert any("sobran" in e for e in esquema.validar({**_guion_con(1100), "variante": "tiktok"}))


def test_control_de_duracion_por_variante():
    nombre, ok = auditoria.control_duracion(40)
    assert ok and nombre.startswith("Duración entre 20 y 45 s")                 # el control del Reel no cambia
    assert not auditoria.control_duracion(65)[1]
    assert auditoria.control_duracion(65, "tiktok")[1] and auditoria.control_duracion(75, "tiktok")[1]
    for d in (45, 60.0, 75.2):
        assert not auditoria.control_duracion(d, "tiktok")[1]
    assert "TikTok" in auditoria.control_duracion(65, "tiktok")[0]               # producir.py lo vuelve obligatorio en la variante


# ── redacción de la ampliación ───────────────────────────────────────────────────────────────────────────────────
_BASE = None


def _base():
    global _BASE
    if _BASE is None:
        _BASE = redactor.generar({**SOL, "pieza_id": "R20261210-T073"}, transporte, simulador_con(), env={}, archivo_uso=Path("/tmp/_uso_tt.jsonl"))
        _BASE["copy"] = redactor.copy_reel(_BASE, _BASE["razonamiento"])
    return copy.deepcopy(_BASE)


def _largo(**cambios):
    b = copy.deepcopy(BORRADOR)
    b["escenas"][1]["texto"] = ("La respuesta está en el artículo diecisiete de la Constitución, que aplica en todo el país, y vale la pena "
                                "conocerla completa antes de asustarte por una amenaza.")
    b["escenas"].insert(4, {"tipo": "lista", "texto": ("Por ejemplo, si le debes dinero a un vecino por un préstamo, él puede cobrarte por la vía "
                                                       "legal y pedirlo ante un juez, pero esa deuda civil, por sí sola, no te lleva a prisión. Lo que "
                                                       "sí pueden hacer es reclamarte el pago con un juicio."),
                            "items": ["Préstamo entre vecinos", "Cobro ante un juez", "Sin prisión por la deuda"]})
    b["escenas"][5]["texto"] = ("Si alguien te amenaza con la cárcel por una deuda civil, esa amenaza no tiene sustento en la Constitución. Recuerda: "
                                "pueden cobrarte por la vía legal, pero no encarcelarte solo por deber dinero de carácter civil.")
    b["afirmaciones"].append({"escena": 4, "fuente": "F1", "tipo": "interpretacion", "texto": "Una deuda civil entre particulares se cobra por la vía legal, sin prisión.",
                              "cita_literal": "Nadie puede ser aprisionado por deudas de carácter puramente civil", "duda": None})
    b["ampliacion"] = {"tipo": "ejemplo", "resumen": "préstamo entre vecinos"}
    b.update(cambios)
    return b


def test_amplia_el_reel_aprobado_con_los_mismos_controles(tmp_path):
    base = _base(); sim = simulador_con(redactar=_largo())
    g = redactor.ampliar_tiktok(base, transporte, sim, env={}, archivo_uso=tmp_path / "u.jsonl")
    assert g["id"] == "R20261210-T073-TT" and g["variante"] == "tiktok" and esquema.validar(g) == []
    assert g["titulo"] == base["titulo"] and g["pregunta_original"] == base["pregunta_original"] and g["copy"] == base["copy"]
    assert g["razonamiento"] == base["razonamiento"] and g["escenas"][0]["texto"] == base["escenas"][0]["texto"]
    citas = lambda x: [e["cita"] for e in x["escenas"] if e["tipo"] == "cita"]
    assert citas(base)[0] in citas(g)                                                         # misma cita literal
    assert {(f["documento"], f["articulo"]) for f in g["fuentes"].values()} <= {(f["documento"], f["articulo"]) for f in base["fuentes"].values()}
    assert esquema.MIN_NARRACION_TIKTOK <= sum(len(e["texto"]) for e in g["escenas"]) <= esquema.MAX_NARRACION_TIKTOK
    assert g["version_tiktok"]["de"] == base["id"] and g["version_tiktok"]["ampliacion"]["tipo"] == "ejemplo"
    assert len(sim.llamadas["redactor"]) == 1 and len(sim.llamadas["auditor"]) == 1 and not sim.llamadas["investigador"]
    v = verificador.verificar_guion(g, transporte)
    assert v["decision"] in ("APTA", "APTA_CON_CRITERIO")
    assert auditoria.dictamen(g, v, date.today())["decision"] in ("APTO", "APTO_CON_CRITERIO")


def test_ejemplo_con_cita_inventada_no_cuenta_como_ampliacion(tmp_path):
    b = _largo(); b["afirmaciones"][-1]["cita_literal"] = "Nadie puede ser aprisionado por deudas de ninguna clase jamás en ningún caso"
    with pytest.raises(redactor.Descartada) as x:
        redactor.ampliar_tiktok(_base(), transporte, simulador_con(redactar=b), env={}, archivo_uso=tmp_path / "u.jsonl")
    assert "[ampliación]" in str(x.value) or any("[ampliación]" in e for h in x.value.historial for e in h.get("errores_esquema", []))


def test_sin_la_cita_del_reel_o_con_otro_articulo_no_pasa():
    base = _base(); g = copy.deepcopy(base)
    g["escenas"] = [e for e in g["escenas"] if e["tipo"] != "cita"]
    assert any("misma cita literal" in e for e in redactor.controles_ampliacion(g, base))
    g = copy.deepcopy(base); g["fuentes"]["F9"] = {**g["fuentes"]["F1"], "articulo": "18"}
    assert any("no es un artículo del Reel" in e for e in redactor.controles_ampliacion(g, base))


def test_objecion_del_auditor_se_corrige_o_se_descarta(tmp_path):
    obj = {"veredicto": "con_objeciones", "objeciones": [{"donde": "ejemplo", "problema": "va más allá de la cita", "correccion": "quítalo"}]}
    sim = simulador_con(redactar=_largo(), auditar=obj)
    with pytest.raises(redactor.Descartada):
        redactor.ampliar_tiktok(_base(), transporte, sim, env={}, archivo_uso=tmp_path / "u.jsonl")
    assert len(sim.llamadas["auditor"]) == 3
    sim = simulador_con(redactar=_largo(), auditar=lambda n: obj if n == 1 else {"veredicto": "sin_objeciones", "objeciones": []})
    assert redactor.ampliar_tiktok(_base(), transporte, sim, env={}, archivo_uso=tmp_path / "u.jsonl")["variante"] == "tiktok"


def test_no_amplia_temas_de_riesgo_alto_ni_variantes():
    with pytest.raises(redactor.Descartada): redactor.ampliar_tiktok({**_base(), "riesgo": "alto"}, transporte, simulador_con(), env={})
    with pytest.raises(redactor.Descartada): redactor.ampliar_tiktok({**_base(), "variante": "tiktok"}, transporte, simulador_con(), env={})


# ── registro, calendario y aprobación ────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def entorno(tmp_path, monkeypatch):
    raiz = tmp_path
    for d in ("estado", "data", "registro", "piezas"): (raiz / d).mkdir()
    monkeypatch.setattr(tiktok_largo, "RAIZ", raiz)
    monkeypatch.setattr(tiktok_largo, "REG", raiz / "estado" / "tiktok_largo.json")
    monkeypatch.setattr(tiktok_largo, "CAL", raiz / "data" / "cal.json")
    monkeypatch.setattr(tiktok_largo, "AUT", raiz / "data" / "lanzamiento.json")
    monkeypatch.setattr(tiktok_largo, "PIEZAS", raiz / "registro" / "piezas.jsonl")
    monkeypatch.setattr(publicador, "APROB", raiz / "estado" / "aprobaciones.jsonl")
    monkeypatch.setattr(publicador, "CAL", raiz / "data" / "cal.json")
    monkeypatch.setattr(publicador, "PAUSA", raiz / "estado" / "pausa.json")
    monkeypatch.setattr(revision, "REGISTRO", raiz / "estado" / "aprobaciones.jsonl")
    monkeypatch.setattr(publicar, "LIBRO", raiz / "estado" / "ops.jsonl")
    import cola, modelos                                                 # bitácora y uso de IA: nunca los del repositorio
    monkeypatch.setattr(cola, "BITACORA", raiz / "estado" / "bitacora.jsonl")
    monkeypatch.setattr(modelos, "USO", raiz / "estado" / "uso_ia.jsonl")
    (raiz / "data" / "lanzamiento.json").write_text(json.dumps({"TIKTOK_LARGO_DESDE": "2026-12-01"}))
    dias = []
    for i, f in enumerate(("2026-12-02", "2026-12-06", "2026-12-05", "2026-12-08", "2026-12-09")):
        dias.append({"fecha": f, "reel": {"pieza": f"R{i}", "version": f"v{i}", "hora": "19:00", "archivo": f"R{i}_final.mp4",
                                          "sha256": f"{i}" * 64, "asset_id": 100 + i}})
    (raiz / "data" / "cal.json").write_text(json.dumps({"nota": "x", "dias": dias}, ensure_ascii=False, indent=1) + "\n")
    filas = [{"pieza": f"R{i}", "decision": "APROBADA", "version": f"v{i}", "huella_archivo": f"{i}" * 64, "fecha": "2026-11-20T00:00:00+00:00", "canal": "delegada"}
             for i in range(5) if i != 4]                                                      # R4 sin aprobación
    (raiz / "estado" / "aprobaciones.jsonl").write_text("".join(json.dumps(x) + "\n" for x in filas))
    (raiz / "registro" / "piezas.jsonl").write_text(json.dumps({"id": "R3", "duracion_s": 62.0}) + "\n")   # R3 ya dura más de 1 min
    return raiz


def test_inactiva_antes_de_la_fecha(entorno):
    assert tiktok_largo.ejecutar(hoy=date(2026, 11, 30), env={})["estado"] == "INACTIVO"
    assert tiktok_largo.activo(date(2026, 12, 1)) and not tiktok_largo.activo(date(2026, 11, 30))


def test_candidatos_por_cercania_con_aprobacion_vigente(entorno):
    cal = json.loads((entorno / "data" / "cal.json").read_text())
    c = tiktok_largo.candidatos(cal, {}, date(2026, 12, 1), {})
    # R0 (2-12) no cabe en el veto; R3 ya dura más de 60 s; R4 no está aprobado; R2 (5-12) va antes que R1 (6-12)
    assert [e["pieza"] for _, e in c] == ["R2", "R1"]
    reg = {"R2-TT": {"version_base": "v2", "estado": "REVISION_HUMANA"}, "R1-TT": {"version_base": "otra", "estado": "APROBADA"}}
    assert [e["pieza"] for _, e in tiktok_largo.candidatos(cal, reg, date(2026, 12, 1), {})] == ["R1"]   # R1 cambió de versión: se rehace
    reg = {"R2-TT": {"version_base": "v2", "estado": "PENDIENTE", "intentos": 2}}
    assert [e["pieza"] for _, e in tiktok_largo.candidatos(cal, reg, date(2026, 12, 1), {})] == ["R1"]   # dos descartes: Reel normal
    assert tiktok_largo.candidatos(cal, {}, date(2026, 12, 1), {"PUBLICAR_HASTA": "2026-12-05"})[0][1]["pieza"] == "R2"


def test_produccion_registra_revision_humana_o_descarte(entorno, monkeypatch):
    import producir, respaldo
    base = _base(); base["id"] = "R2"
    (entorno / "piezas" / "R2").mkdir(); (entorno / "piezas" / "R2" / "guion.json").write_text(json.dumps(base, ensure_ascii=False))
    original = (entorno / "piezas" / "R2" / "guion.json").read_bytes()
    monkeypatch.setattr(producir, "producir", lambda carpeta, ver: ({"duracion_s": 66.2, "sha256": "e" * 64},
                                                                      [{"control": "x", "resultado": "APROBADO", "detalle": ""}], {"decision": "APTO", "motivos": []}))
    monkeypatch.setattr(respaldo, "respaldar", lambda pid, carpeta, env: {f"{pid}_final.mp4": {"sha256": "e" * 64, "asset_id": 9, "release": "piezas-2026-12"}})
    monkeypatch.setattr(revision, "version", lambda pid, fmt: ("ver-tt-0001", "hg", "e" * 64))
    r = tiktok_largo.ejecutar(hoy=date(2026, 12, 1), env={}, transporte=transporte, simulador=simulador_con(redactar=_largo()))
    assert r["producidas"][0]["pieza"] == "R2-TT"
    v = tiktok_largo.cargar()["R2-TT"]
    assert v["estado"] == "REVISION_HUMANA" and v["revision"]["version"] == "ver-tt-0001" and v["version_base"] == "v2" and v["asset_id"] == 9
    g = json.loads((entorno / "piezas" / "R2-TT" / "guion.json").read_text())
    assert g["id"] == "R2-TT" and g["version_tiktok"]["version_base"] == "v2"
    assert (entorno / "piezas" / "R2" / "guion.json").read_bytes() == original                 # el Reel aprobado no se toca
    # un tema que no se puede ampliar: dos descartes y ese día va el Reel normal
    (entorno / "piezas" / "R1").mkdir(); (entorno / "piezas" / "R1" / "guion.json").write_text(json.dumps({**base, "id": "R1"}, ensure_ascii=False))
    monkeypatch.setattr(redactor, "ampliar_tiktok", lambda *a, **k: (_ for _ in ()).throw(redactor.Descartada("sin ejemplo sustentable")))
    for esperado in ("PENDIENTE", "DESCARTADA"):
        tiktok_largo.ejecutar(hoy=date(2026, 12, 1), env={}, transporte=transporte)
        assert tiktok_largo.cargar()["R1-TT"]["estado"] == esperado


def _registrar_variante(entorno, pid="R1-TT", base="R1", vb="v1"):
    reg = tiktok_largo.cargar()
    reg[pid] = {"de": base, "version_base": vb, "estado": "REVISION_HUMANA", "sha256": "f" * 64, "asset_id": 77, "release": "piezas-2026-12",
                "duracion_s": 68.0, "revision": {"version": "vtt1"}}
    tiktok_largo.guardar(reg)


def test_aprobacion_propia_y_calendario_sin_tocar_el_reel(entorno, monkeypatch):
    _registrar_variante(entorno)
    monkeypatch.setattr(revision, "version", lambda pid, fmt: ("vtt1", "hg", "f" * 64))
    antes = json.loads((entorno / "data" / "cal.json").read_text())
    with pytest.raises(tiktok_largo.NoDecidible): decidir.decidir({"trabajos": {}}, "R1-TT", "APROBADA", "otra", "Claude")
    fila = decidir.decidir({"trabajos": {}}, "R1-TT", "APROBADA", "vtt1", "Claude (revisión editorial delegada)", canal="delegada")
    assert fila["pieza"] == "R1-TT" and fila["canal"] == "delegada"
    assert publicador.ultima_decision("R1")["version"] == "v1"                                 # la aprobación del Reel sigue igual
    cal = json.loads((entorno / "data" / "cal.json").read_text())
    dia = next(d for d in cal["dias"] if d["reel"]["pieza"] == "R1")
    assert dia["reel"]["tiktok"] == {"pieza": "R1-TT", "version": "vtt1", "archivo": "R1-TT_final.mp4", "sha256": "f" * 64, "asset_id": 77,
                                     "release": "piezas-2026-12", "aprobada": fila["fecha"], "aprobacion": "delegada (72 h de veto)",
                                     "de_version": "v1", "duracion_s": 68.0}
    sin = copy.deepcopy(cal); [d["reel"].pop("tiktok", None) for d in sin["dias"]]
    assert sin == antes                                                                          # nada más cambió en el calendario
    # veto del responsable dentro de las 72 h: sale del calendario
    with pytest.raises(tiktok_largo.NoDecidible): decidir.decidir({"trabajos": {}}, "R1-TT", "RECHAZADA", "vtt1", "responsable")
    decidir.decidir({"trabajos": {}}, "R1-TT", "RECHAZADA", "vtt1", "responsable", nota="veto del responsable")
    assert "tiktok" not in next(d for d in json.loads((entorno / "data" / "cal.json").read_text())["dias"] if d["reel"]["pieza"] == "R1")["reel"]


def test_variante_de_otra_version_del_reel_sale_del_calendario(entorno, monkeypatch):
    _registrar_variante(entorno); monkeypatch.setattr(revision, "version", lambda pid, fmt: ("vtt1", "hg", "f" * 64))
    tiktok_largo.decidir("R1-TT", "APROBADA", "vtt1", "Claude", canal="delegada")
    cal = json.loads((entorno / "data" / "cal.json").read_text())
    for d in cal["dias"]:
        if d["reel"]["pieza"] == "R1": d["reel"]["version"] = "v1-nueva"
    (entorno / "data" / "cal.json").write_text(json.dumps(cal, ensure_ascii=False, indent=1) + "\n")
    assert tiktok_largo.al_calendario() == ["2026-12-06 -R1-TT"]


# ── envío a la bandeja de TikTok ─────────────────────────────────────────────────────────────────────────────────
def _dia_con_variante(entorno):
    cal = json.loads((entorno / "data" / "cal.json").read_text())
    dia = next(d for d in cal["dias"] if d["fecha"] == "2026-12-06")
    dia["reel"]["tiktok"] = {"pieza": "R1-TT", "version": "vtt1", "archivo": "R1-TT_final.mp4", "sha256": "f" * 64, "asset_id": 77, "de_version": "v1"}
    (entorno / "data" / "cal.json").write_text(json.dumps(cal, ensure_ascii=False, indent=1) + "\n")
    return dia


def _comprobar_falso(en_veto=(), sin_aprobar=()):
    def comprobar(e, f, ahora=None):
        if e["pieza"] in en_veto: raise publicador.EnPlazoDeVeto(f'{e["pieza"]}: veto')
        if e["pieza"] in sin_aprobar: raise publicador.NoAprobada(f'{e["pieza"]}: no aprobada')
        return True
    return comprobar


def test_tiktok_envia_la_version_larga_aprobada_y_fuera_de_veto(entorno, monkeypatch, tmp_path):
    _dia_con_variante(entorno); bajados = []
    def bajar(e, carpeta, env): bajados.append(e["pieza"]); f = tmp_path / e["archivo"]; f.write_bytes(b"v"); return f
    monkeypatch.setattr(publicador, "texto", lambda p: f"copy de {p}")
    monkeypatch.setattr(publicador, "comprobar", _comprobar_falso())
    r = tiktok.ejecutar("2026-12-06", env={}, bajar=bajar, ahora=AHORA)
    assert r["pieza"] == "R1-TT" and r["variante"] == "larga" and r["estado"] == "SIMULADO" and r["copy"] == "copy de R1" and bajados == ["R1-TT"]
    monkeypatch.setattr(publicador, "comprobar", _comprobar_falso(en_veto=("R1-TT",)))
    r = tiktok.ejecutar("2026-12-06", env={}, bajar=bajar, ahora=AHORA)
    assert r["pieza"] == "R1" and r["variante"] == "reel" and "veto" in r["variante_omitida"]
    monkeypatch.setattr(publicador, "comprobar", _comprobar_falso(sin_aprobar=("R1-TT",)))
    assert tiktok.ejecutar("2026-12-06", env={}, bajar=bajar, ahora=AHORA)["pieza"] == "R1"
    # el responsable vetó el Reel: tampoco sale su versión larga (hereda el contenido) y no se envía nada
    with publicador.APROB.open("a") as h: h.write(json.dumps({"pieza": "R1", "decision": "RECHAZADA", "version": "v1", "fecha": "2026-12-01T00:00:00+00:00"}) + "\n")
    monkeypatch.setattr(publicador, "comprobar", _comprobar_falso(sin_aprobar=("R1",)))
    r = tiktok.ejecutar("2026-12-06", env={}, bajar=bajar, ahora=AHORA)
    assert r["estado"] == "NO_APROBADA" and "R1-TT" in r["variante_omitida"]


def test_tiktok_no_usa_una_variante_de_otra_version_ni_manda_dos_piezas(entorno, monkeypatch, tmp_path):
    dia = _dia_con_variante(entorno)
    def bajar(e, carpeta, env): f = tmp_path / e["archivo"]; f.write_bytes(b"v"); return f
    monkeypatch.setattr(publicador, "texto", lambda p: "copy")
    monkeypatch.setattr(publicador, "comprobar", _comprobar_falso())
    cal = json.loads((entorno / "data" / "cal.json").read_text())
    next(d for d in cal["dias"] if d["fecha"] == "2026-12-06")["reel"]["tiktok"]["de_version"] = "vieja"
    (entorno / "data" / "cal.json").write_text(json.dumps(cal))
    r = tiktok.ejecutar("2026-12-06", env={}, bajar=bajar, ahora=AHORA)
    assert r["pieza"] == "R1" and "otra versión" in r["variante_omitida"]
    _dia_con_variante(entorno)
    # el Reel normal ya está en la bandeja (modo real): no se manda también la versión larga
    real = {"PUBLICAR": "1", "LANZAMIENTO_AUTORIZADO": "SI", "META_PAGE_ID": "1", "META_PAGE_TOKEN": "t", "TIKTOK": "1",
            "TIKTOK_CLIENT_KEY": "k", "TIKTOK_CLIENT_SECRET": "s", "TIKTOK_CLAVE": "c"}
    monkeypatch.setattr(tiktok, "TOKENS", tmp_path / "tt.enc"); tiktok.TOKENS.write_bytes(b"x")
    publicar.registrar({"pieza": "R1", "marca": publicar.marca("R1", "v1") + "-tt", "modo": "real", "fase": "CONFIRMADA", "publish_id": "P0"})
    llamadas = []
    r = tiktok.ejecutar("2026-12-06", env=real, http=lambda *a, **k: llamadas.append(a), bajar=bajar, ahora=AHORA)
    assert r["estado"] == "EN_BANDEJA" and r["pieza"] == "R1" and r["variante"] == "reel" and not llamadas
