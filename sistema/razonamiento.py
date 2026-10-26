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


def contexto_omitido(texto_articulo, cita, ventana=420):
    """Condiciones del artículo que rodean a la cita y que la cita NO incluye (la oración anterior y la actual)."""
    pa, pc = plano(texto_articulo), plano(cita)
    i, f = _ubicar(pa, pc)
    if i < 0: return []
    antes = pa[max(0, i - ventana):i]; despues = pa[f: f + 160]
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
    return out


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
            if not re.match(r"^(si|no|depende|en general|solo|depende de)\b", plano(rc)):
                h("respuesta", "bloqueante", f"La respuesta corta no contesta de forma directa (debe empezar con Sí, No, Depende…): «{rc[:90]}».")
            if clave and presentes < max(2, len(clave) // 2):
                h("respuesta", "bloqueante", f"La respuesta corta no aparece en el contenido visible: «{rc[:90]}».")

    # 1b. DERIVA DE TEMA: la pieza responde la pregunta que pidió el plan editorial, no otra
    original = g.get("pregunta_original") or ""
    if original and ia:
        pieza_txt = titulo + " " + (rz.get("pregunta") or "") + " " + (rz.get("respuesta_corta") or "")
        if not (_temas(original) & _temas(pieza_txt)) and not ({g2 for g2, _ in conceptos_en(original)} & {g2 for g2, _ in conceptos_en(pieza_txt)}):
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
                if _coincide(frase, concl) and not _marcadores_en(frase) and (_es_absoluta(frase) or not declaradas.strip()):
                    h("condiciones", "bloqueante", f"Generalización: «{frase.strip()[:90]}» se presenta sin la condición que impone {fid} («…{frag}…»).")
    # frases absolutas visibles apoyadas en reglas condicionadas aunque no estén en el mapa
    for frase in re.split(r"(?<=[.!?])\s+|\n", cuerpo):
        if not _es_absoluta(frase): continue
        for fid, fi in fichas.items():
            txt = tx(fi) or ""; cita = fi.get("texto_literal", "")
            if cita and _coincide(frase, cita) and contexto_omitido(txt, cita) and not _marcadores_en(frase):
                frag = fragmento_condicion(txt, cita, contexto_omitido(txt, cita)[0])
                h("condiciones", "bloqueante", f"Frase absoluta «{frase.strip()[:80]}» sobre una regla condicionada de {fid} («…{frag}…»).")
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
