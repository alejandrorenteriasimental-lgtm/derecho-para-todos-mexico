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
import esquema, modelos, verificador

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
        return verificador.articulo_texto(cuerpo, numero, max_car=2200)


# ---------------- instrucciones a los modelos ----------------
REGLAS_COMUNES = """Eres parte del equipo editorial de «Aquí Dice la Ley», un medio de divulgación jurídica para público
general en México. Escribes en español de México, claro, cercano y exacto. Reglas que no se negocian:
- Usa SOLO los textos oficiales que se te entregan. No agregues artículos, tesis, cifras, fechas, casos ni personas que no estén ahí.
- Cada afirmación jurídica lleva "cita_literal": un fragmento COPIADO EXACTAMENTE del texto oficial (8 a 40 palabras).
- Distingue lo que dice la norma ("hecho_normativo") de tu explicación ("interpretacion"). Si existe una duda real sobre el alcance, escríbela en "duda".
- Nada de asesoría personalizada: prohibido "en tu caso", "te garantizo", "contáctanos", "asesoría gratuita".
- No llames culpable, asesino o delincuente a nadie. No menciones personas reales.
- No uses lenguaje absoluto ("siempre", "nunca", "en todos los casos") salvo que el texto oficial lo diga.
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
Gancho sugerido: {gancho}
Textos oficiales disponibles (fuente → texto):
{textos}

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

AUDITAR = """Eres auditor jurídico independiente. Revisa la pieza contra los textos oficiales y responde con rigor.
Textos oficiales:
{textos}

Pieza:
{pieza}

Revisa también la COHERENCIA: el titular, el mito, la realidad, el gancho y la conclusión deben hablar de la misma figura jurídica
que regulan los textos citados (p. ej., no titular sobre la renuncia y responder con el «mutuo consentimiento», que es otra causa).
Señala SOLO problemas reales: afirmaciones que el texto oficial no sustenta, cifras o plazos distintos, excepciones omitidas que
cambian el sentido, lenguaje absoluto, frases que parezcan asesoría personalizada, o confusión entre jurisdicción federal y estatal.
Devuelve: {{"veredicto": "sin_objeciones" | "con_objeciones", "objeciones": [{{"donde": "...", "problema": "...", "correccion": "..."}}]}}"""


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
        if sigla not in ORDEN or not re.fullmatch(r"\d{1,4}(?:o|°|º)?(?: (?:Bis|Ter|Quater))?", num, re.I):
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
            "tema_id": sol["tema_id"], "fuentes": fichas, "escenas": escenas,
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
            "generacion": {"afirmaciones_eliminadas_sin_ancla": quitadas}}


def auditar_ia(guion, fuentes, auditor, simulador=None):
    pieza = json.dumps({k: guion[k] for k in ("titulo", "escenas", "pieza", "copy") if k in guion}, ensure_ascii=False)[:9000]
    return auditor.completar(REGLAS_COMUNES, AUDITAR.format(textos=_textos(fuentes), pieza=pieza), simulador)


def generar(sol, transporte=verificador.transporte_http, simulador=None, env=None, archivo_uso=None):
    """Devuelve el guion listo para la cola, o lanza Descartada con el motivo."""
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
        textos = _textos(fuentes)
        if sol["formato"] == "reel":
            pedir = lambda extra="": red.completar(REGLAS_COMUNES, PEDIR_REEL.format(titulo=sol["titulo"], gancho=sol.get("gancho", ""), textos=textos) + extra, simulador)
            construir = construir_reel
        else:
            pl = sol.get("plantilla", "concepto")
            pedir = lambda extra="": red.completar(REGLAS_COMUNES, PEDIR_IMAGEN.format(titulo=sol["titulo"], angulo=sol.get("angulo", ""), plantilla=pl,
                                                                                    campos=CAMPOS_PLANTILLA[pl], textos=textos) + extra, simulador)
            construir = construir_imagen
        historial = []
        extra = ""
        for intento in range(3):                                     # borrador + dos correcciones como máximo
            g = construir(sol, pedir(extra), fuentes)
            errores = esquema.validar(g)
            if errores:
                historial.append({"intento": intento, "errores_esquema": errores})
                extra = "\n\nTu versión anterior tenía estos problemas; corrígelos:\n- " + "\n- ".join(errores[:8]); continue
            a = auditar_ia(g, fuentes, aud, simulador)
            historial.append({"intento": intento, "auditoria_ia": a})
            if a.get("veredicto") == "sin_objeciones":
                m_aud, m_red = str(getattr(aud, "ultimo_modelo", "")), str(getattr(red, "ultimo_modelo", ""))
                fam = lambda m: m.split("-")[0].split("/")[-1].lower()
                g["auditoria_ia"] = {"veredicto": "sin_objeciones", "modelo_auditor": m_aud or aud.modelos, "historial": historial,
                                     "familia_distinta": bool(m_aud and m_red and fam(m_aud) != fam(m_red))}
                g["generacion"].update({"fuentes_descartadas": descartes, "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                        "solicitud": sol.get("archivo"), "modelos": {"investigador": getattr(inv, "ultimo_modelo", inv.modelos), "redactor": getattr(red, "ultimo_modelo", red.modelos)}})
                return g
            extra = "\n\nUn auditor independiente objetó lo siguiente; corrige sin agregar información nueva:\n" + \
                    json.dumps(a.get("objeciones", []), ensure_ascii=False)[:2500]
        raise Descartada("no superó la validación o la auditoría independiente tras dos correcciones: " +
                         json.dumps(historial[-1], ensure_ascii=False)[:400])
    except (modelos.CuotaAgotada, modelos.FallaModelo) as e:
        raise Descartada(f"modelo no disponible: {e}", transitoria=True)
