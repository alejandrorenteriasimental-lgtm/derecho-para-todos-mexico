"""Video largo semanal de YouTube (8 a 10 min) — decisión del responsable, 16-11-2026 (data/lanzamiento.json →
monetizacion_decisiones.youtube_video_largo_semanal: ruta de 4,000 h de visualización, que los Shorts no suman).

Qué hace (desde YOUTUBE_SEMANAL_DESDE de data/lanzamiento.json; antes no hace nada):
  · JUEVES (youtube-semanal.yml, «armar»): reúne Reels del calendario YA APROBADOS en su versión exacta y YA PUBLICADOS
    (fecha anterior a hoy, dentro del tramo autorizado y con el plazo de veto vencido antes de su hora) de los últimos 7 días,
    agrupados por rama del derecho (la del artículo que cita cada Reel; la Constitución, arts. 13 a 23, cuenta como justicia
    penal). Si la rama no llega a 8 min, completa con Reels publicados antes de la misma rama (primero los que no se han usado
    en otro video semanal). Nunca usa piezas no aprobadas: cada archivo se descarga del respaldo y se comprueba su huella.
  · Arma un video horizontal 1920x1080: intro y cierre de marca (marca/tokens.json, logotipo y firma sonora; sin rediseño),
    cada Reel centrado sobre el fondo de marca con la pregunta y su fuente a los lados, fundidos breves y audio normalizado
    (−14 LUFS, pico ≤ −1 dBTP, dos pasadas). Título, descripción con capítulos y fuentes oficiales de cada segmento, y el
    aviso «Información general, no asesoría legal».
  · Auditoría técnica: duración de 8 a 10 min, 1920x1080, H.264, 30 cps, AAC 48 kHz estéreo, sonoridad, integridad, capítulos
    (≥ 3, el primero en 0:00, ≥ 10 s cada uno) y fuentes presentes. Si falla, queda RETENIDO y no se revisa.
  · Respaldo en el release privado con su SHA-256; queda en REVISION_HUMANA (estado/youtube_semanal.json). Aprobación
    delegada con 72 h de veto: python sistema/decidir.py aprobar Y<AAAAMMDD>-SEM <versión> --por "…" --delegada
  · DOMINGO 11:07 CDMX («programar»): si está aprobado y el veto terminó, lo sube con youtube.py como video normal (no Short)
    programado (publishAt) para el domingo 12:00 CDMX. Si el veto termina después, la ejecución del lunes 11:07 lo programa
    para las 12:00 de ese día. Idempotente con el libro de operaciones (marca «…-yt»): nunca se sube dos veces.
Costo: 0 MXN (minutos de Actions dentro de la guardia; cuota gratuita de la API de YouTube).

Uso:  python sistema/youtube_semanal.py activo | armar | programar | listar
"""
import hashlib, json, os, re, subprocess, sys, unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

RAIZ = Path(__file__).resolve().parent.parent
REG = RAIZ / "estado" / "youtube_semanal.json"
DIR = RAIZ / "semanal"
CAL = RAIZ / "data" / "calendario_lanzamiento.json"
AUT = RAIZ / "data" / "lanzamiento.json"
PIEZAS = RAIZ / "registro" / "piezas.jsonl"
FIRMA = RAIZ / "marca" / "firma_sonora.wav"      # identidad sonora de la marca (no cambia)
MX = timezone(timedelta(hours=-6))
W, H, FPS = 1920, 1080, 30
DUR_MIN, DUR_MAX = 480.0, 600.0              # 8 a 10 min
INTRO_S, CIERRE_S, FUNDIDO_S = 5.0, 6.0, 0.3
HORA_PUBLICACION = (12, 0)                   # domingo 12:00 CDMX
AVISO = "Información general, no asesoría legal."
CAPITULO_MIN_S = 10                          # YouTube: capítulos de al menos 10 s, el primero en 0:00, mínimo 3

RAMAS = {"LFT": "laboral", "LSS": "laboral", "LFPC": "consumidor", "LPDUSF": "consumidor", "LIC": "consumidor",
         "CPF": "penal", "CNPP": "penal", "LNEP": "penal", "LGV": "penal",
         "CPEUM": "constitucional", "LAmp": "constitucional", "LOPJF": "constitucional", "LMigra": "constitucional",
         "CCF": "familia", "CNPCF": "familia", "LGDNNA": "familia", "LGAMVLV": "familia",
         "LFPDPPP": "cotidiano", "LFDA": "cotidiano", "LAgra": "cotidiano"}
CPEUM_PENAL = range(13, 24)                  # CPEUM arts. 13 a 23: garantías en la investigación, detención, juicio y penas
TEMAS = {"laboral": "derechos laborales", "penal": "detenciones y justicia penal", "constitucional": "derechos constitucionales",
         "consumidor": "derechos del consumidor", "familia": "familia, niñez y vida libre de violencia", "cotidiano": "derechos de la vida diaria"}
LOCALES = ("CPF", "CCF")
# Si la rama no alcanza 8 min ni con sus Reels anteriores, se completa con la rama del derecho que la contiene: la justicia
# penal de los arts. 13 a 23 y los demás derechos de la Constitución son, ambos, derecho constitucional.
RAMA_AMPLIA = {"penal": ("constitucional", "derechos constitucionales y justicia penal"),
               "constitucional": ("penal", "derechos constitucionales y justicia penal")}


class NoDecidible(ValueError):
    pass


def ahora_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def es_semanal(pid):
    return bool(re.fullmatch(r"Y\d{8}-SEM", str(pid)))


def domingo_de(d):
    """El domingo siguiente (o el mismo día si ya es domingo)."""
    return d + timedelta(days=(6 - d.weekday()) % 7)


def id_semana(domingo):
    return f"Y{domingo:%Y%m%d}-SEM"


def hora_publicacion(domingo):
    return datetime(domingo.year, domingo.month, domingo.day, *HORA_PUBLICACION, tzinfo=MX)


def desde(archivo=None):
    try: return json.loads(Path(archivo or AUT).read_text()).get("YOUTUBE_SEMANAL_DESDE")
    except (OSError, ValueError): return None


def activo(hoy, archivo=None):
    d = desde(archivo)
    return bool(d) and hoy.isoformat() >= d


def cargar():
    try: return json.loads(REG.read_text())
    except (OSError, ValueError): return {}


def guardar(reg):
    REG.parent.mkdir(parents=True, exist_ok=True)
    REG.write_text(json.dumps(reg, ensure_ascii=False, indent=1) + "\n")


def _plano(t):
    t = unicodedata.normalize("NFD", (t or "").lower())
    return re.sub(r"\s+", " ", "".join(c for c in t if unicodedata.category(c) != "Mn")).strip()


_SIGLAS = None


def sigla_de(documento):
    global _SIGLAS
    if _SIGLAS is None:
        try: _SIGLAS = {_plano(o["documento"]): o["sigla"] for o in json.loads((RAIZ / "data" / "ordenamientos.json").read_text())["ordenamientos"]}
        except (OSError, ValueError, KeyError): _SIGLAS = {}
    return _SIGLAS.get(_plano(documento))


def ficha_principal(g):
    """La ficha de la cita del Reel (primera afirmación de la escena «cita»); si no hay, la primera ficha."""
    fichas = g.get("fuentes") or {}
    if isinstance(fichas, list): fichas = {f.get("id"): f for f in fichas}
    for e in g.get("escenas", []):
        if e.get("tipo") == "cita":
            for a in e.get("afirmaciones") or []:
                if a.get("fuente") in fichas: return fichas[a["fuente"]]
    return next(iter(fichas.values()), {})


def rama_de(g):
    f = ficha_principal(g); s = sigla_de(f.get("documento"))
    if s == "CPEUM":
        m = re.match(r"\d+", str(f.get("articulo", "")))
        if m and int(m.group()) in CPEUM_PENAL: return "penal"
    return RAMAS.get(s, "cotidiano")


def fuentes_de(g):
    fichas = g.get("fuentes") or {}
    vistos, out = set(), []
    for f in (fichas.values() if isinstance(fichas, dict) else fichas):
        k = (f.get("documento"), str(f.get("articulo")))
        if k in vistos: continue
        vistos.add(k); out.append({"documento": f.get("documento"), "articulo": str(f.get("articulo")), "url": f.get("url"), "sigla": sigla_de(f.get("documento"))})
    return out


def duracion_registrada(pid):
    d = None
    try:
        for l in PIEZAS.read_text().splitlines():
            if l.strip():
                x = json.loads(l)
                if x.get("id") == pid: d = x.get("duracion_s")
    except (OSError, ValueError):
        return None
    return d


# ── selección ────────────────────────────────────────────────────────────────────────────────────────────────────
def _publicado(dia, e, hoy, desde_pub, hasta):
    """Aprobado en su versión exacta y ya publicado: fecha anterior a hoy, dentro del tramo autorizado y con el veto vencido
    antes de su hora de publicación (si no, el publicador no lo habría podido publicar)."""
    import publicador
    if dia["fecha"] >= hoy.isoformat(): return False
    if desde_pub and dia["fecha"] < desde_pub: return False
    if hasta and dia["fecha"] > hasta: return False
    try: d = publicador.ultima_decision(e["pieza"])
    except OSError: return False
    if not (d and d.get("decision") == "APROBADA" and d.get("version") == e.get("version") and d.get("huella_archivo") == e.get("sha256")):
        return False
    return publicador.plazo_de_veto(d, publicador.hora_utc(dia["fecha"], e.get("hora", "19:00"))) is None


def publicados(cal, hoy, env):
    import publicador
    desde_pub = publicador.desde_efectivo(env, cal); hasta = env.get("PUBLICAR_HASTA")
    out = []
    for dia in cal.get("dias", []):
        e = dia.get("reel")
        if not e or not _publicado(dia, e, hoy, desde_pub, hasta): continue
        gp = RAIZ / "piezas" / e["pieza"] / "guion.json"
        try: g = json.loads(gp.read_text())
        except (OSError, ValueError): continue
        out.append({"fecha": dia["fecha"], "pieza": e["pieza"], "version": e["version"], "sha256": e["sha256"], "asset_id": e.get("asset_id"),
                    "archivo": e.get("archivo") or f'{e["pieza"]}_final.mp4', "release": e.get("release"), "hora": e.get("hora", "19:00"),
                    "titulo": g.get("titulo") or e["pieza"], "tema_id": g.get("tema_id"), "rama": rama_de(g), "fuentes": fuentes_de(g),
                    "duracion_s": duracion_registrada(e["pieza"]) or 40.0})
    return out


def seleccionar(cal, hoy, env, usados=()):
    """{"rama", "segmentos", "duracion_estimada"} o {"insuficiente": motivo}. Primero la semana (hoy−7 a hoy−1)."""
    pubs = publicados(cal, hoy, env)
    ini = (hoy - timedelta(days=7)).isoformat()
    semana = [p for p in pubs if ini <= p["fecha"] < hoy.isoformat()]
    if not semana:
        return {"insuficiente": f"no hay Reels aprobados y publicados del {ini} al {(hoy - timedelta(days=1)).isoformat()}"}
    ramas = {}
    for p in semana: ramas.setdefault(p["rama"], []).append(p)
    orden = sorted(ramas, key=lambda r: (-len(ramas[r]), -sum(p["duracion_s"] for p in ramas[r]), r))
    detalle = []
    for rama in orden:
        segs = sorted(ramas[rama], key=lambda p: p["fecha"])
        total = INTRO_S + CIERRE_S + sum(p["duracion_s"] for p in segs)
        if total > DUR_MAX - 5:                                  # semana muy cargada en una rama: se quitan los más antiguos
            while segs and total > DUR_MAX - 5: total -= segs.pop(0)["duracion_s"]
        previos = [p for p in pubs if p["rama"] == rama and p["fecha"] < ini]
        previos.sort(key=lambda p: p["fecha"], reverse=True)                  # el más reciente primero…
        previos.sort(key=lambda p: p["pieza"] in set(usados))                 # …y los que no salieron en otro video semanal, antes
        extra = []
        for p in previos:
            if total >= DUR_MIN + 20: break
            if total + p["duracion_s"] > DUR_MAX - 10: continue
            extra.append(p); total += p["duracion_s"]
        tema = TEMAS.get(rama, rama)
        if total < DUR_MIN + 5 and rama in RAMA_AMPLIA:          # segundo nivel: la rama del derecho que la contiene
            otra, tema_amplio = RAMA_AMPLIA[rama]
            vecinos = [p for p in pubs if p["rama"] == otra and p not in segs + extra]
            vecinos.sort(key=lambda p: p["fecha"], reverse=True); vecinos.sort(key=lambda p: (p["fecha"] < ini, p["pieza"] in set(usados)))
            agregados = 0
            for p in vecinos:
                if total >= DUR_MIN + 20: break
                if total + p["duracion_s"] > DUR_MAX - 10: continue
                extra.append(p); total += p["duracion_s"]; agregados += 1
            if agregados: tema = tema_amplio
        segs += sorted(extra, key=lambda p: p["fecha"])
        if DUR_MIN + 5 <= total <= DUR_MAX - 5 and len(segs) >= 3:
            return {"rama": rama, "tema": tema, "segmentos": segs, "duracion_estimada": round(total, 1),
                    "de_la_semana": len(ramas[rama]), "anteriores": len(extra)}
        detalle.append(f"{rama}: {round(total)} s con {len(segs)} Reels")
    return {"insuficiente": "ninguna rama de la semana alcanza 8 min con Reels aprobados y publicados (" + "; ".join(detalle) + ")"}


# ── título, descripción y capítulos ──────────────────────────────────────────────────────────────────────────────
def marca_tiempo(s):
    s = int(s); h, m, x = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02d}:{x:02d}" if h else f"{m}:{x:02d}"


def capitulos(segmentos, duraciones):
    """Un capítulo por Reel; la intro va dentro del primero (empieza en 0:00) y el cierre dentro del último."""
    caps, t = [], INTRO_S
    for i, (s, d) in enumerate(zip(segmentos, duraciones)):
        inicio = 0.0 if i == 0 else t
        caps.append({"inicio_s": round(inicio, 2), "marca": marca_tiempo(inicio), "titulo": s["titulo"].replace("<", "").replace(">", "")})
        t += d
    return caps


def titulo_video(sel):
    t = f'{len(sel["segmentos"])} preguntas sobre {sel["tema"]}: lo que dice la ley en México'
    return t if len(t) <= 100 else f'{sel["tema"].capitalize()}: lo que dice la ley en México'[:100]


def descripcion_video(sel, caps):
    segs = sel["segmentos"]
    locales = any(f.get("sigla") in LOCALES for s in segs for f in s["fuentes"])
    lin = [f'Las preguntas de la semana sobre {sel["tema"]}, cada una respondida con el texto oficial de la norma que la contesta.',
           "", "Capítulos:"] + [f'{c["marca"]} {c["titulo"]}' for c in caps] + ["", "Fuentes oficiales:"]
    for s in segs:
        refs = "; ".join(f'{f["documento"]}, artículo {f["articulo"]}' + (f' ({f["url"]})' if f.get("url") else "") for f in s["fuentes"])
        lin.append(f'• {s["titulo"]} — {refs}')
    lin += ["", AVISO + (" Las leyes penales y civiles pueden variar según tu estado." if locales else ""), "",
            "Aquí Dice la Ley · El Derecho, explicado en voz clara."]
    return "\n".join(lin).replace("<", "").replace(">", "")


def controles_metadatos(m, duracion):
    """Capítulos, fuentes, aviso y límites de YouTube. Devuelve la lista de controles (APROBADO/FALLA)."""
    res = []
    def ok(nombre, cond, detalle=""): res.append({"control": nombre, "resultado": "APROBADO" if cond else "FALLA", "detalle": detalle})
    caps, desc, tit = m.get("capitulos") or [], m.get("descripcion") or "", m.get("titulo") or ""
    inicios = [c["inicio_s"] for c in caps]
    ok("Capítulos: al menos 3, el primero en 0:00", len(caps) >= 3 and caps[0]["marca"] == "0:00" and inicios[0] == 0, f"{len(caps)} capítulos")
    tramos = [b - a for a, b in zip(inicios, inicios[1:] + [duracion])]
    ok(f"Capítulos en orden y de {CAPITULO_MIN_S} s o más", all(t >= CAPITULO_MIN_S for t in tramos) and inicios == sorted(inicios), f"mínimo {min(tramos, default=0):.0f} s")
    ok("Capítulos escritos en la descripción", all(f'{c["marca"]} {c["titulo"]}' in desc for c in caps), "")
    faltan = [s["pieza"] for s in m.get("segmentos", []) if not s.get("fuentes") or not all(f'{f["documento"]}, artículo {f["articulo"]}' in desc for f in s["fuentes"])]
    ok("Fuentes oficiales de cada segmento en la descripción", not faltan, ", ".join(faltan) or f'{len(m.get("segmentos", []))} segmentos')
    ok("Aviso «Información general, no asesoría legal»", AVISO.lower() in desc.lower(), "")
    ok("Título de 100 caracteres o menos, sin «<» ni «>»", 0 < len(tit) <= 100 and "<" not in tit and ">" not in tit, f"{len(tit)} caracteres")
    ok("Descripción de 4,900 caracteres o menos (sin recorte en YouTube)", len(desc) <= 4900 and "<" not in desc and ">" not in desc, f"{len(desc)} caracteres")
    return res


# ── video ────────────────────────────────────────────────────────────────────────────────────────────────────────
FF_TIMEOUT_S = 1200          # 17-11: una llamada a ffmpeg que no termina falla con error claro en lugar de agotar el trabajo


def _ff(args):
    """ffmpeg sin leer la entrada estándar (-nostdin) y con tiempo límite (17-11-2026: el ciclo 44063222044 quedó colgado
    23 min en las pruebas con un ffmpeg huérfano tras agregar el video semanal)."""
    try:
        r = subprocess.run(["ffmpeg", "-nostdin", "-y", "-hide_banner", "-loglevel", "error"] + args, capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=FF_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"ffmpeg: no terminó en {FF_TIMEOUT_S} s")
    if r.returncode: raise RuntimeError(f"ffmpeg: {r.stderr.strip()[-400:]}")


def duracion(mp4):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp4)], capture_output=True, text=True)
    return float(r.stdout.strip())


def _fondo():
    """Fondo de marca 1920x1080 (noche → noche 2, resplandor frío y líneas diagonales tenues), como las portadas y el Reel."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter
    import marca
    y = np.linspace(0, 1, H)[:, None, None]
    base = np.array(marca.C["noche"]) * (1 - y) + np.array(marca.C["noche_2"]) * y
    im = Image.fromarray(np.repeat(base, W, axis=1).astype(np.uint8)).convert("RGBA")
    capa = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(capa)
    d.ellipse([W * 0.58, -H * 0.5, W * 1.2, H * 1.0], fill=(70, 110, 160, 70))
    im.alpha_composite(capa.filter(ImageFilter.GaussianBlur(H * 0.2)))
    lin = Image.new("RGBA", (W, H), (0, 0, 0, 0)); dl = ImageDraw.Draw(lin)
    for x in range(-H, W, 120): dl.line([(x, 0), (x + H, H)], fill=(255, 255, 255, 9), width=2)
    im.alpha_composite(lin)
    return im


def _envolver(d, texto, fuente, ancho):
    lineas, actual = [], ""
    for w in texto.split():
        p = (actual + " " + w).strip()
        if d.textlength(p, font=fuente) <= ancho: actual = p
        else:
            if actual: lineas.append(actual)
            actual = w
    return lineas + ([actual] if actual else [])


def _texto(d, xy, lineas, fuente, color, interlinea=1.18):
    x, y = xy
    for l in lineas:
        d.text((x, y), l, font=fuente, fill=color); y += int(fuente.size * interlinea)
    return y


def tarjeta(tipo, sel, n=None, seg=None):
    """Tarjetas de marca: «intro», «cierre» o el fondo de un segmento (pregunta a la izquierda, fuente a la derecha)."""
    from PIL import ImageDraw
    import marca
    im = _fondo(); d = ImageDraw.Draw(im); C, F = marca.C, marca.F
    if tipo in ("intro", "cierre"):
        logo = marca.logo_horizontal(170, "oscuro"); im.alpha_composite(logo, ((W - logo.width) // 2, 200))
        if tipo == "intro":
            l1 = _envolver(d, f'Esta semana: {sel["tema"]}', F("display_black", 76), 1500)
            y = 470
            for l in l1:
                f = F("display_black", 76); d.text(((W - d.textlength(l, font=f)) / 2, y), l, font=f, fill=C["papel"]); y += 92
            sub = f'{len(sel["segmentos"])} preguntas, cada una con su fuente oficial'
            f = F("semi", 40); d.text(((W - d.textlength(sub, font=f)) / 2, y + 30), sub, font=f, fill=C["cempasuchil"])
        else:
            y = 480
            for l, f, c in ((AVISO, F("display_xbold", 58), C["papel"]),
                            ("Las fuentes oficiales de cada respuesta están en la descripción.", F("semi", 36), C["bruma"]),
                            ("Síguenos para entender tus derechos.", F("semi", 42), C["cempasuchil"])):
                d.text(((W - d.textlength(l, font=f)) / 2, y), l, font=f, fill=c); y += int(f.size * 1.9)
        return im.convert("RGB")
    # segmento: el Reel (608x1080) va centrado en x = 656; paneles laterales de 520 px
    xl, xr, ancho = 90, 1330, 500
    d.text((xl, 150), f"PREGUNTA {n} DE {len(sel['segmentos'])}", font=F("semi", 30), fill=C["cempasuchil"])
    tam = 58
    while True:
        f = F("display_xbold", tam); lin = _envolver(d, seg["titulo"], f, ancho)
        if len(lin) <= 6 or tam <= 40: break
        tam -= 4
    y = _texto(d, (xl, 205), lin, f, C["papel"])
    d.rectangle([xl, y + 30, xl + 120, y + 36], fill=C["cempasuchil"])
    d.text((xl, y + 60), sel["tema"].capitalize(), font=F("semi", 30), fill=C["bruma"])
    d.text((xl, H - 90), AVISO, font=F("texto", 24), fill=C["bruma"])
    d.text((xr, 150), "FUENTE OFICIAL", font=F("semi", 30), fill=C["cempasuchil"])
    y = 205
    for fu in seg["fuentes"][:3]:
        y = _texto(d, (xr, y), _envolver(d, fu["documento"], F("semi", 36), ancho), F("semi", 36), C["papel"])
        y = _texto(d, (xr, y + 4), [f'Artículo {fu["articulo"]}'], F("bold", 40), C["cempasuchil"]) + 26
    logo = marca.logo_horizontal(80, "oscuro"); im.alpha_composite(logo, (W - logo.width - 70, H - 80 - 60))
    return im.convert("RGB")


PRESET = "veryfast"           # las pruebas usan «ultrafast» (mismo formato, archivo más pesado)
COD_V = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", str(FPS), "-pix_fmt", "yuv420p", "-g", "60"]


def _cod_v():
    return [x if x != "veryfast" else PRESET for x in COD_V]
COD_A = ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]


FONDO_FIJO = f"loop=loop=-1:size=1:start=0,setpts=N/{FPS}/TB"   # la imagen se decodifica una vez (con -loop 1, en cada cuadro: el doble de tiempo)


def _parte_tarjeta(png, dur, salida):
    """Tarjeta fija con la firma sonora de la marca sobre el pad musical de los Reels (musica.pad, original y sin licencias)."""
    # 17-11-2026: «apad» sin límite (audio infinito acotado solo por atrim/-t) colgaba ffmpeg de forma intermitente con la
    # compilación master de BtbN que usa CI (3/20 locales con 2 núcleos; ciclo 44121434570 falló así). Con whole_dur: 0/70.
    import musica
    firma = FIRMA
    pad = Path(salida).with_suffix(".pad.wav"); musica.pad(dur, salida=str(pad))
    fv = f"fade=t=in:st=0:d={FUNDIDO_S},fade=t=out:st={dur - FUNDIDO_S:.3f}:d={FUNDIDO_S}"
    _ff(["-i", str(png), "-i", str(firma), "-i", str(pad), "-filter_complex",
         f"[0:v]format=yuv420p,{FONDO_FIJO},trim=duration={dur:.3f},{fv}[v];[1:a]aresample=48000,aformat=channel_layouts=stereo,volume=0.6,adelay=300|300[f];"
         f"[2:a]aresample=48000,aformat=channel_layouts=stereo,volume=0.35[p];[f][p]amix=inputs=2:duration=longest:normalize=0,"
         f"apad=whole_dur={dur:.3f},atrim=0:{dur:.3f},afade=t=out:st={dur - 0.5:.3f}:d=0.5[a]", "-map", "[v]", "-map", "[a]", "-t", f"{dur:.3f}"] + _cod_v() + COD_A + [str(salida)])
    pad.unlink(missing_ok=True)


def _parte_reel(png, reel, dur, salida):
    fv = f"fade=t=in:st=0:d={FUNDIDO_S},fade=t=out:st={dur - FUNDIDO_S:.3f}:d={FUNDIDO_S}"
    _ff(["-i", str(png), "-i", str(reel), "-filter_complex",
         f"[0:v]format=yuv420p,{FONDO_FIJO},trim=duration={dur:.3f}[bg];[1:v]scale=-2:{H},setsar=1,fps={FPS},format=yuv420p[r];"
         f"[bg][r]overlay=(W-w)/2:0:shortest=1:format=yuv420,format=yuv420p,{fv}[v];"
         f"[1:a]aresample=48000,aformat=channel_layouts=stereo,afade=t=in:st=0:d=0.15,afade=t=out:st={dur - FUNDIDO_S:.3f}:d={FUNDIDO_S}[a]",
         "-map", "[v]", "-map", "[a]", "-t", f"{dur:.3f}"] + _cod_v() + COD_A + [str(salida)])


def _normalizar(entrada, salida):
    """Sonoridad en dos pasadas (loudnorm medido + lineal): −14 LUFS integrados, pico verdadero ≤ −1.5 dBTP."""
    r = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-nostats", "-i", str(entrada), "-af", "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json",
                        "-f", "null", "-"], capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=FF_TIMEOUT_S)
    m = json.loads(r.stderr[r.stderr.rfind("{"):r.stderr.rfind("}") + 1])
    filtro = (f"loudnorm=I=-14:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:"
              f"measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true,aresample=48000")
    _ff(["-i", str(entrada), "-map", "0:v", "-map", "0:a", "-c:v", "copy", "-af", filtro] + COD_A + ["-movflags", "+faststart", str(salida)])


def armar_video(sel, archivos, carpeta, pid):
    """Compone el MP4 final. archivos = [ruta del Reel descargado y comprobado] en el orden de sel["segmentos"]."""
    tmp = carpeta / "tmp"; tmp.mkdir(parents=True, exist_ok=True); salida = carpeta / "salida"; salida.mkdir(parents=True, exist_ok=True)
    partes, durs = [], []
    tarjeta("intro", sel).save(tmp / "intro.png"); _parte_tarjeta(tmp / "intro.png", INTRO_S, tmp / "00_intro.mp4"); partes.append(tmp / "00_intro.mp4")
    for i, (seg, f) in enumerate(zip(sel["segmentos"], archivos), 1):
        d = duracion(f); png = tmp / f"fondo_{i:02d}.png"; tarjeta("segmento", sel, i, seg).save(png)
        p = tmp / f"{i:02d}.mp4"; _parte_reel(png, f, d, p); partes.append(p); durs.append(duracion(p))
    tarjeta("cierre", sel).save(tmp / "cierre.png"); _parte_tarjeta(tmp / "cierre.png", CIERRE_S, tmp / "99_cierre.mp4"); partes.append(tmp / "99_cierre.mp4")
    lista = tmp / "lista.txt"; lista.write_text("".join(f"file '{p.resolve()}'\n" for p in partes))
    _ff(["-f", "concat", "-safe", "0", "-i", str(lista), "-c", "copy", str(tmp / "unido.mp4")])
    final = salida / f"{pid}_final.mp4"
    _normalizar(tmp / "unido.mp4", final)
    return final, durs, duracion(tmp / "00_intro.mp4")


def auditar(mp4, m, dur_min=None, dur_max=None):
    """Auditoría técnica del video largo (determinista, con ffprobe/ffmpeg) + controles de capítulos, fuentes y aviso."""
    dur_min = DUR_MIN if dur_min is None else dur_min; dur_max = DUR_MAX if dur_max is None else dur_max
    res = []
    def ok(nombre, cond, detalle=""): res.append({"control": nombre, "resultado": "APROBADO" if cond else "FALLA", "detalle": detalle})
    out = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(mp4)], capture_output=True, text=True).stdout
    info = json.loads(out or "{}")
    v = next((s for s in info.get("streams", []) if s["codec_type"] == "video"), {})
    au = [s for s in info.get("streams", []) if s["codec_type"] == "audio"]
    dur = float((info.get("format") or {}).get("duration") or 0)
    ok("Resolución 1920x1080 (16:9, video normal de YouTube)", v.get("width") == W and v.get("height") == H, f'{v.get("width")}x{v.get("height")}')
    ok("Códec H.264, yuv420p", v.get("codec_name") == "h264" and v.get("pix_fmt") == "yuv420p", f'{v.get("codec_name")}, {v.get("pix_fmt")}')
    try: fr = eval(v.get("r_frame_rate", "0/1"))
    except ZeroDivisionError: fr = 0
    ok("30 cuadros por segundo", abs(fr - FPS) < 0.01, f"{fr:.2f} fps")
    ok(f"Duración entre {dur_min / 60:g} y {dur_max / 60:g} min", dur_min <= dur <= dur_max, f"{dur:.1f} s")
    ok("Pista de audio AAC 48 kHz estéreo", bool(au) and au[0]["codec_name"] == "aac" and au[0]["sample_rate"] == "48000" and au[0]["channels"] == 2,
       f'{au[0]["codec_name"]}, {au[0]["sample_rate"]} Hz, {au[0]["channels"]} canales' if au else "sin audio")
    r = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(mp4), "-f", "null", "-"], capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=FF_TIMEOUT_S)
    ok("Archivo íntegro (decodificación completa sin errores)", r.returncode == 0 and not r.stderr.strip(), r.stderr.strip()[:200])
    err = subprocess.run(["ffmpeg", "-nostdin", "-nostats", "-i", str(mp4), "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=FF_TIMEOUT_S).stderr
    li = re.findall(r"I:\s+(-?[\d.]+) LUFS", err); tp = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", err)
    lufs = float(li[-1]) if li else None; pico = float(tp[-1]) if tp else None
    ok("Sonoridad -14 LUFS ±1.5 (audio normalizado)", lufs is not None and abs(lufs + 14) <= 1.5, f"{lufs} LUFS")
    ok("Pico verdadero ≤ -1 dBTP", pico is not None and pico <= -1.0, f"{pico} dBTP")
    err = subprocess.run(["ffmpeg", "-nostdin", "-nostats", "-i", str(mp4), "-af", "silencedetect=n=-45dB:d=2", "-f", "null", "-"], capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=FF_TIMEOUT_S).stderr
    sil = re.findall(r"silence_duration: ([\d.]+)", err)
    ok("Sin silencios mayores a 2 s", not sil, f"{len(sil)} silencios")
    err = subprocess.run(["ffmpeg", "-nostdin", "-nostats", "-i", str(mp4), "-vf", "blackdetect=d=1:pix_th=0.05", "-an", "-f", "null", "-"], capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=FF_TIMEOUT_S).stderr
    neg = re.findall(r"black_duration:([\d.]+)", err)
    ok("Sin pantallas negras mayores a 1 s (los fundidos son de 0.3 s)", not neg, f"{len(neg)} tramos")
    return res + controles_metadatos(m, dur), dur


# ── versión, registro y aprobación ───────────────────────────────────────────────────────────────────────────────
def manifiesto_path(pid):
    return DIR / pid / "manifiesto.json"


def version(pid):
    """(versión, huella del manifiesto, huella del MP4 respaldado). Cambia si cambia el título, la descripción, los
    capítulos, los segmentos o el archivo: una aprobación anterior deja de valer."""
    import respaldo
    mp = manifiesto_path(pid)
    hm = hashlib.sha256(mp.read_bytes()).hexdigest() if mp.exists() else ""
    ha = (respaldo.cargar().get(pid, {}).get(f"{pid}_final.mp4") or {}).get("sha256", "")
    if not (hm and ha): return None, hm, ha
    return hashlib.sha256(f"{hm}:{ha}".encode()).hexdigest()[:16], hm, ha


def armar(hoy=None, env=None, bajar=None, ahora=None):
    """Arma el video de la semana que termina el día anterior a «hoy» (jueves) para el domingo siguiente."""
    import publicador, respaldo
    env = env if env is not None else os.environ
    hoy = hoy or (datetime.now(timezone.utc).astimezone(MX)).date()
    ahora = ahora or datetime.now(timezone.utc)
    if not activo(hoy):
        return {"estado": "INACTIVO", "desde": desde(), "hoy": hoy.isoformat()}
    dom = domingo_de(hoy + timedelta(days=1)); pid = id_semana(dom)
    reg = cargar(); r = reg.get(pid) or {}
    if r.get("estado") in ("REVISION_HUMANA", "APROBADA", "PROGRAMADO", "RECHAZADA"):
        return {"estado": "YA_ARMADO", "pieza": pid, "estado_registro": r["estado"]}
    if env.get("PUBLICAR_HASTA") and dom.isoformat() > env["PUBLICAR_HASTA"]:
        return {"estado": "SIN_AUTORIZACION_DE_PUBLICACION", "pieza": pid}
    cal = json.loads(CAL.read_text())
    usados = {s["pieza"] for k, x in reg.items() if k != pid and x.get("estado") in ("REVISION_HUMANA", "APROBADA", "PROGRAMADO")
              for s in x.get("segmentos", []) if isinstance(s, dict)}
    sel = seleccionar(cal, hoy, env, usados)
    base = {"semana": {"del": (hoy - timedelta(days=7)).isoformat(), "al": (hoy - timedelta(days=1)).isoformat()}, "domingo": dom.isoformat(),
            "publicar_en": hora_publicacion(dom).isoformat(), "armado": ahora_iso()}
    if sel.get("insuficiente"):
        reg[pid] = {**base, "estado": "INSUFICIENTE", "motivo": sel["insuficiente"]}; guardar(reg)
        return {"estado": "INSUFICIENTE", "pieza": pid, "motivo": sel["insuficiente"]}
    carpeta = DIR / pid; (carpeta / "reels").mkdir(parents=True, exist_ok=True)
    bajar = bajar or publicador.descargar
    archivos = []
    try:
        for s in sel["segmentos"]:          # el archivo EXACTO aprobado: huella del calendario y aprobación vigente
            e = {k: s[k] for k in ("pieza", "version", "sha256", "asset_id", "archivo")}
            f = bajar(e, carpeta / "reels", env); publicador.comprobar(e, f, ahora); archivos.append(f)
        final, durs, intro = armar_video(sel, archivos, carpeta, pid)
    except Exception as x:                  # queda registrado; se puede repetir con youtube-semanal.yml (accion=armar)
        reg[pid] = {**base, "estado": "ERROR", "motivo": f"{type(x).__name__}: {x}"[:600], "segmentos": [s["pieza"] for s in sel["segmentos"]]}
        guardar(reg)
        return {"estado": "ERROR", "pieza": pid, "motivo": reg[pid]["motivo"]}
    caps = capitulos(sel["segmentos"], durs)
    for s, d, c in zip(sel["segmentos"], durs, caps): s.update(duracion_s=round(d, 2), inicio_s=c["inicio_s"])
    m = {"id": pid, **base, "rama": sel["rama"], "tema": sel["tema"], "titulo": titulo_video(sel), "capitulos": caps,
         "descripcion": descripcion_video(sel, caps), "de_la_semana": sel["de_la_semana"], "anteriores": sel["anteriores"],
         "segmentos": [{k: s.get(k) for k in ("fecha", "pieza", "version", "sha256", "titulo", "tema_id", "rama", "fuentes", "duracion_s", "inicio_s")} for s in sel["segmentos"]]}
    manifiesto_path(pid).write_text(json.dumps(m, ensure_ascii=False, indent=1) + "\n")
    tec, dur = auditar(final, m)
    (carpeta / "salida" / "auditoria.json").write_text(json.dumps({"tecnica": tec, "duracion_s": dur}, ensure_ascii=False, indent=1))
    resp = respaldo.respaldar(pid, carpeta / "salida", env)
    import shutil; shutil.rmtree(carpeta / "tmp", ignore_errors=True); shutil.rmtree(carpeta / "reels", ignore_errors=True)
    fallas = [f'{c["control"]} ({c["detalle"]})' for c in tec if c["resultado"] == "FALLA"]
    a = resp.get(f"{pid}_final.mp4") or {}
    r = {**base, "rama": m["rama"], "titulo": m["titulo"], "segmentos": m["segmentos"],
         "duracion_s": round(dur, 1), "sha256": a.get("sha256"), "asset_id": a.get("asset_id"), "release": a.get("release"),
         "archivo": f"{pid}_final.mp4", "fallas_tecnicas": fallas}
    if fallas:
        r.update(estado="RETENIDO", motivo="; ".join(fallas)[:600])
    else:
        ver, hm, ha = version(pid)
        r.update(estado="REVISION_HUMANA" if ver else "RETENIDO", revision={"version": ver, "huella_manifiesto": hm, "huella_archivo": ha, "preparada": ahora_iso()},
                 **({} if ver else {"motivo": "sin respaldo del archivo"}))
    reg[pid] = r; guardar(reg)
    return {"estado": r["estado"], "pieza": pid, "duracion_s": r["duracion_s"], "segmentos": len(m["segmentos"]), "rama": m["rama"],
            "version": (r.get("revision") or {}).get("version"), "fallas": fallas}


def pendientes():
    return [{"pieza": k, "formato": "video largo semanal de YouTube", "titulo": v.get("titulo"), "domingo": v.get("domingo"),
             "version": (v.get("revision") or {}).get("version"), "duracion_s": v.get("duracion_s"), "archivo": v.get("archivo"),
             "manifiesto": str(manifiesto_path(k).relative_to(RAIZ))}
            for k, v in sorted(cargar().items()) if v.get("estado") == "REVISION_HUMANA"]


def decidir(pid, decision, ver, por, nota="", canal="chat"):
    import revision
    reg = cargar(); v = reg.get(pid)
    permitido = {"REVISION_HUMANA": ("APROBADA", "RECHAZADA"), "APROBADA": ("RECHAZADA",)}
    if not v or decision not in permitido.get(v.get("estado"), ()):
        raise NoDecidible(f"{pid}: estado {v.get('estado') if v else 'desconocido'}; no admite «{decision}»")
    actual, hm, ha = version(pid)
    preparada = (v.get("revision") or {}).get("version")
    if not actual or ver != actual or ver != preparada:
        raise NoDecidible(f"{pid}: la versión {ver} no es la vigente (preparada {preparada}, actual {actual}); no se registró")
    if decision == "RECHAZADA" and not nota.strip():
        raise NoDecidible("un rechazo necesita el motivo (--nota)")
    fila = revision.registrar(pid, decision, ver, hm, ha, {"nombre": por}, canal, nota or "video largo semanal de YouTube")
    v.update(estado=decision, decision={"fecha": fila["fecha"], "canal": canal, "por": por, "nota": nota}); guardar(reg)
    return fila


# ── programación en YouTube ──────────────────────────────────────────────────────────────────────────────────────
def programar(ahora=None, env=None, http=None, bajar=None, carpeta="/tmp/youtube_semanal"):
    """Sube como video normal, programado (publishAt), cada video semanal aprobado cuyo plazo de veto ya terminó."""
    import publicador, publicar, youtube
    env = env if env is not None else os.environ
    ahora = ahora or datetime.now(timezone.utc)
    http = http or youtube.http_yt; bajar = bajar or publicador.descargar
    res = {"ahora": ahora.isoformat(timespec="minutes"), "acciones": []}
    p = publicador.pausado(env)
    if p: return {**res, "pausa": p}
    reg = cargar()
    for pid, v in sorted(reg.items()):
        if v.get("estado") != "APROBADA": continue
        acc = {"pieza": pid}
        ver = (v.get("revision") or {}).get("version")
        e = {"pieza": pid, "version": ver, "sha256": v.get("sha256"), "asset_id": v.get("asset_id"), "archivo": v.get("archivo") or f"{pid}_final.mp4"}
        objetivo = datetime.fromisoformat(v["publicar_en"])
        cuando = objetivo
        if cuando - ahora < timedelta(minutes=20):          # veto vencido tarde: siguiente 12:00 CDMX con al menos 20 min de margen
            d = ahora.astimezone(MX).date()
            cuando = hora_publicacion(d)
            if cuando - ahora < timedelta(minutes=20): cuando = hora_publicacion(d + timedelta(days=1))
        if cuando - objetivo > timedelta(days=6):
            v.update(estado="VENCIDO", motivo="no se pudo programar en la semana que le correspondía"); acc["estado"] = "VENCIDO"
            res["acciones"].append(acc); continue
        if env.get("PUBLICAR_HASTA") and cuando.astimezone(MX).date().isoformat() > env["PUBLICAR_HASTA"]:
            acc["estado"] = "SIN_AUTORIZACION_DE_PUBLICACION"; res["acciones"].append(acc); continue
        try:
            f = bajar(e, carpeta, env); publicador.comprobar(e, f, ahora)
            m = json.loads(manifiesto_path(pid).read_text())
            r = youtube.publicar_yt(pid, f, m["titulo"], m["descripcion"], ver, cuando, env=env, http=http, formato="video_largo")
            acc.update(estado=r["estado"], publicar_en=cuando.isoformat(timespec="minutes"), **({"tarde": True} if cuando != objetivo else {}))
            if r["estado"] == "PROGRAMADO":
                v.update(estado="PROGRAMADO", video_id=r.get("video_id"), programado_para=cuando.isoformat(timespec="minutes"))
            else:
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


if __name__ == "__main__":
    accion = sys.argv[1] if len(sys.argv) > 1 else "listar"
    hoy = datetime.now(timezone.utc).astimezone(MX).date()
    if accion == "activo":
        a = activo(hoy); print(json.dumps({"activo": a, "desde": desde(), "hoy": hoy.isoformat()}))
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a") as h: h.write(f"activo={'true' if a else 'false'}\n")
        sys.exit(0)
    if accion == "listar":
        print(json.dumps(pendientes(), ensure_ascii=False, indent=1)); sys.exit(0)
    import publicador
    env = publicador.con_autorizacion(os.environ)
    if accion == "armar":
        r = armar(env=env)
    elif accion == "programar":
        r = programar(env=env)
    else:
        sys.exit(f"acción desconocida: {accion}")
    out = RAIZ / "registro" / "youtube_semanal.jsonl"; out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a") as h: h.write(json.dumps({"accion": accion, **r}, ensure_ascii=False) + "\n")
    print(json.dumps(r, ensure_ascii=False, indent=1))
