"""Generación editorial autónoma, anclada en el texto oficial: solicitud del planificador → guion verificable.

Por qué es confiable aunque la redacte un modelo de lenguaje:
  1. El modelo NO elige fuentes libres: solo puede proponer artículos de los ordenamientos de data/ordenamientos.json.
  2. El sistema descarga el PDF oficial y extrae el texto del artículo. Si el artículo no existe, la propuesta se descarta.
  3. El modelo redacta SOLO con ese texto delante, y cada afirmación debe traer una cita copiada de él.
     El programa comprueba que la cita esté en el texto oficial. Si no está, la afirmación se elimina o el guion se
     rechaza; nunca se «corrige» con texto inventado.
  4. El cierre (aviso de información general y leyenda de jurisdicción) lo escribe el programa, no el modelo.
  5. Un segundo modelo, de otra familia, audita el guion contra los mismos textos oficiales. Si encuentra objeciones,
     hay una corrección; si persisten, el tema se descarta y se pasa al siguiente.
  6. Después el guion pasa por esquema.py, verificador.py (nueva descarga y cotejo) y las reglas editoriales del ciclo.
Lo que no garantiza: que la interpretación sea la única posible. Por eso los temas de riesgo alto (carril C) no se
automatizan y las interpretaciones con duda declarada se retienen.
"""
import json, re, sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import esquema, modelos, verificador, razonamiento

RAIZ = Path(__file__).resolve().parent.parent
ORDEN = {o["sigla"]: o for o in json.loads((RAIZ / "data" / "ordenamientos.json").read_text())["ordenamientos"]}
RIESGO_CARRIL = {"A": "bajo", "B": "medio", "C": "alto"}
LOCALES = ("CPF", "CCF")  # tienen equivalentes estatales distintos → leyenda de jurisdicción obligatoria


class Descartada(Exception):
    """El tema no puede convertirse en una pieza verificable ahora. `transitoria` = reintentar más tarde."""
    def __init__(self, motivo, transitoria=False):
        super().__init__(motivo); self.transitoria = transitoria


# ---------------- textos oficiales ----------------
class Biblioteca:
    """Descarga cada PDF oficial una sola vez por ejecución y extrae artículos con su texto original."""
    def __init__(self, transporte=verificador.transporte_http):
        self.transporte, self.docs = transporte, {}

    def articulo(self, sigla, numero):
        o = ORDEN.get(sigla)
        if not o: return None
        if sigla not in self.docs:
            try:
                estado, ctype, datos = self.transporte(o["url"])
            except verificador.SinConexion as e:
                raise Descartada(f"sin conexión con {o['url']} ({e})", transitoria=True)
            if estado != 200:
                raise Descartada(f"{o['url']} respondió HTTP {estado}", transitoria=estado >= 500 or estado in (403, 429))
            cab, cuerpo = verificador.texto_de(ctype, datos)
            if verificador._plano(o["documento"]) not in verificador._plano(cab):
                raise Descartada(f"{o['url']} no corresponde a «{o['documento']}»")
            self.docs[sigla] = (cab, cuerpo)
        cab, cuerpo = self.docs[sigla]
        return verificador.articulo_texto(cuerpo, numero, max_car=6000)


# ---------------- instrucciones a los modelos ----------------
REGLAS_COMUNES = """Eres parte del equipo editorial de «Aquí Dice la Ley», un medio de divulgación jurídica para público
general en México. Escribes en español de México, claro, cercano y exacto. Reglas que no se negocian:
- Usa SOLO los textos oficiales que se te entregan. No agregues artículos, tesis, cifras, fechas, casos ni personas que no estén ahí.
- Cada afirmación jurídica lleva "cita_literal": un fragmento COPIADO EXACTAMENTE del texto oficial (8 a 40 palabras).
- Distingue lo que dice la norma ("hecho_normativo") de tu explicación ("interpretacion"). Si existe una duda real sobre el alcance, escríbela en "duda".
- Nada de asesoría personalizada: prohibido "en tu caso", "te garantizo", "contáctanos", "asesoría gratuita".
- No llames culpable, asesino o delincuente a nadie. No menciones personas reales.
- No uses lenguaje absoluto ("siempre", "nunca", "en todos los casos") salvo que el texto oficial lo diga.
- Razona como abogado ANTES de redactar: identifica la pregunta, la norma que la responde, sus condiciones, requisitos,
  límites y excepciones, y los conceptos parecidos que NO son lo mismo. Si el artículo dice «todo bien que se ofrezca con
  garantía…», la regla vale para ESOS bienes, no para todos. Si preguntan por la renuncia, responde sobre la renuncia y no
  sobre otra causa de terminación. Si los textos no alcanzan para responder, dilo («la ley no lo establece de forma
  general…») en lugar de forzar una respuesta.
- El contenido visible debe RESPONDER la pregunta del título de forma directa (Sí / No / Depende de…).
Responde únicamente con un objeto JSON válido."""

PEDIR_FUENTES = """Tema: {titulo}
Gancho: {gancho}
Fuentes sugeridas por el catálogo (pueden ser imprecisas): {sugeridas}
Ordenamientos disponibles (sigla: nombre): {lista}

Propón de 1 a 4 artículos que sustenten el tema. Devuelve:
{{"articulos": [{{"sigla": "...", "articulo": "17", "para_que": "qué afirmación sustenta"}}]}}
Usa solo siglas de la lista. El número de artículo sin la palabra «artículo» (p. ej., "17", "87", "1o", "17 Bis")."""

PEDIR_REEL = """Escribe el guion de un Reel vertical de 45 a 70 segundos (700 a 1,100 caracteres de narración en total) sobre:
Tema: {titulo}
Pregunta que DEBE responder: {gancho}
Textos oficiales disponibles (fuente → texto):
{textos}


Antes del contenido, incluye el campo "razonamiento" (no se publica; sirve para revisar tu lógica):
{{"razonamiento": {{"pregunta": "la pregunta exacta que responde la pieza",
   "respuesta_corta": "Sí, … / No, … / Depende: … (una oración)",
   "reglas": [{{"conclusion": "…", "fuente": "F1", "cita_literal": "copia exacta que la sostiene", "condiciones": ["…"], "excepciones": ["…"]}}],
   "distinciones": [{{"a": "concepto", "b": "concepto parecido", "diferencia": "…"}}],
   "limites": "lo que la norma no dice"}}, …resto de campos…}}
Conceptos que el público suele confundir en este tema (no los mezcles; si usas dos, explica su diferencia):
{glosario}
Estructura obligatoria del JSON:
{{"titulo": "pregunta o frase de 40 a 70 caracteres",
  "escenas": [
    {{"tipo": "gancho", "texto": "pregunta inicial de una oración", "titulo": ["2 A 3", "LÍNEAS CORTAS", "EN MAYÚSCULAS"]}},
    {{"tipo": "titular", "texto": "contexto en una o dos oraciones", "titulo": ["LÍNEAS", "CORTAS"]}},
    {{"tipo": "cita", "texto": "narración que INCLUYE la cita literal completa", "fuente": "F1", "cita_literal": "copia exacta del texto oficial", "etiqueta": "Ley, artículo N"}},
    {{"tipo": "lista", "texto": "explicación práctica", "items": ["máx. 28 caracteres", "...", "..."]}},
    {{"tipo": "excepcion", "numero": 1, "texto": "una excepción o condición importante", "encabezado": "máx. 40 caracteres", "detalle": "máx. 36 caracteres", "fuente": "F2", "fuente_corta": "Ley, art. N"}},
    {{"tipo": "titular", "texto": "conclusión útil en una o dos oraciones", "titulo": ["LÍNEAS", "CORTAS"]}}
  ],
  "afirmaciones": [{{"escena": 2, "fuente": "F1", "tipo": "hecho_normativo", "texto": "qué se afirma", "cita_literal": "copia exacta", "duda": null}}]}}
Puedes omitir la escena de excepción si los textos no traen una, o repetirla con "numero": 2. No escribas el cierre: lo agrega el sistema.
Cada escena que afirme algo jurídico debe tener al menos una afirmación con su cita_literal."""

PEDIR_IMAGEN = """Escribe una pieza gráfica editorial (imagen fija) con UNA idea central sobre:
Tema: {titulo}
Ángulo: {angulo}
Plantilla: {plantilla}
Textos oficiales disponibles (fuente → texto):
{textos}


Antes del contenido, incluye el campo "razonamiento" (no se publica; sirve para revisar tu lógica):
{{"razonamiento": {{"pregunta": "la pregunta exacta que responde la pieza",
   "respuesta_corta": "Sí, … / No, … / Depende: … (una oración)",
   "reglas": [{{"conclusion": "…", "fuente": "F1", "cita_literal": "copia exacta que la sostiene", "condiciones": ["…"], "excepciones": ["…"]}}],
   "distinciones": [{{"a": "concepto", "b": "concepto parecido", "diferencia": "…"}}],
   "limites": "lo que la norma no dice"}}, …resto de campos…}}
Conceptos que el público suele confundir en este tema (no los mezcles; si usas dos, explica su diferencia):
{glosario}
Devuelve JSON con:
{{"titular": "≤ 60 caracteres", "bajada": "≤ 150 caracteres",
  {campos}
  "copy": "texto de acompañamiento de 3 a 5 párrafos breves: explica, cita las fuentes por nombre y artículo, y termina invitando a guardar o compartir",
  "alt": "descripción para lectores de pantalla",
  "afirmaciones": [{{"fuente": "F1", "tipo": "hecho_normativo", "texto": "...", "cita_literal": "copia exacta", "duda": null}}]}}
No escribas el aviso legal: lo agrega el sistema. Contenido de la imagen ≤ 55 palabras."""

CAMPOS_PLANTILLA = {
    "concepto": '"cita_literal_destacada": "fragmento exacto del texto oficial (≤ 130 caracteres)", "fuente_cita": "F1", "ojo": "≤ 60 caracteres, una precisión importante",',
    "dato": '"cita_literal_destacada": "fragmento exacto del texto oficial (≤ 130 caracteres)", "fuente_cita": "F1", "ojo": "≤ 60 caracteres",',
    "tres_claves": '"puntos": ["≤ 60 caracteres", "≤ 60 caracteres", "≤ 60 caracteres"],',
    "mito_realidad": '"mito": "creencia común (≤ 90 caracteres)", "realidad": "lo que dice la norma (≤ 140 caracteres)",',
    "diferencia": '"columnas": [["Concepto A", "≤ 120 caracteres"], ["Concepto B", "≤ 120 caracteres"]],',
}

ANALIZAR = """ETAPA 1 DE 2 — ANÁLISIS JURÍDICO (todavía NO redactes la pieza).
Pregunta del plan editorial que la pieza DEBE responder (no la cambies por otra): {pregunta}
Tema: {titulo}
Textos oficiales disponibles (fuente → texto completo del artículo):
{textos}

Conceptos que el público suele confundir en este tema:
{glosario}

Trabaja como abogado, en este orden:
1. Identifica qué pregunta exactamente el público y qué concepto jurídico está en juego (usa el mismo término de la pregunta).
2. Busca en los textos la regla que la responde. Copia la cita literal (8 a 40 palabras) que la sostiene.
3. Lee la oración completa y las anteriores: anota TODAS las condiciones, requisitos, plazos y excepciones de esa regla
   («siempre que», «cuando», «salvo», «que se ofrezca…», «en los casos…»). Si la regla solo vale para ciertos supuestos, dilo.
4. Distingue los conceptos parecidos que NO son lo mismo y que podrían confundirse en la respuesta.
5. Con todo lo anterior, escribe la respuesta corta: empieza con «Sí», «No» o «Depende» y menciona en ella la condición principal.
6. COBERTURA. Esta pregunta es de tipo «{tipo}». Quien la hace necesita saber: {requeridos}. Para CADA uno escribe un
   elemento: "cubierto" con su respuesta, la fuente y una cita literal que lo diga expresamente; o "no_aplica" con el motivo
   (p. ej., no hay nada que reclamar). Si un artículo no lo dice expresamente, NO lo deduzcas: márcalo "no_cubierto" y el
   sistema buscará el artículo que falta. Un solo artículo rara vez basta para explicar efecto, vía, autoridad y plazo.
7. Separa lo que la norma dice expresamente de lo que es interpretación (criterio judicial, consecuencia que depende de
   pruebas o de condiciones): las interpretaciones van en "interpretaciones" con su condición, nunca como regla general.
8. Si los textos no permiten responder la pregunta con seguridad, NO fuerces una respuesta: marca "suficiente": false.
Devuelve:
{{"suficiente": true,
  "pregunta": "{pregunta}",
  "concepto_central": "el concepto de la pregunta",
  "respuesta_corta": "Sí/No/Depende: … (una oración, ≤ 160 caracteres, con la condición principal)",
  "reglas": [{{"conclusion": "qué establece la norma para ESTA pregunta", "fuente": "F1", "cita_literal": "copia exacta",
              "condiciones": ["condición o requisito que limita la regla"], "excepciones": ["excepción que prevé el texto"]}}],
  "elementos": [{{"elemento": "efecto | que_hacer | ante_quien | plazo | definicion", "estado": "cubierto | no_aplica | no_cubierto",
                 "respuesta": "en una oración, con las palabras que usará la pieza", "fuente": "F1", "cita_literal": "copia exacta", "motivo": "solo si no aplica"}}],
  "interpretaciones": [{{"afirmacion": "…", "condicion": "de qué depende", "base": "qué la apoya"}}],
  "distinciones": [{{"a": "concepto", "b": "concepto parecido", "diferencia": "en una oración"}}],
  "limites": "lo que estos textos NO dicen o lo que la pieza no debe afirmar",
  "fuentes_irrelevantes": ["F3"]}}
Usa solo F1, F2… de la lista. Ninguna conclusión puede ir más allá de lo que dice su cita."""

PLAN_FIJO = """
ETAPA 2 DE 2 — REDACCIÓN. El análisis jurídico de abajo YA FUE REVISADO contra el texto oficial. Redacta la pieza usando
EXCLUSIVAMENTE ese análisis:
- El título debe ser la pregunta del análisis (puedes acortarla, pero conserva sus palabras clave).
- La respuesta corta debe aparecer en el contenido visible con casi las mismas palabras ({donde_respuesta}).
- Cada condición y excepción del análisis debe decirse en el contenido visible; nunca presentes la regla como general.
- Cada afirmación debe salir de una regla del análisis y llevar su misma cita literal y su misma fuente. No agregues reglas,
  artículos, cifras ni ejemplos jurídicos que no estén en el análisis.
- Cada elemento «cubierto» del análisis (efecto, qué hacer, ante quién, plazo…) debe decirse en el contenido visible con
  casi las mismas palabras de su «respuesta». No aludas a un recurso, vía o autoridad sin nombrarlo («existe un recurso legal
  específico» está prohibido). Las «interpretaciones» solo pueden aparecer con su condición («si se demuestra…»).
- Si usas dos conceptos de las distinciones, explica su diferencia.
- Repite en "razonamiento" exactamente el análisis recibido (no lo modifiques).
Análisis aprobado:
{mapa}
"""

AUDITAR = """Eres auditor jurídico independiente. No basta con que las citas existan: revisa si las CONCLUSIONES que la pieza saca
de ellas son jurídicamente válidas. Textos oficiales (completos):
{textos}

Pieza (incluye el mapa de razonamiento del redactor y la pregunta que debía responder):
{pieza}

Para cada conclusión, pregúntate: ¿el texto citado la sostiene por completo, solo en parte o no la sostiene? ¿Omite una
condición, requisito, límite o excepción del artículo (p. ej., «que se ofrezca con garantía», «siempre que», «salvo»)?
¿Confunde conceptos parecidos (garantía, devolución, cambio, bonificación, rescisión; renuncia, mutuo consentimiento,
despido)? ¿La pieza responde de forma directa la pregunta de su título y la del plan editorial? ¿Presenta como regla general
lo que la ley solo prevé en supuestos concretos? ¿Afirma algo que la ley no dice (p. ej., que algo es ilegal sin que un texto
lo establezca)?
COBERTURA: ponte en el lugar de quien hizo la pregunta. ¿La pieza le dice lo esencial (qué consecuencia tiene, qué puede
hacer, ante quién y en qué plazo, cuando aplique)? ¿O responde un aspecto lateral (p. ej., la validez de un documento) y
deja sin contestar el núcleo? ¿Alguna consecuencia se apoya en un artículo que no la establece? ¿Hay referencias vagas
(«existe un recurso», «acude a las autoridades competentes») sin nombrar la vía o la autoridad?
Señala SOLO problemas reales, cada uno con la corrección concreta.
Devuelve: {{"veredicto": "sin_objeciones" | "con_objeciones",
 "cobertura": {{"responde_nucleo": true | false, "faltantes": ["lo esencial que no se responde"]}},
 "conclusiones": [{{"conclusion": "...", "sostenida": "si" | "parcial" | "no", "motivo": "..."}}],
 "objeciones": [{{"donde": "...", "problema": "...", "correccion": "..."}}]}}
Si alguna conclusión es «parcial» o «no», o si "responde_nucleo" es false, el veredicto es «con_objeciones»."""


def _textos(fuentes):
    return "\n\n".join(f'{fid} — {f["documento"]}, artículo {f["articulo"]}:\n{f["texto_oficial"]}' for fid, f in fuentes.items())


# ---------------- etapas ----------------
def investigar(sol, investigador, biblio, simulador=None):
    lista = "; ".join(f'{s}: {o["documento"]}' for s, o in ORDEN.items())
    r = investigador.completar(REGLAS_COMUNES, PEDIR_FUENTES.format(titulo=sol["titulo"], gancho=sol.get("gancho") or sol.get("angulo", ""),
                                                                    sugeridas=sol.get("fuentes_sugeridas", ""), lista=lista), simulador)
    fuentes, descartes = {}, []
    for c in (r.get("articulos") or [])[:4]:
        sigla, num = str(c.get("sigla", "")).strip(), str(c.get("articulo", "")).strip()
        if sigla not in ORDEN or not re.fullmatch(r"\d{1,4}(?:o|°|º)?(?: (?:Bis|Ter|Quater))?(?:-[A-Z])?", num, re.I):
            descartes.append(f"{sigla} {num}: fuera del catálogo o número inválido"); continue
        texto = biblio.articulo(sigla, num)
        if not texto:
            descartes.append(f"{sigla} {num}: el artículo no existe en el documento oficial"); continue
        fid = f"F{len(fuentes) + 1}"
        fuentes[fid] = {"sigla": sigla, "documento": ORDEN[sigla]["documento"], "articulo": num, "url": ORDEN[sigla]["url"],
                        "ambito": ORDEN[sigla]["ambito"], "texto_oficial": texto, "para_que": c.get("para_que", "")}
    if not fuentes:
        raise Descartada("ninguna fuente propuesta existe en los documentos oficiales: " + "; ".join(descartes))
    return fuentes, descartes


def _anclar(afirmaciones, fuentes):
    """Conserva solo afirmaciones cuya cita esté en el texto oficial de su fuente."""
    ok, quitadas = [], []
    for a in afirmaciones:
        f = fuentes.get(a.get("fuente"))
        cita = (a.get("cita_literal") or "").strip().strip("«»\"")
        if len((a.get("texto") or "").strip()) < 10:
            quitadas.append("(afirmación sin texto)"); continue
        if f and len(cita.split()) >= 5 and verificador.contiene(f["texto_oficial"], cita):
            ok.append({**a, "cita_literal": cita})
        else:
            quitadas.append(a.get("texto", "")[:80])
    return ok, quitadas


def _fuentes_guion(fuentes, afirmaciones):
    """Una ficha de fuente por cita (el verificador coteja cada cita en su artículo)."""
    fichas, mapa = {}, []
    for i, a in enumerate(afirmaciones, 1):
        f = fuentes[a["fuente"]]; fid = f"F{i}"
        fichas[fid] = {"tipo": "ley", "nivel": "oficial", "documento": f["documento"], "articulo": f["articulo"], "url": f["url"],
                       "texto_literal": a["cita_literal"], "cita": f'{f["documento"]}, artículo {f["articulo"]}',
                       "jurisdiccion": f["ambito"], "consultado": datetime.now(timezone.utc).date().isoformat()}
        mapa.append(fid)
    return fichas, mapa


def _cierre(fuentes):
    locales = any(f["sigla"] in LOCALES for f in fuentes.values())
    texto = "Esto es información general, no asesoría legal." + (" Las leyes penales y civiles pueden variar según tu estado." if locales else "") + \
            " Síguenos para entender tus derechos."
    return {"tipo": "cierre", "texto": texto, "aviso": "Información general, no asesoría legal." + (" Las leyes varían por estado." if locales else ""),
            "afirmaciones": []}


def _mapa(borrador, fuentes):
    rz = dict(borrador.get("razonamiento") or {})
    rz["reglas"] = [{**r, "ref": {k: fuentes[r["fuente"]][k] for k in ("documento", "articulo")} if r.get("fuente") in fuentes else {}}
                    for r in (rz.get("reglas") or []) if isinstance(r, dict)]
    return rz


def construir_reel(sol, borrador, fuentes):
    afs, quitadas = _anclar(borrador.get("afirmaciones", []), fuentes)
    if not afs:
        raise Descartada("ninguna afirmación del borrador está anclada en el texto oficial")
    fichas, mapa = _fuentes_guion(fuentes, afs)
    escenas = []
    for i, e in enumerate(borrador.get("escenas", [])):
        e = {k: v for k, v in e.items() if k not in ("fuente", "cita_literal")}
        if e.get("tipo") == "cita":
            src = borrador["escenas"][i]
            cita = (src.get("cita_literal") or "").strip().strip("«»\"")
            f = fuentes.get(src.get("fuente"))
            if not (f and verificador.contiene(f["texto_oficial"], cita)):
                continue                                         # una cita no verificable no se muestra en pantalla
            e["cita"] = cita; e.setdefault("etiqueta", f'{f["documento"].split(",")[0]}, artículo {f["articulo"]}')
            if not verificador.contiene(e.get("texto", ""), cita):
                e["texto"] = (e.get("texto", "").rstrip(". ") + ": " + cita).strip(": ")
        e["afirmaciones"] = [{"id": f"A{j + 1}", "tipo": a.get("tipo", "interpretacion"), "texto": a.get("texto", ""), "fuente": mapa[j],
                              **({"nota": a["duda"]} if a.get("duda") else {}), **({"comparar_literal": True} if e.get("tipo") == "cita" else {})}
                             for j, a in enumerate(afs) if a.get("escena") == i]
        escenas.append(e)
    asignadas = {a["fuente"] for e in escenas for a in e["afirmaciones"]}
    huérfanas = [j for j in range(len(afs)) if mapa[j] not in asignadas]
    if huérfanas and escenas:                                    # afirmaciones sin escena válida → a la escena más cercana con texto
        for j in huérfanas:
            destino = min(max(int(afs[j].get("escena", 1) or 1), 0), len(escenas) - 1)
            escenas[destino]["afirmaciones"].append({"id": f"A{j + 1}", "tipo": afs[j].get("tipo", "interpretacion"),
                                                     "texto": afs[j].get("texto", ""), "fuente": mapa[j], **({"nota": afs[j]["duda"]} if afs[j].get("duda") else {})})
    escenas.append(_cierre(fuentes))
    return {"id": sol["pieza_id"], "formato": "reel", "titulo": borrador.get("titulo") or sol["titulo"], "version_esquema": "0.3",
            "riesgo": RIESGO_CARRIL.get(sol.get("carril", "A"), "medio"), "carril_inicial": sol.get("carril", "A"),
            "tema_id": sol["tema_id"], "fuentes": fichas, "escenas": escenas, "razonamiento": _mapa(borrador, fuentes),
            "generacion": {"afirmaciones_eliminadas_sin_ancla": quitadas}}


def construir_imagen(sol, borrador, fuentes):
    afs, quitadas = _anclar(borrador.get("afirmaciones", []), fuentes)
    if not afs:
        raise Descartada("ninguna afirmación de la imagen está anclada en el texto oficial")
    fichas, mapa = _fuentes_guion(fuentes, afs)
    pl = sol.get("plantilla", "concepto")
    pieza = {"titular": borrador.get("titular", "")[:70], "bajada": borrador.get("bajada", "")[:160]}
    if pl in ("concepto", "dato"):
        f = fuentes.get(borrador.get("fuente_cita")); cita = (borrador.get("cita_literal_destacada") or "").strip().strip("«»\"")
        if f and verificador.contiene(f["texto_oficial"], cita):
            pieza.update(cita=cita, etiqueta_cita=f'{f["documento"].split(",")[0]}, artículo {f["articulo"]}')
        if borrador.get("ojo"): pieza["ojo"] = borrador["ojo"][:70]
    elif pl == "tres_claves":
        pieza["puntos"] = [p[:70] for p in borrador.get("puntos", [])[:3]]
    elif pl == "mito_realidad":
        pieza.update(mito=borrador.get("mito", ""), realidad=borrador.get("realidad", ""))
    elif pl == "diferencia":
        pieza["columnas"] = borrador.get("columnas", [])[:2]
    usados = {}
    for a in afs: usados.setdefault((fuentes[a["fuente"]]["documento"], fuentes[a["fuente"]]["articulo"]), 1)
    por_doc = {}
    for d, n in usados: por_doc.setdefault(d.split(",")[0], []).append(n)
    y = lambda ns: ns[0] if len(ns) == 1 else ", ".join(ns[:-1]) + " y " + ns[-1]
    pieza["fuente_visible"] = " · ".join(f'{d}, art{"s" if len(ns) > 1 else ""}. {y(ns)}' for d, ns in por_doc.items())
    locales = any(f["sigla"] in LOCALES for f in fuentes.values())
    copy = borrador.get("copy", "").strip() + "\n\nEsto es información general, no es asesoría legal." + \
           (" Las leyes penales y civiles pueden variar según tu estado." if locales else "")
    return {"id": sol["pieza_id"], "formato": "imagen", "plantilla": pl, "titulo": pieza["titular"], "version_esquema": "0.3",
            "riesgo": RIESGO_CARRIL.get(sol.get("carril", "A"), "medio"), "tema_id": sol["tema_id"], "pieza": pieza, "copy": copy,
            "alt": borrador.get("alt") or pieza["titular"], "relacion_reel": sol.get("relacion"), "fuentes": fichas,
            "afirmaciones": [{"id": f"A{j + 1}", "tipo": a.get("tipo", "interpretacion"), "texto": a.get("texto", ""), "fuente": mapa[j],
                              **({"nota": a["duda"]} if a.get("duda") else {})} for j, a in enumerate(afs)],
            "razonamiento": _mapa(borrador, fuentes), "generacion": {"afirmaciones_eliminadas_sin_ancla": quitadas}}


def _glosario(sol, fuentes):
    """Conceptos confundibles del tema (por la pregunta y por los textos oficiales), con su definición editorial."""
    base = " ".join([sol.get("titulo", ""), sol.get("gancho", ""), sol.get("angulo", "")] + [f["texto_oficial"][:1500] for f in fuentes.values()])
    grupos = {g for g, _ in razonamiento.conceptos_en(base)}
    lin = []
    for g in sorted(grupos):
        for c, d in razonamiento.CONCEPTOS["grupos"][g]["conceptos"].items():
            lin.append(f"- {c.replace('_', ' ')}: {d['definicion']}")
    return "\n".join(lin) or "- (sin conceptos confundibles detectados)"


def _fuentes_por_ficha(g, fuentes):
    """Las fichas del guion (F1, F2… una por cita) apuntan a artículos; devuelve {ficha: fuente con su texto oficial}."""
    out = {}
    for fid, fi in (g.get("fuentes") or {}).items():
        src = next((f for f in fuentes.values() if f["documento"] == fi["documento"] and f["articulo"] == fi["articulo"]), None)
        if src: out[fid] = src
    return out


PEDIR_COMPLEMENTO = """Tema: {titulo}
Pregunta: {pregunta}
Ya se tienen estos artículos: {tenidos}
Falta sustento oficial para: {faltan}
Ordenamientos disponibles (sigla: nombre): {lista}

Propón de 1 a 3 artículos ADICIONALES que establezcan expresamente lo que falta (p. ej., la acción que se puede ejercer,
la autoridad ante la que se hace y el plazo). Devuelve:
{{"articulos": [{{"sigla": "...", "articulo": "48", "para_que": "qué elemento sustenta"}}]}}"""


def investigar_complemento(sol, faltan, fuentes, investigador, biblio, simulador=None, maximo=6):
    """Segunda búsqueda dirigida: cuando el análisis no encuentra sustento para un elemento esencial de la respuesta."""
    lista = "; ".join(f'{s}: {o["documento"]}' for s, o in ORDEN.items())
    tenidos = ", ".join(f'{f["sigla"]} art. {f["articulo"]}' for f in fuentes.values())
    r = investigador.completar(REGLAS_COMUNES, PEDIR_COMPLEMENTO.format(titulo=sol["titulo"], pregunta=pregunta_plan(sol), tenidos=tenidos,
                                                                        faltan="; ".join(faltan), lista=lista), simulador)
    nuevas, ya = {}, {(f["sigla"], f["articulo"]) for f in fuentes.values()}
    for c in (r.get("articulos") or [])[:3]:
        sigla, num = str(c.get("sigla", "")).strip(), str(c.get("articulo", "")).strip()
        if len(fuentes) + len(nuevas) >= maximo or (sigla, num) in ya or sigla not in ORDEN: continue
        if not re.fullmatch(r"\d{1,4}(?:o|°|º)?(?: (?:Bis|Ter|Quater))?(?:-[A-Z])?", num, re.I): continue
        texto = biblio.articulo(sigla, num)
        if not texto: continue
        fid = f"F{len(fuentes) + len(nuevas) + 1}"
        nuevas[fid] = {"sigla": sigla, "documento": ORDEN[sigla]["documento"], "articulo": num, "url": ORDEN[sigla]["url"],
                       "ambito": ORDEN[sigla]["ambito"], "texto_oficial": texto, "para_que": c.get("para_que", "")}
    return nuevas


def pregunta_plan(sol):
    return sol.get("gancho") or sol.get("angulo") or sol["titulo"]


def analizar(sol, fuentes, red, glosario, simulador=None, extra=""):
    """Etapa 1: la regla, sus condiciones, excepciones y fuentes ANTES de escribir una sola línea de la pieza."""
    tipo, req = razonamiento.tipo_pregunta(pregunta_plan(sol))
    nota = ""
    if sol.get("investigacion") and (RAIZ / sol["investigacion"]).exists():   # investigación editorial previa (p. ej., tras un rechazo humano)
        nota = ("\n\nNOTA DE INVESTIGACIÓN EDITORIAL (no es texto oficial: úsala para entender el problema y los errores a evitar; "
                "toda afirmación normativa debe salir de los textos oficiales de arriba, y lo que la nota marca como interpretación solo "
                "puede ir en «interpretaciones» con su condición):\n" + (RAIZ / sol["investigacion"]).read_text()[:5000])
    r = red.completar(REGLAS_COMUNES, ANALIZAR.format(pregunta=pregunta_plan(sol), titulo=sol["titulo"], textos=_textos(fuentes), glosario=glosario,
                                                       tipo=tipo, requeridos="; ".join(f"{k} ({razonamiento.ELEMENTOS[k]})" for k in req)) + nota + extra, simulador)
    return r if isinstance(r, dict) else {}


def validar_mapa(mapa, sol, fuentes):
    """Revisión determinista del análisis contra el texto oficial COMPLETO de cada artículo. Aplica las MISMAS reglas que
    después se aplican a la pieza (razonamiento.revisar), más las propias del análisis. Devuelve la lista de errores."""
    if mapa.get("suficiente") is False:
        return ["INSUFICIENTE: " + (mapa.get("limites") or mapa.get("motivo") or "los textos no permiten responder la pregunta")]
    err = []
    reglas = [r for r in (mapa.get("reglas") or []) if isinstance(r, dict)]
    if not reglas:
        err.append("[mapa] No hay reglas: cada conclusión debe ligarse a una fuente con su cita literal.")
    for r in reglas:
        if r.get("fuente") not in fuentes:
            err.append(f'[mapa] La regla «{str(r.get("conclusion", ""))[:60]}» usa una fuente que no existe ({r.get("fuente")}).')
        elif len(str(r.get("cita_literal", "")).split()) < 5:
            err.append(f'[mapa] La regla «{str(r.get("conclusion", ""))[:60]}» no trae una cita literal suficiente.')
    rz = {**mapa, "reglas": [{**r, "ref": {k: fuentes[r["fuente"]][k] for k in ("documento", "articulo")}} for r in reglas if r.get("fuente") in fuentes]}
    prueba = {"titulo": pregunta_plan(sol).strip(), "pregunta_original": pregunta_plan(sol), "razonamiento": rz,
              "pieza": {"bajada": mapa.get("respuesta_corta", "")}, "fuentes": {}, "_solo_analisis": True}
    if not prueba["titulo"].endswith("?"): prueba["titulo"] += "?"
    textos = {(f["documento"], f["articulo"]): f["texto_oficial"] for f in fuentes.values()}
    err += [f'[{x["regla"]}] {x["detalle"]}' for x in razonamiento.bloqueantes(razonamiento.revisar(prueba, textos, ia=True))]
    # el análisis debe responder la MISMA pregunta del plan (la prueba de arriba usa la pregunta del plan como título)
    plan = pregunta_plan(sol)
    propio = " ".join([str(mapa.get("pregunta", "")), str(mapa.get("respuesta_corta", ""))] + [str(r.get("conclusion", "")) for r in reglas])
    if not (razonamiento._temas(plan) & razonamiento._temas(propio)) and \
       not ({g for g, _ in razonamiento.conceptos_en(plan)} & {g for g, _ in razonamiento.conceptos_en(propio)}):
        err.append(f"[tema] El análisis no responde la pregunta del plan editorial («{plan[:80]}»): trata «{str(mapa.get('pregunta', ''))[:80]}».")
    return err


def _mapa_fijo(mapa, fuentes):
    """El análisis validado, con la referencia oficial de cada regla; es lo que viaja en el guion (el redactor no lo cambia)."""
    usadas = {r.get("fuente") for r in mapa.get("reglas", []) if isinstance(r, dict)}
    return {k: v for k, v in {**mapa, "reglas": [{**r, "ref": {k2: fuentes[r["fuente"]][k2] for k2 in ("documento", "articulo")}}
                                                  for r in mapa.get("reglas", []) if isinstance(r, dict) and r.get("fuente") in fuentes]}.items()
            if k not in ("fuentes_irrelevantes",)}, usadas


def auditar_ia(guion, fuentes, auditor, simulador=None):
    pieza = json.dumps({k: guion[k] for k in ("pregunta_original", "titulo", "razonamiento", "escenas", "pieza", "copy") if k in guion}, ensure_ascii=False)[:12000]
    return auditor.completar(REGLAS_COMUNES, AUDITAR.format(textos=_textos(fuentes), pieza=pieza), simulador)


DONDE_RESPUESTA = {"reel": "en la escena «titular» que sigue al gancho, y otra vez en la conclusión",
                   "concepto": "en la bajada", "dato": "en la bajada", "tres_claves": "en la bajada", "diferencia": "en la bajada",
                   "mito_realidad": "en «realidad»"}


def _objeta_mapa(a, mapa):
    """¿El auditor declara no sostenida (total o parcialmente) una conclusión del análisis? Entonces el error está en la
    etapa 1 y se corrige el análisis, no solo la redacción."""
    concl = [str(r.get("conclusion", "")) for r in mapa.get("reglas", []) if isinstance(r, dict)]
    for x in a.get("conclusiones", []) or []:
        if str(x.get("sostenida", "si")).lower() != "si" and any(razonamiento._coincide(str(x.get("conclusion", "")), c) for c in concl):
            return True
    return False


def generar(sol, transporte=verificador.transporte_http, simulador=None, env=None, archivo_uso=None):
    """Devuelve el guion listo para la cola, o lanza Descartada con el motivo.
    Etapa 1 (analizar): pregunta → regla → condiciones/excepciones → distinciones → respuesta corta, validado de forma
    determinista contra el texto oficial ANTES de redactar. Etapa 2 (redactar): la pieza se escribe sobre ese análisis
    congelado; después pasan los mismos controles de siempre (esquema, razonamiento, auditor independiente)."""
    import os
    env = env if env is not None else os.environ
    if sol.get("carril") == "C":
        raise Descartada("tema de riesgo alto: no se automatiza (requiere revisión humana)")
    cfg = modelos.config()
    if simulador: cfg = {**cfg, "proveedor": "simulado"}
    inv, red, aud = (modelos.Modelo(r, cfg, env, archivo_uso) for r in ("investigador", "redactor", "auditor"))
    try:
        biblio = Biblioteca(transporte)
        fuentes, descartes = investigar(sol, inv, biblio, simulador)
        glosario = _glosario(sol, fuentes)
        historial, extra_a, reanalisis, complemento = [], "", 0, False
        while True:
            # ---- etapa 1: análisis jurídico (dos oportunidades) ----
            mapa = None
            for intento in range(2):
                m = analizar(sol, fuentes, red, glosario, simulador, extra_a)
                errores = validar_mapa(m, sol, fuentes)
                if errores and errores[0].startswith("INSUFICIENTE"):
                    raise Descartada("el análisis concluyó que los textos oficiales no bastan para responder la pregunta: " + errores[0][14:300])
                historial.append({"etapa": "analisis", "intento": intento, "errores": errores})
                if not errores:
                    mapa = m; break
                faltan = [e for e in errores if e.startswith("[cobertura]") and ("Falta sustento" in e or "no dice" in e)]
                if faltan and not complemento:
                    complemento = True
                    nuevas = investigar_complemento(sol, faltan, fuentes, inv, biblio, simulador)
                    historial.append({"etapa": "investigacion_complementaria", "faltan": faltan, "agregadas": [f'{f["sigla"]} {f["articulo"]}' for f in nuevas.values()]})
                    fuentes.update(nuevas); glosario = _glosario(sol, fuentes)
                extra_a = "\n\nTu análisis anterior tenía estos problemas; corrígelos sin cambiar la pregunta:\n- " + "\n- ".join(errores[:8])
            if mapa is None:
                raise Descartada("el análisis jurídico no superó la revisión contra el texto oficial: " + json.dumps(historial[-1], ensure_ascii=False)[:400])
            mapa_fijo, usadas = _mapa_fijo(mapa, fuentes)
            fuentes_red = {fid: f for fid, f in fuentes.items() if fid in usadas} or fuentes
            textos = _textos(fuentes_red)
            fijo = PLAN_FIJO.format(mapa=json.dumps({k: v for k, v in mapa.items() if k != "fuentes_irrelevantes"}, ensure_ascii=False, indent=1),
                                    donde_respuesta=DONDE_RESPUESTA.get("reel" if sol["formato"] == "reel" else sol.get("plantilla", "concepto"), "en la bajada"))
            if sol["formato"] == "reel":
                pedir = lambda extra="": red.completar(REGLAS_COMUNES, PEDIR_REEL.format(titulo=sol["titulo"], gancho=pregunta_plan(sol), textos=textos, glosario=glosario) + fijo + extra, simulador)
                construir = construir_reel
            else:
                pl = sol.get("plantilla", "concepto")
                pedir = lambda extra="": red.completar(REGLAS_COMUNES, PEDIR_IMAGEN.format(titulo=sol["titulo"], angulo=sol.get("angulo", ""), plantilla=pl,
                                                                                        campos=CAMPOS_PLANTILLA[pl], textos=textos, glosario=glosario) + fijo + extra, simulador)
                construir = construir_imagen
            # ---- etapa 2: redacción sobre el análisis congelado (borrador + dos correcciones) ----
            extra, volver = "", False
            for intento in range(3):
                borrador = pedir(extra)
                borrador = {**(borrador if isinstance(borrador, dict) else {}), "razonamiento": mapa}   # el redactor no puede alterar el análisis
                g = construir(sol, borrador, fuentes_red)
                g["razonamiento"] = mapa_fijo
                g["pregunta_original"] = pregunta_plan(sol)
                errores = esquema.validar(g)
                hall = razonamiento.revisar(g, {(f["documento"], f["articulo"]): f["texto_oficial"] for f in fuentes.values()}, ia=True)
                g["revision_razonamiento"] = hall
                errores += [f'[{x["regla"]}] {x["detalle"]}' for x in razonamiento.bloqueantes(hall)]
                if errores:
                    historial.append({"etapa": "redaccion", "intento": intento, "errores_esquema": errores})
                    extra = "\n\nTu versión anterior tenía estos problemas; corrígelos respetando el análisis aprobado:\n- " + "\n- ".join(errores[:8]); continue
                a = auditar_ia(g, fuentes_red, aud, simulador)
                historial.append({"etapa": "redaccion", "intento": intento, "auditoria_ia": a})
                if a.get("veredicto") == "sin_objeciones" and any(str(x.get("sostenida", "si")).lower() != "si" for x in a.get("conclusiones", []) or []):
                    a = {**a, "veredicto": "con_objeciones", "objeciones": (a.get("objeciones") or []) + [
                        {"donde": x.get("conclusion", ""), "problema": f'conclusión {x.get("sostenida")} sostenida: {x.get("motivo", "")}', "correccion": "ajústala al texto o elimínala"}
                        for x in a["conclusiones"] if str(x.get("sostenida", "si")).lower() != "si"]}
                cob = a.get("cobertura") or {}
                if a.get("veredicto") == "sin_objeciones" and cob.get("responde_nucleo") is False:
                    a = {**a, "veredicto": "con_objeciones", "objeciones": (a.get("objeciones") or []) + [
                        {"donde": "respuesta", "problema": "no responde el núcleo de la pregunta: " + "; ".join(map(str, cob.get("faltantes") or [])),
                         "correccion": "explica lo que falta con su fuente o descarta la pieza"}]}
                if a.get("veredicto") == "sin_objeciones":
                    m_aud, m_red = str(getattr(aud, "ultimo_modelo", "")), str(getattr(red, "ultimo_modelo", ""))
                    fam = lambda m: m.split("-")[0].split("/")[-1].lower()
                    g["auditoria_ia"] = {"veredicto": "sin_objeciones", "modelo_auditor": m_aud or aud.modelos, "historial": historial,
                                         "familia_distinta": bool(m_aud and m_red and fam(m_aud) != fam(m_red))}
                    g["generacion"].update({"fuentes_descartadas": descartes, "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                            "solicitud": sol.get("archivo"), "metodo": "analisis_previo_v2_cobertura",
                                            "modelos": {"investigador": getattr(inv, "ultimo_modelo", inv.modelos), "redactor": getattr(red, "ultimo_modelo", red.modelos)}})
                    return g
                if _objeta_mapa(a, mapa) and reanalisis < 1:
                    reanalisis += 1; volver = True
                    extra_a = ("\n\nUn auditor independiente revisó una pieza basada en tu análisis y objetó estas conclusiones; "
                               "corrige el ANÁLISIS (ajusta la conclusión a lo que dice la cita, agrega condiciones o elimina la regla):\n") + \
                              json.dumps(a.get("objeciones", []), ensure_ascii=False)[:2500]
                    break
                extra = ("\n\nUn auditor independiente objetó lo siguiente. Aplica TODAS las correcciones sin salirte del análisis aprobado; "
                         "si una afirmación no puede sustentarse con el texto oficial, ELIMÍNALA; no agregues información nueva:\n") + \
                        json.dumps(a.get("objeciones", []), ensure_ascii=False)[:2500]
            if not volver:
                raise Descartada("no superó la validación o la auditoría independiente tras dos correcciones: " +
                                 json.dumps(historial[-1], ensure_ascii=False)[:400])
    except (modelos.CuotaAgotada, modelos.FallaModelo) as e:
        raise Descartada(f"modelo no disponible: {e}", transitoria=True)
