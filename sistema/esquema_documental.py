"""Esquema y validador del guion de un DOCUMENTAL semanal de YouTube (decisión del responsable, 26-11-2026: un documental
de caso real por semana, horizontal, de 8 a 12 min, en lugar del video semanal que junta Reels).

El guion lo escribe y verifica el editor (Claude) en documentales/<ID>/guion.json; este módulo solo comprueba su FORMA y
las reglas de producción, no la exactitud jurídica (eso es la revisión editorial):

{
 "id": "D20261206-xxx",            # D + fecha de publicación (AAAAMMDD) + sufijo en minúsculas
 "titulo": str (≤ 100),            # título del video en YouTube
 "titulo_corto": str (opcional),   # ≤ 6 palabras del título para la miniatura; si falta: el título o lo que va antes de «:»
 "descripcion": str,               # resumen para YouTube (los capítulos, las fuentes y el aviso se agregan solos)
 "fecha": "AAAA-MM-DD",            # se publica ese día a las 12:00 CDMX
 "aviso": str,                     # obligatorio; el aviso de marca «Información general, no asesoría legal.» lo añade el sistema
 "escenas": [ { "n": int, "capitulo": str|null,  # inicia capítulo si es distinto del de la escena anterior
                "narracion": str,
                "pantalla": { "tipo": "titulo"|"cita"|"linea_tiempo"|"dato"|"documento"|"pregunta"|"recreacion"|"cierre",
                              "textos": [str, ...], "fuente_corta": str|null,
                              "escenario": "tribunal"|"oficina"|"calle"|"casa"|"generico" (opcional, solo «recreacion") },
                "fuentes": [ {"tipo": "ley"|"sentencia"|"tesis"|"oficial"|"hemerografica", "referencia": str, "url": str} ] } ],
 "fuentes": [ ... lista completa ... ]
}

Reglas: duración estimada de 6 a 15 min por la longitud de la narración (≈ 150 palabras por minuto); al menos 3 capítulos y
el primero en la escena 1; cada escena «cita» o «dato» con al menos una fuente (que además esté en la lista completa); las
escenas «recreacion» llevan SIEMPRE el rótulo visible «Recreación» (lo dibuja el render; el guion no puede pedir quitarlo);
prohibidas las fotos de personas reales y el material de terceros: el guion no puede traer imágenes, videos, audios ni
archivos (solo textos que el render convierte en gráficos originales de la marca).

Uso:  python sistema/esquema_documental.py documentales/<ID>/guion.json
"""
import json, re, sys
from datetime import date
from pathlib import Path

PALABRAS_POR_MIN = 150
MIN_MIN, MAX_MIN = 6.0, 15.0                    # duración estimada admitida (la meta editorial es de 8 a 12 min)
AVISO = "Información general, no asesoría legal."
TIPOS = ("titulo", "cita", "linea_tiempo", "dato", "documento", "pregunta", "recreacion", "cierre")
TIPOS_FUENTE = ("ley", "sentencia", "tesis", "oficial", "hemerografica", "tratado", "cronica")   # 26-11: tratado y crónica oficial (guion D20261206-T001)
ESCENARIOS = ("tribunal", "oficina", "calle", "casa", "generico")
CON_FUENTE = ("cita", "dato")
ROTULO_RECREACION = "Recreación"
ID_RE = re.compile(r"D(\d{8})-[A-Za-z0-9][A-Za-z0-9-]{1,40}")
TITULO_MAX = 100
TITULO_CORTO_MAX = 6
NARRACION_MAX = 1400                             # caracteres por escena: una escena larga es una diapositiva estática
TEXTOS_MAX = {"linea_tiempo": 6, "cierre": 5, "documento": 5}
TEXTO_MAX_CAR = {"cita": 420, "documento": 220}
TEXTO_MAX_CAR_DEF = 160
# Nada de imágenes, videos, audios ni archivos externos: el render solo dibuja gráficos originales de la marca.
CLAVES_PROHIBIDAS = {"imagen", "imagenes", "foto", "fotos", "fotografia", "video", "videos", "audio", "archivo", "archivos",
                     "media", "clip", "url_imagen", "rostro", "retrato", "material"}
ARCHIVO_RE = re.compile(r"(https?://|www\.)|\.(jpe?g|png|gif|webp|bmp|tiff?|heic|mp4|mov|avi|mkv|webm|mp3|wav|m4a)\b", re.I)


def palabras(t):
    return len(re.findall(r"\w+", t or ""))


def minutos_estimados(guion):
    return sum(palabras(e.get("narracion")) for e in guion.get("escenas") or []) / PALABRAS_POR_MIN


def _palabras_norm(t):
    import unicodedata
    t = unicodedata.normalize("NFD", (t or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.findall(r"[a-z0-9ñ]+", t)


def titulo_corto(guion):
    """Tema de la miniatura: «titulo_corto» o, si el título tiene 6 palabras o menos, el título."""
    tc = (guion.get("titulo_corto") or "").strip()
    if tc: return tc
    t = (guion.get("titulo") or "").strip()
    for c in (t, t.split(":")[0].strip(), t.split("·")[0].strip()):      # «El caso X: …» → «El caso X»
        if c and len(_palabras_norm(c)) <= TITULO_CORTO_MAX: return c
    return ""


def capitulos(guion):
    """[(n de la escena que lo inicia, título)]. Un capítulo empieza en la escena cuyo «capitulo» no es null y es distinto del
    de la escena anterior: el editor puede escribirlo solo en la primera escena o repetirlo en todas las del capítulo."""
    out, previo = [], None
    for e in guion.get("escenas") or []:
        c = e.get("capitulo") if isinstance(e, dict) else None
        c = c.strip() if isinstance(c, str) and c.strip() else None
        if c and c != previo: out.append((e.get("n"), c))
        if c: previo = c
    return out


def capitulo_de(guion):
    """{n de escena: título del capítulo al que pertenece}."""
    out, actual = {}, None
    inicios = dict(capitulos(guion))
    for e in guion.get("escenas") or []:
        actual = inicios.get(e.get("n"), actual); out[e.get("n")] = actual
    return out


def _claves(o, ruta=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield f"{ruta}.{k}" if ruta else k, k
            yield from _claves(v, f"{ruta}.{k}" if ruta else k)
    elif isinstance(o, list):
        for i, v in enumerate(o): yield from _claves(v, f"{ruta}[{i}]")


def _fuente(f, donde, err):
    if not isinstance(f, dict): err.append(f"{donde}: cada fuente debe ser un objeto"); return None
    if f.get("tipo") not in TIPOS_FUENTE: err.append(f"{donde}: tipo de fuente «{f.get('tipo')}» no admitido ({', '.join(TIPOS_FUENTE)})")
    if not isinstance(f.get("referencia"), str) or len(f["referencia"].strip()) < 5: err.append(f"{donde}: falta la referencia")
    if not isinstance(f.get("url"), str) or not re.match(r"https://\S+\.\S+", f.get("url") or ""): err.append(f"{donde}: la URL debe ser https://…")
    return (f.get("referencia"), f.get("url"))


def validar(guion, min_min=None, max_min=None):
    """Lista de errores (vacía = válido). min_min/max_min: límites de duración estimada en minutos (las pruebas los reducen)."""
    min_min = MIN_MIN if min_min is None else min_min; max_min = MAX_MIN if max_min is None else max_min
    err = []
    if not isinstance(guion, dict): return ["el guion debe ser un objeto JSON"]
    pid = guion.get("id") or ""
    m = ID_RE.fullmatch(pid)
    if not m: err.append(f"id «{pid}» inválido (formato D<AAAAMMDD>-<sufijo en minúsculas>)")
    try:
        f = date.fromisoformat(guion.get("fecha") or "")
        if m and m.group(1) != f"{f:%Y%m%d}": err.append(f"el id {pid} no corresponde a la fecha {guion['fecha']}")
    except (TypeError, ValueError):
        err.append("fecha inválida (AAAA-MM-DD)")
    t = guion.get("titulo")
    if not isinstance(t, str) or not t.strip(): err.append("falta el título")
    elif len(t) > TITULO_MAX or "<" in t or ">" in t: err.append(f"título de {len(t)} caracteres o con «<»/«>» (máximo {TITULO_MAX})")
    tc = titulo_corto(guion)
    if not tc: err.append(f"el título tiene más de {TITULO_CORTO_MAX} palabras: falta «titulo_corto» para la miniatura")
    elif len(_palabras_norm(tc)) > TITULO_CORTO_MAX: err.append(f"titulo_corto de más de {TITULO_CORTO_MAX} palabras")
    elif isinstance(t, str) and set(_palabras_norm(tc)) - set(_palabras_norm(t)):
        err.append("titulo_corto con palabras que no están en el título: " + ", ".join(sorted(set(_palabras_norm(tc)) - set(_palabras_norm(t)))))
    if not isinstance(guion.get("descripcion"), str) or len(guion["descripcion"].strip()) < 40: err.append("falta la descripción (40 caracteres o más)")
    elif len(guion["descripcion"]) > 2500: err.append("descripción de más de 2,500 caracteres (los capítulos y las fuentes también deben caber)")
    # El aviso de la marca («Información general, no asesoría legal.») lo pone SIEMPRE el sistema al inicio, al final y en la
    # descripción. El «aviso» del guion es obligatorio; si es otro texto (p. ej. el de las recreaciones) se agrega a la descripción.
    if not isinstance(guion.get("aviso"), str) or len(guion["aviso"].strip()) < 10: err.append("falta el aviso")
    elif len(guion["aviso"]) > 400: err.append("aviso de más de 400 caracteres")
    for ruta, k in _claves(guion):
        if k.lower() in CLAVES_PROHIBIDAS: err.append(f"{ruta}: no se admiten imágenes, videos, audios ni material de terceros (solo gráficos originales de la marca)")
    globales = set()          # URL de la lista completa (la escena puede citar la misma fuente con una referencia más corta)
    fg = guion.get("fuentes")
    if not isinstance(fg, list) or not fg: err.append("falta la lista completa de fuentes")
    else:
        for i, x in enumerate(fg):
            k = _fuente(x, f"fuentes[{i}]", err)
            if k: globales.add(k[1])
    esc = guion.get("escenas")
    if not isinstance(esc, list) or len(esc) < 3: err.append("se necesitan al menos 3 escenas"); return err
    for i, e in enumerate(esc, 1):
        d = f"escena {i}"
        if not isinstance(e, dict): err.append(f"{d}: debe ser un objeto"); continue
        if e.get("n") != i: err.append(f"{d}: «n» debe ser {i} (consecutivo desde 1)")
        if e.get("capitulo") is not None and (not isinstance(e["capitulo"], str) or not e["capitulo"].strip() or len(e["capitulo"]) > 60):
            err.append(f"{d}: «capitulo» debe ser null o un título de 1 a 60 caracteres")
        n = e.get("narracion")
        if not isinstance(n, str) or palabras(n) < 3: err.append(f"{d}: falta la narración")
        elif len(n) > NARRACION_MAX: err.append(f"{d}: narración de {len(n)} caracteres (máximo {NARRACION_MAX}: divídela en más escenas)")
        elif ARCHIVO_RE.search(n): err.append(f"{d}: la narración no debe contener URL ni nombres de archivo")
        p = e.get("pantalla")
        if not isinstance(p, dict): err.append(f"{d}: falta «pantalla»"); continue
        tipo = p.get("tipo")
        if tipo not in TIPOS: err.append(f"{d}: tipo de pantalla «{tipo}» no admitido"); continue
        tx = p.get("textos")
        if not isinstance(tx, list) or not tx or not all(isinstance(x, str) and x.strip() for x in tx):
            err.append(f"{d}: «textos» debe ser una lista de textos no vacíos")
        else:
            maxi = TEXTOS_MAX.get(tipo, 3)
            if tipo == "linea_tiempo" and len(tx) < 2: err.append(f"{d}: la línea de tiempo necesita al menos 2 momentos")
            if len(tx) > maxi: err.append(f"{d}: {len(tx)} textos en pantalla (máximo {maxi} para «{tipo}»)")
            largos = [x[:30] for x in tx if len(x) > TEXTO_MAX_CAR.get(tipo, TEXTO_MAX_CAR_DEF)]
            if largos: err.append(f"{d}: texto en pantalla demasiado largo para leerse: «{largos[0]}…»")
            if any(ARCHIVO_RE.search(x) for x in tx): err.append(f"{d}: los textos en pantalla no deben contener URL ni archivos")
        fc = p.get("fuente_corta")
        if fc is not None and (not isinstance(fc, str) or len(fc) > 80): err.append(f"{d}: «fuente_corta» debe ser null o de 80 caracteres o menos")
        if tipo == "recreacion":
            if p.get("rotulo") not in (None, ROTULO_RECREACION): err.append(f"{d}: el rótulo de una recreación es siempre «{ROTULO_RECREACION}»")
            if p.get("escenario") not in (None,) + ESCENARIOS: err.append(f"{d}: escenario «{p.get('escenario')}» no admitido ({', '.join(ESCENARIOS)})")
        fu = e.get("fuentes")
        if fu is None: fu = []
        if not isinstance(fu, list): err.append(f"{d}: «fuentes» debe ser una lista"); fu = []
        if tipo in CON_FUENTE and not fu: err.append(f"{d}: una escena «{tipo}» necesita al menos una fuente")
        for j, x in enumerate(fu):
            k = _fuente(x, f"{d}.fuentes[{j}]", err)
            if k and globales and k[1] not in globales: err.append(f"{d}.fuentes[{j}]: su URL no está en la lista completa de fuentes")
    caps = capitulos(guion)
    if len(caps) < 3: err.append(f"se necesitan al menos 3 capítulos ({len(caps)})")
    if not (isinstance(esc[0], dict) and isinstance(esc[0].get("capitulo"), str) and esc[0]["capitulo"].strip()):
        err.append("el primer capítulo debe empezar en la escena 1")
    if len({c for _, c in caps}) != len(caps): err.append("un capítulo reaparece después de otro (títulos repetidos no consecutivos)")
    mins = minutos_estimados(guion)
    if not (min_min <= mins <= max_min):
        err.append(f"duración estimada de {mins:.1f} min (≈ {PALABRAS_POR_MIN} palabras/min); debe estar entre {min_min:g} y {max_min:g} min")
    return err


def cargar(ruta):
    return json.loads(Path(ruta).read_text())


if __name__ == "__main__":
    if len(sys.argv) < 2: sys.exit("uso: python sistema/esquema_documental.py documentales/<ID>/guion.json")
    g = cargar(sys.argv[1]); e = validar(g)
    print(json.dumps({"id": g.get("id"), "valido": not e, "minutos_estimados": round(minutos_estimados(g), 1),
                      "capitulos": [c for _, c in capitulos(g)], "errores": e}, ensure_ascii=False, indent=1))
    sys.exit(1 if e else 0)
