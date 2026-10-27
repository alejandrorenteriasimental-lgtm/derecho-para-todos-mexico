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
         "razonamiento": {"elementos": [{"elemento": "efecto", "estado": "cubierto", "fuente": "F1", "respuesta": "no",
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
    assert LOTE_REAL["max_por_formato"] <= 3
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
    assert len([s for s in plan if s["formato"] == "reel"]) == 3 and len([s for s in plan if s["formato"] == "imagen"]) == 3
    assert all(s["lote"] == "piloto-1" and s["pregunta"] for s in plan)
    archivos = sorted(p.name for p in (tmp_path / "sol").glob("*.json"))
    assert len(archivos) == 6 and not any("T999" in a for a in archivos)
    planificador.planificar()                                         # idempotente
    assert sorted(p.name for p in (tmp_path / "sol").glob("*.json")) == archivos
    img = json.loads(next((tmp_path / "sol").glob("*_imagen_T016-*.json")).read_text())
    assert img["plantilla"] == "dato" and img["angulo"] == img["pregunta"]


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
    assert vistas and all("piloto-1" in v for v in vistas), vistas
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
