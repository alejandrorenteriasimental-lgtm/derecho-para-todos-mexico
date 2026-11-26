"""Documental semanal de YouTube (decisión del responsable, 26-11-2026): esquema y validador del guion, producción técnica
(voz por escena, render 1920x1080, capítulos de los tiempos reales, fuentes, aviso, rótulo «Recreación», miniatura), auditoría,
versión = huella del manifiesto (video + miniatura + guion), aprobación delegada con veto de 72 h y programación en YouTube
como video normal para su fecha a las 12:00 CDMX, sin duplicados. El guion de prueba es FICTICIO (pruebas/datos/documental_prueba)."""
import copy, json, shutil, subprocess, sys, tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import numpy as np
import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "sistema"))
import decidir, documental as dc, esquema_documental as esq, publicador, publicar, render_documental as rd, respaldo, revision, youtube, youtube_semanal as ys

PRUEBA = RAIZ / "pruebas" / "datos" / "documental_prueba" / "guion.json"
PID = "D20261206-prueba"


def guion_prueba():
    return json.loads(PRUEBA.read_text())


def largo(g, factor=9):
    """El guion de prueba con la narración repetida hasta durar lo de un documental real (solo para el validador)."""
    g = copy.deepcopy(g)
    for e in g["escenas"]: e["narracion"] = " ".join([e["narracion"]] * factor)
    return g


# ── esquema ──────────────────────────────────────────────────────────────────────────────────────────────────────
def test_guion_de_prueba_es_ficticio_y_valido():
    g = guion_prueba()
    assert "PRUEBA" in g["titulo"] and "FICTICIO" in g["prueba"] and all("example.org" in f["url"] for f in g["fuentes"])
    assert esq.validar(g, 0.5, 15) == []
    assert any("duración estimada" in e for e in esq.validar(g))          # corto: con los límites reales no pasa
    assert esq.validar(largo(g)) == [] and 6 <= esq.minutos_estimados(largo(g)) <= 15


def test_guion_real_del_primer_documental_es_valido():
    p = RAIZ / "documentales" / "D20261206-T001" / "guion.json"
    if not p.exists(): pytest.skip("sin el guion del primer documental")
    g = json.loads(p.read_text())
    assert esq.validar(g) == []
    assert [c for _, c in esq.capitulos(g)][:2] == ["Prólogo", "Capítulo 1 · La detención"]     # capítulo repetido en cada escena
    assert esq.titulo_corto(g) == "El caso Florence Cassez"                                      # lo que va antes de «:»


@pytest.mark.parametrize("cambio,error", [
    (lambda g: g.update(id="D20261213-prueba"), "no corresponde a la fecha"),
    (lambda g: g.update(id="X1"), "id «X1» inválido"),
    (lambda g: g.update(titulo="x" * 101), "título de 101"),
    (lambda g: g.update(titulo_corto="otra cosa"), "titulo_corto con palabras"),
    (lambda g: g.update(aviso=""), "falta el aviso"),
    (lambda g: [e.update(capitulo=None) for e in g["escenas"][1:]], "al menos 3 capítulos"),
    (lambda g: g["escenas"][0].update(capitulo=None), "primer capítulo debe empezar en la escena 1"),
    (lambda g: g["escenas"][3].update(fuentes=[]), "escena 4: una escena «cita» necesita al menos una fuente"),
    (lambda g: g["escenas"][4].update(fuentes=[]), "escena 5: una escena «dato» necesita al menos una fuente"),
    (lambda g: g["escenas"][3]["fuentes"][0].update(url="https://otra.org/x"), "no está en la lista completa"),
    (lambda g: g["escenas"][3]["fuentes"][0].update(tipo="blog"), "tipo de fuente «blog»"),
    (lambda g: g["escenas"][2]["pantalla"].update(rotulo="Material de archivo"), "rótulo de una recreación"),
    (lambda g: g["escenas"][2]["pantalla"].update(imagen="foto_real.jpg"), "no se admiten imágenes"),
    (lambda g: g["escenas"][0]["pantalla"]["textos"].append("https://example.org/foto.jpg"), "no deben contener URL"),
    (lambda g: g["escenas"][1].update(n=7), "«n» debe ser 2"),
    (lambda g: g["escenas"][1]["pantalla"].update(tipo="video"), "tipo de pantalla «video»"),
    (lambda g: g["escenas"][6]["pantalla"].update(textos=["solo uno"]), "al menos 2 momentos"),
    (lambda g: g["escenas"][6].update(capitulo="Prueba: el comienzo"), "reaparece"),
])
def test_validador_detecta_errores(cambio, error):
    g = guion_prueba(); cambio(g)
    errores = esq.validar(g, 0.5, 15)
    assert any(error in e for e in errores), errores


def test_duracion_estimada_fuera_de_rango():
    assert any("entre 6 y 15 min" in e for e in esq.validar(largo(guion_prueba(), 20)))


def test_capitulos_repetidos_en_cada_escena_cuentan_una_vez():
    g = guion_prueba()
    g["escenas"][1]["capitulo"] = g["escenas"][0]["capitulo"]                      # repetido en la escena siguiente
    assert [n for n, _ in esq.capitulos(g)] == [1, 4, 7]
    assert esq.capitulo_de(g)[3] == "Prueba: el comienzo" and esq.capitulo_de(g)[8] == "Prueba: el desenlace"


# ── piezas de la producción ──────────────────────────────────────────────────────────────────────────────────────
def test_linea_de_tiempo_con_cortinillas_y_respiro():
    g = guion_prueba()
    lt = dc.linea_tiempo(g, [5.0] * 8, [[("x", 0.0, 5.0)]] * 8)
    e = lt["escenas"]
    assert e[0]["cortinilla"] == [dc.INICIO_S, dc.INICIO_S + dc.CORTINILLA_S] and e[0]["voz_inicio"] == pytest.approx(dc.INICIO_S + dc.CORTINILLA_S)
    assert e[1]["cortinilla"] is None and e[1]["inicio"] == pytest.approx(e[0]["voz_fin"] + dc.RESPIRO_S)
    assert [c["n"] for c in lt["capitulos"]] == [1, 4, 7] and e[3]["capitulo"] == "Prueba: lo que dice la norma"
    assert all(a["fin"] == pytest.approx(b["inicio"]) for a, b in zip(e, e[1:]))
    assert lt["total_s"] == pytest.approx(dc.INICIO_S + 3 * dc.CORTINILLA_S + 8 * (5 + dc.RESPIRO_S) + dc.FINAL_S)
    caps = dc.capitulos_video(lt, 5.0)
    assert caps[0]["marca"] == "0:00" and caps[1]["inicio_s"] == pytest.approx(5.0 + e[3]["inicio"])


def test_descripcion_con_capitulos_fuentes_y_aviso():
    g = guion_prueba(); g["aviso"] = "Las recreaciones son ilustraciones."
    caps = [{"marca": "0:00", "titulo": "Uno"}, {"marca": "1:10", "titulo": "Dos"}, {"marca": "3:05", "titulo": "Tres"}]
    d = dc.descripcion_video(g, caps)
    assert d.startswith(g["descripcion"]) and "0:00 Uno\n1:10 Dos\n3:05 Tres" in d
    for f in g["fuentes"]: assert f["referencia"] in d and f["url"] in d
    assert esq.AVISO in d and "Las recreaciones son ilustraciones." in d and "«Recreación»" in d and "Voz generada con IA" in d


def test_textos_y_partes():
    assert rd.capitulo_partes("Capítulo 3 · El efecto corruptor") == ("CAPÍTULO 3", "El efecto corruptor")
    assert rd.capitulo_partes("Prólogo") == ("", "Prólogo")
    assert rd.partir_momento("4:30 a.m. · detención (parte policial)") == ("4:30 a.m.", "detención (parte policial)")
    assert rd.partir_momento("Día 1 | Compra") == ("Día 1", "Compra")
    esc = {"pantalla": {"tipo": "recreacion", "textos": ["RECREACIÓN", "9 de diciembre"]}}
    assert rd.textos_visibles(esc) == ["9 de diciembre"]                       # el rótulo lo pone el render, no se duplica


def test_modo_documental_desactiva_el_video_semanal(tmp_path):
    a = json.loads((RAIZ / "data" / "lanzamiento.json").read_text())
    assert a["YOUTUBE_SEMANAL_MODO"] == "documental"
    assert not ys.activo(date(2026, 12, 10))                                   # youtube-semanal.yml termina sin hacer nada
    f = tmp_path / "l.json"; f.write_text(json.dumps({"YOUTUBE_SEMANAL_DESDE": "2026-12-03"}))
    assert ys.activo(date(2026, 12, 10), f)                                    # sin la bandera, el semanal seguiría igual
    f.write_text(json.dumps({"YOUTUBE_SEMANAL_DESDE": "2026-12-03", "YOUTUBE_SEMANAL_MODO": "documental"}))
    assert not ys.activo(date(2026, 12, 10), f)


def test_miniatura_del_generador_semanal_con_el_titulo_corto(tmp_path):
    g = guion_prueba(); tc = esq.titulo_corto(g)
    mi = ys.miniatura({"tema": tc, "segmentos": []}, tmp_path / "m.png", textos=("", tc))
    assert all(c["resultado"] == "APROBADO" for c in ys.auditar_miniatura(tmp_path / "m.png", mi, g["titulo"]))
    # sin «textos», el video semanal no cambia (mismo antetítulo «N PREGUNTAS»)
    mi2 = ys.miniatura({"tema": "derechos laborales", "segmentos": [{}] * 8}, tmp_path / "s.png")
    assert mi2["textos"][0]["texto"] == "8 PREGUNTAS"


# ── producción completa con voz simulada (tonos) ─────────────────────────────────────────────────────────────────
def voz_falsa(texto, voz):
    sr = 24000; dur = max(1.0, 0.16 * len(texto.split()))
    t = np.arange(int(dur * sr)) / sr
    a = (0.25 * np.sin(2 * np.pi * 180 * t) * (0.6 + 0.4 * np.sin(2 * np.pi * 3 * t))).astype(np.float32)
    return a, sr, [(texto, 0.0, dur)]


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    for d in ("estado", "documentales"): (tmp_path / d).mkdir()
    monkeypatch.setattr(dc, "DIR", tmp_path / "documentales"); monkeypatch.setattr(dc, "REG", tmp_path / "estado" / "documentales.json")
    monkeypatch.setattr(dc, "PRESET", "ultrafast"); monkeypatch.setattr(ys, "FF_TIMEOUT_S", 240)
    monkeypatch.setattr(publicador, "APROB", tmp_path / "estado" / "aprobaciones.jsonl")
    monkeypatch.setattr(publicador, "PAUSA", tmp_path / "estado" / "pausa.json")
    monkeypatch.setattr(revision, "REGISTRO", tmp_path / "estado" / "aprobaciones.jsonl")
    monkeypatch.setattr(respaldo, "MANIFIESTO", tmp_path / "estado" / "respaldo.json")
    monkeypatch.setattr(publicar, "LIBRO", tmp_path / "estado" / "ops.jsonl")
    (tmp_path / "estado" / "aprobaciones.jsonl").write_text("")
    (tmp_path / "documentales" / PID).mkdir(); shutil.copy(PRUEBA, tmp_path / "documentales" / PID / "guion.json")
    return tmp_path


LIMITES = dict(min_min=0.5, max_min=15, dur_min=20, dur_max=900)
_CACHE = {}


def _producir(entorno):
    """Se produce una vez por sesión (≈ 40 s) y se copia a cada entorno."""
    if not _CACHE:
        r = dc.producir(PID, env={}, sintetizar=voz_falsa, **LIMITES)
        copia = Path(tempfile.mkdtemp(prefix="doc_cache_")) / PID
        shutil.copytree(entorno / "documentales" / PID, copia)
        _CACHE.update(r=r, dir=copia, reg=dc.REG.read_text(), resp=respaldo.MANIFIESTO.read_text())
        return r
    shutil.rmtree(entorno / "documentales" / PID); shutil.copytree(_CACHE["dir"], entorno / "documentales" / PID)
    dc.REG.write_text(_CACHE["reg"]); respaldo.MANIFIESTO.write_text(_CACHE["resp"])
    return _CACHE["r"]


def test_produce_audita_respalda_y_queda_en_revision(entorno):
    r = _producir(entorno)
    assert r["estado"] == "REVISION_HUMANA", r
    sal = entorno / "documentales" / PID / "salida"
    tec = json.loads((sal / "auditoria.json").read_text())["tecnica"]
    assert all(c["resultado"] == "APROBADO" for c in tec), [c for c in tec if c["resultado"] != "APROBADO"]
    nombres = " | ".join(c["control"] for c in tec)
    for clave in ("1920x1080", "30 cuadros", "AAC 48 kHz", "-14 LUFS", "Capítulos: al menos 3", "Fuentes completas", "Rótulo «Recreación»",
                  "Subtítulos quemados", "Aviso en pantalla", "Miniatura 1280x720", "SHA-256"):
        assert clave in nombres, clave
    m = json.loads(dc.manifiesto_path(PID).read_text())
    assert m["capitulos"][0]["marca"] == "0:00" and len(m["capitulos"]) == 3 and m["publicar_en"] == "2026-12-06T12:00:00-06:00"
    assert m["capitulos"][1]["inicio_s"] == pytest.approx(m["intro_s"] + dc.linea_tiempo(guion_prueba(), [1] * 8)["escenas"][3]["inicio"], abs=30)
    assert all(f'{c["marca"]} {c["titulo"]}' in m["descripcion"] for c in m["capitulos"])
    assert m["guion"]["sha256"] == respaldo.sha256(entorno / "documentales" / PID / "guion.json")
    resp = respaldo.cargar()[PID]
    assert resp[f"{PID}_final.mp4"]["sha256"] == m["video"]["sha256"] and resp[f"{PID}_miniatura.png"]["sha256"] == m["miniatura"]["sha256"]
    assert f"{PID}_final.srt" in resp and "auditoria.json" in resp
    v = dc.cargar()[PID]
    assert v["revision"]["version"] == dc.version(PID)[0] and v["revision"]["huella_archivo"] == m["video"]["sha256"]
    assert not (entorno / "documentales" / PID / "tmp").exists()
    info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(sal / f"{PID}_final.mp4")], capture_output=True, text=True).stdout)
    vs = next(s for s in info["streams"] if s["codec_type"] == "video"); assert (vs["width"], vs["height"], vs["codec_name"]) == (1920, 1080, "h264")
    assert [x["pieza"] for x in dc.pendientes()] == [PID]


def test_version_cambia_si_cambia_el_guion_el_video_o_la_miniatura(entorno):
    _producir(entorno)
    ver = dc.version(PID)[0]; assert ver
    gp = entorno / "documentales" / PID / "guion.json"; orig = gp.read_text()
    gp.write_text(orig.replace("Fin de la prueba.", "Fin de la prueba técnica."))
    assert dc.version(PID)[0] is None                                          # guion editado: hay que volver a producir
    with pytest.raises(ValueError): decidir.decidir({"trabajos": {}}, PID, "APROBADA", ver, "Claude", canal="delegada")
    gp.write_text(orig); assert dc.version(PID)[0] == ver
    r = json.loads(respaldo.MANIFIESTO.read_text()); r[PID][f"{PID}_miniatura.png"]["sha256"] = "0" * 64; respaldo.MANIFIESTO.write_text(json.dumps(r))
    assert dc.version(PID)[0] is None


def test_guion_invalido_no_se_produce(entorno):
    gp = entorno / "documentales" / PID / "guion.json"; g = json.loads(gp.read_text()); g["escenas"][3]["fuentes"] = []
    gp.write_text(json.dumps(g, ensure_ascii=False))
    r = dc.producir(PID, env={}, sintetizar=voz_falsa, **LIMITES)
    assert r["estado"] == "INVALIDO" and any("necesita al menos una fuente" in e for e in r["errores"])
    assert dc.cargar()[PID]["estado"] == "INVALIDO" and not (entorno / "documentales" / PID / "salida").exists()
    assert dc.producir("../otro", env={})["estado"] == "ID_INVALIDO"


def test_rotulo_de_recreacion_ausente_retiene_el_video(entorno, monkeypatch):
    """Si el render dejara de dibujar el rótulo «Recreación», la auditoría (que lo mide en los píxeles) lo retiene."""
    gp = entorno / "documentales" / PID / "guion.json"; g = json.loads(gp.read_text())
    g["escenas"] = g["escenas"][:4]; g["escenas"][3]["capitulo"] = "Prueba: lo que dice la norma"
    g["escenas"][1]["capitulo"] = "Prueba: la pregunta"; gp.write_text(json.dumps(g, ensure_ascii=False))
    monkeypatch.setattr(rd, "_rotulo", lambda d: list(rd.ROTULO_CAJA))
    r = dc.producir(PID, env={}, sintetizar=voz_falsa, min_min=0.2, max_min=15, dur_min=10, dur_max=900)
    assert r["estado"] == "RETENIDO" and any("Rótulo" in f for f in r["fallas"]), r


def test_no_se_modifica_un_documental_aprobado(entorno, monkeypatch):
    _producir(entorno); ver = dc.version(PID)[0]
    monkeypatch.setattr(revision, "_ahora", lambda: "2026-12-02T14:00:00+00:00")
    decidir.decidir({"trabajos": {}}, PID, "APROBADA", ver, "Claude (revisión editorial delegada)", canal="delegada")
    assert dc.cargar()[PID]["estado"] == "APROBADA"
    assert dc.producir(PID, env={}, sintetizar=voz_falsa, **LIMITES)["estado"] == "YA_APROBADO"
    fila = [json.loads(l) for l in publicador.APROB.read_text().splitlines()][-1]
    assert fila["pieza"] == PID and fila["canal"] == "delegada" and fila["version"] == ver and fila["huella_archivo"] == dc.cargar()[PID]["sha256"]


# ── programación ─────────────────────────────────────────────────────────────────────────────────────────────────
class HttpYT:
    def __init__(self): self.llamadas = []; self.cabeceras = []
    def __call__(self, metodo, url, cab=None, datos=None, timeout=60):
        self.llamadas.append((metodo, url, datos)); self.cabeceras.append(cab or {})
        if url == youtube.TOKEN_URL: return 200, b'{"access_token": "A"}'
        if url.startswith(youtube.MINIATURA_URL): return 200, b'{"items": [{}]}'
        if metodo == "POST": return 200, json.dumps({"location": "https://subida/1"}).encode()
        return 200, json.dumps({"id": "DOC1", "status": {"privacyStatus": "private"}}).encode()


REAL = {"PUBLICAR": "1", "LANZAMIENTO_AUTORIZADO": "SI", "META_PAGE_ID": "1", "META_PAGE_TOKEN": "t",
        "YOUTUBE": "1", "YT_CLIENT_ID": "c", "YT_CLIENT_SECRET": "s", "YT_REFRESH_TOKEN": "r", "PUBLICAR_HASTA": "2027-02-20"}


def _aprobado(entorno, monkeypatch, fecha):
    _producir(entorno); ver = dc.version(PID)[0]
    monkeypatch.setattr(revision, "_ahora", lambda: fecha)
    decidir.decidir({"trabajos": {}}, PID, "APROBADA", ver, "Claude (revisión editorial delegada)", canal="delegada")
    sal = entorno / "documentales" / PID / "salida"
    return ver, (lambda e, carpeta, env: sal / e["archivo"])


def _cargas(h):
    return [d for m, u, d in h.llamadas if m == "POST" and u.startswith(youtube.CARGA_URL.split("?")[0])]


def test_programa_su_fecha_a_las_12_como_video_normal_y_sin_duplicar(entorno, monkeypatch):
    ver, bajar = _aprobado(entorno, monkeypatch, "2026-12-02T14:00:00+00:00")          # miércoles 08:00 CDMX
    h = HttpYT()
    r = dc.programar(ahora=datetime(2026, 12, 4, 17, 7, tzinfo=timezone.utc), env=REAL, http=h, bajar=bajar)   # viernes: aún en veto
    assert r["acciones"][0]["estado"] == "EN_PLAZO_DE_VETO" and not h.llamadas
    r = dc.programar(ahora=datetime(2026, 12, 6, 17, 7, tzinfo=timezone.utc), env=REAL, http=h, bajar=bajar)   # domingo 11:07
    assert r["acciones"][0]["estado"] == "PROGRAMADO" and r["acciones"][0]["miniatura"] == "PUESTA" and "tarde" not in r["acciones"][0]
    meta = json.loads(_cargas(h)[0])
    m = json.loads(dc.manifiesto_path(PID).read_text())
    assert meta["status"]["publishAt"] == "2026-12-06T18:00:00Z" and meta["status"]["privacyStatus"] == "private"
    assert meta["snippet"]["title"] == m["titulo"] and meta["snippet"]["description"].startswith(m["descripcion"][:200])
    assert "0:00 " in meta["snippet"]["description"] and "#shorts" not in meta["snippet"]["description"].lower()
    mins = [(d, c) for (mt, u, d), c in zip(h.llamadas, h.cabeceras) if u.startswith(youtube.MINIATURA_URL)]
    assert len(mins) == 1 and "videoId=DOC1" in [u for mt, u, d in h.llamadas if u.startswith(youtube.MINIATURA_URL)][0]
    import hashlib; assert hashlib.sha256(mins[0][0]).hexdigest() == m["miniatura"]["sha256"]
    v = dc.cargar()[PID]; assert v["estado"] == "PROGRAMADO" and v["video_id"] == "DOC1"
    n = len(h.llamadas)
    dc.programar(ahora=datetime(2026, 12, 7, 17, 7, tzinfo=timezone.utc), env=REAL, http=h, bajar=bajar)
    assert len(h.llamadas) == n                                                                         # nunca dos veces
    assert publicar.operacion(publicar.marca(PID, ver) + "-yt", "real")["formato"] == "video_largo"


def test_veto_tardio_lunes_simulacion_espera_y_limites(entorno, monkeypatch):
    ver, bajar = _aprobado(entorno, monkeypatch, "2026-12-03T22:00:00+00:00")          # el veto termina el domingo 16:00 CDMX
    r = dc.programar(ahora=datetime(2026, 11, 27, 17, 7, tzinfo=timezone.utc), env=REAL, http=HttpYT(), bajar=bajar)
    assert r["acciones"][0]["estado"] == "EN_ESPERA"                                    # más de 8 días antes de su fecha
    assert dc.programar(ahora=datetime(2026, 12, 6, 17, 7, tzinfo=timezone.utc), env=REAL, http=HttpYT(), bajar=bajar)["acciones"][0]["estado"] == "EN_PLAZO_DE_VETO"
    r = dc.programar(ahora=datetime(2026, 12, 7, 17, 7, tzinfo=timezone.utc), env={}, http=HttpYT(), bajar=bajar)
    assert r["acciones"][0]["estado"] == "SIMULADO" and dc.cargar()[PID]["estado"] == "APROBADA"
    r = dc.programar(ahora=datetime(2026, 12, 7, 17, 7, tzinfo=timezone.utc), env={**REAL, "PUBLICAR_HASTA": "2026-12-01"}, http=HttpYT(), bajar=bajar)
    assert r["acciones"][0]["estado"] == "SIN_AUTORIZACION_DE_PUBLICACION"
    h = HttpYT()
    r = dc.programar(ahora=datetime(2026, 12, 7, 17, 7, tzinfo=timezone.utc), env=REAL, http=h, bajar=bajar)
    assert r["acciones"][0]["estado"] == "PROGRAMADO" and r["acciones"][0]["tarde"] is True
    assert json.loads(_cargas(h)[0])["status"]["publishAt"] == "2026-12-07T18:00:00Z"


def test_veto_del_responsable_y_pausa(entorno, monkeypatch):
    ver, bajar = _aprobado(entorno, monkeypatch, "2026-12-02T14:00:00+00:00")
    with pytest.raises(ValueError): decidir.decidir({"trabajos": {}}, PID, "RECHAZADA", ver, "responsable")      # sin motivo
    decidir.decidir({"trabajos": {}}, PID, "RECHAZADA", ver, "responsable", nota="veto del responsable")
    h = HttpYT()
    assert dc.programar(ahora=datetime(2026, 12, 6, 17, 7, tzinfo=timezone.utc), env=REAL, http=h, bajar=bajar)["acciones"] == [] and not h.llamadas
    publicador.PAUSA.write_text(json.dumps({"motivo": "prueba"}))
    assert dc.programar(env=REAL, http=HttpYT())["pausa"] == "prueba"


def test_archivo_distinto_del_aprobado_no_se_sube(entorno, monkeypatch, tmp_path):
    ver, bajar = _aprobado(entorno, monkeypatch, "2026-12-02T14:00:00+00:00")
    otro = tmp_path / f"{PID}_final.mp4"; otro.write_bytes(b"no es el aprobado")
    h = HttpYT()
    r = dc.programar(ahora=datetime(2026, 12, 6, 17, 7, tzinfo=timezone.utc), env=REAL, http=h,
                     bajar=lambda e, c, env: otro if e["archivo"].endswith(".mp4") else bajar(e, c, env))
    assert r["acciones"][0]["estado"] == "NO_APROBADA" and not _cargas(h)


# ── voz real (solo si los modelos están descargados; en CI se omite) ─────────────────────────────────────────────
@pytest.mark.skipif(not (RAIZ / "models" / "kokoro-v1.0.int8.onnx").exists(), reason="sin modelos de voz")
def test_voz_de_la_marca_por_escena():
    a, sr, ors = dc.voz_escena("Esta es una prueba de la voz de la marca.", dc.voz_marca())
    assert sr == 24000 and 1.0 < len(a) / sr < 6 and ors and ors[0][2] <= len(a) / sr + 0.01
