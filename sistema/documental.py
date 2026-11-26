"""Documental semanal de YouTube — decisión del responsable, 26-11-2026: un DOCUMENTAL de caso real por semana (horizontal,
8 a 12 min) en lugar del video semanal que junta Reels (data/lanzamiento.json → YOUTUBE_SEMANAL_MODO = "documental").
Aprobación delegada (Claude aprueba con decidir.py --delegada; el responsable tiene 72 h de veto). Primer documental:
domingo 6-12-2026 a las 12:00 CDMX.

Este módulo es la PRODUCCIÓN técnica. El contenido (guion verificado contra fuentes oficiales) lo escribe el editor en
documentales/<ID>/guion.json con el esquema de sistema/esquema_documental.py; aquí no se redacta ni se corrige nada jurídico.

  producir <ID>  (documental.yml, workflow_dispatch con el id):
    1. valida el guion (esquema_documental.validar); si falla queda INVALIDO con los errores;
    2. narra cada escena con el motor de voz de la marca (config_voz.json, la misma voz de los Reels): duración de la escena
       = audio + respiro; cada capítulo abre con una cortinilla de 2.6 s sin narración;
    3. renderiza el cuerpo 1920x1080 a 30 cps con gráficos animados originales (render_documental.py), subtítulos quemados
       y el rótulo «RECREACIÓN» en las recreaciones; música: el pad original del repositorio (musica.pad, generado por
       código, sin licencias de terceros) bajo la voz con compresión lateral, como en los Reels;
    4. entrada y cierre de marca con la firma sonora (las mismas piezas del video semanal: _fondo, logotipo, _parte_tarjeta),
       con el aviso «Información general, no asesoría legal.» al inicio y al final; sonoridad −14 LUFS en dos pasadas;
    5. descripción con capítulos de los tiempos reales (0:00 primero), fuentes completas (referencia + URL) y el aviso;
       miniatura 1280x720 con el generador del video semanal (tema = título corto);
    6. auditoría técnica (duración 6-15 min, formato, audio, capítulos, fuentes, rótulo de recreación medido en los píxeles
       del video final, subtítulos, miniatura) → documentales/<ID>/salida/auditoria.json;
    7. respaldo en el release (SHA-256) y registro en estado/documentales.json: REVISION_HUMANA (o RETENIDO si algo falla).
       Versión = huella del manifiesto, que contiene las huellas del video, la miniatura y el guion.
  aprobar:   python sistema/decidir.py aprobar <ID> <versión> --por "Claude (revisión editorial delegada)" --delegada
  veto:      python sistema/decidir.py rechazar <ID> <versión> --por "responsable" --nota "veto del responsable"
  programar  (documental.yml, domingo y lunes 11:07 CDMX): sube como video normal (no Short), privado con publishAt = fecha
             del guion a las 12:00 CDMX, y pone la miniatura; idempotente con el libro de operaciones (marcas «…-yt» y
             «…-yt-min», igual que el video semanal). Solo simula sin las condiciones de YouTube.

Uso:  python sistema/documental.py validar <ID> | producir <ID> | programar | listar
Costo: 0 MXN (Actions gratuito en repositorio público; voz y gráficos locales; cuota gratuita de la API de YouTube).
"""
import hashlib, json, os, re, shutil, subprocess, sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import esquema_documental as esquema

RAIZ = Path(__file__).resolve().parent.parent
DIR = RAIZ / "documentales"
REG = RAIZ / "estado" / "documentales.json"
MX = timezone(timedelta(hours=-6))
W, H, FPS = 1920, 1080, 30
DUR_MIN, DUR_MAX = 360.0, 900.0              # auditoría: 6 a 15 min (meta editorial: 8 a 12)
INICIO_S = 0.4                               # aire antes de la primera cortinilla
CORTINILLA_S = 2.6                           # tarjeta de capítulo sin narración
RESPIRO_S = 0.7                              # silencio después de cada escena
FINAL_S = 0.6
VOL_MUSICA = 0.16
HORA_PUBLICACION = (12, 0)
AVISO = esquema.AVISO
PRESET = "veryfast"
CAPITULO_MIN_S = 10
ROTULO_MIN_COBERTURA = 0.30                  # fracción de la caja del rótulo con su color (medido en el video final)
SUBTITULOS_MIN_COBERTURA = 0.85
ESTADOS_BLOQUEADOS = ("APROBADA", "PROGRAMADO")   # no se toca una pieza aprobada: para cambiarla hay que vetarla primero


class NoDecidible(ValueError):
    pass


def ahora_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def es_documental(pid):
    return bool(esquema.ID_RE.fullmatch(str(pid or "")))


def carpeta(pid):
    return DIR / pid


def guion_path(pid):
    return carpeta(pid) / "guion.json"


def manifiesto_path(pid):
    return carpeta(pid) / "manifiesto.json"


def cargar():
    try: return json.loads(REG.read_text())
    except (OSError, ValueError): return {}


def guardar(reg):
    REG.parent.mkdir(parents=True, exist_ok=True)
    REG.write_text(json.dumps(reg, ensure_ascii=False, indent=1) + "\n")


def hora_publicacion(d):
    return datetime(d.year, d.month, d.day, *HORA_PUBLICACION, tzinfo=MX)


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()


# ── narración y línea de tiempo ──────────────────────────────────────────────────────────────────────────────────
def voz_marca(guion=None):
    v = (guion or {}).get("voz")
    return v if isinstance(v, dict) else json.loads((Path(__file__).resolve().parent / "config_voz.json").read_text())["voz"]


def voz_escena(texto, voz):
    """(audio float32, sr, [(oración, inicio, fin)] relativos). Misma cadena que los Reels (voces.sintetizar por oración)."""
    import numpy as np, voces
    audio, sr, ors = voces.sintetizar(texto, voz, pausa=voz.get("pausa_oracion", 0.36), con_tiempos=True)
    idx = np.where(np.abs(audio) > 0.006)[0]
    if len(idx): audio = audio[: idx[-1] + int(0.08 * sr)]
    return audio, sr, ors


def linea_tiempo(guion, duraciones, oraciones=None):
    """Tiempos del cuerpo (sin la entrada de marca). duraciones[i] = segundos de voz de la escena i; oraciones[i] =
    [(texto, ini, fin)] relativos. Cada escena: [cortinilla de capítulo] + voz + respiro."""
    inicios = dict(esquema.capitulos(guion)); de = esquema.capitulo_de(guion)
    t = INICIO_S; out = []
    for i, (e, dur) in enumerate(zip(guion["escenas"], duraciones)):
        s = {"n": e["n"], "inicio": round(t, 3), "capitulo": de.get(e["n"]), "texto": e["narracion"], "cortinilla": None}
        if e["n"] in inicios:
            s["cortinilla"] = [round(t, 3), round(t + CORTINILLA_S, 3)]; t += CORTINILLA_S
        s["voz_inicio"] = round(t, 3); s["voz_fin"] = round(t + dur, 3)
        if oraciones and oraciones[i]:
            s["oraciones"] = [{"texto": o, "inicio": round(t + a, 3), "fin": round(t + b, 3)} for o, a, b in oraciones[i]]
        t += dur + RESPIRO_S; s["fin"] = round(t, 3); out.append(s)
    total = t + FINAL_S
    out[-1]["fin"] = round(total, 3)
    return {"escenas": out, "total_s": round(total, 3), "capitulos": [{"n": s["n"], "titulo": inicios[s["n"]], "inicio_s": s["cortinilla"][0]}
                                                                     for s in out if s["cortinilla"]]}


def narrar(guion, tmp, sintetizar=None):
    """Voz completa del cuerpo (48 kHz, masterizada como los Reels) y su línea de tiempo."""
    import numpy as np, soundfile as sf, voces
    sintetizar = sintetizar or voz_escena
    voz = voz_marca(guion); audios, durs, ors, sr0 = [], [], [], None
    for e in guion["escenas"]:
        a, sr, o = sintetizar(e["narracion"], voz)
        if sr0 is None: sr0 = sr
        if sr != sr0: raise RuntimeError("frecuencias de muestreo distintas entre escenas")
        audios.append(np.asarray(a, np.float32)); durs.append(len(a) / sr); ors.append(o)
    lt = linea_tiempo(guion, durs, ors)
    pista = np.zeros(int(round(lt["total_s"] * sr0)) + sr0, np.float32)
    for a, s in zip(audios, lt["escenas"]):
        i = int(round(s["voz_inicio"] * sr0)); pista[i:i + len(a)] += a[: len(pista) - i]
    pista = pista[: int(round(lt["total_s"] * sr0))]
    crudo = Path(tmp) / "voz_cruda.wav"; sf.write(crudo, pista, sr0)
    voces.postproceso(crudo, Path(tmp) / "voz.wav"); crudo.unlink()
    lt["voz"] = {k: voz.get(k) for k in ("motor", "id", "lang", "velocidad")}
    lt["palabras"] = sum(esquema.palabras(e["narracion"]) for e in guion["escenas"])
    return lt


def _ff(args):
    import youtube_semanal as ys
    return ys._ff(args)


def mezclar_cuerpo(video_mudo, voz_wav, total, salida, tmp):
    """Voz + pad musical original (musica.pad) con compresión lateral, como en los Reels; video copiado."""
    import musica, youtube_semanal as ys
    mus = Path(tmp) / "musica.wav"; musica.pad(total, salida=str(mus))
    filtro = ("[1:a]aresample=48000,pan=stereo|c0=c0|c1=c0,asplit=2[v][vsc];"
              f"[2:a]aresample=48000,volume={VOL_MUSICA}[m];[m][vsc]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[md];"
              f"[v][md]amix=inputs=2:duration=first:normalize=0,apad=whole_dur={total:.3f},atrim=0:{total:.3f}[a]")
    _ff(["-i", str(video_mudo), "-i", str(voz_wav), "-i", str(mus), "-filter_complex", filtro, "-map", "0:v", "-map", "[a]",
         "-c:v", "copy"] + ys.COD_A + ["-t", f"{total:.3f}", str(salida)])
    mus.unlink(missing_ok=True)


# ── descripción, capítulos y fuentes ─────────────────────────────────────────────────────────────────────────────
def marca_tiempo(s):
    s = int(s); h, m, x = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02d}:{x:02d}" if h else f"{m}:{x:02d}"


def capitulos_video(lt, intro_s):
    """Capítulos de los tiempos reales: el primero en 0:00 (incluye la entrada de marca)."""
    caps = []
    for i, c in enumerate(lt["capitulos"]):
        ini = 0.0 if i == 0 else intro_s + c["inicio_s"]
        caps.append({"inicio_s": round(ini, 2), "marca": marca_tiempo(ini), "titulo": c["titulo"].replace("<", "").replace(">", ""), "escena": c["n"]})
    return caps


def fuentes_completas(guion):
    vistos, out = set(), []
    for f in list(guion.get("fuentes") or []) + [x for e in guion["escenas"] for x in (e.get("fuentes") or [])]:
        if f.get("url") in vistos: continue
        vistos.add(f.get("url")); out.append({k: f.get(k) for k in ("tipo", "referencia", "url")})
    return out


TIPO_FUENTE = {"ley": "Ley", "sentencia": "Sentencia", "tesis": "Tesis", "oficial": "Fuente oficial", "hemerografica": "Hemerografía",
               "tratado": "Tratado", "cronica": "Crónica oficial"}


def descripcion_video(guion, caps):
    rec = any(e["pantalla"]["tipo"] == "recreacion" for e in guion["escenas"])
    lin = [guion["descripcion"].strip(), "", "Capítulos:"] + [f'{c["marca"]} {c["titulo"]}' for c in caps] + ["", "Fuentes:"]
    for f in fuentes_completas(guion):
        lin.append(f'• {f["referencia"]} ({TIPO_FUENTE.get(f["tipo"], f["tipo"])}): {f["url"]}')
    lin += ["", AVISO]
    av = (guion.get("aviso") or "").strip()
    if av and av != AVISO: lin.append(av)
    if rec: lin.append("Las escenas con el rótulo «Recreación» son ilustraciones originales, no material auténtico.")
    lin += ["Voz generada con IA.", "", "Aquí Dice la Ley · El Derecho, explicado en voz clara."]
    return "\n".join(lin).replace("<", "").replace(">", "")


def titulo_yt(guion):
    return guion["titulo"].replace("<", "").replace(">", "")


# ── auditoría ────────────────────────────────────────────────────────────────────────────────────────────────────
def _cuadro(mp4, t, salida):
    _ff(["-ss", f"{t:.3f}", "-i", str(mp4), "-frames:v", "1", str(salida)])
    return salida


def rotulo_visible(mp4, t, caja, tmp):
    """Fracción de la caja del rótulo con el color del rótulo, en el cuadro t del video final."""
    import numpy as np
    from PIL import Image
    import marca
    f = _cuadro(mp4, t, Path(tmp) / f"rotulo_{t:.2f}.png")
    x0, y0, x1, y1 = (int(v) for v in caja)
    zona = np.asarray(Image.open(f).convert("RGB")).astype(int)[y0:y1, x0:x1].reshape(-1, 3)
    col = np.array(marca.C["coral_texto"])
    f.unlink(missing_ok=True)
    return float((np.abs(zona - col).sum(axis=1) < 60).mean()) if len(zona) else 0.0


def leer_srt(p):
    cues = []
    for b in Path(p).read_text().strip().split("\n\n"):
        m = re.search(r"(\d+):(\d+):(\d+),(\d+) --> (\d+):(\d+):(\d+),(\d+)", b)
        if m:
            g = [int(x) for x in m.groups()]
            cues.append((g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000, g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000))
    return cues


def auditar(final, m, guion, lt, info_render, tarjetas, tmp, dur_min=None, dur_max=None):
    import youtube_semanal as ys
    dur_min = DUR_MIN if dur_min is None else dur_min; dur_max = DUR_MAX if dur_max is None else dur_max
    res, dur = ys.auditar_tecnica(final, dur_min, dur_max)
    def ok(nombre, cond, detalle=""): res.append({"control": nombre, "resultado": "APROBADO" if cond else "FALLA", "detalle": detalle})
    caps, desc, tit = m["capitulos"], m["descripcion"], m["titulo"]
    ini = [c["inicio_s"] for c in caps]
    ok("Capítulos: al menos 3, el primero en 0:00", len(caps) >= 3 and caps[0]["marca"] == "0:00" and ini[0] == 0, f"{len(caps)} capítulos")
    tramos = [b - a for a, b in zip(ini, ini[1:] + [dur])]
    ok(f"Capítulos en orden y de {CAPITULO_MIN_S} s o más", bool(tramos) and all(t >= CAPITULO_MIN_S for t in tramos) and ini == sorted(ini), f"mínimo {min(tramos, default=0):.0f} s")
    ok("Capítulos escritos en la descripción", all(f'{c["marca"]} {c["titulo"]}' in desc for c in caps), "")
    fu = fuentes_completas(guion)
    faltan = [f["referencia"][:40] for f in fu if f["referencia"] not in desc or f["url"] not in desc]
    ok("Fuentes completas (referencia y URL) en la descripción", bool(fu) and not faltan, ", ".join(faltan) or f"{len(fu)} fuentes")
    sin = [e["n"] for e in guion["escenas"] if e["pantalla"]["tipo"] in esquema.CON_FUENTE and not e.get("fuentes")]
    ok("Cada escena «cita» o «dato» con su fuente", not sin, ", ".join(map(str, sin)) or "todas")
    ok("Aviso «Información general, no asesoría legal» en la descripción", AVISO in desc, "")
    ok("Aviso en pantalla al inicio y al final", AVISO in tarjetas.get("intro", []) and AVISO in tarjetas.get("cierre", []), "")
    # rótulo de recreación: dibujado en todos los cuadros de cada escena «recreacion» y visible en el video final
    rec = [s for e, s in zip(guion["escenas"], lt["escenas"]) if e["pantalla"]["tipo"] == "recreacion"]
    det = []
    for s in rec:
        n = s["n"]; ini_e = (s["cortinilla"][1] if s["cortinilla"] else s["inicio"]); fin_e = s["fin"]
        dibujados, esperados = info_render["cuadros_rotulo"].get(n, info_render["cuadros_rotulo"].get(str(n), 0)), info_render["cuadros_recreacion"].get(n, info_render["cuadros_recreacion"].get(str(n), 0))
        vis = [rotulo_visible(final, m["intro_s"] + t, info_render["caja_rotulo"], tmp) for t in (ini_e + 0.05, (ini_e + fin_e) / 2, fin_e - 0.4)]
        if dibujados < esperados - 1 or min(vis) < ROTULO_MIN_COBERTURA: det.append(f"escena {n}: {dibujados}/{esperados} cuadros, {min(vis):.2f}")
    ok("Rótulo «Recreación» visible durante cada recreación (medido en el video)", not det, "; ".join(det) or (f"{len(rec)} recreaciones" if rec else "sin recreaciones"))
    cues = leer_srt(m["subtitulos"]["ruta"])
    voz = sum(s["voz_fin"] - s["voz_inicio"] for s in lt["escenas"])
    cub = sum(b - a for a, b in cues) / voz if voz else 0
    ok("Subtítulos quemados durante la narración", cub >= SUBTITULOS_MIN_COBERTURA and info_render["cuadros_con_subtitulo"] > 0, f"{cub:.0%} de la voz, {len(cues)} bloques")
    ok("Solo gráficos originales de la marca (sin imágenes ni material de terceros en el guion)", not esquema.validar(guion, 0, 1e9), "")
    ok("Título de 100 caracteres o menos, sin «<» ni «>»", 0 < len(tit) <= 100 and "<" not in tit and ">" not in tit, f"{len(tit)} caracteres")
    ok("Descripción de 4,900 caracteres o menos (sin recorte en YouTube)", len(desc) <= 4900, f"{len(desc)} caracteres")
    res += ys.controles_miniatura(Path(final).parent, m)
    return res, dur


# ── producción ───────────────────────────────────────────────────────────────────────────────────────────────────
def version(pid):
    """(versión, huella del manifiesto, huella del MP4 respaldado). El manifiesto lleva las huellas del video, la miniatura y
    el guion; la versión solo existe si las tres coinciden con el respaldo y con el guion vigente."""
    import respaldo
    mp = manifiesto_path(pid)
    if not mp.exists(): return None, "", ""
    hm = sha256(mp)
    try: m = json.loads(mp.read_text())
    except ValueError: return None, hm, ""
    resp = respaldo.cargar().get(pid, {})
    ha = (resp.get(m["video"]["archivo"]) or {}).get("sha256", "")
    hmin = (resp.get(m["miniatura"]["archivo"]) or {}).get("sha256", "")
    gp = guion_path(pid)
    hg = sha256(gp) if gp.exists() else ""
    if not ha or ha != m["video"]["sha256"] or not hmin or hmin != m["miniatura"]["sha256"] or hg != m["guion"]["sha256"]:
        return None, hm, ha
    return hashlib.sha256(f"documental:{hm}".encode()).hexdigest()[:16], hm, ha


def producir(pid, env=None, sintetizar=None, ahora=None, min_min=None, max_min=None, dur_min=None, dur_max=None, muestras=None):
    """Produce, audita y respalda el documental <pid> a partir de documentales/<pid>/guion.json."""
    import respaldo, render_documental as rd, youtube_semanal as ys
    env = env if env is not None else os.environ
    if not es_documental(pid): return {"estado": "ID_INVALIDO", "pieza": pid}
    reg = cargar(); r0 = reg.get(pid) or {}
    if r0.get("estado") in ESTADOS_BLOQUEADOS:
        return {"estado": "YA_APROBADO", "pieza": pid, "estado_registro": r0["estado"], "nota": "una pieza aprobada no se modifica; para cambiarla hay que vetarla"}
    gp = guion_path(pid)
    try: guion = json.loads(gp.read_text())
    except (OSError, ValueError) as x:
        reg[pid] = {"estado": "INVALIDO", "motivo": f"guion ilegible: {x}"[:300], "fecha": ahora_iso()}; guardar(reg)
        return {"estado": "INVALIDO", "pieza": pid, "errores": [reg[pid]["motivo"]]}
    errores = esquema.validar(guion, min_min, max_min)
    if not errores and guion["id"] != pid: errores = [f"el id del guion ({guion['id']}) no coincide con la carpeta ({pid})"]
    base = {"titulo": guion.get("titulo"), "fecha_publicacion": guion.get("fecha"), "guion_sha256": sha256(gp), "producido": ahora_iso()}
    if errores:
        reg[pid] = {**base, "estado": "INVALIDO", "errores": errores}; guardar(reg)
        return {"estado": "INVALIDO", "pieza": pid, "errores": errores}
    if env.get("PUBLICAR_HASTA") and guion["fecha"] > env["PUBLICAR_HASTA"]:
        base["aviso_publicacion"] = f"la fecha {guion['fecha']} es posterior a PUBLICAR_HASTA ({env['PUBLICAR_HASTA']}): no se programará sin nueva autorización"
    c = carpeta(pid); tmp = c / "tmp"; sal = c / "salida"
    shutil.rmtree(tmp, ignore_errors=True); shutil.rmtree(sal, ignore_errors=True)
    tmp.mkdir(parents=True); sal.mkdir(parents=True)
    old_preset = ys.PRESET; ys.PRESET = PRESET
    try:
        lt = narrar(guion, tmp, sintetizar)
        info = rd.render(guion, lt, tmp / "cuerpo_mudo.mp4", preset=PRESET, cuadros=muestras)
        mezclar_cuerpo(tmp / "cuerpo_mudo.mp4", tmp / "voz.wav", lt["total_s"], tmp / "cuerpo.mp4", tmp)
        tarjetas = {}
        for tipo, dur in (("intro", ys.INTRO_S), ("cierre", ys.CIERRE_S)):
            im, textos = rd.tarjeta(tipo, guion, AVISO); im.save(tmp / f"{tipo}.png"); tarjetas[tipo] = textos
            ys._parte_tarjeta(tmp / f"{tipo}.png", dur, tmp / f"{tipo}.mp4")
        intro_s = ys.duracion(tmp / "intro.mp4")
        lista = tmp / "lista.txt"; lista.write_text("".join(f"file '{(tmp / x).resolve()}'\n" for x in ("intro.mp4", "cuerpo.mp4", "cierre.mp4")))
        _ff(["-f", "concat", "-safe", "0", "-i", str(lista), "-c", "copy", str(tmp / "unido.mp4")])
        final = sal / f"{pid}_final.mp4"; ys._normalizar(tmp / "unido.mp4", final)
        srt = sal / f"{pid}_final.srt"; escribir_srt(lt, intro_s, srt)
        caps = capitulos_video(lt, intro_s)
        tc = esquema.titulo_corto(guion)
        mini = ys.miniatura({"tema": tc, "segmentos": []}, sal / f"{pid}_miniatura.png", textos=("", tc[:1].upper() + tc[1:]))
    except Exception as x:
        ys.PRESET = old_preset
        reg[pid] = {**base, "estado": "ERROR", "motivo": f"{type(x).__name__}: {x}"[:600]}; guardar(reg)
        return {"estado": "ERROR", "pieza": pid, "motivo": reg[pid]["motivo"]}
    ys.PRESET = old_preset
    m = {"id": pid, "titulo": titulo_yt(guion), "titulo_corto": tc, "fecha": guion["fecha"],
         "publicar_en": hora_publicacion(date.fromisoformat(guion["fecha"])).isoformat(), "descripcion": descripcion_video(guion, caps),
         "capitulos": caps, "intro_s": round(intro_s, 3), "cuerpo_s": lt["total_s"],
         "escenas": [{"n": s["n"], "tipo": e["pantalla"]["tipo"], "capitulo": s["capitulo"], "inicio_s": round(intro_s + s["inicio"], 2),
                      "fin_s": round(intro_s + s["fin"], 2)} for e, s in zip(guion["escenas"], lt["escenas"])],
         "fuentes": fuentes_completas(guion), "voz": lt["voz"], "palabras": lt["palabras"],
         "musica": "musica.pad (original del repositorio, generada por código; sin material de terceros)",
         "guion": {"archivo": f"documentales/{pid}/guion.json", "sha256": base["guion_sha256"]},
         "video": {"archivo": final.name, "sha256": sha256(final)},
         "subtitulos": {"archivo": srt.name, "sha256": sha256(srt), "ruta": str(srt)},
         "miniatura": {**mini, "sha256": sha256(sal / mini["archivo"])},
         "render": {k: info[k] for k in ("cuadros", "segundos_render", "cuadros_con_subtitulo", "bloques_subtitulo")}}
    tec, dur = auditar(final, m, guion, lt, info, tarjetas, tmp, dur_min, dur_max)
    m["subtitulos"].pop("ruta", None); m["video"]["duracion_s"] = round(dur, 2)
    manifiesto_path(pid).write_text(json.dumps(m, ensure_ascii=False, indent=1) + "\n")
    (sal / "auditoria.json").write_text(json.dumps({"tecnica": tec, "duracion_s": dur, "minutos": round(dur / 60, 2)}, ensure_ascii=False, indent=1))
    try:
        resp = respaldo.respaldar(pid, sal, env)
    except Exception as x:
        resp = {}; base["respaldo_error"] = f"{type(x).__name__}: {x}"[:300]
    shutil.rmtree(tmp, ignore_errors=True)
    fallas = [f'{c_["control"]} ({c_["detalle"]})' for c_ in tec if c_["resultado"] == "FALLA"]
    a_ = resp.get(final.name) or {}; am = resp.get(mini["archivo"]) or {}
    r = {**base, "titulo": m["titulo"], "publicar_en": m["publicar_en"], "duracion_s": round(dur, 1), "archivo": final.name,
         "sha256": a_.get("sha256"), "asset_id": a_.get("asset_id"), "release": a_.get("release"),
         "miniatura": {"archivo": mini["archivo"], "sha256": am.get("sha256"), "asset_id": am.get("asset_id"), "release": am.get("release")},
         "capitulos": len(caps), "fallas_tecnicas": fallas}
    if fallas:
        r.update(estado="RETENIDO", motivo="; ".join(fallas)[:600])
    else:
        ver, hm, ha = version(pid)
        r.update(estado="REVISION_HUMANA" if ver else "RETENIDO",
                 revision={"version": ver, "huella_manifiesto": hm, "huella_archivo": ha, "huella_miniatura": m["miniatura"]["sha256"],
                           "huella_guion": base["guion_sha256"], "preparada": ahora_iso()},
                 **({} if ver else {"motivo": base.get("respaldo_error") or "sin respaldo del archivo"}))
    reg[pid] = r; guardar(reg)
    return {"estado": r["estado"], "pieza": pid, "duracion_s": r["duracion_s"], "capitulos": len(caps),
            "version": (r.get("revision") or {}).get("version"), "fallas": fallas, "render_s": info["segundos_render"]}


def escribir_srt(lt, desplazamiento, salida):
    import render_documental as rd
    def ts(x):
        h = int(x // 3600); m_ = int(x % 3600 // 60); s = x % 60
        return f"{h:02d}:{m_:02d}:{int(s):02d},{int(round((s % 1) * 1000)) % 1000:03d}"
    with open(salida, "w") as f:
        for i, b in enumerate(rd.bloques_subtitulos(lt), 1):
            f.write(f"{i}\n{ts(desplazamiento + b[0][1])} --> {ts(desplazamiento + b[-1][2])}\n{' '.join(x[0] for x in b)}\n\n")


# ── aprobación ───────────────────────────────────────────────────────────────────────────────────────────────────
def pendientes():
    return [{"pieza": k, "formato": "documental semanal de YouTube", "titulo": v.get("titulo"), "publicar_en": v.get("publicar_en"),
             "version": (v.get("revision") or {}).get("version"), "duracion_s": v.get("duracion_s"), "archivo": v.get("archivo"),
             "miniatura": (v.get("miniatura") or {}).get("archivo"), "manifiesto": f"documentales/{k}/manifiesto.json"}
            for k, v in sorted(cargar().items()) if v.get("estado") == "REVISION_HUMANA"]


def decidir(pid, decision, ver, por, nota="", canal="chat"):
    import revision
    reg = cargar(); v = reg.get(pid)
    permitido = {"REVISION_HUMANA": ("APROBADA", "RECHAZADA"), "APROBADA": ("RECHAZADA",), "PROGRAMADO": ("RECHAZADA",)}
    if not v or decision not in permitido.get(v.get("estado"), ()):
        raise NoDecidible(f"{pid}: estado {v.get('estado') if v else 'desconocido'}; no admite «{decision}»")
    actual, hm, ha = version(pid)
    preparada = (v.get("revision") or {}).get("version")
    if not actual or ver != actual or ver != preparada:
        raise NoDecidible(f"{pid}: la versión {ver} no es la vigente (preparada {preparada}, actual {actual}); no se registró")
    if decision == "RECHAZADA" and not nota.strip():
        raise NoDecidible("un rechazo necesita el motivo (--nota)")
    fila = revision.registrar(pid, decision, ver, hm, ha, {"nombre": por}, canal, nota or "documental semanal de YouTube")
    previo = v.get("estado")
    v.update(estado=decision, decision={"fecha": fila["fecha"], "canal": canal, "por": por, "nota": nota})
    if decision == "RECHAZADA" and previo == "PROGRAMADO":
        v["aviso"] = "vetado después de programarse: el video sigue en YouTube como privado programado; quitarlo a mano en YouTube Studio"
    guardar(reg)
    return fila


# ── programación en YouTube (misma lógica que el video semanal) ──────────────────────────────────────────────────
MINIATURA_INTENTOS = 6
ANTICIPACION_MAX = timedelta(days=8)          # se programa en la semana de su fecha


def programar(ahora=None, env=None, http=None, bajar=None, carpeta_tmp="/tmp/documental"):
    import publicador, publicar, youtube
    env = env if env is not None else os.environ
    ahora = ahora or datetime.now(timezone.utc)
    http = http or youtube.http_yt; bajar = bajar or publicador.descargar
    res = {"ahora": ahora.isoformat(timespec="minutes"), "acciones": []}
    p = publicador.pausado(env)
    if p: return {**res, "pausa": p}
    reg = cargar()
    for pid, v in sorted(reg.items()):
        if v.get("estado") == "PROGRAMADO" and _miniatura_pendiente(v):
            acc = {"pieza": pid, "estado": "PROGRAMADO", "reintento": "miniatura"}
            acc["miniatura"] = _poner_miniatura(pid, v, (v.get("revision") or {}).get("version"), v.get("video_id"), env, http, bajar, carpeta_tmp)["estado"]
            res["acciones"].append(acc); continue
        if v.get("estado") != "APROBADA": continue
        acc = {"pieza": pid}
        ver = (v.get("revision") or {}).get("version")
        e = {"pieza": pid, "version": ver, "sha256": v.get("sha256"), "asset_id": v.get("asset_id"), "archivo": v.get("archivo") or f"{pid}_final.mp4"}
        objetivo = datetime.fromisoformat(v["publicar_en"]); cuando = objetivo
        if objetivo - ahora > ANTICIPACION_MAX:
            acc["estado"] = "EN_ESPERA"; acc["publicar_en"] = objetivo.isoformat(timespec="minutes"); res["acciones"].append(acc); continue
        if cuando - ahora < timedelta(minutes=20):          # veto vencido tarde: siguiente 12:00 CDMX con 20 min de margen
            d = ahora.astimezone(MX).date(); cuando = hora_publicacion(d)
            if cuando - ahora < timedelta(minutes=20): cuando = hora_publicacion(d + timedelta(days=1))
        if cuando - objetivo > timedelta(days=6):
            v.update(estado="VENCIDO", motivo="no se pudo programar en la semana que le correspondía"); acc["estado"] = "VENCIDO"
            res["acciones"].append(acc); continue
        if env.get("PUBLICAR_HASTA") and cuando.astimezone(MX).date().isoformat() > env["PUBLICAR_HASTA"]:
            acc["estado"] = "SIN_AUTORIZACION_DE_PUBLICACION"; res["acciones"].append(acc); continue
        try:
            if version(pid)[0] != ver: raise publicador.NoAprobada(f"{pid}: la versión vigente no es la aprobada ({ver})")
            f = bajar(e, carpeta_tmp, env); publicador.comprobar(e, f, ahora)
            m = json.loads(manifiesto_path(pid).read_text())
            r = youtube.publicar_yt(pid, f, m["titulo"], m["descripcion"], ver, cuando, env=env, http=http, formato="video_largo")
            acc.update(estado=r["estado"], publicar_en=cuando.isoformat(timespec="minutes"), **({"tarde": True} if cuando != objetivo else {}))
            if r["estado"] == "PROGRAMADO":
                v.update(estado="PROGRAMADO", video_id=r.get("video_id"), programado_para=cuando.isoformat(timespec="minutes"))
            if r["estado"] in ("PROGRAMADO", "SIMULADO"):
                acc["miniatura"] = _poner_miniatura(pid, v, ver, r.get("video_id"), env, http, bajar, carpeta_tmp)["estado"]
            if r["estado"] != "PROGRAMADO":
                v["ultimo_intento"] = {"fecha": ahora_iso(), "estado": r["estado"], "motivo": r.get("motivo")}
        except publicador.EnPlazoDeVeto as x:
            acc.update(estado="EN_PLAZO_DE_VETO", detalle=str(x))
        except publicador.NoAprobada as x:
            acc.update(estado="NO_APROBADA", error=str(x)); v["ultimo_intento"] = {"fecha": ahora_iso(), "estado": "NO_APROBADA", "motivo": str(x)}
        except (youtube.ErrorYouTube, youtube.YouTubeAmbigua, publicar.SinRed, OSError, KeyError) as x:
            acc.update(estado="ERROR", error=str(x)[:300]); v["ultimo_intento"] = {"fecha": ahora_iso(), "estado": "ERROR", "motivo": str(x)[:300]}
        res["acciones"].append(acc)
    guardar(reg)
    return res


def _miniatura_pendiente(v):
    m = v.get("miniatura_yt") or {}
    return bool((v.get("miniatura") or {}).get("archivo")) and m.get("estado") != "PUESTA" and m.get("intentos", 0) < MINIATURA_INTENTOS


def _poner_miniatura(pid, v, ver, video_id, env, http, bajar, carpeta_tmp):
    import publicador, publicar, youtube
    est = dict(v.get("miniatura_yt") or {})
    try:
        actual = version(pid)[0]
        if not ver or actual != ver: raise publicador.NoAprobada(f"{pid}: la versión vigente ({actual}) no es la aprobada ({ver})")
        mi = json.loads(manifiesto_path(pid).read_text())["miniatura"]
        e = {"pieza": pid, "version": ver, "sha256": mi["sha256"], "asset_id": (v.get("miniatura") or {}).get("asset_id"), "archivo": mi["archivo"]}
        f = bajar(e, carpeta_tmp, env)
        if sha256(f) != mi["sha256"]: raise publicador.NoAprobada(f"{pid}: la miniatura descargada no es la aprobada")
        r = youtube.poner_miniatura(pid, video_id, f, ver, env=env, http=http)
        est.update(estado=r["estado"], fecha=ahora_iso()); est.pop("motivo", None)
        if r["estado"] == "SIMULADO": est.pop("intentos", None)
    except (publicador.NoAprobada, youtube.ErrorYouTube, publicar.SinRed, OSError, KeyError, ValueError) as x:
        est.update(estado="ERROR", motivo=f"{type(x).__name__}: {x}"[:300], fecha=ahora_iso(), intentos=est.get("intentos", 0) + 1)
    v["miniatura_yt"] = est
    return est


if __name__ == "__main__":
    accion = sys.argv[1] if len(sys.argv) > 1 else "listar"
    pid = sys.argv[2] if len(sys.argv) > 2 else None
    if accion == "listar":
        print(json.dumps(pendientes(), ensure_ascii=False, indent=1)); sys.exit(0)
    if accion == "validar":
        if not es_documental(pid): sys.exit(f"id inválido: {pid}")
        g = json.loads(guion_path(pid).read_text()); e = esquema.validar(g)
        print(json.dumps({"id": pid, "valido": not e, "minutos_estimados": round(esquema.minutos_estimados(g), 1), "errores": e}, ensure_ascii=False, indent=1))
        sys.exit(1 if e else 0)
    import publicador
    env = publicador.con_autorizacion(os.environ)
    if accion == "producir":
        if not es_documental(pid): sys.exit(f"id inválido: {pid!r} (formato D<AAAAMMDD>-<sufijo>)")
        r = producir(pid, env=env)
    elif accion == "programar":
        r = programar(env=env)
    else:
        sys.exit(f"acción desconocida: {accion}")
    out = RAIZ / "registro" / "documentales.jsonl"; out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a") as h: h.write(json.dumps({"accion": accion, "fecha": ahora_iso(), **r}, ensure_ascii=False) + "\n")
    print(json.dumps(r, ensure_ascii=False, indent=1))
    if accion == "producir" and r["estado"] not in ("REVISION_HUMANA",): sys.exit(1 if r["estado"] in ("ERROR", "INVALIDO", "ID_INVALIDO") else 0)
