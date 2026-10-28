"""Lote piloto y plantillas por tipo de pregunta (instrucción del responsable, 27-10-2026): pocas piezas, pregunta y tipo
fijados por el plan, y nada fuera del lote mientras se mide; análisis validados reutilizables; modelos caídos no se
vuelven a llamar en el mismo ciclo."""
import json, sys
from pathlib import Path
import pytest

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / "sistema")); sys.path.insert(0, str(AQUI))
import ciclo, modelos, planificador, razonamiento, redactor
from test_ciclo import raiz, raiz_vacia   # noqa: F401 (fixtures)

LOTE_REAL = json.loads((AQUI.parent / "data" / "lote_piloto.json").read_text())


# ---------- tipos de pregunta ----------
@pytest.mark.parametrize("pregunta,tipo", [
    ("¿Te pueden volver a juzgar por el mismo delito?", "derecho"),
    ("¿Cuándo y cuánto te deben pagar de aguinaldo?", "obligacion"),
    ("¿Cuántos días de vacaciones te corresponden?", "obligacion"),
    ("¿Cómo se denuncia una extorsión?", "procedimiento"),
    ("¿Siempre tienes que pagar una multa de tránsito?", "excepcion"),
    ("¿Qué pasa si te obligan a firmar tu renuncia?", "consecuencia"),
    ("¿Es legal «no hay cambios ni devoluciones»?", "legalidad"),
    ("¿Qué significa la presunción de inocencia?", "definicion"),
])
def test_deteccion_de_tipo(pregunta, tipo):
    assert razonamiento.tipo_pregunta(pregunta)[0] == tipo


def test_tipo_fijado_por_el_plan_tiene_prioridad():
    assert razonamiento.tipo_pregunta("¿Te pueden meter a la cárcel por deber dinero?", "legalidad") == ("legalidad", ("efecto",))
    assert razonamiento.tipo_pregunta("¿Qué es X?", "inventado")[0] == "definicion"      # un tipo desconocido no se acepta


def test_pregunta_de_derecho_exige_condiciones_y_excepciones():
    g = {"pregunta_original": "¿Te pueden volver a juzgar por el mismo delito?", "_solo_analisis": True,
         "razonamiento": {"elementos": [{"elemento": "contenido", "estado": "cubierto", "fuente": "F1", "respuesta": "no",
                                          "cita_literal": "Nadie puede ser juzgado dos veces por el mismo delito"}],
                          "reglas": [{"fuente": "F1", "ref": {"documento": "CPEUM", "articulo": "23"}}]}}
    textos = {("CPEUM", "23"): "Nadie puede ser juzgado dos veces por el mismo delito, ya sea que en el juicio se le absuelva o se le condene."}
    faltan = {h["detalle"].split("«")[-1].rstrip("»).") for h in razonamiento.revisar_cobertura(g, textos)}
    assert faltan == {"condiciones", "excepcion"}
    g["razonamiento"]["elementos"] += [{"elemento": "condiciones", "estado": "no_aplica", "motivo": "el artículo no pone requisitos adicionales"},
                                       {"elemento": "excepcion", "estado": "no_aplica", "motivo": "el texto no prevé ninguna excepción"}]
    assert razonamiento.revisar_cobertura(g, textos) == []


def test_pregunta_plan_usa_la_pregunta_fijada():
    assert redactor.pregunta_plan({"titulo": "t", "gancho": "g", "pregunta": "¿p?"}) == "¿p?"
    assert redactor.pregunta_plan({"titulo": "t", "gancho": "g"}) == "g"


# ---------- lote piloto ----------
def test_lote_real_respeta_el_tope_y_fija_pregunta_tipo_y_fuentes():
    assert LOTE_REAL["max_por_formato"] <= 4
    for t in LOTE_REAL["temas"]:
        assert t["pregunta"].startswith("¿") and t["tipo_pregunta"] in razonamiento.TIPOS_VALIDOS and t["fuentes_sugeridas"]
        assert razonamiento.tipo_pregunta(t["pregunta"], t["tipo_pregunta"])[0] == t["tipo_pregunta"]


def test_planificar_con_lote_no_crea_temas_del_catalogo(tmp_path, monkeypatch):
    lote = {**LOTE_REAL, "temas": LOTE_REAL["temas"] + [{**LOTE_REAL["temas"][0], "tema_id": "T999"}]}   # uno de más
    (tmp_path / "lote.json").write_text(json.dumps(lote, ensure_ascii=False))
    monkeypatch.setattr(planificador, "LOTE", tmp_path / "lote.json")
    monkeypatch.setattr(planificador, "SOLICITUDES", tmp_path / "sol")
    monkeypatch.setattr(planificador, "RAIZ", tmp_path)
    plan = planificador.planificar()
    n = LOTE_REAL["max_por_formato"]
    assert len([s for s in plan if s["formato"] == "reel"]) == n and len([s for s in plan if s["formato"] == "imagen"]) == n
    assert all(s["lote"] == LOTE_REAL["id"] and s["pregunta"] for s in plan)
    archivos = sorted(p.name for p in (tmp_path / "sol").glob("*.json"))
    assert len(archivos) == 2 * n and not any("T999" in a for a in archivos)
    planificador.planificar()                                         # idempotente
    assert sorted(p.name for p in (tmp_path / "sol").glob("*.json")) == archivos
    for f in (tmp_path / "sol").glob("*_imagen_*.json"):
        img = json.loads(f.read_text())
        assert img["plantilla"] and img["angulo"] == img["pregunta"]


def test_ciclo_solo_redacta_solicitudes_del_lote(raiz_vacia, monkeypatch):
    (raiz_vacia / "data").mkdir(exist_ok=True)
    (raiz_vacia / "data" / "lote_piloto.json").write_text(json.dumps(LOTE_REAL, ensure_ascii=False))
    sol = raiz_vacia / "estado" / "solicitudes"; sol.mkdir(parents=True, exist_ok=True)
    (sol / "2026-10-20_reel_T068v2.json").write_text(json.dumps({"fecha": "2026-10-20", "formato": "reel", "tema_id": "T068",
                                                                   "titulo": "x", "gancho": "¿x?", "estado": "PENDIENTE_GUION"}))
    vistas = []
    def generar(s, *a, **k):
        vistas.append(s["archivo"]); raise redactor.Descartada("prueba", categoria="juridico")
    monkeypatch.setattr(redactor, "generar", generar)
    ciclo.ciclo("t", lambda u, timeout=60: (200, "application/pdf", b""), env={})
    assert vistas and all(LOTE_REAL["id"] in v for v in vistas), vistas
    assert json.loads((sol / "2026-10-20_reel_T068v2.json").read_text())["estado"] == "PENDIENTE_GUION"   # en espera, intacta


# ---------- reutilización del análisis ----------
FUENTES = {"F1": {"sigla": "CPEUM", "documento": "CPEUM", "articulo": "23", "texto_oficial": "Nadie puede ser juzgado dos veces."}}


def test_analisis_validado_se_reutiliza_y_el_objetado_no(monkeypatch):
    sol = {"tema_id": "T031", "pregunta": "¿p?", "tipo_pregunta": "derecho"}
    monkeypatch.setattr(redactor, "validar_mapa", lambda m, s, f: [])
    redactor.guardar_analisis(sol, FUENTES, {"respuesta_corta": "no"})
    assert redactor.analisis_guardado(sol, FUENTES) == {"respuesta_corta": "no"}
    otra = {**FUENTES, "F1": {**FUENTES["F1"], "texto_oficial": "texto distinto"}}
    assert redactor.analisis_guardado(sol, otra) is None                 # otro texto oficial: no se reutiliza
    redactor.guardar_analisis(sol, FUENTES, {"respuesta_corta": "no"}, objetado=True)
    assert redactor.analisis_guardado(sol, FUENTES) is None


def test_analisis_guardado_que_ya_no_pasa_la_revision_no_se_usa(monkeypatch):
    sol = {"tema_id": "T031", "pregunta": "¿p?"}
    redactor.guardar_analisis(sol, FUENTES, {"respuesta_corta": "no"})
    monkeypatch.setattr(redactor, "validar_mapa", lambda m, s, f: ["[cobertura] falta algo"])
    assert redactor.analisis_guardado(sol, FUENTES) is None


# ---------- cortacircuitos ----------
def test_modelo_con_5xx_repetidos_no_se_vuelve_a_llamar_en_el_ciclo(tmp_path, monkeypatch):
    cfg = {"proveedor": "gemini", "roles": {"auditor": {"modelos": ["gemini:m-caido", "gemini:m-bien"], "tope_diario": 50}},
           "pausa_5xx_s": 0, "pausa_429_s": 0}
    llamadas = []
    def http(self, modelo, sistema, usuario, json_mode=True):
        llamadas.append(modelo)
        if modelo == "m-caido": raise modelos.Saturado("m-caido: HTTP 500")
        return {"choices": [{"message": {"content": "{\"ok\": 1}"}}], "usage": {}}
    monkeypatch.setattr(modelos.Modelo, "_http_gemini", http)
    monkeypatch.setattr(modelos.Modelo, "caidos_ciclo", set()); monkeypatch.setattr(modelos.Modelo, "llamadas_ciclo", 0)
    m = modelos.Modelo("auditor", cfg, {"GEMINI_API_KEY": "x"}, archivo_uso=tmp_path / "uso.jsonl")
    assert m.completar("s", "u") == {"ok": 1} and m.completar("s", "u") == {"ok": 1}
    assert llamadas == ["m-caido", "m-caido", "m-bien", "m-bien"]


# ---------- regresiones del primer ciclo del piloto (27-10-2026, corrida 40555659141) ----------
def test_plazo_escrito_con_letra_en_la_ley_no_es_falta_de_sustento():
    """I20261123-T016 se descartó: «12 días» frente a «doce días laborables» del art. 76 LFT."""
    ley = "disfrutarán de un periodo anual de vacaciones pagadas, que en ningún caso podrá ser inferior a doce días laborables"
    assert razonamiento.consecuencias_sin_sustento("El mínimo es de 12 días laborables tras el primer año.", [ley]) == []
    assert razonamiento.consecuencias_sin_sustento("Te tocan 30 días.", [ley])          # una cifra que no está sí se bloquea


def test_obligacion_pide_contenido_no_una_consecuencia_inventada():
    """R20261124-T015: con «efecto» el modelo inventó que el pago tardío «constituye una violación»."""
    tipo, req = razonamiento.tipo_pregunta("¿Cuándo y cuánto te deben pagar de aguinaldo?", "obligacion")
    assert "contenido" in req and "efecto" not in req


def test_condicion_dicha_con_las_palabras_de_la_cita_cuenta_como_dicha():
    """R20261123-T031: la pieza decía «ya sea que te absuelvan o te condenen» y el control exigía «declarados inocentes»."""
    cita = "ya sea que en el juicio se le absuelva o se le condene"
    g = {"pregunta_original": "¿Te pueden volver a juzgar por el mismo delito?", "tipo_pregunta": "derecho",
         "escenas": [{"tipo": "texto", "texto": "Nadie puede ser juzgado dos veces por el mismo delito, ya sea que en el juicio se le absuelva o se le condene."}],
         "razonamiento": {"reglas": [{"fuente": "F1", "ref": {"documento": "CPEUM", "articulo": "23"}}], "elementos": [
             {"elemento": "contenido", "estado": "cubierto", "fuente": "F1", "respuesta": "Nadie puede ser juzgado dos veces por el mismo delito", "cita_literal": "Nadie puede ser juzgado dos veces por el mismo delito"},
             {"elemento": "condiciones", "estado": "cubierto", "fuente": "F1", "respuesta": "La protección aplica tanto para quienes fueron declarados inocentes como condenados", "cita_literal": cita},
             {"elemento": "excepcion", "estado": "no_aplica", "motivo": "el artículo no prevé ninguna excepción"}]}}
    textos = {("CPEUM", "23"): "Nadie puede ser juzgado dos veces por el mismo delito, ya sea que en el juicio se le absuelva o se le condene."}
    assert razonamiento.revisar_cobertura(g, textos) == [], razonamiento.revisar_cobertura(g, textos)


def test_objecion_a_la_respuesta_corta_del_analisis_provoca_reanalisis():
    """R20261125-T093: el auditor objetó tres veces «es ilegal… exclusivamente por el Estado», que venía del análisis."""
    mapa = {"reglas": [{"conclusion": "Nadie puede hacerse justicia por sí misma"}],
            "respuesta_corta": "Cualquier intento de justicia por propia mano es ilegal y violenta el derecho a que la justicia sea administrada exclusivamente por el Estado."}
    a = {"conclusiones": [{"conclusion": "Cualquier intento de justicia por propia mano es ilegal y violenta el derecho a que la justicia sea administrada exclusivamente por el Estado.", "sostenida": "parcial"}]}
    assert redactor._objeta_mapa(a, mapa)


def test_un_anio_frente_a_el_anio_de_la_ley():
    """R20261124-T015 (2.º ciclo): «menos de un año trabajado» frente a «no hayan cumplido el año de servicios» (art. 87 LFT)."""
    ley = "Los que no hayan cumplido el año de servicios, independientemente de que se encuentren laborando o no"
    assert razonamiento.consecuencias_sin_sustento("Si tienes menos de un año trabajado, te toca la parte proporcional.", [ley]) == []


def test_el_auditor_ve_cada_afirmacion_con_el_articulo_exacto():
    """R20261123-T031 (2.º ciclo): el auditor objetó tres veces «fuente inexistente F2/F3/F4»: las fichas del guion
    (una por cita) no coincidían con la numeración de los textos que recibía."""
    fuentes = {"F1": {"documento": "CPEUM", "articulo": "23", "texto_oficial": "Nadie puede ser juzgado dos veces por el mismo delito."}}
    guion = {"titulo": "¿t?", "fuentes": {f"F{i}": {"documento": "CPEUM", "articulo": "23"} for i in (1, 2, 3)},
             "escenas": [{"afirmaciones": [{"id": "A1", "fuente": "F1"}, {"id": "A2", "fuente": "F2"}]}, {"afirmaciones": [{"id": "A3", "fuente": "F3"}]}],
             "razonamiento": {"reglas": [{"fuente": "F1", "conclusion": "x"}]}}
    g, textos = redactor._para_auditor(guion, fuentes)
    refs = {a["fuente"] for e in g["escenas"] for a in e["afirmaciones"]} | {g["razonamiento"]["reglas"][0]["fuente"]}
    assert refs == {"CPEUM, artículo 23"} and textos.startswith("CPEUM, artículo 23:")
    assert guion["escenas"][0]["afirmaciones"][1]["fuente"] == "F2"          # el guion real no se modifica


def test_reproduccion_de_una_imagen_no_bloquea_redactar_otra(raiz_vacia, monkeypatch):
    """27-10: la re-producción de I20261124-T073 (PENDIENTE tras una edición) impidió redactar T016 y T028."""
    import cola
    c = cola.cargar()
    c["trabajos"]["I-VIEJA"] = {"id": "I-VIEJA", "formato": "imagen", "estado": "PENDIENTE", "prioridad": 0, "intentos": 0, "creado": "2026-10-27T00:00:00+00:00",
                                "historial": [{"de": "PENDIENTE", "a": "PRODUCIDO", "ts": "2026-10-27T10:00:00+00:00"}, {"de": "REVISION_HUMANA", "a": "PENDIENTE", "ts": "2026-10-27T11:00:00+00:00"}],
                                "error": None, "publicaciones": {}, "proximo_intento": None, "retencion": None}
    cola.guardar(c)
    sol = raiz_vacia / "estado" / "solicitudes"; sol.mkdir(parents=True, exist_ok=True)
    (sol / "2026-10-28_imagen_T016.json").write_text(json.dumps({"fecha": "2026-10-28", "formato": "imagen", "tema_id": "T016", "titulo": "x",
                                                                  "gancho": "¿x?", "estado": "PENDIENTE_GUION", "plantilla": "dato"}))
    vistas = []
    def generar(s, *a, **k):
        vistas.append(s["archivo"]); raise redactor.Descartada("prueba", categoria="juridico")
    monkeypatch.setattr(redactor, "generar", generar)
    c = cola.cargar(); ciclo.redactar_pendientes(c, {"descartadas": [], "redactadas": []}, None, {})
    assert "2026-10-28_imagen_T016.json" in vistas
    c["trabajos"]["I-VIEJA"]["historial"] = []                       # un guion NUEVO sin producir sí ocupa el espacio
    vistas.clear(); ciclo.redactar_pendientes(c, {"descartadas": [], "redactadas": []}, None, {})
    assert not any("imagen" in v for v in vistas)


def test_el_motivo_exacto_de_cada_descarte_queda_registrado(raiz_vacia, monkeypatch):
    sol = raiz_vacia / "estado" / "solicitudes"; sol.mkdir(parents=True, exist_ok=True)
    (sol / "2026-10-28_reel_T031.json").write_text(json.dumps({"fecha": "2026-10-28", "formato": "reel", "tema_id": "T031", "titulo": "x",
                                                                 "gancho": "¿x?", "estado": "PENDIENTE_GUION", "carril": "A", "fuentes_sugeridas": ""}))
    monkeypatch.setattr(redactor, "generar", lambda s, *a, **k: (_ for _ in ()).throw(redactor.Descartada("[sustento] motivo exacto", categoria="juridico")))
    import cola
    ciclo.redactar_pendientes(cola.cargar(), {"descartadas": [], "redactadas": []}, None, {})
    m = [json.loads(l) for l in (raiz_vacia / "registro" / "metricas_generacion.jsonl").read_text().splitlines()]
    r = next(x for x in m if x["tema_id"] == "T031")
    assert r["motivo"] == "[sustento] motivo exacto" and r["categoria"] == "juridico" and r["resultado"] == "descartada"


def test_el_analisis_pide_los_elementos_correctos_y_sin_creatividad():
    """El formato de respuesta listaba elementos viejos (efecto|que_hacer|…) aunque el tipo pidiera «contenido»,
    «condiciones» o «excepcion»; y el análisis se pedía con la temperatura de la redacción (0.5)."""
    vistos = {}
    class Red:
        temperatura = 0.5
        def completar(self, sistema, usuario, simulador=None):
            vistos["prompt"] = usuario; vistos["temp"] = self.temperatura; return {}
    red = Red()
    sol = {"titulo": "t", "pregunta": "¿Cuándo y cuánto te deben pagar de aguinaldo?", "tipo_pregunta": "obligacion"}
    redactor.analizar(sol, {"F1": {"documento": "LFT", "articulo": "87", "texto_oficial": "x"}}, red, "")
    assert "contenido | condiciones" in vistos["prompt"] and "efecto | que_hacer" not in vistos["prompt"]
    assert vistos["temp"] <= 0.15 and red.temperatura == 0.5
    assert "Inventar una consecuencia" in vistos["prompt"]


def _g_vacaciones(visible):
    return {"pregunta_original": "¿Cuántos días de vacaciones te corresponden?", "tipo_pregunta": "obligacion",
            "escenas": [{"tipo": "texto", "texto": visible}],
            "razonamiento": {"reglas": [{"fuente": "F1", "ref": {"documento": "LFT", "articulo": "76"}}], "elementos": [
                {"elemento": "contenido", "estado": "cubierto", "fuente": "F1", "respuesta": "El periodo mínimo es de doce días laborables",
                 "cita_literal": "en ningún caso podrá ser inferior a doce días laborables"},
                {"elemento": "condiciones", "estado": "cubierto", "fuente": "F1",
                 "respuesta": "Este derecho se adquiere una vez que la persona trabajadora ha acumulado más de un año de servicios para el empleador.",
                 "cita_literal": "Las personas trabajadoras que tengan más de un año de servicios disfrutarán de un periodo anual de vacaciones pagadas"}]}}


TEXTO_76 = {("LFT", "76"): "Las personas trabajadoras que tengan más de un año de servicios disfrutarán de un periodo anual de vacaciones pagadas, que en ningún caso podrá ser inferior a doce días laborables"}


def test_condicion_dicha_en_singular_o_con_otra_flexion_cuenta():
    """I20261123-T016 (28-10): «si tienes más de un año de servicio» frente a «personas trabajadoras … un año de servicios»."""
    g = _g_vacaciones("Si eres persona trabajadora y tienes más de un año de servicio, disfrutarás de vacaciones pagadas: el periodo mínimo es de doce días laborables.")
    assert razonamiento.revisar_cobertura(g, TEXTO_76) == []


def test_condicion_omitida_sigue_bloqueando():
    g = _g_vacaciones("Te tocan como mínimo doce días laborables de vacaciones.")
    assert any("condiciones" in h["detalle"] or "requisitos" in h["detalle"] for h in razonamiento.revisar_cobertura(g, TEXTO_76))


def test_imagen_demasiado_larga_se_detecta_al_redactar():
    """I20261125-T028 (28-10): 64 palabras visibles; la auditoría técnica la retuvo después de producirla."""
    import imagen
    g2 = json.loads((AQUI.parent / "piezas" / "I20261124-T073" / "guion.json").read_text())
    assert imagen.revision_previa(g2) == []
    import copy
    g = copy.deepcopy(g2); g["pieza"]["realidad"] += " " + " ".join(["palabra"] * 40)
    assert any("demasiado largo" in e for e in imagen.revision_previa(g))


def test_reel_lleva_texto_de_publicacion_sin_ia():
    """R20261123-T031 (28-10) llegó a revisión sin texto de publicación: se publicaría solo con el título."""
    g = {"pregunta_original": "¿Te pueden volver a juzgar por el mismo delito?",
         "fuentes": {"F1": {"documento": "Constitución Política de los Estados Unidos Mexicanos", "articulo": "23"},
                     "F2": {"documento": "Constitución Política de los Estados Unidos Mexicanos", "articulo": "23"}}}
    c = redactor.copy_reel(g, {"respuesta_corta": "No: nadie puede ser juzgado dos veces por el mismo delito."})
    assert c.count("artículo 23") == 1 and "no es asesoría legal" in c and c.startswith("¿Te pueden")


def test_definicion_no_se_contesta_con_si_o_no():
    """I20261125-T028 (28-10): «¿Qué significa la presunción de inocencia?» → «Sí: la persona imputada es inocente…»."""
    g = {"pregunta_original": "¿Qué significa la presunción de inocencia?", "tipo_pregunta": "definicion", "_solo_analisis": True,
         "razonamiento": {"respuesta_corta": "Sí: la persona imputada es inocente hasta que un juez emita sentencia.", "elementos": []}}
    assert any("definición" in h["detalle"] for h in razonamiento.revisar_cobertura(g, {}))
    g["razonamiento"]["respuesta_corta"] = "Significa que a la persona imputada se le presume inocente mientras una sentencia no declare su responsabilidad."
    assert not any("definición" in h["detalle"] for h in razonamiento.revisar_cobertura(g, {}))


def test_definicion_contestada_directamente_no_se_bloquea():
    """I20261125-T028 (28-10): la regla exigía «Sí/No/Depende» también en definiciones (contradicción con el control nuevo)."""
    g = json.loads((AQUI.parent / "piezas" / "I20261125-T028" / "guion.json").read_text())
    h = [x for x in razonamiento.revisar(g, {}) if x["regla"] == "respuesta" and "directa" in x["detalle"]]
    assert h == []
    g2 = {**g, "razonamiento": {**g["razonamiento"], "respuesta_corta": "La Constitución protege a las personas."}, "pregunta_original": "¿Es legal X?", "tipo_pregunta": None, "titulo": "¿Es legal X?"}
    assert [x for x in razonamiento.revisar(g2, {}) if x["regla"] == "respuesta" and "directa" in x["detalle"]]


def test_solicitud_del_lote_descartada_no_se_reabre_por_el_catalogo(raiz_vacia):
    """28-10: la pregunta fijada del lote difiere del gancho del catálogo y reabrir_por_cambio la reabría en cada ciclo."""
    sol = raiz_vacia / "estado" / "solicitudes"; sol.mkdir(parents=True, exist_ok=True)
    f = sol / "2026-11-24_reel_T015-piloto-1.json"
    f.write_text(json.dumps({"fecha": "2026-11-24", "formato": "reel", "tema_id": "T015", "titulo": "x", "gancho": "¿Cuándo y cuánto…?",
                             "pregunta": "¿Cuándo y cuánto…?", "lote": "piloto-1", "estado": "DESCARTADA", "huella_entrada": "0" * 16}))
    ciclo.reabrir_por_cambio()
    assert json.loads(f.read_text())["estado"] == "DESCARTADA"


def test_condicion_parafraseada_breve_cuenta():
    """I20261123-T016 (28-10, 3.er intento): «Aplica al cumplir más de un año de servicios» frente a
    «Aplica a las personas trabajadoras a partir de que cumplen más de un año de servicios»."""
    g = _g_vacaciones("El periodo mínimo es de doce días laborables. Aplica al cumplir más de un año de servicios.")
    g["razonamiento"]["elementos"][1]["respuesta"] = "Aplica a las personas trabajadoras a partir de que cumplen más de un año de servicios."
    assert razonamiento.revisar_cobertura(g, TEXTO_76) == []


def test_palabras_partidas_por_el_pdf_se_unen_sin_cambiar_la_cita():
    """R20261124-T015 (28-10): en pantalla aparecía «independienteme nte» (corte de línea del PDF oficial)."""
    doc = "independientemente administración costas responsabilidad el año de servicios en el juicio se le absuelva porque"
    assert redactor.limpiar_cortes("independienteme nte de que se encuentren", doc) == "independientemente de que se encuentren"
    assert redactor.limpiar_cortes("que se le adm inistre justicia", doc) == "que se le administre justicia"
    assert redactor.limpiar_cortes("las cost as judiciales", doc) == "las costas judiciales"
    for igual in ("cumplido el año de servicios", "en el juicio se le absuelva", "por que motivo"):
        assert redactor.limpiar_cortes(igual, doc) == igual
    import verificador
    assert verificador.contiene("tendrán derecho, independienteme nte de que se encuentren laborando o no",
                                "independientemente de que se encuentren laborando o no")


def test_obligacion_puede_contestarse_con_depende():
    """R20261124-T015 (28-10): «Depende del tiempo trabajado: debe pagarse antes del 20 de diciembre…» se retuvo."""
    g = json.loads((AQUI.parent / "piezas" / "R20261124-T015" / "guion.json").read_text())
    assert not [x for x in razonamiento.revisar(g, {}) if x["regla"] == "respuesta" and "directa" in x["detalle"]]


def test_ojo_que_repite_la_respuesta_se_detecta_al_redactar():
    """I20261123-T084 (28-10): «OJO: Prohibida por la Constitución Federal» repetía la bajada (el 27-10 se rechazó un «OJO» vacío)."""
    import imagen
    g = json.loads((AQUI.parent / "piezas" / "I20261123-T084" / "guion.json").read_text())
    g["pieza"]["ojo"] = "Prohibida por la Constitución Federal"
    assert any(e.startswith("[ojo]") for e in imagen.revision_previa(g))
    g["pieza"]["ojo"] = "También prohíbe la mutilación y los azotes."
    assert not any(e.startswith("[ojo]") for e in imagen.revision_previa(g))


@pytest.mark.parametrize("tipo,pregunta,rc,bloquea", [
    ("obligacion", "¿Cuántos días de permiso de paternidad te corresponden?", "Te corresponden cinco días laborables con goce de sueldo.", False),
    ("derecho", "¿Cuánto tiempo puede retenerte el Ministerio Público?", "Hasta cuarenta y ocho horas; el plazo puede duplicarse en delincuencia organizada.", False),
    ("derecho", "¿Cuánto tiempo puede retenerte el Ministerio Público?", "La Constitución establece reglas sobre la detención.", True),
    ("legalidad", "¿Puedes hacerte justicia por tu propia mano?", "Hacerse justicia está prohibido.", True),
    ("legalidad", "¿Puedes hacerte justicia por tu propia mano?", "No: nadie puede hacerse justicia por sí mismo.", False),
])
def test_respuesta_directa_segun_tipo(tipo, pregunta, rc, bloquea):
    """28-10 (piloto-2): T025 y T061 se descartaron por exigir «Sí/No» o una lista cerrada de inicios."""
    g = {"titulo": pregunta, "pregunta_original": pregunta, "tipo_pregunta": tipo, "razonamiento": {"respuesta_corta": rc},
         "escenas": [{"tipo": "texto", "texto": rc}]}
    h = [x for x in razonamiento.revisar(g, {}) if x["regla"] == "respuesta" and "directa" in x["detalle"]]
    assert bool(h) == bloquea


def test_minimo_legal_no_se_presenta_como_cifra_exacta():
    """I20261127-T015 (28-10): «equivale a quince días de salario» — la ley dice «quince días de salario, por lo menos»."""
    cita = "que deberá pagarse antes del día veinte de diciembre, equivalente a quince días de salario, por lo menos"
    base = {"pregunta_original": "¿Antes de qué fecha deben pagarte el aguinaldo?", "tipo_pregunta": "obligacion",
            "razonamiento": {"reglas": [{"fuente": "F1", "cita_literal": cita}], "elementos": []}}
    mal = {**base, "escenas": [{"tipo": "texto", "texto": "Debe pagarse antes del 20 de diciembre; equivale a quince días de salario."}]}
    bien = {**base, "escenas": [{"tipo": "texto", "texto": "Debe pagarse antes del 20 de diciembre y equivale, por lo menos, a quince días de salario."}]}
    assert any(h["regla"] == "minimo" for h in razonamiento.revisar_cobertura(mal, {}))
    assert not any(h["regla"] == "minimo" for h in razonamiento.revisar_cobertura(bien, {}))


def test_retenidas_archivadas_no_se_reverifican(raiz):
    """28-10: 4 piezas viejas se re-verificaban con cada versión del verificador y ocupaban los lugares de producción."""
    import cola, verificador as v
    ciclo.ciclo("t", lambda u, timeout=60: (200, "application/pdf", b""), env={})
    c = cola.cargar(); t = c["trabajos"]["X1"]
    t["estado"] = "RETENIDO"; t["retencion"] = {"tipo": "sustantivo", "verificador": "0.0.1", "archivada": "prueba"}; cola.guardar(c)
    ciclo.ciclo("t", lambda u, timeout=60: (200, "application/pdf", b""), env={})
    assert cola.cargar()["trabajos"]["X1"]["estado"] == "RETENIDO"


def test_condicion_de_otro_parrafo_no_se_exige_y_la_cita_textual_no_es_generalizacion():
    """R20261126-T061 (28-10): se exigía la prórroga del arraigo («siempre y cuando…») como condición de la retención de
    48 horas y se marcaba como «generalización» la propia frase literal del art. 16."""
    t = json.loads((AQUI.parent / "registro" / "textos" / "CPEUM_16.json").read_text())["texto"]
    cita = "Ningún indiciado podrá ser retenido por el Ministerio Público por más de cuarenta y ocho horas"
    assert "siempre y cuando" not in razonamiento.contexto_omitido(t, cita)
    frase = "Ningún indiciado podrá ser retenido por el Ministerio Público por más de cuarenta y ocho horas, plazo en que deberá ordenarse su libertad o ponérsele a disposición de la autoridad judicial."
    g = {"titulo": "¿Cuánto tiempo puede retenerte el Ministerio Público?", "tipo_pregunta": "derecho",
         "razonamiento": {"respuesta_corta": "Hasta cuarenta y ocho horas.", "reglas": [{"fuente": "F1", "conclusion": "Ningún indiciado podrá ser retenido más de cuarenta y ocho horas",
                          "cita_literal": cita, "condiciones": [], "ref": {"documento": "CPEUM", "articulo": "16"}}]},
         "fuentes": {"F1": {"documento": "CPEUM", "articulo": "16", "texto_literal": cita}},
         "escenas": [{"tipo": "texto", "texto": frase}]}
    h = [x for x in razonamiento.revisar(g, {("CPEUM", "16"): t}) if x["regla"] == "condiciones" and ("Generalización" in x["detalle"] or "Frase absoluta" in x["detalle"])]
    assert h == [], h


def test_cita_textual_introducida_por_el_narrador_no_es_generalizacion():
    t = json.loads((AQUI.parent / "registro" / "textos" / "CPEUM_16.json").read_text())["texto"]
    assert razonamiento._cita_textual("La Constitución señala que Ningún indiciado podrá ser retenido por el Ministerio Público por más de cuarenta y ocho horas.", t)
    assert not razonamiento._cita_textual("Nadie puede estar detenido nunca más de dos días en ningún caso.", t)


def test_el_nombre_de_la_marca_no_es_una_persona_real():
    """I20261128-T010 (28-10): «Aquí Dice» (la marca, en el texto de publicación) se detectó como persona real."""
    import auditoria
    g = json.loads((AQUI.parent / "piezas" / "I20261128-T010" / "guion.json").read_text())
    r = auditoria.editorial(g)
    assert not [x for x in r["reglas"] if x["control"] == "Sin personas reales identificables" and x["resultado"] == "FALLA"]
