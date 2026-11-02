"""Regresión del razonamiento jurídico: los errores reales del 26-10-2026 deben detectarse AUNQUE las citas sean
auténticas (todas están, palabra por palabra, en el texto oficial vigente). Si alguien relaja las reglas de
razonamiento.py y uno de estos errores vuelve a pasar, estas pruebas fallan.

  T089 — título sobre la RENUNCIA; la respuesta se apoya en el MUTUO CONSENTIMIENTO (LFT 53 fr. I).
  T020 — «La garantía mínima legal es de noventa días»: el art. 77 LFPC lo prevé para lo que «se ofrezca con garantía»;
         además, el título pregunta si es legal «no hay cambios ni devoluciones» y la respuesta habla de otra cosa.
  T052 — se pidió «¿El banco tiene que devolverte un cargo que no hiciste?» y el Reel explicó quién designa al presidente
         de una institución: no responde la pregunta del plan editorial.
  v2   — la corrección de T020 escrita con el mapa de razonamiento: debe pasar sin bloqueantes.
"""
import copy, json, sys
from pathlib import Path
import pytest

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / "sistema")); sys.path.insert(0, str(AQUI))
import razonamiento as R, verificador as V
from fixtures import pdf_ley

DATOS = json.loads((AQUI / "datos" / "textos_oficiales.json").read_text())
TEXTOS = {(a["documento"], a["articulo"]): a["texto"] for a in DATOS["articulos"]}
pieza = lambda pid: json.loads((AQUI / "datos" / "regresion" / f"{pid}.json").read_text())
reglas = lambda hall: {x["regla"] for x in R.bloqueantes(hall)}


@pytest.mark.parametrize("pid", ["I20261025-T089", "I20261026-T020", "I20261026-T020v2"])
def test_las_citas_son_autenticas(pid):
    g = pieza(pid)
    for f in g["fuentes"].values():
        assert V.contiene(TEXTOS[(f["documento"], f["articulo"])], f["texto_literal"]), f


def test_T089_respuesta_sobre_otro_concepto_se_bloquea():
    hall = R.revisar(pieza("I20261025-T089"), TEXTOS)
    assert "conceptos" in reglas(hall)
    assert any("mutuo_consentimiento" in x["detalle"] and "renuncia" in x["detalle"] for x in R.bloqueantes(hall))


def test_T089_aunque_traiga_mapa_de_razonamiento():
    g = pieza("I20261025-T089")
    g["razonamiento"] = {"pregunta": "¿Renunciar significa perder tus derechos?",
                         "respuesta_corta": "No, al terminar por mutuo consentimiento conservas la parte proporcional del aguinaldo.",
                         "reglas": [{"conclusion": "Al terminar por mutuo consentimiento conservas el aguinaldo proporcional.", "ref": {"documento": "Ley Federal del Trabajo", "articulo": "53"},
                                     "cita_literal": "Son causas de terminación de las relaciones de trabajo: I. El mutuo consentimiento de las partes", "condiciones": [], "excepciones": []}],
                         "distinciones": [], "limites": ""}
    assert "conceptos" in reglas(R.revisar(g, TEXTOS))


def test_T020_generalizacion_del_articulo_77_se_bloquea():
    hall = R.revisar(pieza("I20261026-T020"), TEXTOS)
    assert "condiciones" in reglas(hall)
    assert any("noventa" in x["detalle"] and "se ofrezca con garantia" in x["detalle"] for x in R.bloqueantes(hall))


def test_T020_titulo_sin_respuesta_se_bloquea():
    hall = R.revisar(pieza("I20261026-T020"), TEXTOS)
    assert {"respuesta", "conceptos"} <= reglas(hall)


def test_T020_corregir_solo_el_ojo_no_basta():
    g = pieza("I20261026-T020"); g["pieza"]["ojo"] = "Si se ofrece garantía, no puede ser menor a noventa días."
    hall = R.revisar(g, TEXTOS)
    assert "condiciones" not in reglas(hall)                  # la generalización ya no está…
    assert "conceptos" in reglas(hall)                       # …pero sigue sin responder sobre cambios y devoluciones


def test_T020_con_mapa_que_repite_la_generalizacion():
    g = pieza("I20261026-T020")
    g["razonamiento"] = {"pregunta": "¿Es legal la frase 'no hay cambios ni devoluciones'?",
                         "respuesta_corta": "No, la garantía mínima legal es de noventa días y no se puede reducir.",
                         "reglas": [{"conclusion": "La garantía mínima legal es de noventa días.", "ref": {"documento": "Ley Federal de Protección al Consumidor", "articulo": "77"},
                                     "cita_literal": "la garantía no podrá se r inferior a noventa días contados a partir de la entrega del bien o la prestación del servicio",
                                     "condiciones": [], "excepciones": []}],
                         "distinciones": [], "limites": ""}
    assert {"condiciones", "conceptos"} <= reglas(R.revisar(g, TEXTOS))


def test_T052_deriva_de_tema_se_bloquea():
    g = pieza("R20261027-T052")
    assert "tema" in reglas(R.revisar(g, TEXTOS, ia=True))


def test_v2_corregida_pasa_sin_bloqueantes():
    g = pieza("I20261026-T020v2")
    assert R.bloqueantes(R.revisar(g, TEXTOS)) == []


def test_v2_si_se_quita_la_respuesta_vuelve_a_bloquearse():
    g = pieza("I20261026-T020v2"); g["pieza"]["bajada"] = "La ley protege a los consumidores."; g["razonamiento"]["respuesta_corta"] = ""
    assert "respuesta" in reglas(R.revisar(g, TEXTOS))


def test_v2_si_se_mezclan_conceptos_sin_distinguir():
    g = pieza("I20261026-T020v2"); g["razonamiento"]["distinciones"] = []
    assert "conceptos" in reglas(R.revisar(g, TEXTOS))


def _pdf_lfpc():
    arts = [(a["articulo"], a["texto"]) for a in DATOS["articulos"] if a["sigla"] == "LFPC"]
    return pdf_ley(titulo="LEY FEDERAL DE PROTECCIÓN AL CONSUMIDOR", reforma="12-12-2025", articulos=arts, paginas_relleno=1)


def test_integracion_el_verificador_retiene_T020_aunque_todas_las_citas_se_verifiquen():
    doc = _pdf_lfpc(); tr = lambda url, timeout=60: (200, "application/pdf", doc)
    v = V.verificar_guion(pieza("I20261026-T020"), tr)
    assert all(x["estado"] == "VERIFICADA" for x in v["fuentes"].values()), v["fuentes"]
    assert v["decision"] == "RETENER" and R.bloqueantes(v["razonamiento"])


def test_integracion_el_verificador_aprueba_la_v2():
    doc = _pdf_lfpc(); tr = lambda url, timeout=60: (200, "application/pdf", doc)
    v = V.verificar_guion(pieza("I20261026-T020v2"), tr)
    assert all(x["estado"] == "VERIFICADA" for x in v["fuentes"].values()), v["fuentes"]
    assert v["decision"] in ("APTA", "APTA_CON_CRITERIO") and not R.bloqueantes(v["razonamiento"]), v


def test_cargo_institucional_citado_en_la_ley_no_es_persona_real():
    import auditoria
    g = pieza("R20261027-T052")
    r = auditoria.editorial(g) if hasattr(auditoria, "editorial") else None
    assert r is None or all(x["resultado"] == "APROBADO" for x in r["reglas"] if x["control"] == "Sin personas reales identificables"), r


def test_renuncia_de_derechos_no_activa_el_glosario_de_terminacion_laboral():
    # regresión 02-11-2026: I20261213-T107 (LFT 33) se descartó porque el glosario de «renuncia» (terminación del trabajo)
    # llevó al redactor a distinguirla del mutuo consentimiento, algo ajeno a la renuncia de salarios devengados
    import razonamiento as r
    nada = ["¿Vale firmar que renuncias a un salario que ya ganaste?",
            "Es nula la renuncia que los trabajadores hagan de los salarios devengados",
            "siempre que no contenga renuncia de los derechos de los trabajadores"]
    for t in nada: assert ("terminacion_laboral", "renuncia") not in r.conceptos_en(t), t
    for t in ["¿Si renuncias pierdes tu aguinaldo?", "presentó su renuncia voluntaria", "renunciar a tu trabajo"]:
        assert ("terminacion_laboral", "renuncia") in r.conceptos_en(t), t
