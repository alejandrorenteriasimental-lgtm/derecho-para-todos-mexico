"""Verificación documental de fuentes jurídicas contra el documento oficial publicado.

Para cada fuente con nivel «oficial» el verificador:
  1. Valida la URL: https y dominio en la lista de dominios oficiales (coincidencia exacta de sufijo, no por subcadena).
  2. Descarga el documento (transporte inyectable para pruebas). Sin conexión o con error HTTP → RETENER, nunca aprobar.
  3. Extrae el texto (PDF con pypdf; HTML sin etiquetas), elimina encabezados repetidos de página y normaliza.
  4. Identidad: el título esperado del ordenamiento debe aparecer en el encabezado del documento.
  5. Vigencia: rechaza documentos con leyenda de abrogación; extrae «Última reforma publicada DOF dd-mm-aaaa»
     y la compara con la fecha registrada en el guion. Si el documento es más reciente → CAMBIO_NORMATIVO (retener
     y re-verificar el contenido, porque el artículo pudo cambiar).
  6. Contenido: localiza el encabezado «Artículo N» exacto (distingue 17 de 17 Bis o 170) y exige que el texto
     literal citado esté DENTRO de ese artículo, no en otro lugar del documento.
  7. Evidencia: guarda URL, estado HTTP, sha256 del archivo, tamaño, fecha de consulta, fecha de reforma extraída,
     posición del artículo y un extracto alrededor del literal, para que cualquier persona pueda repetir la comprobación.

Lo que NO hace (límites declarados): no interpreta el alcance jurídico de una afirmación; no verifica jurisprudencia
contra el Semanario Judicial (pendiente: verificar registro digital vía sjf2.scjn.gob.mx); no detecta reformas
publicadas en el DOF que aún no estén incorporadas al texto compilado. Las afirmaciones interpretativas se marcan
«requiere_criterio» y, por política, una pieza de riesgo alto no se aprueba sin revisión humana.
"""
import hashlib, io, json, re, unicodedata, urllib.error, urllib.request
from datetime import datetime, timezone, date
from urllib.parse import urlparse

VERSION = "0.3.2"   # al cambiar la lógica de cotejo, las piezas retenidas por verificación se vuelven a verificar

DOMINIOS_OFICIALES = (
    "diputados.gob.mx",        # Cámara de Diputados — LeyesBiblio (textos vigentes compilados)
    "scjn.gob.mx",             # Suprema Corte (incluye sjf2.scjn.gob.mx y www.scjn.gob.mx)
    "supremacorte.gob.mx",     # Suprema Corte (portal y Constitución comentada por artículo)
    "dof.gob.mx",              # Diario Oficial de la Federación
    "ordenjuridico.gob.mx",    # Orden Jurídico Nacional (SEGOB)
    "congresocdmx.gob.mx",     # se amplía por entidad conforme se usen leyes locales
)
UA = "DPT-verificador/0.2 (+divulgacion juridica; contacto en README)"


class SinConexion(Exception):
    pass


# ---------------- transporte ----------------
def transporte_http(url, timeout=60):
    """Devuelve (estado_http, content_type, bytes). Lanza SinConexion ante fallas de red."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", "") if e.headers else "", e.read() if hasattr(e, "read") else b""
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
        raise SinConexion(str(e))


# ---------------- normalización de texto ----------------
def _plano(t):
    t = unicodedata.normalize("NFD", t)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = t.replace("­", "").replace("“", '"').replace("”", '"').replace("«", '"').replace("»", '"')
    t = re.sub(r"-\s*\n\s*", "", t)            # palabras cortadas al final de línea
    return re.sub(r"\s+", " ", t).strip().lower()


def _sinpunt(t):
    """Comparación insensible a signos de puntuación (las compilaciones difieren en comas); las palabras deben coincidir."""
    return re.sub(r"\s+", " ", re.sub(r"[,;:.\"'()\[\]¿?¡!]", " ", t)).strip()


def _compacto(t):
    """Solo letras y dígitos, sin espacios ni puntuación. La extracción de texto de los PDF oficiales inserta espacios
    espurios dentro de las palabras («resp onsabilidad», «moti vo»); comparar en esta forma los neutraliza, y una sola
    letra distinta sigue haciendo fallar el cotejo."""
    return re.sub(r"[^a-z0-9ñ]", "", _plano(t))


def dominio_oficial(url):
    u = urlparse(url)
    if u.scheme != "https" or not u.hostname:
        return False, "la URL no usa https"
    h = u.hostname.lower()
    if any(h == d or h.endswith("." + d) for d in DOMINIOS_OFICIALES):
        return True, h
    return False, f"dominio no oficial: {h}"


def texto_de(content_type, datos):
    if datos[:5] == b"%PDF-" or "pdf" in content_type.lower():
        from pypdf import PdfReader
        paginas = [(p.extract_text() or "") for p in PdfReader(io.BytesIO(datos)).pages]
        # encabezados/pies repetidos en ≥50 % de las páginas (p. ej. «CÁMARA DE DIPUTADOS… Última Reforma DOF…  12 de 400»)
        cuenta = {}
        for p in paginas:
            for l in {re.sub(r"\d+", "#", l.strip()) for l in p.splitlines() if l.strip()}:
                cuenta[l] = cuenta.get(l, 0) + 1
        repetidas = {l for l, n in cuenta.items() if len(paginas) >= 3 and n >= 0.5 * len(paginas)}
        cabecera = "\n".join(paginas[:2])
        cuerpo = "\n".join("\n".join(l for l in p.splitlines() if re.sub(r"\d+", "#", l.strip()) not in repetidas) for p in paginas)
        return cabecera, cuerpo
    html = datos.decode("utf-8", "replace")
    html = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    t = re.sub(r"<[^>]+>", " ", html)
    import html as h
    t = h.unescape(t)
    return t[:6000], t


FECHA = r"(\d{1,2})[-/ ](\d{1,2})[-/ ](\d{4})"


def ultima_reforma(cabecera):
    m = re.search(r"ultima\s+reforma\s+publicada\s+dof\s+" + FECHA, _plano(cabecera))
    if not m:
        m = re.search(r"ultima\s+reforma\s+dof\s+" + FECHA, _plano(cabecera))
    if not m:
        return None
    d, mth, y = map(int, m.groups())
    return date(y, mth, d).isoformat()


def _lineas_planas(t):
    t = re.sub(r"-\s*\n\s*", "", t)
    return "\n".join(_plano(l) for l in t.splitlines())


def segmento_articulo(cuerpo, numero):
    """Texto del artículo `numero` hasta el siguiente encabezado de artículo.
    Un encabezado es «Artículo N.» al inicio de línea (las remisiones internas «el artículo 16 de…» no cortan el texto).
    Distingue «17» de «17 Bis» y de «170». Devuelve (texto_plano, posición) o (None, None)."""
    lp = _lineas_planas(cuerpo)
    num = re.escape(str(numero).lower())
    sufijo = r"(?:o\b|[°º])?"
    variantes = [  # (inicio del artículo buscado, inicio del siguiente artículo)
        # 1) encabezado al inicio de línea, como en los PDF de LeyesBiblio
        (rf"(?m)^[ \t]*articulo\s+{num}{sufijo}\s*[.\-–](?!\s*(?:bis|ter|quater)\b)",
         rf"(?m)^[ \t]*articulo\s+\d+{sufijo}(?:\s+(?:bis|ter|quater))?\s*[.\-–]"),
        # 2) texto con líneas fusionadas: exige punto tras el número y mayúscula/palabra después
        (rf"\barticulo\s+{num}{sufijo}\s*\.(?!\s*(?:bis|ter|quater)\b)",
         rf"\barticulo\s+\d+{sufijo}(?:\s+(?:bis|ter|quater))?\s*\.\s+[a-z]"),
    ]
    for ini_pat, sig_pat in variantes:
        m = re.search(ini_pat, lp)
        if m:
            n = re.compile(sig_pat).search(lp, m.end())
            return re.sub(r"\s+", " ", lp[m.end(): n.start() if n else len(lp)]).strip(), m.start()
    return None, None


_TABLA = str.maketrans("ÁÉÍÓÚÜÑáéíóúüñ", "AEIOUUNaeiouun")


def articulo_texto(cuerpo, numero, max_car=6000):
    """Texto ORIGINAL (con mayúsculas y acentos) del artículo, con las mismas reglas de encabezado que
    segmento_articulo. La normalización conserva la longitud para poder recortar el original."""
    orig = re.sub(r"-[ \t]*\n[ \t]*", "", cuerpo)
    norm = orig.translate(_TABLA).lower()
    if len(norm) != len(orig):
        return None
    num = re.escape(str(numero).lower()); suf = r"(?:o\b|[°º])?"
    pares = [(rf"(?m)^[ \t]*articulo\s+{num}{suf}\s*[.\-–](?!\s*(?:bis|ter|quater)\b)",
              rf"(?m)^[ \t]*articulo\s+\d+{suf}(?:\s+(?:bis|ter|quater))?\s*[.\-–]"),
             (rf"\barticulo\s+{num}{suf}\s*\.(?!\s*(?:bis|ter|quater)\b)",
              rf"\barticulo\s+\d+{suf}(?:\s+(?:bis|ter|quater))?\s*\.\s+[a-z]")]
    for ini, sig in pares:
        m = re.search(ini, norm)
        if m:
            n = re.compile(sig).search(norm, m.end())
            return re.sub(r"\s+", " ", orig[m.end(): n.start() if n else len(orig)]).strip()[:max_car]
    return None


def contiene(texto_oficial, cita):
    """¿La cita aparece en el texto oficial? (insensible a mayúsculas, acentos y puntuación)."""
    return len(_plano(cita).split()) >= 5 and _compacto(cita) in _compacto(texto_oficial)


# ---------------- verificación de una fuente ----------------
def verificar_fuente(f, transporte=transporte_http, ahora=None):
    ev = {"fuente": f.get("id"), "url": f.get("url"), "consultado": (ahora or datetime.now(timezone.utc)).isoformat(timespec="seconds")}
    def res(estado, motivo, **kw):
        ev.update(kw); ev["estado"] = estado; ev["motivo"] = motivo; return ev

    if f.get("nivel") != "oficial":
        return res("NO_VERIFICABLE", "fuente secundaria: no sustenta por sí sola una afirmación jurídica")
    faltan = [k for k in ("url", "documento", "articulo", "literal") if not f.get(k)]
    if faltan:
        return res("RECHAZADA", f"ficha de fuente incompleta: faltan {', '.join(faltan)}")
    ok, info = dominio_oficial(f["url"])
    if not ok:
        return res("RECHAZADA", info)
    try:
        estado, ctype, datos = transporte(f["url"])
    except SinConexion as e:
        return res("RETENER", f"sin conexión con la fuente oficial ({e}); no se aprueba sin comprobar")
    ev.update({"http": estado, "bytes": len(datos), "sha256": hashlib.sha256(datos).hexdigest()})
    if estado != 200:
        return res("RECHAZADA" if estado in (404, 410) else "RETENER", f"HTTP {estado}")
    if len(datos) < 200:
        return res("RETENER", "respuesta vacía o truncada")
    try:
        cabecera, cuerpo = texto_de(ctype, datos)
    except Exception as e:
        return res("RETENER", f"no se pudo extraer el texto: {type(e).__name__}")
    cab, cue = _plano(cabecera), _plano(cuerpo)
    if _plano(f["documento"]) not in cab:
        return res("RECHAZADA", "el documento descargado no es el ordenamiento citado", titulo_esperado=f["documento"])
    if re.search(r"\babrogad[oa]\b", cab[:1500]):
        return res("RECHAZADA", "el ordenamiento aparece como abrogado")
    reforma = ultima_reforma(cabecera)
    ev["ultima_reforma_documento"] = reforma
    seg, pos = segmento_articulo(cuerpo, f["articulo"])
    if seg is None:
        return res("RECHAZADA", f"no existe el encabezado «Artículo {f['articulo']}» en el documento")
    ev["posicion_articulo"] = pos
    if len(_plano(f["literal"]).split()) < 5:
        return res("RECHAZADA", "la cita es demasiado corta para cotejarla con seguridad (mínimo 5 palabras)")
    lit = _compacto(f["literal"])
    seg_c, cue_c = _compacto(seg), _compacto(cue)
    i = seg_c.find(lit)
    if i < 0:
        if lit in cue_c:
            return res("RECHAZADA", f"el texto citado existe, pero no en el artículo {f['articulo']}")
        return res("RECHAZADA", "el texto citado no coincide con el texto oficial")
    for ancla in f.get("anclas", []):
        if _compacto(ancla) not in seg_c:
            return res("RECHAZADA", f"ancla no encontrada en el artículo: «{ancla}»")
    ev["extracto"] = seg[:600]
    huella = hashlib.sha256(seg.encode()).hexdigest()
    ev["huella_articulo"] = huella   # se fija en el guion tras la primera verificación
    esperada = f.get("ultima_reforma_documento")
    if reforma is None:
        return res("RETENER", "el documento no declara fecha de última reforma; no se puede confirmar vigencia")
    if f.get("huella_articulo"):
        if f["huella_articulo"] != huella:
            return res("CAMBIO_NORMATIVO", f"el texto del artículo {f['articulo']} cambió respecto de la versión verificada (reforma del documento: {reforma})")
        if esperada and reforma > esperada:
            ev["nota"] = f"el ordenamiento se reformó el {reforma}, pero el artículo {f['articulo']} no cambió"
    elif esperada and reforma > esperada:
        return res("CAMBIO_NORMATIVO", f"el ordenamiento se reformó el {reforma} (el guion registra {esperada}) y no hay huella previa del artículo; re-verificar")
    return res("VERIFICADA", "identidad, vigencia y literal comprobados en el documento oficial")


MOTIVOS_TRANSITORIOS = ("sin conexión", "HTTP 5", "HTTP 403", "HTTP 429", "respuesta vacía", "no se pudo extraer")


def es_transitoria(ver):
    """True si la retención se debe solo a fallas de acceso (red, servidor) y no a problemas del contenido."""
    no_ok = [x for x in ver["fuentes"].values() if x["estado"] != "VERIFICADA"]
    return (bool(no_ok) and all(x["estado"] == "RETENER" and any(m in x["motivo"] for m in MOTIVOS_TRANSITORIOS) for x in no_ok)
            and not any(a["dictamen"] in ("RECHAZADA", "SIN_FUENTE") or a.get("duda") for a in ver["afirmaciones"]))


def adaptar(g):
    """Acepta el formato de guion v0.1 (fuentes como diccionario, una fuente por afirmación) y lo lleva al v0.2."""
    fu = g.get("fuentes", [])
    if isinstance(fu, dict):
        fu = [{"id": k, **x, "literal": x.get("literal") or x.get("texto_literal"),
               "url": x.get("url_oficial") or x.get("url"),
               "nivel": "oficial" if x.get("url_oficial") else x.get("nivel")} for k, x in fu.items()]
    esc = []
    escenas = g.get("escenas") or ([{"afirmaciones": g["afirmaciones"]}] if g.get("afirmaciones") else [])
    for e in escenas:
        afs = []
        for a in e.get("afirmaciones", []):
            fs = a.get("fuentes") or ([a["fuente"]] if a.get("fuente") else [])
            afs.append({**a, "fuentes": fs, "interpretativa": a.get("interpretativa", a.get("tipo") == "interpretacion"),
                        "duda": a.get("duda") or a.get("nota")})
        esc.append({**e, "afirmaciones": afs})
    return {**g, "fuentes": fu, "escenas": esc}


def verificar_guion(g, transporte=transporte_http):
    """Devuelve el dictamen documental de todas las fuentes y la regla de decisión aplicada a las afirmaciones."""
    g = adaptar(g)
    memo = {}
    def una_vez(url, timeout=60):   # un mismo PDF (p. ej. el Código Penal) se descarga una sola vez por guion
        if url not in memo:
            try: memo[url] = ("ok", transporte(url))
            except SinConexion as e: memo[url] = ("err", e)
        tipo, val = memo[url]
        if tipo == "err": raise val
        return val
    ev = {f["id"]: verificar_fuente(f, una_vez) for f in g.get("fuentes", [])}
    afirm = []
    for e in g.get("escenas", []):
        for a in e.get("afirmaciones", []):
            ests = [ev.get(fid, {"estado": "INEXISTENTE"})["estado"] for fid in a.get("fuentes", [])]
            if not ests:
                d = "SIN_FUENTE"
            elif any(s == "VERIFICADA" for s in ests) and a.get("duda"):
                d = "RETENER"   # duda material declarada por el propio guion (en un hecho o en una interpretación)
            elif any(s == "VERIFICADA" for s in ests) and not a.get("interpretativa"):
                d = "VERIFICADA"
            elif any(s == "VERIFICADA" for s in ests):
                d = "REQUIERE_CRITERIO"
            elif any(s in ("RETENER", "CAMBIO_NORMATIVO") for s in ests):
                d = "RETENER"
            else:
                d = "RECHAZADA"
            afirm.append({"id": a["id"], "fuentes": a.get("fuentes", []), "dictamen": d, "duda": a.get("duda")})
    todas = [a["dictamen"] for a in afirm]
    if not todas:
        decision = "RETENER"
    elif all(x == "VERIFICADA" for x in todas):
        decision = "APTA"
    elif any(x in ("RECHAZADA", "SIN_FUENTE") for x in todas):
        decision = "RECHAZADA"
    elif any(x == "RETENER" for x in todas):
        decision = "RETENER"
    else:
        # afirmaciones interpretativas con fuente verificada: solo el riesgo bajo pasa sin revisión humana
        # Riesgo bajo: pasa. Riesgo medio: solo si un auditor independiente (otro modelo, contra los mismos
        # textos oficiales) no encontró objeciones. Riesgo alto: siempre revisión humana.
        r = g.get("riesgo", "medio")
        aia = g.get("auditoria_ia") or {}
        ia_ok = aia.get("veredicto") == "sin_objeciones" and aia.get("familia_distinta", True) is not False   # auditor de otra familia
        decision = "APTA_CON_CRITERIO" if r == "bajo" or (r == "medio" and ia_ok) else "REVISION_HUMANA"
    return {"decision": decision, "fuentes": ev, "afirmaciones": afirm}


if __name__ == "__main__":
    import sys
    g = json.loads(open(sys.argv[1]).read())
    print(json.dumps(verificar_guion(g), ensure_ascii=False, indent=2))
