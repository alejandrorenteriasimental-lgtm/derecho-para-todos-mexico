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
import copy, json, re, sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import esquema, modelos, verificador, razonamiento

RAIZ = Path(__file__).resolve().parent.parent
ORDEN = {o["sigla"]: o for o in json.loads((RAIZ / "data" / "ordenamientos.json").read_text())["ordenamientos"]}
RIESGO_CARRIL = {"A": "bajo", "B": "medio", "C": "alto"}
def nombre_doc(d):
    """Nombre del ordenamiento para lo visible. Solo se quita un sufijo «, artículo …»/«, art. …»: hay leyes con coma
    en el nombre (Ley General de los Derechos de Niñas, Niños y Adolescentes) que no deben cortarse."""
    return re.split(r",\s*(?:art[íi]culos?|arts?\.)\s", d or "", maxsplit=1, flags=re.I)[0].strip()


def etiqueta_generica(t):
    """«Ley, artículo 58», «Código, art. 3»: la etiqueta no nombra el ordenamiento (la Constitución sí es identificable)."""
    return bool(re.match(r"^\s*(ley|c[óo]digo|reglamento|norma|ordenamiento)\s*(,|$)", t or "", flags=re.I))


LOCALES = ("CPF", "CCF")  # tienen equivalentes estatales distintos → leyenda de jurisdicción obligatoria


class Descartada(Exception):
    """El tema no puede convertirse en una pieza verificable ahora. `transitoria` = reintentar más tarde."""
    def __init__(self, motivo, transitoria=False, historial=None, categoria=None, metricas=None):
        super().__init__(motivo); self.transitoria = transitoria; self.historial = historial
        self.categoria = categoria or categoria_de(motivo, transitoria); self.metricas = metricas


JURIDICAS = ("[cobertura]", "[sustento]", "[conceptos]", "[condiciones]", "[respuesta]", "[tema]", "[mapa]", "[jurisprudencia]", "INSUFICIENTE")
PUNTUALES = ("demasiado larg", "más de ", "línea de título", "[vaguedad]", "narración de ", "pero la pieza no lo dice", "[ojo]")   # se corrigen sin regenerar


def categoria_de(motivo, transitoria=False, errores=None):
    """jurídico | redacción | técnico | cuota: para medir y decidir qué corregir (no se mezclan en las estadísticas)."""
    m = str(motivo) + " " + " ".join(errores or [])
    if transitoria and re.search(r"cuota|tope|429|PerDay|quota", m, re.I): return "cuota"
    if transitoria or re.search(r"sin conexión|HTTP \d|no corresponde a|no es JSON|modelo no disponible|no existe en el documento oficial|número inválido", m): return "tecnico"
    if any(x in m for x in JURIDICAS) or re.search(r"auditor|objeci|no bastan|anclad|fuentes insuficientes", m, re.I): return "juridico"
    return "redaccion"


# ---------------- textos oficiales ----------------
COMUNES = set("a ante bajo con contra de desde durante en entre hacia hasta mediante para por según sin sobre tras el la lo los las un una unos unas y e ni o u que qué quien cual se le les su sus no si sí ya al del más mas como cuando donde este esta estos estas ese esa es son ser fue sea haya han ha hay".split())


def limpiar_cortes(texto, documento=""):
    """El PDF oficial a veces parte palabras con un espacio al cambiar de línea («independienteme nte», «adm inistre»,
    «cost as»). Se unen dos pedazos contiguos solo si ninguno es una palabra común y la unión existe como palabra en el
    documento (o, si mide 8 letras o más, es el inicio de una). No cambia ninguna letra: el cotejo del verificador ignora los
    espacios, así que la cita sigue siendo literal (R20261124-T015, 28-10: «independienteme nte» aparecía en pantalla)."""
    import re as _re, bisect
    vocab = set(_re.findall(r"[a-záéíóúñü]+", (documento or texto).lower()))
    orden = sorted(vocab)
    def existe(w):
        if w in vocab: return True
        if len(w) < 8: return False
        k = w[:-2]; i = bisect.bisect_left(orden, k)
        return i < len(orden) and orden[i].startswith(k)
    partes = _re.split(r"( )", texto)            # palabras y espacios simples, en orden
    out = []
    for p in partes:
        if out and len(out) >= 2 and out[-1] == " " and p and p.isalpha() and p.islower() and out[-2].isalpha():
            a = out[-2]
            if a.lower() not in COMUNES and p not in COMUNES and existe((a + p).lower()):
                out[-2] = a + p; out.pop(); continue
        out.append(p)
    return "".join(out)


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
        t = verificador.articulo_texto(cuerpo, numero, max_car=14000)   # LFT 132 fr. XXVII Bis empieza en el carácter 9568
        return limpiar_cortes(t, cuerpo) if t else t


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

PEDIR_REEL = """Escribe el guion de un Reel vertical de 30 a 42 segundos (420 a 600 caracteres de narración en total; Instagram por API no acepta nuestros Reels de más de 45 s) sobre:
Tema: {titulo}
Pregunta que DEBE responder: {gancho}
Textos oficiales disponibles (fuente → texto):
{textos}


Antes del contenido, incluye el campo "razonamiento" (no se publica; sirve para revisar tu lógica):
{{"razonamiento": {{"pregunta": "la pregunta exacta que responde la pieza",
   "respuesta_corta": "Sí, … / No, … / Depende: … (una oración)",
   "reglas": [{{"conclusion": "…", "fuente": "F1", "cita_literal": "copia exacta que la sostiene", "condiciones": ["…"], "excepciones": ["…"]}}],
   "distinciones": [{{"a": "concepto", "b": "concepto parecido", "diferencia": "…"}}],  (solo conceptos que aparezcan en los textos oficiales o en la lista de conceptos confundibles; si no hay, [])
   "limites": "lo que la norma no dice"}}, …resto de campos…}}
Conceptos que el público suele confundir en este tema (no los mezcles; si usas dos, explica su diferencia):
{glosario}
Estructura obligatoria del JSON:
{{"titulo": "pregunta o frase de 40 a 70 caracteres",
  "escenas": [
    {{"tipo": "gancho", "texto": "pregunta inicial de una oración", "titulo": ["2 A 3", "LÍNEAS CORTAS", "EN MAYÚSCULAS"]}},  (cada línea de "titulo": máx. 20 caracteres, contando espacios y signos)
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
   "distinciones": [{{"a": "concepto", "b": "concepto parecido", "diferencia": "…"}}],  (solo conceptos que aparezcan en los textos oficiales o en la lista de conceptos confundibles; si no hay, [])
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
5. Con todo lo anterior, escribe la respuesta corta: si la pregunta se contesta con sí o no, empieza con «Sí», «No» o «Depende» y
   menciona la condición principal; si pregunta qué es, qué significa, cuánto o cuándo, contesta directamente («Significa que…»,
   «Al menos…», «Antes del…»), nunca con «Sí» o «No».
6. COBERTURA. Esta pregunta es de tipo «{tipo}». Quien la hace necesita saber: {requeridos}. Para CADA uno escribe un
   elemento: "cubierto" con su respuesta, la fuente y una cita literal que lo diga expresamente; o "no_aplica" con el motivo
   (p. ej., no hay nada que reclamar). Si un artículo no lo dice expresamente, NO lo deduzcas: márcalo "no_cubierto" y el
   sistema buscará el artículo que falta. Un solo artículo rara vez basta para explicar efecto, vía, autoridad y plazo.
7. Separa lo que la norma dice expresamente de lo que es interpretación (criterio judicial, consecuencia que depende de
   pruebas o de condiciones): las interpretaciones van en "interpretaciones" con su condición, nunca como regla general.
8. Si los textos no permiten responder la pregunta con seguridad, NO fuerces una respuesta: marca "suficiente": false.
   «Suficiente» se juzga solo contra la pregunta formulada y los elementos de cobertura del paso 6. Si un artículo la
   contesta literalmente, NO marques false porque falten temas que la pregunta no pide (sanciones, denuncia, plazos de
   prescripción): no los menciones en la pieza.

ERRORES QUE YA OCURRIERON EN ESTE PROYECTO (revisión humana y auditoría de oct-2026). No los repitas:
- Inventar una consecuencia: escribir que algo «constituye una violación», «es delito», «genera una multa», «es nulo» o «te
  pueden demandar» cuando el artículo no lo dice. Si el texto solo fija una obligación, la respuesta es la obligación, no su sanción.
- Responder otra figura: garantía no es cambio ni devolución; renuncia no es terminación por mutuo consentimiento; un cargo
  no reconocido no es un tema de nombramientos. Usa el mismo término de la pregunta y, si el texto habla de otra figura, dilo.
- Calificar más fuerte que la ley: no digas «ilegal», «absoluto», «siempre», «exclusivamente» o «en todos los casos» si el texto
  solo dice «no podrá», «se prohíbe» o «tiene derecho». Usa el verbo del propio artículo.
- Citar media regla: si una conclusión tiene dos partes (p. ej., «15 días de salario» y «la parte proporcional»), la cita debe
  contener ambas o hay que separarla en dos reglas, cada una con su cita.
- Afirmar cambios en la ley («se reformó», «ahora», «recientemente», «nueva regla»): están prohibidos; responde con el texto
  vigente, sin historia legislativa.
- Dejar una respuesta incompleta: si la pregunta es «¿qué pasa si…?», la persona necesita qué puede hacer, ante quién y en qué
  plazo; si algo de eso no está en los textos, márcalo "no_cubierto", no lo supongas.
- Referencias vagas («autoridad competente», «este límite», «revisa tu ley»): nombra la autoridad o la cifra del texto, o no lo digas.
- Convertir una presunción o un derecho en un hecho: «se presume inocente» no es «es inocente»; «tiene derecho a» no es «recibe».
- Cambiar quién tiene la obligación: si el texto obliga a los tribunales o a la autoridad (p. ej., resolver en plazo, servicio
  gratuito), no lo presentes como un requisito o condición que debe cumplir la persona.
Devuelve:
{{"suficiente": true,
  "pregunta": "{pregunta}",
  "concepto_central": "el concepto de la pregunta",
  "respuesta_corta": "Sí/No/Depende: … (una oración, ≤ 160 caracteres, con la condición principal)",
  "reglas": [{{"conclusion": "qué establece la norma para ESTA pregunta", "fuente": "F1", "cita_literal": "copia exacta",
              "condiciones": ["condición o requisito que limita la regla"], "excepciones": ["excepción que prevé el texto"]}}],
  "elementos": [{{"elemento": "uno de los pedidos en el punto 6: {nombres}", "estado": "cubierto | no_aplica | no_cubierto",
                 "respuesta": "en una oración, con las palabras que usará la pieza", "fuente": "F1", "cita_literal": "copia exacta", "motivo": "solo si no aplica"}}],
  "interpretaciones": [{{"afirmacion": "…", "condicion": "de qué depende", "base": "qué la apoya"}}],
  "distinciones": [{{"a": "concepto", "b": "concepto parecido", "diferencia": "en una oración"}}],  (solo conceptos presentes en los textos oficiales o en la lista de conceptos confundibles; si no hay, [])
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
  específico», «autoridad competente» o «instancia correspondiente» están prohibidos, también en listas y encabezados: usa el
  nombre que da el texto oficial, p. ej., «Centro de Conciliación», «Tribunal», «Profeco»). Las «interpretaciones» solo
  pueden aparecer con su condición («si se demuestra…»).
- Si usas dos conceptos de las distinciones, explica su diferencia.
- En una lista, el encabezado debe describir con exactitud lo que enumera: no llames «condiciones obligatorias» o
  «requisitos» a garantías u obligaciones que la ley impone a la autoridad.
- No califiques más fuerte que el análisis («ilegal», «absoluto», «siempre», «exclusivamente») ni agregues sanciones o
  consecuencias que el análisis no tiene; no hables de reformas ni de cambios recientes.
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


def _alinear_fuente_cita(escenas, fichas):
    """La línea «Fuente:» al pie de una escena de cita sale de su primera afirmación. Si el modelo asignó a la cita una
    afirmación de otro artículo, el pie contradice la etiqueta (R20261208-T102, 01-11: cita del art. 60 con pie «art. 61»).
    Se pone primero una afirmación del mismo artículo de la escena; si no hay, se intercambia con una de otra escena."""
    def art(a):
        fu = fichas.get(a["fuente"]) or {}
        return (fu.get("documento"), str(fu.get("articulo")))
    for e in escenas:
        src = e.pop("_src", None)
        if not src or not e["afirmaciones"] or art(e["afirmaciones"][0]) == src:
            continue
        propia = next((a for a in e["afirmaciones"] if art(a) == src), None)
        if propia:
            e["afirmaciones"].remove(propia); e["afirmaciones"].insert(0, propia); continue
        for otra in escenas:
            if otra is e or otra.get("tipo") == "cita":
                continue
            ajena = next((a for a in otra["afirmaciones"] if art(a) == src), None)
            if ajena:
                mia = e["afirmaciones"][0]
                i, j = otra["afirmaciones"].index(ajena), 0
                mia.pop("comparar_literal", None); ajena["comparar_literal"] = True
                otra["afirmaciones"][i], e["afirmaciones"][j] = mia, ajena
                break


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
            e["cita"] = cita if len(cita) <= 220 else cita[:214].rsplit(" ", 1)[0] + " …"   # en pantalla, fragmento literal; la voz dice la cita completa
            if not e.get("etiqueta") or etiqueta_generica(e["etiqueta"]):
                # el modelo copia el ejemplo del formato («Ley, artículo N») y la tarjeta no decía de qué ley era la cita
                # (R20270108-T133, 10-11: «LEY, ARTÍCULO 58» en lugar de la Ley Federal de Protección al Consumidor)
                e["etiqueta"] = f'{nombre_doc(f["documento"])}, artículo {f["articulo"]}'
            if not verificador.contiene(e.get("texto", ""), cita):
                # La voz dice la cita UNA vez. Si el modelo parafraseó en lugar de citar, la paráfrasis se cambia por una
                # entrada breve: antes se le pegaba la cita y se narraba dos veces (R20270113-T138, 09-11), lo que además
                # alargaba los Reels por encima de 620 caracteres (descartes por longitud del 8 y 9-11).
                entrada = e.get("texto", "").strip().rstrip(".:; ")
                if len(entrada) > 40: entrada = "La ley dice"
                e["texto"] = (entrada + ": «" + cita + "».").lstrip(": ")
            e["_src"] = (f["documento"], str(f["articulo"]))
        e["afirmaciones"] = [{"id": f"A{j + 1}", "tipo": a.get("tipo", "interpretacion"), "texto": a.get("texto", ""), "fuente": mapa[j],
                              **({"nota": a["duda"]} if a.get("duda") else {}), **({"comparar_literal": True} if e.get("tipo") == "cita" else {})}
                             for j, a in enumerate(afs) if a.get("escena") == i]
        escenas.append(e)
    _alinear_fuente_cita(escenas, fichas)
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


def copy_reel(g, mapa):
    """Texto de publicación del Reel SIN IA, solo con lo ya validado: la pregunta, la respuesta corta del análisis aprobado,
    las fuentes exactas y el aviso. Antes los Reels no tenían texto propio y se publicarían solo con el título."""
    fuentes = g.get("fuentes") or {}
    vistos = []
    for f in (fuentes.values() if isinstance(fuentes, dict) else fuentes):
        ref = f'{f.get("documento")}, artículo {f.get("articulo")}'
        if ref not in vistos: vistos.append(ref)
    partes = [g.get("pregunta_original") or g.get("titulo", ""), str(mapa.get("respuesta_corta", "")).strip(),
              "Fuente: " + "; ".join(vistos) + "." if vistos else "", "Esto es información general, no es asesoría legal."]
    return "\n\n".join(p for p in partes if p)


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
            pieza.update(cita=cita, etiqueta_cita=f'{nombre_doc(f["documento"])}, artículo {f["articulo"]}')
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
    for d, n in usados: por_doc.setdefault(nombre_doc(d), []).append(n)
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


SENALES = {   # ¿los textos oficiales contienen, al menos, el tipo de dato que exige cada elemento de la respuesta?
    "que_hacer": r"podr[aá]n? (solicitar|demandar|reclamar|exigir|pedir|optar|acudir)|tendr[aá]n? derecho|tiene derecho|tienen derecho|acci[oó]n|reclam|denunci|querell|queja",
    "ante_quien": r"tribunal|centros? (federal )?de conciliaci|autoridad conciliadora|procuradur|profeco|\bjuez|ministerio p[uú]blico|condusef|fiscal[ií]a|comisi[oó]n nacional",
    "via": r"solicitud|demanda|denuncia|querella|queja|tr[aá]mite|por escrito|presentar|promover|reclamaci[oó]n",
    "plazo": r"\b(\d{1,3}|un|una|dos|tres|cuatro|cinco|seis|siete|ocho|diez|quince|treinta|sesenta|noventa)\s+(d[ií]as|mes(es)?|a[nñ]os?|semanas?|horas)\b|prescrib",
}


def prechequeo(sol, fuentes):
    """Comprobación sin IA: ¿los artículos oficiales reunidos pueden, en principio, responder la pregunta? Devuelve los
    elementos para los que no hay ni una señal en los textos (p. ej., ninguna autoridad ni plazo en una pregunta de
    «¿qué pasa si…?»). Si falta algo, primero se buscan más fuentes; si sigue faltando, no se llama al redactor."""
    tipo, req = razonamiento.tipo_pregunta(pregunta_plan(sol), sol.get("tipo_pregunta"))
    texto = " ".join(f["texto_oficial"] for f in fuentes.values()).lower()
    return [k for k in req if k in SENALES and not re.search(SENALES[k], texto)]


def fuentes_sugeridas(sol, biblio, maximo=6):
    """Artículos del catálogo editorial («LFT arts. 33, 48, 518; CPEUM 17») obtenidos directo del texto oficial, sin IA.
    Si bastan, no hace falta gastar una llamada del investigador."""
    fuentes = {}
    for grupo in re.split(r"[;\n]", sol.get("fuentes_sugeridas") or ""):
        m = re.match(r"\s*([A-Za-zÁÉÍÓÚ]{2,10})\b\.?\s*(?:arts?\.?|artículos?)?\s*(.*)", grupo.strip())
        # 7-11-2026: las siglas con minúsculas («LMigra», «LAmp», «LAgra») nunca coincidían porque se comparaba
        # m.group(1).upper() con las claves originales de ORDEN; la fuente sugerida se perdía en silencio.
        sigla = {k.upper(): k for k in ORDEN}.get(m.group(1).upper()) if m else None
        if not sigla: continue
        for num in re.findall(r"\d{1,4}(?:o|°|º)?(?: (?:Bis|Ter|Quater))?(?:-[A-Z])?", m.group(2)):
            if len(fuentes) >= maximo: break
            try:
                texto = biblio.articulo(sigla, num)
            except Descartada:                     # documento no disponible: el investigador sigue siendo la vía de respaldo
                texto = None
            if not texto: continue
            fid = f"F{len(fuentes) + 1}"
            fuentes[fid] = {"sigla": sigla, "documento": ORDEN[sigla]["documento"], "articulo": num, "url": ORDEN[sigla]["url"],
                            "ambito": ORDEN[sigla]["ambito"], "texto_oficial": texto, "para_que": "sugerida por el catálogo editorial"}
    return fuentes


def pregunta_plan(sol):
    """La pregunta exacta que la pieza debe contestar. El lote piloto la fija («pregunta»); si no, la del catálogo."""
    return sol.get("pregunta") or sol.get("gancho") or sol.get("angulo") or sol["titulo"]


def analizar(sol, fuentes, red, glosario, simulador=None, extra=""):
    """Etapa 1: la regla, sus condiciones, excepciones y fuentes ANTES de escribir una sola línea de la pieza."""
    tipo, req = razonamiento.tipo_pregunta(pregunta_plan(sol), sol.get("tipo_pregunta"))
    nota = ""
    if sol.get("investigacion") and (RAIZ / sol["investigacion"]).exists():   # investigación editorial previa (p. ej., tras un rechazo humano)
        nota = ("\n\nNOTA DE INVESTIGACIÓN EDITORIAL (no es texto oficial: úsala para entender el problema y los errores a evitar; "
                "toda afirmación normativa debe salir de los textos oficiales de arriba, y lo que la nota marca como interpretación solo "
                "puede ir en «interpretaciones» con su condición):\n" + (RAIZ / sol["investigacion"]).read_text()[:5000])
    t0 = getattr(red, "temperatura", None)
    if t0 is not None: red.temperatura = min(t0, 0.15)     # el análisis jurídico no debe ser creativo; la redacción sí conserva su temperatura
    try:
        r = red.completar(REGLAS_COMUNES, ANALIZAR.format(pregunta=pregunta_plan(sol), titulo=sol["titulo"], textos=_textos(fuentes), glosario=glosario,
                                                           tipo=tipo, requeridos="; ".join(f"{k} ({razonamiento.ELEMENTOS[k]})" for k in req),
                                                           nombres=" | ".join(req)) + nota + extra, simulador)
    finally:
        if t0 is not None: red.temperatura = t0
    return r if isinstance(r, dict) else {}


def _citas_exactas(mapa, fuentes):
    """Corrección puntual SIN IA: si la cita de un elemento o regla no es literal pero el artículo contiene un fragmento
    casi idéntico (≥ 85 % de las palabras en el mismo orden), se sustituye por el texto oficial exacto. El contenido de la
    respuesta no cambia; si no hay un fragmento así, la cita queda como estaba y la revisión la bloquea."""
    from difflib import SequenceMatcher
    for x in [*(mapa.get("reglas") or []), *(mapa.get("elementos") or [])]:
        if not isinstance(x, dict) or x.get("fuente") not in fuentes or not x.get("cita_literal"): continue
        oficial = fuentes[x["fuente"]]["texto_oficial"]
        if verificador.contiene(oficial, x["cita_literal"]): continue
        pc = razonamiento.plano(x["cita_literal"]).split(); po = oficial.split(); n = len(pc)
        if n < 6: continue
        mejor, frag = 0.0, None
        for i in range(0, max(1, len(po) - n + 1)):
            for m in (n - 2, n - 1, n, n + 1, n + 2):
                cand = po[i:i + m]
                r = SequenceMatcher(None, pc, razonamiento.plano(" ".join(cand)).split()).ratio()
                if r > mejor: mejor, frag = r, " ".join(cand)
        if mejor >= 0.85 and frag:
            x["cita_literal_original"] = x["cita_literal"]; x["cita_literal"] = frag.strip(" ,;:")
    return mapa


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
              "pieza": {"bajada": mapa.get("respuesta_corta", "")}, "fuentes": {}, "_solo_analisis": True, "tipo_pregunta": sol.get("tipo_pregunta")}
    if not prueba["titulo"].endswith("?"): prueba["titulo"] += "?"
    textos = {(f["documento"], f["articulo"]): f["texto_oficial"] for f in fuentes.values()}
    err += [f'[{x["regla"]}] {x["detalle"]}' for x in razonamiento.bloqueantes(razonamiento.revisar(prueba, textos, ia=True))]
    # el análisis debe responder la MISMA pregunta del plan (la prueba de arriba usa la pregunta del plan como título)
    plan = pregunta_plan(sol)
    propio = " ".join([str(mapa.get("pregunta", "")), str(mapa.get("respuesta_corta", ""))] + [str(r.get("conclusion", "")) for r in reglas])
    if not razonamiento.tema_comun(plan, propio) and \
       not ({g for g, _ in razonamiento.conceptos_en(plan)} & {g for g, _ in razonamiento.conceptos_en(propio)}):
        err.append(f"[tema] El análisis no responde la pregunta del plan editorial («{plan[:80]}»): trata «{str(mapa.get('pregunta', ''))[:80]}».")
    return err


ANALISIS = RAIZ / "estado" / "analisis"


def _clave_analisis(sol, fuentes):
    """Un análisis validado se reutiliza solo para la MISMA pregunta, el mismo tipo y los mismos artículos oficiales
    (con el mismo texto): así un Reel y su imagen, o un reintento, no gastan otra llamada de IA en repetirlo."""
    import hashlib
    base = {"pregunta": pregunta_plan(sol), "tipo": sol.get("tipo_pregunta"),
            "fuentes": sorted((f["sigla"], str(f["articulo"]), hashlib.sha256(f["texto_oficial"].encode()).hexdigest()[:12]) for f in fuentes.values())}
    return hashlib.sha256(json.dumps(base, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def analisis_guardado(sol, fuentes):
    f = ANALISIS / f'{sol.get("tema_id", "T")}_{_clave_analisis(sol, fuentes)}.json'
    try: d = json.loads(f.read_text())
    except (OSError, ValueError): return None
    if d.get("objetado"): return None
    m = d.get("mapa")
    return m if isinstance(m, dict) and not validar_mapa(m, sol, fuentes) else None    # se vuelve a revisar (sin IA)


def guardar_analisis(sol, fuentes, mapa, objetado=False):
    try:
        ANALISIS.mkdir(parents=True, exist_ok=True)
        f = ANALISIS / f'{sol.get("tema_id", "T")}_{_clave_analisis(sol, fuentes)}.json'
        f.write_text(json.dumps({"tema_id": sol.get("tema_id"), "pregunta": pregunta_plan(sol), "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                 "objetado": objetado, "mapa": mapa}, ensure_ascii=False, indent=1))
    except OSError:
        pass


def _mapa_fijo(mapa, fuentes):
    """El análisis validado, con la referencia oficial de cada regla; es lo que viaja en el guion (el redactor no lo cambia)."""
    usadas = {r.get("fuente") for r in mapa.get("reglas", []) if isinstance(r, dict)}
    return {k: v for k, v in {**mapa, "reglas": [{**r, "ref": {k2: fuentes[r["fuente"]][k2] for k2 in ("documento", "articulo")}}
                                                  for r in mapa.get("reglas", []) if isinstance(r, dict) and r.get("fuente") in fuentes]}.items()
            if k not in ("fuentes_irrelevantes",)}, usadas


def _para_auditor(guion, fuentes):
    """El guion numera sus fichas por cita (F1…Fn) y el análisis numera los artículos (F1…Fm): son dos numeraciones
    distintas. Antes el auditor veía «F2» en una afirmación sin un texto «F2» y objetaba una fuente inexistente (piloto
    27-10: T031 y T015 se descartaron así). Ahora toda referencia se reescribe con la etiqueta del artículo."""
    etiqueta = lambda doc, art: f"{doc}, artículo {art}"
    textos = {etiqueta(f["documento"], f["articulo"]): f for f in fuentes.values()}
    fichas = guion.get("fuentes") or {}
    if isinstance(fichas, list): fichas = {f.get("id"): f for f in fichas}
    por_ficha = {fid: etiqueta(f.get("documento"), f.get("articulo")) for fid, f in fichas.items() if isinstance(f, dict)}
    por_fuente = {fid: etiqueta(f["documento"], f["articulo"]) for fid, f in fuentes.items()}
    g = copy.deepcopy({k: guion[k] for k in ("pregunta_original", "titulo", "razonamiento", "escenas", "pieza", "copy") if k in guion})
    for e in g.get("escenas") or []:
        for a in e.get("afirmaciones") or []:
            if a.get("fuente") in por_ficha: a["fuente"] = por_ficha[a["fuente"]]
    rz = g.get("razonamiento") or {}
    for x in [*(rz.get("reglas") or []), *(rz.get("elementos") or [])]:
        if isinstance(x, dict) and x.get("fuente") in por_fuente: x["fuente"] = por_fuente[x["fuente"]]
    pz = g.get("pieza") or {}
    if pz.get("fuente_cita") in por_ficha: pz["fuente_cita"] = por_ficha[pz["fuente_cita"]]
    texto = "\n\n".join(f'{et}:\n{f["texto_oficial"]}' for et, f in textos.items())
    return g, texto


def auditar_ia(guion, fuentes, auditor, simulador=None):
    g, textos = _para_auditor(guion, fuentes)
    pieza = json.dumps(g, ensure_ascii=False)[:12000]
    return auditor.completar(REGLAS_COMUNES, AUDITAR.format(textos=textos, pieza=pieza) +
                             "\n\nLas fuentes se identifican por documento y artículo; cada afirmación indica el artículo exacto que la sostiene.", simulador)


DONDE_RESPUESTA = {"reel": "en la escena «titular» que sigue al gancho, y otra vez en la conclusión",
                   "concepto": "en la bajada", "dato": "en la bajada", "tres_claves": "en la bajada", "diferencia": "en la bajada",
                   "mito_realidad": "en «realidad»"}


def _objeta_mapa(a, mapa):
    """¿El auditor declara no sostenida (total o parcialmente) una conclusión del análisis? Entonces el error está en la
    etapa 1 y se corrige el análisis, no solo la redacción. Se compara contra todo lo que el análisis afirma (reglas,
    respuesta corta, elementos e interpretaciones), porque la pieza viaja con el análisis y el redactor no puede cambiarlo
    (piloto 27-10: la objeción repetida a «es ilegal… exclusivamente por el Estado» no se corregía redactando)."""
    concl = [str(r.get("conclusion", "")) for r in mapa.get("reglas", []) if isinstance(r, dict)]
    concl += [str(mapa.get("respuesta_corta", ""))] + [str(e.get("respuesta", "")) for e in mapa.get("elementos", []) or [] if isinstance(e, dict)]
    concl += [json.dumps(x, ensure_ascii=False) if isinstance(x, dict) else str(x) for x in mapa.get("interpretaciones", []) or []]
    for x in a.get("conclusiones", []) or []:
        if str(x.get("sostenida", "si")).lower() != "si" and any(razonamiento._coincide(str(x.get("conclusion", "")), c) for c in concl):
            return True
    return False


REPARAR = """Tu borrador tiene SOLO estos problemas puntuales:
- {errores}
Corrige únicamente esos campos. No cambies el resto, no agregues afirmaciones jurídicas nuevas ni cambies citas literales
(excepción: si el problema dice que falta en la pieza algo del análisis aprobado, agrégalo con esas mismas palabras o las de su cita).
Devuelve: {{"cambios": [{{"escena": 3, "campo": "items", "valor": ["…"]}}, {{"campo": "titular", "valor": "…"}}]}}
("escena" es el índice en "escenas"; omítelo para campos de la pieza gráfica). Borrador:
{borrador}"""


def aplicar_parche(previo, parche):
    """Aplica los cambios del redactor solo a los campos de forma; nunca a citas, fuentes ni afirmaciones."""
    b = copy.deepcopy(previo)
    for c in (parche or {}).get("cambios", []) if isinstance(parche, dict) else []:
        campo = c.get("campo")
        if campo in (None, "cita_literal", "fuente", "afirmaciones", "razonamiento", "fuentes", "tipo"): continue
        if "escena" in c and isinstance(b.get("escenas"), list) and 0 <= int(c["escena"]) < len(b["escenas"]):
            b["escenas"][int(c["escena"])][campo] = c.get("valor")
        elif "escena" not in c:
            b[campo] = c.get("valor")
    return b


def _metricas(inv, red, aud, n_analisis, n_redaccion, complemento=False):
    ll = {r: getattr(m, "llamadas", 0) for r, m in (("investigador", inv), ("redactor", red), ("auditor", aud)) if m is not None}
    return {"llamadas_ia": ll, "llamadas_ia_total": sum(ll.values()), "intentos_analisis": n_analisis, "intentos_redaccion": n_redaccion,
            "investigacion_complementaria": bool(complemento)}


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
        # fuentes: primero las del catálogo (sin IA); el investigador solo si no bastan
        fuentes, descartes = fuentes_sugeridas(sol, biblio), []
        if not fuentes or prechequeo(sol, fuentes):
            prev = fuentes
            try:
                fuentes, descartes = investigar(sol, inv, biblio, simulador)
            except Descartada:
                if not prev: raise
                fuentes = {}
            for f in prev.values():                                   # conserva las del catálogo que no repitió el investigador
                if (f["sigla"], f["articulo"]) not in {(x["sigla"], x["articulo"]) for x in fuentes.values()} and len(fuentes) < 6:
                    fuentes[f"F{len(fuentes) + 1}"] = f
        faltan = prechequeo(sol, fuentes)
        if faltan:
            nuevas = investigar_complemento(sol, [f"{k} ({razonamiento.ELEMENTOS[k]})" for k in faltan], fuentes, inv, biblio, simulador)
            fuentes.update(nuevas); complemento_previo = True
            faltan = prechequeo(sol, fuentes)
        if faltan:
            raise Descartada("fuentes insuficientes (prechequeo sin redactar): los artículos oficiales reunidos no contienen "
                             + ", ".join(razonamiento.ELEMENTOS[k] for k in faltan) + "; "
                             + ", ".join(f'{f["sigla"]} {f["articulo"]}' for f in fuentes.values()),
                             categoria="juridico", metricas=_metricas(inv, red, aud, 0, 0))
        glosario = _glosario(sol, fuentes)
        historial, extra_a, reanalisis = [], "", 0
        complemento = locals().get("complemento_previo", False)
        n_analisis = n_redaccion = 0
        while True:
            # ---- etapa 1: análisis jurídico (dos oportunidades) ----
            mapa = analisis_guardado(sol, fuentes) if not reanalisis else None
            if mapa is not None:
                historial.append({"etapa": "analisis", "reutilizado": True, "errores": []})
            for intento in range(0 if mapa is not None else 2):
                n_analisis += 1
                m = _citas_exactas(analizar(sol, fuentes, red, glosario, simulador, extra_a), fuentes)
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
                raise Descartada("el análisis jurídico no superó la revisión contra el texto oficial: " + json.dumps(historial[-1], ensure_ascii=False)[:400], historial=historial,
                                 categoria="juridico", metricas=_metricas(inv, red, aud, n_analisis, n_redaccion, complemento))
            guardar_analisis(sol, fuentes, mapa)
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
            extra, volver, previo, errores_previos = "", False, None, []
            for intento in range(3):
                n_redaccion += 1
                if previo is not None and errores_previos and all(any(p in e for p in PUNTUALES) for e in errores_previos):
                    # problema puntual (longitud, línea de título, referencia vaga…): se corrige SOLO eso sobre el borrador anterior
                    parche = red.completar(REGLAS_COMUNES, REPARAR.format(borrador=json.dumps({k: v for k, v in previo.items() if k != "razonamiento"}, ensure_ascii=False)[:9000],
                                                                          errores="\n- ".join(errores_previos[:8])), simulador)
                    borrador = aplicar_parche(previo, parche)
                    historial.append({"etapa": "reparacion_puntual", "intento": intento, "errores": errores_previos})
                else:
                    borrador = pedir(extra)
                borrador = {**(borrador if isinstance(borrador, dict) else {}), "razonamiento": mapa}   # el redactor no puede alterar el análisis
                previo = copy.deepcopy(borrador)
                g = construir(sol, borrador, fuentes_red)
                g["razonamiento"] = mapa_fijo
                g["pregunta_original"] = pregunta_plan(sol)
                if sol.get("tipo_pregunta"): g["tipo_pregunta"] = sol["tipo_pregunta"]
                errores = esquema.validar(g)
                if sol["formato"] == "imagen" and not errores:
                    import imagen as _imagen
                    errores += _imagen.revision_previa(g)
                hall = razonamiento.revisar(g, {(f["documento"], f["articulo"]): f["texto_oficial"] for f in fuentes.values()}, ia=True)
                g["revision_razonamiento"] = hall
                errores += [f'[{x["regla"]}] {x["detalle"]}' for x in razonamiento.bloqueantes(hall)]
                errores_previos = errores
                if errores:
                    historial.append({"etapa": "redaccion", "intento": intento, "errores_esquema": errores,
                                      "visible": razonamiento.cuerpo_visible(g)[:700]})   # para diagnosticar sin repetir la llamada
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
                    if sol["formato"] == "reel" and not g.get("copy"): g["copy"] = copy_reel(g, mapa)
                    m_aud, m_red = str(getattr(aud, "ultimo_modelo", "")), str(getattr(red, "ultimo_modelo", ""))
                    fam = lambda m: m.split("-")[0].split("/")[-1].lower()
                    g["auditoria_ia"] = {"veredicto": "sin_objeciones", "modelo_auditor": m_aud or aud.modelos, "historial": historial,
                                         "familia_distinta": bool(m_aud and m_red and fam(m_aud) != fam(m_red))}
                    g["generacion"].update({"fuentes_descartadas": descartes, "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                            "solicitud": sol.get("archivo"), "metodo": "analisis_previo_v2_cobertura",
                                            "metricas": _metricas(inv, red, aud, n_analisis, n_redaccion, complemento),
                                            "modelos": {"investigador": getattr(inv, "ultimo_modelo", inv.modelos), "redactor": getattr(red, "ultimo_modelo", red.modelos)}})
                    return g
                if _objeta_mapa(a, mapa):
                    guardar_analisis(sol, fuentes, mapa, objetado=True)     # no se reutiliza un análisis objetado
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
                ult = historial[-1]
                raise Descartada("no superó la validación o la auditoría independiente tras dos correcciones: " +
                                 json.dumps(ult, ensure_ascii=False)[:400], historial=historial,
                                 categoria=categoria_de("", errores=ult.get("errores_esquema") or (["auditor"] if "auditoria_ia" in ult else [])),
                                 metricas=_metricas(inv, red, aud, n_analisis, n_redaccion, complemento))
    except (modelos.CuotaAgotada, modelos.FallaModelo) as e:
        raise Descartada(f"modelo no disponible: {e}", transitoria=True, categoria="cuota" if isinstance(e, modelos.CuotaAgotada) else "tecnico",
                         metricas=_metricas(*[x for x in (locals().get("inv"), locals().get("red"), locals().get("aud"))], locals().get("n_analisis", 0), locals().get("n_redaccion", 0)))
