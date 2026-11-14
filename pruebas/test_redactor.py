"""Pruebas de la generación editorial autónoma con modelos simulados (sin red, deterministas).
Lo que se prueba es el andamiaje que impide publicar algo que el texto oficial no sustente, no la calidad literaria."""
import copy, json, sys
from datetime import date
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sistema"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import redactor, esquema, verificador, auditoria, modelos, imagen
from fixtures import pdf_ley, LIT17

DOC = pdf_ley()
def transporte(url, timeout=60):
    if "CPEUM" in url: return 200, "application/pdf", DOC
    return 404, "text/html", b"no"
def caida(url, timeout=60): raise verificador.SinConexion("sin red simulada")

SOL = {"pieza_id": "G001", "tema_id": "T073", "formato": "reel", "carril": "A", "titulo": "¿Cárcel por deber dinero?",
       "gancho": "¿Te pueden meter a la cárcel por deber dinero?", "fuentes_sugeridas": "CPEUM art. 17"}
BORRADOR = {"titulo": "¿Te pueden meter a la cárcel por deber dinero?", "escenas": [
    {"tipo": "gancho", "texto": "¿Te pueden meter a la cárcel por deber dinero? Es una duda común.", "titulo": ["¿CÁRCEL", "POR DEUDAS?"]},
    {"tipo": "titular", "texto": "La respuesta está en el artículo diecisiete de la Constitución, que aplica en todo el país.", "titulo": ["LO DICE LA", "CONSTITUCIÓN"]},
    {"tipo": "cita", "texto": "El artículo diecisiete dice: nadie puede ser aprisionado por deudas de carácter puramente civil.", "fuente": "F1",
     "cita_literal": "Nadie puede ser aprisionado por deudas de carácter puramente civil", "etiqueta": "Constitución, artículo 17"},
    {"tipo": "lista", "texto": "Eso significa que una deuda civil, por sí sola, no te lleva a prisión, aunque sí pueden cobrarte por la vía legal.", "items": ["Pueden cobrarte", "Ante un juez", "Sin cárcel por la deuda"]},
    {"tipo": "titular", "texto": "Si alguien te amenaza con la cárcel por una deuda civil, esa amenaza no tiene sustento en la Constitución.", "titulo": ["SIN CÁRCEL", "POR DEUDAS"]}],
  "afirmaciones": [{"escena": 2, "fuente": "F1", "tipo": "hecho_normativo", "texto": "No hay prisión por deudas civiles.",
                    "cita_literal": "Nadie puede ser aprisionado por deudas de carácter puramente civil", "duda": None}],
  "razonamiento": {"pregunta": "¿Te pueden meter a la cárcel por deber dinero?",
                   "respuesta_corta": "No, una deuda civil por sí sola no te lleva a prisión, aunque sí pueden cobrarte por la vía legal.",
                   "reglas": [{"conclusion": "No hay prisión por deudas de carácter puramente civil.", "fuente": "F1",
                               "cita_literal": "Nadie puede ser aprisionado por deudas de carácter puramente civil", "condiciones": [], "excepciones": []}],
                   "elementos": [{"elemento": "efecto", "estado": "cubierto", "respuesta": "Una deuda civil, por sí sola, no te lleva a prisión.",
                                  "fuente": "F1", "cita_literal": "Nadie puede ser aprisionado por deudas de carácter puramente civil"}],
                   "distinciones": [], "limites": "No aborda delitos como el fraude."}}


ANALISIS = {"suficiente": True, **copy.deepcopy(BORRADOR["razonamiento"])}


def simulador_con(investigar=None, redactar=None, auditar=None, analizar=None):
    """Simula los tres roles. La etapa 1 (análisis jurídico) la hace el rol redactor; se cuenta aparte en «analista»."""
    llamadas = {"investigador": [], "redactor": [], "auditor": [], "analista": []}
    def sim(rol, sistema, usuario):
        if rol == "redactor" and "ETAPA 1 DE 2" in usuario:
            llamadas["analista"].append(usuario)
            r = analizar(len(llamadas["analista"])) if callable(analizar) else (analizar or ANALISIS)
            return copy.deepcopy(r)
        llamadas[rol].append(usuario)
        if rol == "investigador":
            if callable(investigar): return investigar(len(llamadas["investigador"]))
            return investigar or {"articulos": [{"sigla": "CPEUM", "articulo": "17"}, {"sigla": "CPEUM", "articulo": "999"}, {"sigla": "XYZ", "articulo": "1"}]}
        if rol == "redactor":
            r = redactar(len(llamadas["redactor"])) if callable(redactar) else (redactar or BORRADOR)
            return copy.deepcopy(r)
        return auditar(len(llamadas["auditor"])) if callable(auditar) else (auditar or {"veredicto": "sin_objeciones", "objeciones": []})
    sim.llamadas = llamadas
    return sim


@pytest.fixture
def uso(tmp_path): return tmp_path / "uso.jsonl"


def test_genera_un_reel_valido_y_verificable(uso):
    sim = simulador_con()
    g = redactor.generar({**SOL, "fuentes_sugeridas": ""}, transporte, sim, env={}, archivo_uso=uso)
    assert esquema.validar(g) == []
    assert g["generacion"]["metricas"]["llamadas_ia_total"] == 4 and g["generacion"]["metricas"]["intentos_redaccion"] == 1
    assert any("999" in d for d in g["generacion"]["fuentes_descartadas"]) and any("XYZ" in d for d in g["generacion"]["fuentes_descartadas"])
    v = verificador.verificar_guion(g, transporte)
    assert v["decision"] in ("APTA", "APTA_CON_CRITERIO"), v
    assert auditoria.dictamen(g, v, date.today())["decision"] in ("APTO", "APTO_CON_CRITERIO")
    assert g["escenas"][-1]["tipo"] == "cierre" and "no asesoría legal" in g["escenas"][-1]["texto"]
    assert len(uso.read_text().splitlines()) == 4      # investigador + análisis + redactor + auditor


def test_cita_inventada_se_elimina_y_si_no_queda_ninguna_se_descarta(uso):
    falso = copy.deepcopy(BORRADOR)
    for a in falso["afirmaciones"]: a["cita_literal"] = "Nadie puede ser aprisionado por deudas de ninguna clase jamás"
    falso["escenas"][2]["cita_literal"] = "Nadie puede ser aprisionado por deudas de ninguna clase jamás"
    with pytest.raises(redactor.Descartada) as e:
        redactor.generar(SOL, transporte, simulador_con(redactar=falso), env={}, archivo_uso=uso)
    assert "anclada" in str(e.value) and not e.value.transitoria


def test_cita_en_pantalla_sin_ancla_no_se_muestra(uso):
    b = copy.deepcopy(BORRADOR); b["escenas"][2]["cita_literal"] = "Texto que no está en la Constitución de ninguna manera posible"
    g = redactor.generar(SOL, transporte, simulador_con(redactar=b), env={}, archivo_uso=uso)
    assert all(e["tipo"] != "cita" for e in g["escenas"])


def test_objecion_del_auditor_se_corrige_una_vez(uso):
    sim = simulador_con(auditar=lambda n: {"veredicto": "con_objeciones", "objeciones": [{"problema": "falta matiz"}]} if n == 1 else {"veredicto": "sin_objeciones"})
    g = redactor.generar(SOL, transporte, sim, env={}, archivo_uso=uso)
    assert len(sim.llamadas["redactor"]) == 2 and "falta matiz" in sim.llamadas["redactor"][1]
    assert g["auditoria_ia"]["veredicto"] == "sin_objeciones"


def test_objeciones_persistentes_descartan_el_tema(uso):
    sim = simulador_con(auditar={"veredicto": "con_objeciones", "objeciones": [{"problema": "afirmación no sustentada"}]})
    with pytest.raises(redactor.Descartada) as e:
        redactor.generar(SOL, transporte, sim, env={}, archivo_uso=uso)
    assert "auditoría" in str(e.value)


def test_borrador_incompleto_se_repara_con_los_errores(uso):
    malo = copy.deepcopy(BORRADOR); malo["escenas"][0].pop("titulo")
    sim = simulador_con(redactar=lambda n: malo if n == 1 else BORRADOR)
    g = redactor.generar(SOL, transporte, sim, env={}, archivo_uso=uso)
    assert "titulo" in sim.llamadas["redactor"][1] and esquema.validar(g) == []


def test_sin_red_es_descarte_transitorio(uso):
    with pytest.raises(redactor.Descartada) as e:
        redactor.generar(SOL, caida, simulador_con(), env={}, archivo_uso=uso)
    assert e.value.transitoria


def test_solo_articulos_inexistentes_descarta(uso):
    with pytest.raises(redactor.Descartada) as e:
        redactor.generar({**SOL, "fuentes_sugeridas": ""}, transporte, simulador_con(investigar={"articulos": [{"sigla": "CPEUM", "articulo": "999"}]}), env={}, archivo_uso=uso)
    assert "ninguna fuente" in str(e.value)


def test_carril_c_no_se_automatiza(uso):
    with pytest.raises(redactor.Descartada):
        redactor.generar({**SOL, "carril": "C"}, transporte, simulador_con(), env={}, archivo_uso=uso)


def test_cuota_agotada_es_transitoria_y_queda_registrada(uso, monkeypatch):
    cfg = modelos.config(); cfg["roles"]["redactor"]["tope_diario"] = 0
    monkeypatch.setattr(modelos, "config", lambda: cfg)
    with pytest.raises(redactor.Descartada) as e:
        redactor.generar(SOL, transporte, simulador_con(), env={}, archivo_uso=uso)
    assert e.value.transitoria


def test_frase_de_asesoria_colada_por_el_modelo_se_retiene(uso):
    b = copy.deepcopy(BORRADOR); b["escenas"][3]["texto"] += " En tu caso, te garantizo que no pasa nada."
    g = redactor.generar(SOL, transporte, simulador_con(redactar=b), env={}, archivo_uso=uso)
    d = auditoria.dictamen(g, verificador.verificar_guion(g, transporte), date.today())
    assert d["decision"] == "RETENIDO"


def test_riesgo_medio_requiere_auditoria_ia_sin_objeciones(uso):
    b = copy.deepcopy(BORRADOR); b["afirmaciones"][0]["tipo"] = "interpretacion"
    g = redactor.generar({**SOL, "carril": "B"}, transporte, simulador_con(redactar=b), env={}, archivo_uso=uso)
    assert verificador.verificar_guion(g, transporte)["decision"] == "APTA_CON_CRITERIO"
    g.pop("auditoria_ia")
    assert verificador.verificar_guion(g, transporte)["decision"] == "REVISION_HUMANA"


def test_genera_imagen_valida_que_pasa_la_auditoria_grafica(uso, tmp_path):
    sol = {**SOL, "pieza_id": "G002", "formato": "imagen", "plantilla": "concepto", "angulo": "concepto clave"}
    b = {"titular": "¿Te pueden encarcelar por una deuda?", "bajada": "La Constitución prohíbe la prisión por deudas de carácter puramente civil.",
         "cita_literal_destacada": "Nadie puede ser aprisionado por deudas de carácter puramente civil", "fuente_cita": "F1",
         "ojo": "Cobrar una deuda por la vía legal sí es válido.", "copy": "Una deuda civil no te lleva a la cárcel.\n\nLo dice el artículo 17 de la Constitución.\n\nGuárdalo y compártelo.",
         "razonamiento": {"pregunta": "¿Te pueden encarcelar por una deuda?", "respuesta_corta": "No, la Constitución prohíbe la prisión por deudas de carácter puramente civil.", "reglas": [{"conclusion": "No hay prisión por deudas de carácter puramente civil.", "fuente": "F1", "cita_literal": "Nadie puede ser aprisionado por deudas de carácter puramente civil", "condiciones": [], "excepciones": []}], "distinciones": [{"a": "deuda civil", "b": "fraude", "diferencia": "El fraude es un delito; no pagar no lo es."}], "limites": ""}, "alt": "Pieza sobre prisión por deudas", "afirmaciones": [{"fuente": "F1", "tipo": "hecho_normativo", "texto": "No hay cárcel por deudas civiles",
                                                                 "cita_literal": "Nadie puede ser aprisionado por deudas de carácter puramente civil"}]}
    g = redactor.generar(sol, transporte, simulador_con(redactar=b), env={}, archivo_uso=uso)
    assert esquema.validar(g) == [] and "no es asesoría legal" in g["copy"]
    png = tmp_path / "g.png"; textos, y = imagen.dibujar(g, png)
    assert all(r["resultado"] == "APROBADO" for r in imagen.auditar(png, textos, y)[0])


def test_cierre_agrega_leyenda_estatal_si_cita_codigo_penal():
    c = redactor._cierre({"F1": {"sigla": "CPF"}})
    assert "según tu estado" in c["texto"]
    assert "según tu estado" not in redactor._cierre({"F1": {"sigla": "CPEUM"}})["texto"]


def test_afirmacion_sin_texto_se_elimina(uso):
    b = copy.deepcopy(BORRADOR)
    for a in b["afirmaciones"]: a["texto"] = ""
    with pytest.raises(redactor.Descartada):
        redactor.generar(SOL, transporte, simulador_con(redactar=b), env={}, archivo_uso=uso)


def test_duda_declarada_en_un_hecho_normativo_retiene(uso):
    b = copy.deepcopy(BORRADOR); b["afirmaciones"][0]["duda"] = "La norma no aclara si aplica a este supuesto."
    g = redactor.generar(SOL, transporte, simulador_con(redactar=b), env={}, archivo_uso=uso)
    assert verificador.verificar_guion(g, transporte)["decision"] == "RETENER"


def test_fuentes_del_catalogo_ahorran_la_llamada_del_investigador(uso):
    sim = simulador_con()
    g = redactor.generar(SOL, transporte, sim, env={}, archivo_uso=uso)
    assert sim.llamadas["investigador"] == [] and g["generacion"]["metricas"]["llamadas_ia"]["investigador"] == 0


def test_cuota_agotada_se_clasifica_como_cuota(uso, monkeypatch):
    cfg = modelos.config(); cfg["roles"]["redactor"]["tope_diario"] = 0
    monkeypatch.setattr(modelos, "config", lambda: cfg)
    with pytest.raises(redactor.Descartada) as e:
        redactor.generar(SOL, transporte, simulador_con(), env={}, archivo_uso=uso)
    assert e.value.categoria == "cuota"


def test_problema_puntual_se_repara_sin_regenerar(uso):
    largo = copy.deepcopy(BORRADOR); largo["escenas"][3]["items"] = ["Pueden cobrarte por la vía legal ante un juez civil", "Ante un juez", "Sin cárcel por la deuda"]
    pedidos = []
    def red(n):
        pedidos.append(n)
        return largo if n == 1 else {"cambios": [{"escena": 3, "campo": "items", "valor": ["Pueden cobrarte", "Ante un juez", "Sin cárcel por la deuda"]}]}
    sim = simulador_con(redactar=red)
    g = redactor.generar(SOL, transporte, sim, env={}, archivo_uso=uso)
    assert any("REPARAR" in u or "SOLO estos problemas puntuales" in u for u in sim.llamadas["redactor"])
    assert g["escenas"][3]["items"][0] == "Pueden cobrarte" and g["escenas"][2]["cita"].startswith("Nadie puede ser aprisionado")


def test_el_parche_no_puede_tocar_citas_ni_afirmaciones():
    previo = copy.deepcopy(BORRADOR)
    b = redactor.aplicar_parche(previo, {"cambios": [{"escena": 2, "campo": "cita_literal", "valor": "otra cosa"},
                                                     {"campo": "afirmaciones", "valor": []}]})
    assert b == previo


def test_prechequeo_sin_autoridad_ni_plazo_no_llama_al_redactor(uso):
    sol = {**SOL, "gancho": "¿Qué pasa si te obligan a firmar tu renuncia?", "fuentes_sugeridas": "CPEUM art. 17"}
    sim = simulador_con(investigar={"articulos": [{"sigla": "CPEUM", "articulo": "17"}]})
    with pytest.raises(redactor.Descartada) as e:
        redactor.generar(sol, transporte, sim, env={}, archivo_uso=uso)
    assert "prechequeo" in str(e.value) and sim.llamadas["redactor"] == [] and sim.llamadas["analista"] == []
    assert e.value.categoria == "juridico"


def test_linea_de_titulo_larga_dice_el_maximo_y_el_pedido_lo_anuncia():
    # regresión 02-11-2026: R20261213-T107 se descartó por «SIN ORDEN DE UN JUEZ?» (21 caracteres);
    # el pedido decía «LÍNEAS CORTAS» sin número y el error no daba el máximo
    g = copy.deepcopy(BORRADOR)
    g["escenas"][0]["titulo"] = ["¿POLICÍA EN TU CASA", "SIN ORDEN DE UN JUEZ?"]
    errs = [e for e in esquema.validar(g) if "línea de título" in e]
    assert errs and "21 caracteres; máximo 20" in errs[0]
    assert any(p in errs[0] for p in redactor.PUNTUALES)
    assert "máx. 20 caracteres" in redactor.PEDIR_REEL


def test_el_pedido_no_invita_a_inventar_distinciones_ajenas_al_texto():
    # regresión 02-11-2026: I20261213-T107 (LFT 33) se descartó dos veces porque el modelo llenó «distinciones» con
    # renuncia vs. mutuo consentimiento, conceptos que el art. 33 no trae; el campo debe poder quedar vacío
    for p in (redactor.PEDIR_REEL, redactor.PEDIR_IMAGEN):
        assert "si no hay, []" in p


def test_fuentes_sugeridas_respeta_siglas_con_minusculas():
    """7-11-2026: «LMigra art. 9» no se reconocía (se buscaba «LMIGRA» en ORDEN) y la solicitud quedaba sin fuente sugerida."""
    class Biblio:
        def articulo(self, sigla, num): return f"texto de {sigla} {num}"
    f = redactor.fuentes_sugeridas({"fuentes_sugeridas": "LMigra art. 9; LGDNNA art. 45; cpeum art. 17"}, Biblio())
    assert [(x["sigla"], x["articulo"]) for x in f.values()] == [("LMigra", "9"), ("LGDNNA", "45"), ("CPEUM", "17")]
    assert f["F1"]["documento"] == "Ley de Migración"


def test_nombre_de_ley_con_coma_no_se_corta():
    # Regresión 09-11-2026: I20270115-T140 mostraba «Ley General de los Derechos de Niñas, art. 77».
    ley = "Ley General de los Derechos de Niñas, Niños y Adolescentes"
    assert redactor.nombre_doc(ley) == ley
    assert redactor.nombre_doc("Ley Federal del Trabajo, artículo 80") == "Ley Federal del Trabajo"
    assert redactor.nombre_doc("Código Penal Federal, arts. 1 y 2") == "Código Penal Federal"
    lit = "Se considerará violación a la intimidad de niñas, niños o adolescentes"
    fuentes = {"F1": {"sigla": "LGDNNA", "documento": ley, "articulo": "77", "url": "https://www.diputados.gob.mx/LeyesBiblio/pdf/LGDNNA.pdf",
                      "ambito": "general", "texto_oficial": lit + " cualquier manejo directo de su imagen"}}
    sol = {"pieza_id": "I1", "tema_id": "T1", "plantilla": "dato", "carril": "A"}
    borr = {"titular": "t", "bajada": "b", "fuente_cita": "F1", "cita_literal_destacada": lit,
            "afirmaciones": [{"tipo": "hecho_normativo", "texto": "Es violación a la intimidad.", "fuente": "F1", "cita_literal": lit}]}
    g = redactor.construir_imagen(sol, borr, fuentes)
    assert g["pieza"]["fuente_visible"] == f"{ley}, art. 77"
    assert g["pieza"]["etiqueta_cita"] == f"{ley}, artículo 77"


def test_cita_parafraseada_se_narra_una_sola_vez(uso):
    # Regresión 09-11-2026 (R20270113-T138): la voz decía la paráfrasis y después la cita completa.
    b = copy.deepcopy(BORRADOR)
    b["escenas"][2]["texto"] = "La Constitución prohíbe que te encarcelen por una deuda civil, sin importar el monto que debas."
    g = redactor.generar({**SOL, "fuentes_sugeridas": ""}, transporte, simulador_con(redactar=b), env={}, archivo_uso=uso)
    cita = next(e for e in g["escenas"] if e["tipo"] == "cita")
    assert cita["texto"] == "La ley dice: «Nadie puede ser aprisionado por deudas de carácter puramente civil»."
    b["escenas"][2]["texto"] = "Dice la Constitución:"
    g = redactor.generar({**SOL, "fuentes_sugeridas": ""}, transporte, simulador_con(redactar=b), env={}, archivo_uso=uso)
    assert next(e for e in g["escenas"] if e["tipo"] == "cita")["texto"].startswith("Dice la Constitución: «Nadie puede")


def test_etiqueta_generica_de_la_cita_se_reemplaza(uso):
    # Regresión 10-11-2026 (R20270108-T133): el modelo copió el ejemplo «Ley, artículo N» y la tarjeta decía «LEY, ARTÍCULO 58».
    assert redactor.etiqueta_generica("Ley, artículo 58") and redactor.etiqueta_generica("Código, art. 3")
    assert not redactor.etiqueta_generica("Ley Federal del Trabajo, artículo 60")
    assert not redactor.etiqueta_generica("Constitución, artículo 8")
    b = copy.deepcopy(BORRADOR)
    b["escenas"][2]["etiqueta"] = "Ley, artículo 17"
    g = redactor.generar({**SOL, "fuentes_sugeridas": ""}, transporte, simulador_con(redactar=b), env={}, archivo_uso=uso)
    et = next(e for e in g["escenas"] if e["tipo"] == "cita")["etiqueta"]
    assert not redactor.etiqueta_generica(et) and et.endswith(", artículo 17")


def test_el_angulo_de_la_solicitud_llega_al_redactor_de_reels(uso):
    """14-11: las instrucciones de alcance, cita única y extensión de una solicitud reabierta no llegaban al Reel."""
    sim = simulador_con()
    redactor.generar({**SOL, "fuentes_sugeridas": "", "angulo": "Cita literal ÚNICA; narración de 430 caracteres o menos."}, transporte, sim, env={}, archivo_uso=uso)
    assert "narración de 430 caracteres o menos" in sim.llamadas["redactor"][0]
    sim2 = simulador_con()
    redactor.generar({**SOL, "fuentes_sugeridas": ""}, transporte, sim2, env={}, archivo_uso=uso)
    assert "sin indicaciones adicionales" in sim2.llamadas["redactor"][0]


def test_objecion_a_una_distincion_del_analisis_obliga_a_rehacerlo():
    """14-11: el auditor objetó dos veces una distinción del análisis congelado («garantía / devolución») que el redactor
    no podía quitar; ahora cuenta como objeción al análisis y se rehace."""
    mapa = {**copy.deepcopy(ANALISIS), "distinciones": [{"a": "garantía", "b": "devolución dinero", "diferencia": "…"}]}
    a = {"veredicto": "con_objeciones", "conclusiones": [{"conclusion": "otra cosa", "sostenida": "si"}],
         "objeciones": [{"donde": "razonamiento.distinciones", "problema": "distinción ajena al texto", "correccion": "elimínala"}]}
    assert redactor._objeta_mapa(a, mapa)
    assert not redactor._objeta_mapa(a, {**mapa, "distinciones": []})
    assert not redactor._objeta_mapa({**a, "objeciones": [{"donde": "escena 3", "problema": "texto largo"}]}, mapa)
