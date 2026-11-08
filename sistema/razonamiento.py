"""Revisión del RAZONAMIENTO jurídico de una pieza (no solo de sus citas).

Una cita auténtica no garantiza una conclusión correcta. Los dos errores reales del 26-10-2026 lo muestran:
  · I20261025-T089: título sobre la RENUNCIA; la «realidad» se apoyaba en el MUTUO CONSENTIMIENTO (LFT 53, fr. I), otra
    figura. Citas auténticas; conclusión sobre un concepto distinto del que se pregunta.
  · I20261026-T020: «La garantía mínima legal es de noventa días». El art. 77 LFPC lo dice para los bienes o servicios que
    se OFRECEN CON GARANTÍA; la cita omitía esa condición. Además, el título preguntaba si es legal «no hay cambios ni
    devoluciones» y la pieza nunca lo respondía.

Este módulo exige y revisa un MAPA DE RAZONAMIENTO que el redactor entrega antes del texto:
  {"pregunta": "...", "respuesta_corta": "Sí / No / Depende: ...",
   "reglas": [{"conclusion": "...", "fuente": "F1", "cita_literal": "...", "condiciones": ["..."], "excepciones": ["..."]}],
   "distinciones": [{"a": "concepto", "b": "concepto", "diferencia": "..."}],
   "limites": "lo que la norma no dice o la pieza no cubre"}
y comprueba, de forma determinista y contra el TEXTO OFICIAL de cada artículo:
  1. RESPUESTA   — si el título pregunta, hay una respuesta corta explícita y aparece en el contenido visible.
  2. CONCEPTOS   — si el título trata un concepto (p. ej., renuncia, devolución), el contenido habla de ESE concepto; si
                   recurre a otro del mismo grupo (mutuo consentimiento, garantía), debe declarar y mostrar la distinción.
  3. SUSTENTO    — cada conclusión trata un concepto que el artículo citado efectivamente regula (aparece en su texto).
  4. CONDICIONES — si el artículo condiciona la regla («que se ofrezca con garantía», «siempre que», «salvo»…) y la cita
                   omite esa condición, la conclusión debe declararla y el texto visible debe expresarla; una frase
                   absoluta («la garantía mínima legal es…», «siempre», «toda») sobre una regla condicionada se bloquea.
Devuelve hallazgos con severidad «bloqueante» o «advertencia». Un bloqueante retiene la pieza.
"""
import json, re, unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CONCEPTOS = json.loads((RAIZ / "data" / "conceptos.json").read_text())


def plano(t):
    t = unicodedata.normalize("NFD", (t or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", t)).strip()


def conceptos_en(texto):
    """{(grupo, concepto)} presentes en el texto."""
    p = plano(texto); out = set()
    for g, d in CONCEPTOS["grupos"].items():
        for c, cd in d["conceptos"].items():
            if any(re.search(pt, p) for pt in cd["patrones"]):
                out.add((g, c))
    return out


def texto_visible(g):
    """Todo lo que el público lee u oye en la pieza (sin el copy, que acompaña)."""
    partes = [g.get("titulo", "")]
    pz = g.get("pieza") or {}
    for k in ("titular", "bajada", "cita", "ojo", "mito", "realidad"):
        if k == "bajada" and g.get("plantilla") == "mito_realidad": continue   # esa plantilla no dibuja la bajada
        partes.append(pz.get(k, ""))
    partes += pz.get("puntos", []) or []
    for col in pz.get("columnas", []) or []:
        partes += [str(x) for x in col]
    for e in g.get("escenas", []) or []:
        partes.append(e.get("texto", "")); partes += e.get("titulo", []) if isinstance(e.get("titulo"), list) else [e.get("titulo", "")]
        partes += e.get("items", []) or []; partes += [e.get("encabezado", ""), e.get("detalle", ""), e.get("cita", "")]
    return " \n ".join(x for x in partes if x)


def cuerpo_visible(g):
    """Contenido visible sin el título (lo que debe responder la pregunta)."""
    v = texto_visible(g); t = g.get("titulo", "")
    pz = g.get("pieza") or {}
    for x in (t, pz.get("titular", "")):
        if x: v = v.replace(x, " ", 1)
    return v


def _marcadores_en(texto):
    p = " " + plano(texto) + " "
    return [m for m in CONCEPTOS["marcadores_condicion"] if f" {m} " in p]


def _ubicar(pa, pc):
    """Posición de la cita en el artículo, tolerando espacios espurios del PDF («se r inferior»)."""
    i = pa.find(pc)
    if i >= 0: return i, i + len(pc)
    ca, cc = pa.replace(" ", ""), pc.replace(" ", "")
    j = ca.find(cc)
    if j < 0 or not cc: return -1, -1
    mapa = [k for k, ch in enumerate(pa) if ch != " "]
    return mapa[j], mapa[j + len(cc) - 1] + 1


PARRAFO_DOF = r"((?:P[áa]rrafo|Fracci[óo]n|Inciso|Apartado|Art[íi]culo)\s+(?:reformad|adicionad|derogad)[oa]s?\b[^.]{0,40}?\bDOF\b)"


def _oraciones_previas(texto_articulo, pa, i):
    """Texto (normalizado) de la oración anterior y del inicio de la actual, sin cruzar a oraciones más lejanas.
    Antes se tomaban 420 caracteres fijos y entraban condiciones de otro párrafo (28-10, CPEUM 16: la prórroga del
    arraigo «siempre y cuando…» se exigía como condición de la retención de 48 horas)."""
    # 7-11-2026: la nota de reforma («Párrafo adicionado DOF 10-06-2011») cierra un párrafo; la oración anterior a ella
    # es de otro párrafo y no condiciona la cita (CPEUM 1: «en los términos que establezca la ley» se exigía como
    # condición de «Está prohibida la esclavitud»; CPEUM 4: la de los animales, como condición del derecho al agua).
    t = re.sub(PARRAFO_DOF, r" zzparrzz \1", texto_articulo or "")
    marc = plano(re.sub(r"[.;](?=\s|$)", " zzfinzz ", t)).split()
    ti = pa[:i].count(" ") if i > 0 else 0          # índice de la palabra donde empieza la cita
    k = n = 0
    for k, w in enumerate(marc):
        if w in ("zzfinzz", "zzparrzz"): continue
        if n == ti: break
        n += 1
    fines = [j for j, w in enumerate(marc[:k]) if w == "zzfinzz"]
    desde = fines[-2] + 1 if len(fines) >= 2 else 0
    parr = [j for j, w in enumerate(marc[:k]) if w == "zzparrzz"]
    if parr: desde = max(desde, parr[-1] + 1)
    return " ".join(w for w in marc[desde:k] if w not in ("zzfinzz", "zzparrzz"))


def _cita_textual(frase, txt):
    """¿La frase reproduce la ley (al menos 8 palabras seguidas del texto oficial), aunque la introduzca el narrador
    («La Constitución señala que Ningún indiciado…»)? Reproducir la norma no es generalizarla (R20261126-T061, 28-10)."""
    if not txt: return False
    pf, pt = plano(frase).split(), plano(txt)
    return any(_ubicar(pt, " ".join(pf[i:i + 8]))[0] >= 0 for i in range(0, max(0, len(pf) - 7)))


def contexto_omitido(texto_articulo, cita, ventana=420):
    """Condiciones del artículo que rodean a la cita y que la cita NO incluye (la oración anterior y la actual)."""
    pa, pc = plano(texto_articulo), plano(cita)
    i, f = _ubicar(pa, pc)
    if i < 0: return []
    antes = _oraciones_previas(texto_articulo, pa, i)[-ventana:]; despues = pa[f: f + 160]
    cand = _marcadores_en(antes) + [m for m in _marcadores_en(despues) if m in ("salvo", "excepto", "a menos que", "siempre que", "siempre y cuando")]
    en_cita = set(_marcadores_en(cita))
    return [m for m in dict.fromkeys(cand) if m not in en_cita]


def fragmento_condicion(texto_articulo, cita, marcador, ventana=420):
    pa, pc = plano(texto_articulo), plano(cita); i, f = _ubicar(pa, pc)
    zona = pa[max(0, i - ventana): f + 160]; j = zona.find(marcador)
    return zona[max(0, j - 60): j + 90].strip() if j >= 0 else ""


def _temas(texto):
    """Raíces de contenido (5 letras) normalizadas con sinónimos jurídicos de uso común."""
    p = plano(texto); out = set()
    for clave, raices in CONCEPTOS.get("sinonimos", {}).items():
        if any(r in p for r in raices): out.add(clave)
    vac = {"puede", "puede", "tiene", "sobre", "cuand", "donde", "quien", "cuant", "porqu", "derec", "legal", "hacer", "sabes", "saber", "pasa ", "puede"}
    out |= {w[:5] for w in p.split() if len(w) > 4 and w[:5] not in vac}
    if not out:
        # 6-11-2026: «¿Tienes derecho al agua?» no tenía ninguna raíz de 5 letras («agua» tiene 4) y el control de
        # tema descartaba la pieza aunque respondiera exactamente esa pregunta (R20270105-T130). Si la pregunta no deja
        # raíces largas, se usan sus palabras de 4 letras que no sean de relleno.
        cortas = {"para", "como", "pero", "este", "esta", "esto", "eso", "tus", "sus", "algo", "cual", "todo", "toda",
                  "solo", "aqui", "otra", "otro", "debe", "hace", "dice", "ante", "sino", "pued"}
        out |= {w for w in p.split() if len(w) == 4 and w not in cortas}
    return out


def tema_comun(plan, propio):
    """¿Comparten tema la pregunta del plan y el texto propio? Raíces comunes; o, si la pregunta solo deja palabras de
    4 letras («agua»), que esas palabras estén en el texto propio."""
    a = _temas(plan)
    if a & _temas(propio): return True
    cortas = {w for w in a if len(w) == 4}
    return bool(cortas) and bool(cortas & set(plano(propio).split()))


def _es_absoluta(frase):
    p = " " + plano(frase) + " "
    return any(f" {a} " in p for a in CONCEPTOS["absolutos"])


def revisar(g, textos, ia=None):
    """g: guion; textos: {(documento, artículo): texto oficial COMPLETO}. Las reglas del mapa y las fichas de fuente se
    resuelven por documento y artículo. Devuelve la lista de hallazgos."""
    H = []
    def h(regla, sev, detalle): H.append({"regla": regla, "severidad": sev, "detalle": detalle})
    ia = bool((g.get("generacion") or {}).get("modelos")) if ia is None else ia
    rz = g.get("razonamiento") or {}
    titulo = g.get("titulo") or (g.get("pieza") or {}).get("titular", "")
    cuerpo = cuerpo_visible(g)

    # 1. RESPUESTA
    if titulo.strip().endswith("?"):
        rc = (rz.get("respuesta_corta") or "").strip()
        if not rc:
            h("respuesta", "bloqueante" if ia else "advertencia", "El título hace una pregunta y no hay respuesta corta explícita en el mapa de razonamiento.")
        else:
            nucleo = plano(rc).split()
            clave = [w for w in nucleo if len(w) > 4][:6]
            presentes = sum(1 for w in clave if w in plano(cuerpo))
            tipo_p = tipo_pregunta(g.get("pregunta_original") or titulo, g.get("tipo_pregunta"))[0]
            sino = r"si|no|depende|en general|solo|depende de"
            directo = r"significa|es|son|consiste|se (le |les )?(presume|considera|entiende|refiere|trata)|al menos|antes|como minimo|minimo|debe|deben|tienes|tiene|en|a la|a las|al|el|la|los|las|se"
            # Sí/No/Depende solo se exige en preguntas cerradas; en las demás basta que no empiece con rodeos
            # (28-10: «Te corresponden cinco días…» y «Hasta cuarenta y ocho horas…» se bloqueaban sin razón).
            rodeo = r"^(la ley|la constitucion|el articulo|es importante|hay que|existen?|segun|de acuerdo)\b"
            if tipo_p in ("legalidad", "general", "excepcion"):
                mal = not re.match(rf"^({sino})\b", plano(rc))
            else:
                mal = bool(re.match(rodeo, plano(rc))) or (tipo_p == "definicion" and re.match(r"^(si|no)\b", plano(rc)))
            if mal:
                h("respuesta", "bloqueante", f"La respuesta corta no contesta de forma directa ({'debe empezar con Sí, No, Depende…' if tipo_p in ('legalidad', 'general', 'excepcion') else 'debe empezar por la respuesta, sin rodeos'}): «{rc[:90]}».")
            if clave and presentes < max(2, len(clave) // 2):
                h("respuesta", "bloqueante", f"La respuesta corta no aparece en el contenido visible: «{rc[:90]}».")

    # 1b. DERIVA DE TEMA: la pieza responde la pregunta que pidió el plan editorial, no otra
    original = g.get("pregunta_original") or ""
    if original and ia:
        pieza_txt = titulo + " " + (rz.get("pregunta") or "") + " " + (rz.get("respuesta_corta") or "")
        if not tema_comun(original, pieza_txt) and not ({g2 for g2, _ in conceptos_en(original)} & {g2 for g2, _ in conceptos_en(pieza_txt)}):
            h("tema", "bloqueante", f"La pieza no responde la pregunta del plan editorial («{original[:80]}»): trata «{titulo[:80]}».")

    # 2. CONCEPTOS del título frente a los del cuerpo
    ct, cb = conceptos_en(titulo), conceptos_en(cuerpo)
    pz = g.get("pieza") or {}
    zona_resp = " ".join([rz.get("respuesta_corta") or "", pz.get("realidad", ""), pz.get("bajada", "") if g.get("plantilla") != "mito_realidad" else "", pz.get("ojo", "")]
                         + [e.get("texto", "") for e in (g.get("escenas") or []) if e.get("tipo") in ("titular", "cita", "excepcion")])
    cr = conceptos_en(zona_resp)
    for (gr, c) in ct:
        if cr and (gr, c) not in cr and any(g2 == gr for (g2, _) in cr):
            otros = sorted(x for (g2, x) in cr if g2 == gr)
            h("conceptos", "bloqueante", f"La respuesta habla de «{', '.join(otros)}», no de «{c}», que es lo que pregunta el título.")
    distinciones = [(plano(d.get("a", "")), plano(d.get("b", ""))) for d in rz.get("distinciones", []) or []]
    for (gr, c) in ct:
        if (gr, c) in cb: continue
        otros = [x for (g2, x) in cb if g2 == gr]
        if otros:
            h("conceptos", "bloqueante", f"El título trata «{c}», pero el contenido visible responde con «{', '.join(otros)}» del mismo grupo ({gr}) sin hablar de «{c}».")
    for (gr, c) in ct:
        otros = [x for (g2, x) in cb if g2 == gr and x != c]
        if (gr, c) in cb and otros:
            declarada = any(c.split("_")[0] in a + " " + b for a, b in distinciones)
            if not declarada:
                h("conceptos", "advertencia" if not ia else "bloqueante",
                  f"El contenido mezcla «{c}» con «{', '.join(otros)}» sin declarar la distinción entre ellos.")

    # 3 y 4. SUSTENTO y CONDICIONES de cada conclusión
    reglas = rz.get("reglas") or []
    if ia and not reglas:
        h("sustento", "bloqueante", "No hay mapa de razonamiento: cada conclusión debe ligarse a su fuente.")
    fichas = g.get("fuentes") or {}
    if isinstance(fichas, list): fichas = {f["id"]: f for f in fichas}
    tx = lambda f: textos.get((f.get("documento"), str(f.get("articulo")))) if f else None
    for r in reglas:
        fid = r.get("fuente"); ref = r.get("ref") or fichas.get(fid) or {}
        txt = tx(ref); fid = f'{ref.get("documento", fid)}, art. {ref.get("articulo", "?")}' if ref else fid
        concl = r.get("conclusion", "")
        if not txt:
            h("sustento", "bloqueante", f"La conclusión «{concl[:70]}» cita {fid}, cuyo texto oficial no está disponible."); continue
        cita = r.get("cita_literal") or ref.get("texto_literal", "")
        if plano(cita) and _ubicar(plano(txt), plano(cita))[0] < 0:
            h("sustento", "bloqueante", f"La cita de la conclusión «{concl[:60]}» no está en {fid}.")
        cc, ca = conceptos_en(concl), conceptos_en(txt)
        for (gr, c) in cc:
            if (gr, c) not in ca:
                h("sustento", "bloqueante", f"La conclusión «{concl[:70]}» trata «{c}», pero {fid} no regula ese concepto (no aparece en su texto).")
        omitidas = contexto_omitido(txt, cita) if cita else []
        if omitidas:
            frag = fragmento_condicion(txt, cita, omitidas[0])
            declaradas = " ".join(r.get("condiciones", []) + r.get("excepciones", []))
            if not declaradas.strip():
                h("condiciones", "bloqueante", f"{fid} condiciona la regla («…{frag}…») y la conclusión «{concl[:60]}» no declara condiciones.")
            # ¿la conclusión se muestra en forma absoluta en el contenido visible?
            for frase in re.split(r"(?<=[.!?])\s+|\n", cuerpo):
                literal = _cita_textual(frase, txt)
                if not literal and _coincide(frase, concl) and not _marcadores_en(frase) and (_es_absoluta(frase) or not declaradas.strip()):
                    h("condiciones", "bloqueante", f"Generalización: «{frase.strip()[:90]}» se presenta sin la condición que impone {fid} («…{frag}…»).")
    # frases absolutas visibles apoyadas en reglas condicionadas aunque no estén en el mapa
    for frase in re.split(r"(?<=[.!?])\s+|\n", cuerpo):
        if not _es_absoluta(frase): continue
        for fid, fi in fichas.items():
            txt = tx(fi) or ""; cita = fi.get("texto_literal", "")
            literal = _cita_textual(frase, txt)   # citar la ley textual no es generalizar
            if cita and not literal and _coincide(frase, cita) and contexto_omitido(txt, cita) and not _marcadores_en(frase):
                frag = fragmento_condicion(txt, cita, contexto_omitido(txt, cita)[0])
                h("condiciones", "bloqueante", f"Frase absoluta «{frase.strip()[:80]}» sobre una regla condicionada de {fid} («…{frag}…»).")
    # 5. COBERTURA, VAGUEDAD y SUSTENTO DE LO VISIBLE (rechazo humano de R20261028-T068, 26-10-2026)
    if ia or rz.get("elementos"):
        for x in revisar_cobertura(g, textos):
            H.append(x)
    acompana = cuerpo + "\n" + (g.get("copy") or "")       # el texto que acompaña también lo lee el público
    for x in vaguedades(acompana, [t for t in textos.values() if t]):
        h("vaguedad", "bloqueante", x)
    for x in afirmaciones_temporales(acompana, g):
        h("sustento", "bloqueante", x)
    for x in coherencia_visible(g):
        h("coherencia", "bloqueante", x)
    # 6. JURISPRUDENCIA: no se cita una tesis o criterio judicial que no se haya verificado en el Semanario Judicial
    verificadas = {str(t) for t in (g.get("tesis_verificadas") or [])}
    for frase in re.split(r"(?<=[.!?:])\s+|\n", cuerpo + " " + (g.get("copy") or "")):
        p_ = plano(frase)
        regs = set(re.findall(r"\b(\d{7})\b", p_))
        if re.search(r"\bjurisprudencia\b|\btesis\b|registro digital|criterio (judicial|de la corte|del tribunal)|\bla (suprema )?corte (resolvio|determino|establecio)", p_) or regs:
            if not regs or not regs <= verificadas:
                h("jurisprudencia", "bloqueante", f"«{frase.strip()[:80]}» invoca un criterio judicial que no está verificado en el Semanario Judicial de la Federación; no se cita.")
    usados = [tx(f) or "" for f in fichas.values()] + [tx(r.get("ref") or fichas.get(r.get("fuente")) or {}) or "" for r in reglas]
    for x in consecuencias_sin_sustento(acompana, usados):
        h("sustento", "bloqueante", x)
    # sin duplicados
    vistos, out = set(), []
    for x in H:
        k = (x["regla"], x["detalle"])
        if k not in vistos: vistos.add(k); out.append(x)
    return out


def _coincide(frase, referencia, minimo=2):
    """¿La frase expresa la misma regla? (comparte al menos dos palabras de contenido poco comunes, p. ej. «noventa», «garantía»)."""
    vac = {"para", "por", "con", "los", "las", "del", "que", "una", "uno", "este", "esta", "como", "sobre", "entre", "sus", "ley", "articulo"}
    a = {w for w in plano(frase).split() if len(w) > 4 and w not in vac}
    b = {w for w in plano(referencia).split() if len(w) > 4 and w not in vac}
    return len(a & b) >= minimo


def bloqueantes(hallazgos):
    return [x for x in hallazgos if x["severidad"] == "bloqueante"]


# ---------------- cobertura de la pregunta ----------------
# Lo que una persona necesita saber según el TIPO de pregunta. Una pieza que pregunta «¿qué pasa si…?» y solo explica la
# validez de un documento, sin decir qué se puede hacer, ante quién ni en qué plazo, no responde la pregunta.
ELEMENTOS = {
    "efecto": "qué consecuencia jurídica tiene la situación (es válida, nula, legal, ilegal…)",
    "que_hacer": "qué puede hacer la persona (qué acción, reclamo o derecho puede ejercer)",
    "ante_quien": "ante qué autoridad u órgano concreto se hace",
    "plazo": "en qué plazo debe hacerse",
    "definicion": "qué es y qué alcance tiene el concepto",
    "contenido": "qué establece la norma como respuesta directa: qué se debe dar o hacer (cuánto y cuándo), qué se garantiza o qué se prohíbe",
    "condiciones": "bajo qué condiciones o requisitos aplica (o «no_aplica» si la ley no pone ninguna)",
    "excepcion": "qué excepciones prevé la ley (o «no_aplica» si el texto no prevé ninguna)",
    "via": "cómo se hace: qué trámite, solicitud o acción concreta",
}
TIPOS_PREGUNTA = (     # en orden: gana el primer patrón que coincide
    ("procedimiento", r"\bcomo (se )?(denuncia|reclama|tramita|pide|solicita|presenta|inicia|promueve|defiende)\b|\b(donde|ante quien) (se )?(denuncia|reclama|acudo|acudir|presento|presentar|tramita)\b",
     ("via", "ante_quien", "plazo")),
    ("consecuencia", r"\bque pasa (si|cuando)\b|\bque (hago|puedo hacer|debo hacer|se puede hacer)\b|\b(me|te|le|nos|les) (obligan|obliga|despiden|despide|corren|corre|niegan|niega|quitan|quita|retienen|retiene)\b",
     ("efecto", "que_hacer", "ante_quien", "plazo")),
    ("excepcion", r"\bsiempre\b|\ben todos los casos\b|\bhay excepciones\b|\bsin excepcion\b",
     ("efecto", "excepcion")),
    ("derecho", r"\b(tengo|tienes|tiene|tenemos|tienen) derecho\b|\b(me|te|le|nos|les) pueden? (volver a |obligar|detener|juzgar|encarcelar|despedir|cobrar)",
     ("contenido", "condiciones", "excepcion")),
    ("obligacion", r"\b(cuando|cuanto|cuantos|cuantas)\b.*\b(deben|debe|tienen que|tiene que|pagan|paga|corresponden?|tocan?)\b|\b(estan?|esta) obligad",
     ("contenido", "condiciones")),
    ("legalidad", r"\bes (legal|ilegal|valido|valida|delito)\b|\besta (permitido|prohibido)\b|\bse (puede|vale)\b|\bpueden?\b|\b(tienen?|tienes|tengo) que\b|\bestan? obligad",
     ("efecto",)),
    ("definicion", r"\bque (es|son|significa|significan)\b|\ben que consiste\b|\bcual es la diferencia\b|\bdiferencia entre\b",
     ("definicion",)),
)


TIPOS_VALIDOS = {n: req for n, _, req in TIPOS_PREGUNTA}


def tipo_pregunta(pregunta, tipo=None):
    """Tipo de pregunta y elementos que la respuesta debe cubrir. Un tipo fijado por el plan editorial (p. ej., el lote
    piloto) tiene prioridad sobre la detección por patrones."""
    if tipo in TIPOS_VALIDOS: return tipo, TIPOS_VALIDOS[tipo]
    p = plano(pregunta)
    for nombre, patron, req in TIPOS_PREGUNTA:
        if re.search(patron, p): return nombre, req
    return "general", ("efecto",)


def elementos_requeridos(pregunta):
    return tipo_pregunta(pregunta)[1]


def revisar_cobertura(g, textos):
    """Cada elemento requerido por el tipo de pregunta debe estar en el análisis («elementos»): cubierto con fuente y cita
    literal que esté en el texto oficial, o «no_aplica» con un motivo. Lo «no_cubierto» bloquea (faltan fuentes). Lo cubierto
    debe decirse en el contenido visible."""
    H = []
    rz = g.get("razonamiento") or {}
    pregunta = g.get("pregunta_original") or rz.get("pregunta") or g.get("titulo", "")
    tipo, req = tipo_pregunta(pregunta, g.get("tipo_pregunta"))
    els = {str(e.get("elemento", "")).strip(): e for e in rz.get("elementos") or [] if isinstance(e, dict)}
    fichas = g.get("fuentes") or {}
    if isinstance(fichas, list): fichas = {f["id"]: f for f in fichas}
    refs = {r.get("fuente"): r.get("ref") for r in rz.get("reglas") or [] if isinstance(r, dict) and r.get("ref")}
    visible = None if g.get("_solo_analisis") else plano(cuerpo_visible(g))
    rc = plano(str(rz.get("respuesta_corta", "")) + " " + str((g.get("pieza") or {}).get("bajada", "")))
    if tipo == "definicion" and re.match(r"\s*(si|no)\b", rc):
        H.append({"regla": "cobertura", "severidad": "bloqueante",
                  "detalle": "La pregunta pide una definición y la respuesta empieza con «Sí» o «No»: contesta qué significa (I20261125-T028, 28-10)."})
    # mínimos legales: si la ley dice «por lo menos / al menos / como mínimo», la pieza no puede presentar la cifra como exacta
    # (I20261127-T015, 28-10: «equivale a quince días de salario» sin «por lo menos»)
    if visible is not None:
        citas = [str(x.get("cita_literal", "")) for x in [*(rz.get("reglas") or []), *(rz.get("elementos") or [])] if isinstance(x, dict)]
        cifras = set()
        for c in citas:
            pc = plano(c)
            cifras |= _cifras_minimas(pc)
        for frase in re.split(r"(?<=[.;!?])\s+|\n", cuerpo_visible(g)):
            pf = plano(frase)
            if any(n in cifras for n, _ in _plazos(pf)) and not re.search(r"\b(por lo menos|al menos|como minimo|minimo|minima|min|o mas|desde)\b", pf):
                H.append({"regla": "minimo", "severidad": "bloqueante",
                          "detalle": f"«{frase.strip()[:90]}» presenta como exacta una cifra que la ley fija como mínimo («por lo menos»)."})
    for k in req:
        e = els.get(k)
        if not e:
            H.append({"regla": "cobertura", "severidad": "bloqueante", "detalle": f"La pregunta es de tipo «{tipo}» y el análisis no dice {ELEMENTOS[k]} (elemento «{k}»)."}); continue
        est = str(e.get("estado", "")).lower()
        if est == "no_aplica":
            if len(str(e.get("motivo", "")).split()) < 4:
                H.append({"regla": "cobertura", "severidad": "bloqueante", "detalle": f"El elemento «{k}» se marca como no aplicable sin explicar por qué."})
            continue
        if est != "cubierto":
            H.append({"regla": "cobertura", "severidad": "bloqueante",
                      "detalle": f"Falta sustento oficial para {ELEMENTOS[k]} (elemento «{k}»): hay que buscar el artículo que lo regula o no publicar la pieza."}); continue
        ref = refs.get(e.get("fuente")) or fichas.get(e.get("fuente")) or {}
        txt = textos.get((ref.get("documento"), str(ref.get("articulo")))) if ref else None
        cita = plano(e.get("cita_literal", ""))
        if not txt or len(cita.split()) < 4 or _ubicar(plano(txt), cita)[0] < 0:
            H.append({"regla": "cobertura", "severidad": "bloqueante",
                      "detalle": f"El elemento «{k}» («{str(e.get('respuesta', ''))[:60]}») no trae una cita literal que esté en el texto oficial de su fuente."}); continue
        if visible is not None:
            raices = {w[:6] for w in visible.split() if len(w) > 4}
            def dicho(texto):          # se acepta con sus palabras o con las de la cita oficial (paráfrasis legítima)
                # por raíz (6 letras): «servicio» = «servicios», «trabajador» = «trabajadoras» (I20261123-T016, 28-10)
                clave = list(dict.fromkeys(w[:6] for w in plano(texto).split() if len(w) > 4))[:6]
                return not clave or sum(1 for w in clave if w in raices) >= max(2, -(-len(clave) // 3))   # un tercio (mín. 2): 28-10, T016 «Aplica al cumplir más de un año de servicios»
            if not (dicho(e.get("respuesta", "")) or (e.get("cita_literal") and dicho(e["cita_literal"]))):
                H.append({"regla": "cobertura", "severidad": "bloqueante",
                          "detalle": f"El análisis responde {ELEMENTOS[k]} («{str(e.get('respuesta', ''))[:160]}»), pero la pieza no lo dice: agrégalo al texto visible."})
    return H


# ---------------- vaguedad ----------------
VAGOS = (
    r"\b(existe|existen|hay) (un|una|unos|unas)? ?(recurso|recursos|mecanismo|mecanismos|via|vias|procedimiento|procedimientos|medio|medios|accion|acciones|instancia|instancias)( legal| legales| juridico| juridicos| especifico| especificos| especial)*\b",
    r"\b(autoridad|autoridades|instancia|instancias) (competente|competentes|correspondiente|correspondientes)\b",
    r"\b(tomar|emprender|iniciar|ejercer) (las )?acciones (legales|correspondientes)\b",
    r"\bla ley (preve|contempla|establece|ofrece) (opciones|mecanismos|alternativas|herramientas|vias)\b",
    r"\b(recurso|via|mecanismo) legal (especifico|especial|adecuado)\b",
    r"^\W*(ojo\W*)?(revisa|consulta|checa|lee) (tu|la) (ley|contrato|caso|situacion)\W*$",
    r"\b(este|ese|dicho) (limite|minimo|maximo|plazo|monto)\b(?! de \d)",
    r"\b(normatividad|legislacion|normativa) aplicable\b|\bsupuestos (muy )?(especificos|particulares) previstos\b",   # R20261126-T061, 28-10
)
CONCRETOS = r"\b(tribunal|tribunales|juez|jueza|centro de conciliacion|centros de conciliacion|profeco|procuraduria|ministerio publico|fiscalia|condusef|demanda|demandar|denuncia|denunciar|queja|amparo|conciliacion|reinstalacion|indemnizacion|nulidad)\b"


def vaguedades(cuerpo, textos_oficiales=()):
    """Frases que aluden a un recurso, vía o autoridad sin nombrarlos («existe un recurso legal específico»).
    Una frase que reproduce textualmente la ley citada no es una alusión vaga (I20261201-T019, LFPC 7 Bis, 28-10)."""
    out = []
    planos = [plano(t) for t in textos_oficiales if t]
    for frase in re.split(r"(?<=[.!?:])\s+|\n", cuerpo or ""):
        p = plano(frase)
        vagas = [m.group(0) for v in VAGOS for m in re.finditer(v, p)]
        # La expresión que la ley citada usa con esas mismas palabras («La autoridad competente expedirá…», CPEUM 4) no es
        # una alusión vaga de la pieza: la pieza no puede nombrar lo que la ley no nombra (I20261210-T104, 31-10).
        if vagas and planos and all(any(re.search(r"\b" + re.escape(x) + r"\b", tp) for tp in planos) for x in vagas):
            continue
        if vagas and not re.search(CONCRETOS, p) \
                and not any(_cita_textual(frase, t) for t in textos_oficiales):
            out.append(f"Referencia vaga: «{frase.strip()[:90]}». Nombra la vía, la autoridad o el derecho concreto (con su fuente) o elimina la frase.")
    return out


# ---------------- consecuencias visibles sin sustento ----------------
# Términos de consecuencia jurídica: si la pieza los dice, algún artículo citado por la pieza debe contenerlos.
CONSECUENCIAS = {
    "despido": r"\bdespid|\bdespedi", "indemnización": r"\bindemniz", "reinstalación": r"\breinstal", "prescripción": r"\bprescri",
    "Tribunal": r"\btribunal", "Centro de Conciliación": r"\bcentros? de conciliacion", "conciliación": r"\bconciliacion",
    "Profeco": r"\bprofeco|\bprocuraduria federal del consumidor", "Ministerio Público": r"\bministerio publico",
    "demanda": r"\bdemand", "multa": r"\bmulta", "prisión": r"prision|carcel|encarcel", "amparo": r"\bamparo", "nulidad": r"\bnul[ao]s?\b|\bnulidad",
}
_NUM = {"un": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
        "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15, "dieciseis": 16, "diecisiete": 17, "dieciocho": 18,
        "diecinueve": 19, "veinte": 20, "veintiun": 21, "veintiuno": 21, "veintidos": 22, "veinticinco": 25, "treinta": 30,
        "cuarenta": 40, "cincuenta": 50, "sesenta": 60, "setenta": 70, "ochenta": 80, "noventa": 90, "cien": 100}   # la ley escribe los números con letra

# Números compuestos con letra («setenta y dos horas», «cuarenta y ocho horas»). Sin esto «setenta y dos horas» se leía
# como «dos horas» y la pieza que decía «72 horas» se bloqueaba (R20270112-T137, CPEUM 19, 8-11-2026).
_DECENAS = {"treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60, "setenta": 70, "ochenta": 80, "noventa": 90}
_UNIDADES = {"un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8,
             "nueve": 9}
_COMPUESTO = r"(?:" + "|".join(_DECENAS) + r") y (?:" + "|".join(_UNIDADES) + r")"


_UNIDAD = {"dias": "dia", "meses": "mes", "anos": "ano", "semanas": "semana", "horas": "hora"}


def _plazos_pos(p, base=False):
    """[(inicio, fin, (n, unidad))] de los plazos «número + unidad» del texto plano.
    - Decimales: `plano` convierte «3.5 horas» en «3 5 horas»; se lee 3.5, no 5 (R20261208-T102, 30-10: «Menor a 3.5 horas
      nocturnas» se bloqueaba por un plazo «5 hora» inexistente).
    - «tres horas y media» = 3.5. En el texto legal (base) cuenta también el entero: LFT 61 dice «siete la nocturna y siete
      horas y media la mixta» y la pieza puede decir «siete horas» para la nocturna."""
    out = []
    nums = dict(_NUM, **({"el": 1} if base else {}))
    patron = (r"\b(" + _COMPUESTO + r"|\d{1,3}(?: \d(?= (?:dia|dias|mes|meses|ano|anos|semana|semanas|hora|horas)\b))?|" + "|".join(nums) +
              r")\s+(dia|dias|mes|meses|ano|anos|semana|semanas|hora|horas)\b( y media\b)?")
    for m in re.finditer(patron, p):
        n, u, media = m.group(1), m.group(2), m.group(3)
        if n in nums: v = nums[n]
        elif " y " in n: a, b = n.split(" y "); v = _DECENAS[a] + _UNIDADES[b]
        elif " " in n: a, b = n.split(); v = float(f"{a}.{b}")
        else: v = int(n)
        u = _UNIDAD.get(u, u)
        if media:
            out.append((m.start(), m.end(), (v + 0.5, u)))
            if base: out.append((m.start(), m.end(), (v, u)))
        else:
            out.append((m.start(), m.end(), (v, u)))
    if base:
        # Edad con la unidad sobreentendida: LFT 22 «Los mayores de quince y menores de dieciséis necesitan…» (el «años»
        # va solo con el primer número). La pieza puede decir «menores de dieciséis años» (R20270104-T129, 6-11-2026).
        edad = r"\b(?:mayores|menores) de (\d{1,3}|" + "|".join(_NUM) + r")\b(?!\s+(?:dia|dias|mes|meses|ano|anos|semana|semanas|hora|horas)\b)"
        for m in re.finditer(edad, p):
            n = m.group(1); v = _NUM[n] if n in _NUM else int(n)
            out.append((m.start(), m.end(), (v, _UNIDAD.get("anos", "ano"))))
    return out


def _plazos(p, base=False):
    """Plazos «número + unidad». En el texto legal, «el año de servicios» o «el mes» también cuentan como 1 (la pieza
    puede decir «un año» si la ley dice «el año»)."""
    return {x for _, _, x in _plazos_pos(p, base)}


_MINIMO = r"\b(por lo menos|al menos|como minimo|minimo)\b"


def _cifras_minimas(pc, ventana=40):
    """Cifras que la ley fija como mínimo: solo la cifra más cercana a «por lo menos / al menos / como mínimo» (antes o
    después, a menos de `ventana` caracteres), no todas las de la cita. R20261207-T101 (30-10): LFT 69 «Por cada seis días
    de trabajo se deberá otorgar, por lo menos, un día de descanso»: el mínimo es «un día»; «seis días» no lo es."""
    out = set()
    pos = _plazos_pos(pc)
    for m in re.finditer(_MINIMO, pc):
        cand = [(m.start() - f if f <= m.start() else i - m.end(), x[0]) for i, f, x in pos]
        cand = [(d, n) for d, n in cand if 0 <= d <= ventana]
        if cand: out.add(min(cand)[1])
    return out


def consecuencias_sin_sustento(cuerpo, textos_citados):
    """Consecuencias, autoridades y plazos que la pieza afirma y que no aparecen en ningún artículo que la pieza cita."""
    base = plano(" ".join(t for t in textos_citados if t))
    out = []
    if not base: return out
    for frase in re.split(r"(?<=[.!?:])\s+|\n", cuerpo or ""):
        p = plano(frase)
        for nombre, pat in CONSECUENCIAS.items():
            if re.search(pat, p) and not re.search(pat, base):
                out.append(f"«{frase.strip()[:80]}» habla de {nombre}, pero ninguno de los artículos que cita la pieza lo establece.")
        for pl in _plazos(p) - _plazos(base, base=True):
            out.append(f"«{frase.strip()[:80]}» menciona un plazo ({pl[0]} {pl[1]}) que no aparece en los artículos citados.")
    return list(dict.fromkeys(out))



def afirmaciones_temporales(texto, g):
    """«La ley cambió recientemente», «nueva reforma»: afirmaciones sobre cambios legales que exigen una fuente que las
    pruebe (el decreto en el DOF). Ninguna pieza las tiene hoy, así que se bloquean."""
    fuentes = g.get("fuentes") or {}
    vals = fuentes.values() if isinstance(fuentes, dict) else fuentes
    hay_dof = any("dof" in str(f.get("url", "")).lower() or "decreto" in str(f.get("documento", "")).lower() for f in vals)
    out = []
    for frase in re.split(r"(?<=[.!?:])\s+|\n", texto or ""):
        p = plano(frase)
        if re.search(r"\b(recientemente|reciente(s)? reforma|nueva(s)? (ley|reforma|regla)|cambi(o|aron) (la ley|las reglas|recientemente)|ya cambio|ahora la ley|desde la reforma)\b", p) and not hay_dof:
            out.append(f"«{frase.strip()[:80]}» afirma un cambio legal sin citar el decreto que lo establece (DOF).")
    return out



# ---------------- coherencia entre lo que se ve y lo que se narra ----------------
_GENERICAS = {"excepc", "import", "recuer", "atenci", "import", "clave", "regla"}


def coherencia_visible(g):
    """El encabezado visible de una escena de excepción debe tratar lo mismo que su narración (R20261130-T014, 29-10:
    la tarjeta decía «Excepción por fallecimiento» mientras la voz hablaba de salarios vencidos si el patrón no prueba
    la causa; quedó de una versión anterior del guion)."""
    out = []
    for i, e in enumerate(g.get("escenas") or []):
        if e.get("tipo") != "excepcion" or not e.get("encabezado"): continue
        raices = {w[:6] for w in plano(e["encabezado"]).split() if len(w) > 5} - _GENERICAS
        narr = {w[:6] for w in plano(e.get("texto", "")).split() if len(w) > 5}
        if raices and not (raices & narr):
            out.append(f"Escena {i + 1}: el encabezado visible «{e['encabezado']}» no corresponde a lo que se narra («{e.get('texto', '')[:70]}»).")
    return out
