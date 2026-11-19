"""Video largo semanal de YouTube (decisión del responsable, 16-11-2026): solo Reels aprobados y ya publicados, agrupados por
rama; 1920x1080 con intro y cierre de marca; capítulos desde 0:00 y fuentes oficiales; auditoría técnica; aprobación propia
con veto de 72 h; programación como video normal el domingo 12:00 CDMX, sin duplicados."""
import json, subprocess, sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sistema"))
import decidir, publicador, publicar, respaldo, revision, youtube, youtube_semanal as ys

DOCS = {"LFT": ("Ley Federal del Trabajo", "https://www.diputados.gob.mx/LeyesBiblio/pdf/LFT.pdf"),
        "CPEUM": ("Constitución Política de los Estados Unidos Mexicanos", "https://www.diputados.gob.mx/LeyesBiblio/pdf/CPEUM.pdf"),
        "LFPC": ("Ley Federal de Protección al Consumidor", "https://www.diputados.gob.mx/LeyesBiblio/pdf/LFPC.pdf")}


def guion(pid, sigla, art, titulo):
    doc, url = DOCS[sigla]
    return {"id": pid, "titulo": titulo, "tema_id": "T" + pid[-3:], "fuentes": {"F1": {"documento": doc, "articulo": art, "url": url}},
            "escenas": [{"tipo": "gancho", "texto": titulo}, {"tipo": "cita", "texto": "…", "cita": "…", "afirmaciones": [{"id": "A1", "fuente": "F1"}]}]}


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    raiz = tmp_path
    for d in ("estado", "data", "registro", "piezas", "semanal"): (raiz / d).mkdir()
    for k, v in {"RAIZ": raiz, "REG": raiz / "estado" / "youtube_semanal.json", "DIR": raiz / "semanal", "CAL": raiz / "data" / "cal.json",
                 "AUT": raiz / "data" / "lanzamiento.json", "PIEZAS": raiz / "registro" / "piezas.jsonl"}.items():
        monkeypatch.setattr(ys, k, v)
    monkeypatch.setattr(ys, "_SIGLAS", {ys._plano(d): s for s, (d, _) in DOCS.items()})
    monkeypatch.setattr(publicador, "APROB", raiz / "estado" / "aprobaciones.jsonl")
    monkeypatch.setattr(publicador, "PAUSA", raiz / "estado" / "pausa.json")
    monkeypatch.setattr(revision, "REGISTRO", raiz / "estado" / "aprobaciones.jsonl")
    monkeypatch.setattr(respaldo, "MANIFIESTO", raiz / "estado" / "respaldo.json")
    monkeypatch.setattr(publicar, "LIBRO", raiz / "estado" / "ops.jsonl")
    (raiz / "data" / "lanzamiento.json").write_text(json.dumps({"YOUTUBE_SEMANAL_DESDE": "2026-12-03"}))
    # 26-11 a 9-12: laboral (LFT) casi todos los días; Constitución arts. 16 y 20 (justicia penal) y 8 (petición)
    plan = [("2026-11-20", "LFT", "88"), ("2026-11-21", "LFT", "69"), ("2026-11-22", "CPEUM", "16"), ("2026-11-23", "LFT", "76"),
            ("2026-11-24", "LFT", "87"), ("2026-11-25", "CPEUM", "8"), ("2026-11-26", "LFT", "47"), ("2026-11-27", "LFT", "48"),
            ("2026-11-28", "CPEUM", "20"), ("2026-11-29", "LFT", "132"), ("2026-11-30", "LFPC", "7"), ("2026-12-01", "LFT", "74"),
            ("2026-12-02", "LFT", "61"), ("2026-12-03", "LFT", "62"), ("2026-12-04", "LFT", "63")]
    dias, filas, durs = [], [], []
    for i, (f, sigla, art) in enumerate(plan):
        pid = f"R{f.replace('-', '')}-T{i:03d}"
        (raiz / "piezas" / pid).mkdir(); (raiz / "piezas" / pid / "guion.json").write_text(json.dumps(guion(pid, sigla, art, f"¿Pregunta {i} sobre {sigla} {art}?"), ensure_ascii=False))
        e = {"pieza": pid, "version": f"v{i}", "hora": "19:00", "archivo": f"{pid}_final.mp4", "sha256": f"{i:x}" * 64, "asset_id": 1000 + i}
        dias.append({"fecha": f, "reel": e})
        filas.append({"pieza": pid, "decision": "APROBADA", "version": f"v{i}", "huella_archivo": e["sha256"], "fecha": "2026-11-10T00:00:00+00:00", "canal": "delegada"})
        durs.append({"id": pid, "duracion_s": 70.0})
    # 27-11: aprobación delegada que vencía DESPUÉS de su hora (no pudo publicarse); 26-11: otra versión aprobada que la del calendario
    filas[7]["fecha"] = "2026-11-26T12:00:00+00:00"; filas[6]["version"] = "otra"
    (raiz / "data" / "cal.json").write_text(json.dumps({"dias": dias}, ensure_ascii=False, indent=1) + "\n")
    (raiz / "estado" / "aprobaciones.jsonl").write_text("".join(json.dumps(x) + "\n" for x in filas))
    (raiz / "registro" / "piezas.jsonl").write_text("".join(json.dumps(x) + "\n" for x in durs))
    return raiz


def test_rama_de_cada_reel():
    assert ys.rama_de(guion("R1", "LFT", "88", "?")) == "laboral"
    assert ys.rama_de(guion("R1", "CPEUM", "16", "?")) == "penal" and ys.rama_de(guion("R1", "CPEUM", "8", "?")) == "constitucional"
    assert ys.rama_de(guion("R1", "LFPC", "7", "?")) == "consumidor"


def test_id_y_fechas():
    assert ys.domingo_de(date(2026, 12, 4)) == date(2026, 12, 6) and ys.domingo_de(date(2026, 12, 6)) == date(2026, 12, 6)
    assert ys.id_semana(date(2026, 12, 6)) == "Y20261206-SEM" and ys.es_semanal("Y20261206-SEM") and not ys.es_semanal("R20261206-T001")
    assert ys.hora_publicacion(date(2026, 12, 6)).astimezone(timezone.utc) == datetime(2026, 12, 6, 18, 0, tzinfo=timezone.utc)
    assert json.loads((Path(ys.__file__).resolve().parent.parent / "data" / "lanzamiento.json").read_text())["YOUTUBE_SEMANAL_DESDE"] == "2026-12-03"


def test_seleccion_solo_aprobados_y_publicados_de_la_rama(entorno):
    cal = json.loads(ys.CAL.read_text())
    s = ys.seleccionar(cal, date(2026, 12, 3), {})
    piezas = [x["pieza"] for x in s["segmentos"]]
    assert s["rama"] == "laboral" and s["tema"] == "derechos laborales"
    assert all(x["rama"] == "laboral" for x in s["segmentos"])
    assert not any("20261203" in p or "20261204" in p for p in piezas)                       # hoy y después: aún no publicados
    assert not any("20261126" in p or "20261127" in p for p in piezas)                       # otra versión aprobada / veto vencido tarde
    assert any(p.startswith("R2026112") and x["fecha"] < "2026-11-26" for p, x in zip(piezas, s["segmentos"]))   # completó con anteriores
    assert ys.DUR_MIN <= s["duracion_estimada"] <= ys.DUR_MAX
    # sin autorización de publicación antes de una fecha (PUBLICAR_DESDE): esos días no cuentan como publicados
    s2 = ys.seleccionar(cal, date(2026, 12, 3), {"PUBLICAR_DESDE": "2026-11-28"})
    assert s2.get("insuficiente") and "laboral" in s2["insuficiente"]


def test_capitulos_descripcion_y_controles():
    segs = [{"pieza": f"R{i}", "titulo": f"¿Pregunta {i}?", "fuentes": [{"documento": "Ley Federal del Trabajo", "articulo": str(80 + i), "url": "https://u", "sigla": "LFT"}]}
            for i in range(3)]
    sel = {"rama": "laboral", "tema": "derechos laborales", "segmentos": segs}
    caps = ys.capitulos(segs, [40.0, 35.5, 42.0])
    assert [c["marca"] for c in caps] == ["0:00", "0:45", "1:20"]
    m = {"titulo": ys.titulo_video(sel), "capitulos": caps, "descripcion": ys.descripcion_video(sel, caps), "segmentos": segs}
    assert m["titulo"] == "3 preguntas sobre derechos laborales: lo que dice la ley en México"
    assert "0:00 ¿Pregunta 0?" in m["descripcion"] and "Ley Federal del Trabajo, artículo 81 (https://u)" in m["descripcion"]
    assert "Información general, no asesoría legal." in m["descripcion"] and "según tu estado" not in m["descripcion"]
    ok = ys.controles_metadatos(m, 128.5)
    assert all(c["resultado"] == "APROBADO" for c in ok), ok
    malos = ys.controles_metadatos({**m, "capitulos": caps[:2], "descripcion": m["descripcion"].replace("Información general, no asesoría legal.", "")}, 128.5)
    fallas = {c["control"] for c in malos if c["resultado"] == "FALLA"}
    assert any("al menos 3" in f for f in fallas) and any("Aviso" in f for f in fallas)
    sin_fuente = ys.controles_metadatos({**m, "segmentos": segs + [{"pieza": "R9", "fuentes": []}]}, 128.5)
    assert any(c["resultado"] == "FALLA" and "Fuentes" in c["control"] for c in sin_fuente)


def _reel_sintetico(f, seg=11):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc2=s=1080x1920:r=30:d={seg}", "-f", "lavfi",
                    "-i", f"sine=frequency=330:duration={seg}:sample_rate=48000", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-ar", "48000", "-ac", "2", "-shortest", str(f)], check=True)
    return f


@pytest.fixture
def corto(entorno, monkeypatch):
    """Video de prueba de ~45 s en lugar de 8 a 10 min (misma lógica, límites reducidos)."""
    monkeypatch.setattr(ys, "DUR_MIN", 30.0); monkeypatch.setattr(ys, "DUR_MAX", 60.0); monkeypatch.setattr(ys, "PRESET", "ultrafast"); monkeypatch.setattr(ys, "FF_TIMEOUT_S", 240)
    ys.PIEZAS.write_text("".join(json.dumps({"id": d["reel"]["pieza"], "duracion_s": 11.0}) + "\n" for d in json.loads(ys.CAL.read_text())["dias"]))
    fuente = _reel_sintetico(entorno / "base.mp4")
    def bajar(e, carpeta, env):
        Path(carpeta).mkdir(parents=True, exist_ok=True); f = Path(carpeta) / e["archivo"]; f.write_bytes(fuente.read_bytes()); return f
    monkeypatch.setattr(publicador, "comprobar", lambda e, f, ahora=None: True)
    return bajar


def test_arma_audita_respalda_y_queda_en_revision(entorno, corto):
    hoy = date(2026, 12, 3)
    assert ys.armar(hoy=date(2026, 11, 26), env={}, bajar=corto)["estado"] == "INACTIVO"
    _armar_una_vez(entorno, corto)                     # (armado real con ffmpeg; las demás pruebas reutilizan este video)
    r = _CACHE["resultado"]
    assert r["estado"] == "REVISION_HUMANA", r
    assert r["pieza"] == "Y20261206-SEM" and r["rama"] == "laboral" and r["segmentos"] >= 3
    m = json.loads((entorno / "semanal" / "Y20261206-SEM" / "manifiesto.json").read_text())
    assert m["capitulos"][0]["marca"] == "0:00" and m["publicar_en"].startswith("2026-12-06T12:00") and m["domingo"] == "2026-12-06"
    mp4 = entorno / "semanal" / "Y20261206-SEM" / "salida" / "Y20261206-SEM_final.mp4"
    info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(mp4)], capture_output=True, text=True).stdout)
    v = next(s for s in info["streams"] if s["codec_type"] == "video"); assert (v["width"], v["height"]) == (1920, 1080)
    reg = ys.cargar()["Y20261206-SEM"]
    assert reg["revision"]["version"] == ys.version("Y20261206-SEM")[0] and reg["sha256"] == respaldo.sha256(mp4)
    assert all(c["resultado"] == "APROBADO" for c in json.loads((mp4.parent / "auditoria.json").read_text())["tecnica"])
    assert not (entorno / "semanal" / "Y20261206-SEM" / "reels").exists()                       # los Reels descargados no se guardan
    assert ys.armar(hoy=hoy, env={}, bajar=corto)["estado"] == "YA_ARMADO"                      # idempotente
    assert [x["pieza"] for x in ys.pendientes()] == ["Y20261206-SEM"]


class HttpYT:
    def __init__(self, fallas_miniatura=0):
        self.llamadas = []; self.cabeceras = []; self.fallas_miniatura = fallas_miniatura
    def __call__(self, metodo, url, cab=None, datos=None, timeout=60):
        self.llamadas.append((metodo, url, datos)); self.cabeceras.append(cab or {})
        if url == youtube.TOKEN_URL: return 200, b'{"access_token": "A"}'
        if url.startswith(youtube.MINIATURA_URL):
            if self.fallas_miniatura:
                self.fallas_miniatura -= 1; return 500, b'{"error": {"message": "backendError"}}'
            return 200, json.dumps({"items": [{"default": {"url": "https://i.ytimg.com/x.jpg"}}]}).encode()
        if metodo == "POST": return 200, json.dumps({"location": "https://subida/1"}).encode()
        return 200, json.dumps({"id": "LARGO1", "status": {"privacyStatus": "private"}}).encode()


_comprobar_real = publicador.comprobar
REAL = {"PUBLICAR": "1", "LANZAMIENTO_AUTORIZADO": "SI", "META_PAGE_ID": "1", "META_PAGE_TOKEN": "t",
        "YOUTUBE": "1", "YT_CLIENT_ID": "c", "YT_CLIENT_SECRET": "s", "YT_REFRESH_TOKEN": "r"}


_CACHE = {}


def _armar_una_vez(entorno, corto):
    """El video se arma una sola vez por sesión de pruebas y se copia a cada entorno (armarlo tarda ~30 s)."""
    import shutil, tempfile
    if not _CACHE:
        r = ys.armar(hoy=date(2026, 12, 3), env={}, bajar=corto)
        assert r["estado"] == "REVISION_HUMANA", r          # 17-11: el motivo del error (p. ej. ffmpeg colgado) queda visible en CI
        copia = Path(tempfile.mkdtemp(prefix="ys_cache_")) / "Y20261206-SEM"     # copia aparte: una prueba puede alterar la suya
        shutil.copytree(entorno / "semanal" / "Y20261206-SEM", copia)
        _CACHE.update(resultado=r, dir=copia, reg=ys.REG.read_text(), resp=respaldo.MANIFIESTO.read_text())
        return
    shutil.copytree(_CACHE["dir"], entorno / "semanal" / "Y20261206-SEM")
    ys.REG.write_text(_CACHE["reg"]); respaldo.MANIFIESTO.write_text(_CACHE["resp"])


def _armado_y_aprobado(entorno, corto, monkeypatch, fecha_aprob):
    _armar_una_vez(entorno, corto)
    pid = "Y20261206-SEM"; ver = ys.cargar()[pid]["revision"]["version"]
    monkeypatch.setattr(revision, "_ahora", lambda: fecha_aprob)
    with pytest.raises(ValueError): decidir.decidir({"trabajos": {}}, pid, "APROBADA", "0" * 16, "Claude")
    decidir.decidir({"trabajos": {}}, pid, "APROBADA", ver, "Claude (revisión editorial delegada)", canal="delegada")
    monkeypatch.setattr(publicador, "comprobar", _comprobar_real)          # programar comprueba aprobación, veto y huella de verdad
    salida = entorno / "semanal" / pid / "salida"
    return pid, ver, (lambda e, carpeta, env: salida / e["archivo"])           # el archivo pedido (video o miniatura)


def test_programa_el_domingo_a_las_12_despues_del_veto_y_sin_duplicar(entorno, corto, monkeypatch):
    pid, ver, bajar = _armado_y_aprobado(entorno, corto, monkeypatch, "2026-12-03T14:00:00+00:00")   # jueves 08:00 CDMX
    h = HttpYT()
    r = ys.programar(ahora=datetime(2026, 12, 5, 17, 7, tzinfo=timezone.utc), env=REAL, http=h, bajar=bajar)   # sábado: aún en veto
    assert r["acciones"][0]["estado"] == "EN_PLAZO_DE_VETO" and not h.llamadas
    r = ys.programar(ahora=datetime(2026, 12, 6, 17, 7, tzinfo=timezone.utc), env=REAL, http=h, bajar=bajar)   # domingo 11:07
    assert r["acciones"][0]["estado"] == "PROGRAMADO" and "tarde" not in r["acciones"][0]
    meta = json.loads(next(d for m, u, d in h.llamadas if m == "POST" and u.startswith(youtube.CARGA_URL.split("?")[0])))
    assert meta["status"]["publishAt"] == "2026-12-06T18:00:00Z" and meta["status"]["privacyStatus"] == "private"
    m = json.loads((entorno / "semanal" / pid / "manifiesto.json").read_text())
    assert meta["snippet"]["title"] == m["titulo"] and "0:00 " in meta["snippet"]["description"]
    assert ys.cargar()[pid]["estado"] == "PROGRAMADO" and ys.cargar()[pid]["video_id"] == "LARGO1"
    n = len(h.llamadas)
    ys.programar(ahora=datetime(2026, 12, 7, 17, 7, tzinfo=timezone.utc), env=REAL, http=h, bajar=bajar)
    assert len(h.llamadas) == n                                                                  # no se sube dos veces
    op = publicar.operacion(publicar.marca(pid, ver) + "-yt", "real")
    assert op["fase"] == "CONFIRMADA" and op["formato"] == "video_largo"


def test_veto_que_termina_tarde_se_programa_el_lunes_y_simulacion_no_cambia_el_estado(entorno, corto, monkeypatch):
    pid, ver, bajar = _armado_y_aprobado(entorno, corto, monkeypatch, "2026-12-03T22:00:00+00:00")   # jueves 16:00 CDMX
    r = ys.programar(ahora=datetime(2026, 12, 6, 17, 7, tzinfo=timezone.utc), env=REAL, http=HttpYT(), bajar=bajar)
    assert r["acciones"][0]["estado"] == "EN_PLAZO_DE_VETO"
    r = ys.programar(ahora=datetime(2026, 12, 7, 17, 7, tzinfo=timezone.utc), env={}, http=HttpYT(), bajar=bajar)
    assert r["acciones"][0]["estado"] == "SIMULADO" and ys.cargar()[pid]["estado"] == "APROBADA"
    h = HttpYT()
    r = ys.programar(ahora=datetime(2026, 12, 7, 17, 7, tzinfo=timezone.utc), env=REAL, http=h, bajar=bajar)
    assert r["acciones"][0]["estado"] == "PROGRAMADO" and r["acciones"][0]["tarde"] is True
    meta = json.loads(next(d for m, u, d in h.llamadas if m == "POST" and u.startswith(youtube.CARGA_URL.split("?")[0])))
    assert meta["status"]["publishAt"] == "2026-12-07T18:00:00Z"


def test_veto_del_responsable_impide_programar(entorno, corto, monkeypatch):
    pid, ver, bajar = _armado_y_aprobado(entorno, corto, monkeypatch, "2026-12-03T14:00:00+00:00")
    with pytest.raises(ValueError): decidir.decidir({"trabajos": {}}, pid, "RECHAZADA", ver, "responsable")      # sin motivo
    decidir.decidir({"trabajos": {}}, pid, "RECHAZADA", ver, "responsable", nota="veto del responsable")
    h = HttpYT()
    assert ys.programar(ahora=datetime(2026, 12, 6, 17, 7, tzinfo=timezone.utc), env=REAL, http=h, bajar=bajar)["acciones"] == [] and not h.llamadas


def test_pausa_de_emergencia(entorno):
    publicador.PAUSA.write_text(json.dumps({"motivo": "prueba"}))
    assert ys.programar(env=REAL, http=HttpYT())["pausa"] == "prueba"


def test_falla_al_descargar_queda_registrada_y_se_puede_repetir(entorno, corto):
    def bajar_falla(e, carpeta, env): raise OSError("sin red")
    r = ys.armar(hoy=date(2026, 12, 3), env={}, bajar=bajar_falla)
    assert r["estado"] == "ERROR" and "sin red" in ys.cargar()["Y20261206-SEM"]["motivo"]
    assert ys.seleccionar(json.loads(ys.CAL.read_text()), date(2026, 12, 3), {})["segmentos"]           # se puede volver a armar
    def bajar_no_aprobado(e, carpeta, env): raise publicador.NoAprobada("huella distinta")
    assert ys.armar(hoy=date(2026, 12, 3), env={}, bajar=bajar_no_aprobado)["estado"] == "ERROR"      # nunca con un archivo no aprobado


def test_ffmpeg_sin_stdin_con_limite_y_fondo_acotado(monkeypatch, tmp_path):
    """Regresión 17-11-2026 (ciclo 44063222044 colgado en las pruebas): cada ffmpeg corre con -nostdin, sin heredar la
    entrada estándar y con tiempo límite; el fondo en bucle infinito del segmento queda acotado por trim a la duración."""
    vistos = []
    def falso(cmd, **kw):
        vistos.append((cmd, kw)); return subprocess.CompletedProcess(cmd, 0, "", "")
    monkeypatch.setattr(ys.subprocess, "run", falso)
    ys._parte_reel(tmp_path / "f.png", tmp_path / "r.mp4", 12.5, tmp_path / "s.mp4")
    cmd, kw = vistos[-1]
    assert cmd[:2] == ["ffmpeg", "-nostdin"] and kw["stdin"] is subprocess.DEVNULL and kw["timeout"] == ys.FF_TIMEOUT_S
    grafo = cmd[cmd.index("-filter_complex") + 1]
    assert "loop=loop=-1" in grafo and "trim=duration=12.500[bg]" in grafo
    def cuelga(cmd, **kw): raise subprocess.TimeoutExpired(cmd, kw.get("timeout"))
    monkeypatch.setattr(ys.subprocess, "run", cuelga)
    with pytest.raises(RuntimeError, match="no terminó"):
        ys._ff(["-i", "x", "y"])


def test_audio_de_tarjeta_con_relleno_acotado(monkeypatch, tmp_path):
    """17-11-2026: «apad» infinito colgaba ffmpeg (master de BtbN) de forma intermitente; el relleno debe tener duración fija."""
    llamadas = []
    monkeypatch.setattr(ys, "_ff", lambda args: llamadas.append(args))
    import musica
    monkeypatch.setattr(musica, "pad", lambda dur, salida: Path(salida).write_bytes(b""))
    ys._parte_tarjeta(tmp_path / "x.png", 5.0, tmp_path / "t.mp4")
    filtro = llamadas[0][llamadas[0].index("-filter_complex") + 1]
    assert "apad=whole_dur=5.000" in filtro and "apad," not in filtro


# ── miniatura personalizada (19-11-2026) ─────────────────────────────────────────────────────────────────────────
def _sel(tema="derechos laborales", n=8):
    return {"rama": "laboral", "tema": tema, "segmentos": [{"pieza": f"R{i}"} for i in range(n)]}


@pytest.mark.parametrize("tema,n", [("derechos laborales", 8), ("familia, niñez y vida libre de violencia", 12),
                                    ("derechos constitucionales y justicia penal", 10), ("detenciones y justicia penal", 9)])
def test_miniatura_de_marca_pasa_su_auditoria(tmp_path, tema, n):
    sel = _sel(tema, n); f = tmp_path / "Y1_miniatura.png"
    mi = ys.miniatura(sel, f)
    from PIL import Image
    im = Image.open(f); assert im.size == (1280, 720) and im.format == "PNG" and f.stat().st_size < 2 * 1024 * 1024
    ante, titular = ys.textos_miniatura(sel)
    assert ante == f"{n} PREGUNTAS" and len(ys._palabras(titular)) <= 6
    assert set(ys._palabras(ante + " " + titular)) <= set(ys._palabras(ys.titulo_video(sel)))     # nada que no diga el título
    res = ys.auditar_miniatura(f, mi, ys.titulo_video(sel))
    assert all(c["resultado"] == "APROBADO" for c in res), res
    assert len(res) >= 8
    # colores de la marca: el fondo es «noche» y el titular «papel» (sin rediseño)
    import marca
    assert {t["color"] for t in mi["textos"]} <= {ys._hex(marca.C["papel"]), ys._hex(marca.C["cempasuchil"])}


def test_auditoria_de_miniatura_detecta_fallas(tmp_path):
    sel = _sel(); f = tmp_path / "m.png"; mi = ys.miniatura(sel, f); tit = ys.titulo_video(sel)
    def fallas(png, m, t=tit): return {c["control"].split(" (")[0].split(":")[0] for c in ys.auditar_miniatura(png, m, t) if c["resultado"] == "FALLA"}
    from PIL import Image
    chica = tmp_path / "chica.png"; Image.open(f).resize((640, 360)).save(chica)
    assert any("1280x720" in x for x in fallas(chica, mi))
    fuera = json.loads(json.dumps(mi)); fuera["textos"][0]["caja"] = [10, 10, 300, 60]
    assert any("márgenes" in x for x in fallas(f, fuera))
    esquina = json.loads(json.dumps(mi)); esquina["logotipo"] = [1100, 640, 1250, 700]
    assert any("márgenes" in x for x in fallas(f, esquina))
    oscuro = json.loads(json.dumps(mi)); oscuro["textos"][-1]["color"] = "#0B1626"        # texto del color del fondo: ilegible
    assert any("Contraste" in x for x in fallas(f, oscuro))
    assert any("tomado del título" in x for x in fallas(f, mi, "Otro título distinto"))
    larga = json.loads(json.dumps(mi)); larga["textos"].append({**larga["textos"][-1], "texto": "uno dos tres cuatro cinco seis siete"})
    assert any("Texto corto" in x for x in fallas(f, larga))
    pegado = json.loads(json.dumps(mi)); pegado["logotipo"] = pegado["textos"][-1]["caja"]
    assert any("Logotipo" in x for x in fallas(f, pegado))
    pesada = tmp_path / "p.png"; pesada.write_bytes(f.read_bytes() + b"\0" * (2 * 1024 * 1024))
    assert any("2 MB" in x for x in fallas(pesada, mi))


def test_miniatura_en_el_manifiesto_la_auditoria_y_la_version(entorno, corto):
    _armar_una_vez(entorno, corto)
    pid = "Y20261206-SEM"; salida = entorno / "semanal" / pid / "salida"
    m = json.loads(ys.manifiesto_path(pid).read_text())
    f = salida / m["miniatura"]["archivo"]
    assert f.name == f"{pid}_miniatura.png" and respaldo.sha256(f) == m["miniatura"]["sha256"]
    reg = ys.cargar()[pid]
    assert reg["miniatura"]["sha256"] == m["miniatura"]["sha256"] and reg["revision"]["huella_miniatura"] == m["miniatura"]["sha256"]
    assert respaldo.cargar()[pid][f.name]["sha256"] == m["miniatura"]["sha256"]                        # respaldada con el video
    tec = json.loads((salida / "auditoria.json").read_text())["tecnica"]
    nombres = [c["control"] for c in tec]
    assert any("Miniatura 1280x720" in c for c in nombres) and any("Contraste" in c for c in nombres) and any("SHA-256" in c for c in nombres)
    assert all(c["resultado"] == "APROBADO" for c in tec)
    assert ys.pendientes()[0]["miniatura"] == f.name
    ver = ys.version(pid)[0]
    # otra miniatura en el respaldo (sin cambiar el manifiesto): no hay versión aprobable
    r = json.loads(respaldo.MANIFIESTO.read_text()); r[pid][f.name]["sha256"] = "0" * 64; respaldo.MANIFIESTO.write_text(json.dumps(r))
    assert ys.version(pid)[0] is None
    # otra miniatura declarada en el manifiesto y respaldada: la versión cambia (la aprobación anterior deja de valer)
    r[pid][f.name]["sha256"] = "1" * 64; respaldo.MANIFIESTO.write_text(json.dumps(r))
    m["miniatura"]["sha256"] = "1" * 64; ys.manifiesto_path(pid).write_text(json.dumps(m, ensure_ascii=False, indent=1) + "\n")
    assert ys.version(pid)[0] not in (None, ver)
    # sin miniatura en la salida, la auditoría falla
    assert ys.controles_miniatura(entorno / "vacio", m)[0]["resultado"] == "FALLA"


def _llamadas_miniatura(h):
    return [(u, d, c) for (m, u, d), c in zip(h.llamadas, h.cabeceras) if u.startswith(youtube.MINIATURA_URL)]


def _cargas_video(h):
    return [u for m, u, d in h.llamadas if m == "POST" and u.startswith(youtube.CARGA_URL.split("?")[0])]


def test_pone_la_miniatura_despues_de_programar_sin_duplicar(entorno, corto, monkeypatch):
    pid, ver, bajar = _armado_y_aprobado(entorno, corto, monkeypatch, "2026-12-03T14:00:00+00:00")
    h = HttpYT()
    r = ys.programar(ahora=datetime(2026, 12, 6, 17, 7, tzinfo=timezone.utc), env=REAL, http=h, bajar=bajar)
    assert r["acciones"][0]["estado"] == "PROGRAMADO" and r["acciones"][0]["miniatura"] == "PUESTA"
    mins = _llamadas_miniatura(h); assert len(mins) == 1
    url, datos, cab = mins[0]
    assert "videoId=LARGO1" in url and cab["Content-Type"] == "image/png" and cab["Authorization"] == "Bearer A"
    m = json.loads(ys.manifiesto_path(pid).read_text())
    import hashlib
    assert hashlib.sha256(datos).hexdigest() == m["miniatura"]["sha256"]                               # la miniatura aprobada
    assert [i for i, (mt, u, d) in enumerate(h.llamadas) if u.startswith(youtube.MINIATURA_URL)][0] > \
           [i for i, (mt, u, d) in enumerate(h.llamadas) if u == "https://subida/1"][0]                 # después del video
    assert ys.cargar()[pid]["miniatura_yt"]["estado"] == "PUESTA"
    n = len(h.llamadas)
    ys.programar(ahora=datetime(2026, 12, 7, 17, 7, tzinfo=timezone.utc), env=REAL, http=h, bajar=bajar)
    assert len(h.llamadas) == n
    op = publicar.operacion(publicar.marca(pid, ver) + "-yt-min", "real")
    assert op["fase"] == "CONFIRMADA" and op["video_id"] == "LARGO1"


def test_si_falla_la_miniatura_solo_se_reintenta_la_miniatura(entorno, corto, monkeypatch):
    pid, ver, bajar = _armado_y_aprobado(entorno, corto, monkeypatch, "2026-12-03T14:00:00+00:00")
    h = HttpYT(fallas_miniatura=1)
    r = ys.programar(ahora=datetime(2026, 12, 6, 17, 7, tzinfo=timezone.utc), env=REAL, http=h, bajar=bajar)
    assert r["acciones"][0]["estado"] == "PROGRAMADO" and r["acciones"][0]["miniatura"] == "ERROR"
    v = ys.cargar()[pid]
    assert v["estado"] == "PROGRAMADO" and v["video_id"] == "LARGO1"                                   # el video sigue programado
    assert v["miniatura_yt"]["estado"] == "ERROR" and v["miniatura_yt"]["intentos"] == 1 and "backendError" in v["miniatura_yt"]["motivo"]
    assert publicar.operacion(publicar.marca(pid, ver) + "-yt-min", "real")["fase"] == "FALLIDA"
    cargas = len(_cargas_video(h))
    r = ys.programar(ahora=datetime(2026, 12, 7, 17, 7, tzinfo=timezone.utc), env=REAL, http=h, bajar=bajar)
    assert r["acciones"][0] == {"pieza": pid, "estado": "PROGRAMADO", "reintento": "miniatura", "miniatura": "PUESTA"}
    assert len(_cargas_video(h)) == cargas and len(_llamadas_miniatura(h)) == 2                        # no se resubió el video
    assert ys.cargar()[pid]["miniatura_yt"]["estado"] == "PUESTA"
    assert publicar.operacion(publicar.marca(pid, ver) + "-yt", "real")["fase"] == "CONFIRMADA"
    # con los intentos agotados se deja de intentar (queda la miniatura automática y el motivo en el registro)
    reg = ys.cargar(); reg[pid]["miniatura_yt"] = {"estado": "ERROR", "intentos": ys.MINIATURA_INTENTOS}; ys.guardar(reg)
    n = len(h.llamadas)
    assert ys.programar(ahora=datetime(2026, 12, 13, 17, 7, tzinfo=timezone.utc), env=REAL, http=h, bajar=bajar)["acciones"] == [] and len(h.llamadas) == n


def test_miniatura_distinta_de_la_aprobada_no_se_sube(entorno, corto, monkeypatch, tmp_path):
    pid, ver, bajar = _armado_y_aprobado(entorno, corto, monkeypatch, "2026-12-03T14:00:00+00:00")
    otra = tmp_path / f"{pid}_miniatura.png"; ys.miniatura(_sel("derechos del consumidor", 5), otra)
    def bajar_otra(e, carpeta, env): return otra if e["archivo"].endswith("_miniatura.png") else bajar(e, carpeta, env)
    h = HttpYT()
    r = ys.programar(ahora=datetime(2026, 12, 6, 17, 7, tzinfo=timezone.utc), env=REAL, http=h, bajar=bajar_otra)
    assert r["acciones"][0]["estado"] == "PROGRAMADO" and r["acciones"][0]["miniatura"] == "ERROR"
    assert not _llamadas_miniatura(h) and "no es la aprobada" in ys.cargar()[pid]["miniatura_yt"]["motivo"]


def test_simulacion_de_miniatura_y_limites(tmp_path):
    libro = tmp_path / "ops.jsonl"; f = tmp_path / "m.png"; ys.miniatura(_sel(), f)
    r = youtube.poner_miniatura("Y1-SEM", None, f, "abcdef0123456789", env={}, libro=libro)
    assert r["estado"] == "SIMULADO"
    youtube.poner_miniatura("Y1-SEM", None, f, "abcdef0123456789", env={}, libro=libro)
    assert len(libro.read_text().splitlines()) == 1                                                   # una sola marca SIMULADA
    h = HttpYT()
    with pytest.raises(youtube.ErrorYouTube):
        g = tmp_path / "m.gif"; g.write_bytes(b"GIF89a"); youtube.poner_miniatura("Y1-SEM", "V1", g, "abcdef0123456789", env=REAL, http=h, libro=libro)
    p = tmp_path / "p.png"; p.write_bytes(b"\0" * (2 * 1024 * 1024))
    with pytest.raises(youtube.ErrorYouTube): youtube.poner_miniatura("Y1-SEM", "V1", p, "abcdef0123456789", env=REAL, http=h, libro=libro)
    assert not h.llamadas                                                                             # no se llama a la API
    assert youtube.poner_miniatura("Y1-SEM", "V1", f, "abcdef0123456789", env=REAL, http=h, libro=libro)["estado"] == "PUESTA"
    assert youtube.poner_miniatura("Y1-SEM", "V1", f, "abcdef0123456789", env=REAL, http=h, libro=libro)["origen"] == "libro"
