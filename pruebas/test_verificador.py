"""Pruebas del verificador documental: casos correctos y casos incorrectos que DEBE rechazar o retener."""
import copy, sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sistema"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import verificador as v
from fixtures import pdf_ley, transporte_fijo, LIT17

URL = "https://www.diputados.gob.mx/LeyesBiblio/pdf/CPEUM.pdf"
BASE = {"id": "F1", "nivel": "oficial", "url": URL, "documento": "Constitución Política de los Estados Unidos Mexicanos",
        "articulo": "17", "literal": LIT17, "ultima_reforma_documento": "2024-09-15"}
DOC = pdf_ley()


def test_fuente_correcta_se_verifica():
    r = v.verificar_fuente(BASE, transporte_fijo(DOC))
    assert r["estado"] == "VERIFICADA", r
    assert r["ultima_reforma_documento"] == "2024-09-15" and len(r["sha256"]) == 64 and "aprisionado" in r["extracto"]


def test_remision_interna_no_corta_el_articulo():
    r = v.verificar_fuente(BASE, transporte_fijo(DOC))
    assert "relleno de un articulo bis" not in r["extracto"]  # el segmento termina en «Artículo 17 Bis.»


@pytest.mark.parametrize("url,motivo", [
    ("https://diputados.gob.mx.sitio-falso.com/CPEUM.pdf", "dominio no oficial"),
    ("https://www.diputadosgob.mx/CPEUM.pdf", "dominio no oficial"),
    ("http://www.diputados.gob.mx/LeyesBiblio/pdf/CPEUM.pdf", "https"),
    ("https://es.wikipedia.org/wiki/Constitucion", "dominio no oficial"),
])
def test_fuente_oficial_falsa_se_rechaza(url, motivo):
    r = v.verificar_fuente({**BASE, "url": url}, transporte_fijo(DOC))
    assert r["estado"] == "RECHAZADA" and motivo in r["motivo"]


def test_documento_equivocado_se_rechaza():
    otro = pdf_ley(titulo="LEY FEDERAL DEL TRABAJO")
    r = v.verificar_fuente(BASE, transporte_fijo(otro))
    assert r["estado"] == "RECHAZADA" and "no es el ordenamiento" in r["motivo"]


def test_cita_alterada_se_rechaza():
    r = v.verificar_fuente({**BASE, "literal": "Nadie puede ser aprisionado por deudas de carácter civil."}, transporte_fijo(DOC))
    assert r["estado"] == "RECHAZADA" and "no coincide" in r["motivo"]


def test_articulo_equivocado_se_rechaza():
    r = v.verificar_fuente({**BASE, "articulo": "18"}, transporte_fijo(DOC))
    assert r["estado"] == "RECHAZADA" and "no en el artículo 18" in r["motivo"]


def test_no_confunde_17_con_17_bis_ni_con_170():
    doc = pdf_ley(articulos=[("17 Bis", LIT17), ("170", LIT17), ("18", "relleno")])
    r = v.verificar_fuente(BASE, transporte_fijo(doc))
    assert r["estado"] == "RECHAZADA" and "no existe el encabezado" in r["motivo"]


def test_articulo_inexistente_se_rechaza():
    r = v.verificar_fuente({**BASE, "articulo": "999"}, transporte_fijo(DOC))
    assert r["estado"] == "RECHAZADA"


def test_cambio_normativo_sin_huella_se_retiene():
    nuevo = pdf_ley(reforma="01-10-2026")
    r = v.verificar_fuente(BASE, transporte_fijo(nuevo))
    assert r["estado"] == "CAMBIO_NORMATIVO"


def test_cambio_en_el_texto_del_articulo_se_detecta_por_huella():
    huella = v.verificar_fuente(BASE, transporte_fijo(DOC))["huella_articulo"]
    reformado = pdf_ley(reforma="01-10-2026", articulos=[("17", "Texto nuevo de prueba con una excepción añadida. " + LIT17), ("18", "x")])
    r = v.verificar_fuente({**BASE, "huella_articulo": huella}, transporte_fijo(reformado))
    assert r["estado"] == "CAMBIO_NORMATIVO" and "cambió" in r["motivo"]


def test_reforma_en_otro_articulo_no_bloquea_si_la_huella_coincide():
    huella = v.verificar_fuente(BASE, transporte_fijo(DOC))["huella_articulo"]
    r = v.verificar_fuente({**BASE, "huella_articulo": huella}, transporte_fijo(pdf_ley(reforma="01-10-2026")))
    assert r["estado"] == "VERIFICADA" and "no cambió" in r["nota"]


def test_ley_abrogada_se_rechaza():
    r = v.verificar_fuente(BASE, transporte_fijo(pdf_ley(abrogada=True)))
    assert r["estado"] == "RECHAZADA" and "abrogado" in r["motivo"]


def test_red_caida_retiene_nunca_aprueba():
    def caida(url, timeout=60): raise v.SinConexion("Temporary failure in name resolution")
    r = v.verificar_fuente(BASE, caida)
    assert r["estado"] == "RETENER"


@pytest.mark.parametrize("estado,esperado", [(404, "RECHAZADA"), (500, "RETENER"), (403, "RETENER")])
def test_errores_http(estado, esperado):
    assert v.verificar_fuente(BASE, transporte_fijo(b"<html>error</html>" * 30, estado, "text/html"))["estado"] == esperado


def test_pagina_html_de_error_con_200_se_rechaza():
    r = v.verificar_fuente(BASE, transporte_fijo(b"<html><body>Pagina no encontrada</body></html>" * 20, 200, "text/html"))
    assert r["estado"] == "RECHAZADA"


def test_respuesta_truncada_se_retiene():
    assert v.verificar_fuente(BASE, transporte_fijo(b"%PDF-1.4 corto"))["estado"] == "RETENER"


def test_pdf_corrupto_se_retiene():
    assert v.verificar_fuente(BASE, transporte_fijo(b"%PDF-1.7\n" + b"basura" * 100))["estado"] == "RETENER"


def test_ficha_incompleta_se_rechaza():
    f = {k: x for k, x in BASE.items() if k != "literal"}
    assert v.verificar_fuente(f, transporte_fijo(DOC))["estado"] == "RECHAZADA"


def test_fuente_secundaria_no_sustenta():
    assert v.verificar_fuente({**BASE, "nivel": "secundaria"}, transporte_fijo(DOC))["estado"] == "NO_VERIFICABLE"


def test_sin_fecha_de_reforma_se_retiene():
    doc = pdf_ley(reforma="")
    assert v.verificar_fuente(BASE, transporte_fijo(doc))["estado"] == "RETENER"


# --------- decisión sobre el guion completo ---------
def guion(afirm, riesgo="bajo", fuentes=None):
    return {"riesgo": riesgo, "fuentes": fuentes or [BASE], "escenas": [{"afirmaciones": afirm}]}


def test_guion_verificado_es_apto():
    g = guion([{"id": "A1", "fuentes": ["F1"]}])
    assert v.verificar_guion(g, transporte_fijo(DOC))["decision"] == "APTA"


def test_afirmacion_sin_fuente_rechaza_el_guion():
    g = guion([{"id": "A1", "fuentes": ["F1"]}, {"id": "A2", "fuentes": []}])
    assert v.verificar_guion(g, transporte_fijo(DOC))["decision"] == "RECHAZADA"


def test_afirmacion_con_fuente_inexistente_rechaza():
    g = guion([{"id": "A1", "fuentes": ["F9"]}])
    assert v.verificar_guion(g, transporte_fijo(DOC))["decision"] == "RECHAZADA"


def test_afirmacion_solo_con_fuente_secundaria_rechaza():
    g = guion([{"id": "A1", "fuentes": ["F2"]}], fuentes=[BASE, {"id": "F2", "nivel": "secundaria"}])
    assert v.verificar_guion(g, transporte_fijo(DOC))["decision"] == "RECHAZADA"


def test_interpretativa_riesgo_medio_va_a_revision_humana():
    g = guion([{"id": "A1", "fuentes": ["F1"], "interpretativa": True}], riesgo="medio")
    assert v.verificar_guion(g, transporte_fijo(DOC))["decision"] == "REVISION_HUMANA"


def test_red_caida_retiene_el_guion():
    def caida(url, timeout=60): raise v.SinConexion("sin red")
    g = guion([{"id": "A1", "fuentes": ["F1"]}])
    assert v.verificar_guion(g, caida)["decision"] == "RETENER"


def test_guion_sin_afirmaciones_se_retiene():
    assert v.verificar_guion(guion([]), transporte_fijo(DOC))["decision"] == "RETENER"


def test_puntuacion_distinta_no_rechaza_pero_palabras_si():
    assert v.verificar_fuente({**BASE, "literal": "Nadie puede ser aprisionado, por deudas de carácter puramente civil"}, transporte_fijo(DOC))["estado"] == "VERIFICADA"
    assert v.verificar_fuente({**BASE, "literal": "Nadie puede ser aprisionado por deudas de carácter puramente mercantil"}, transporte_fijo(DOC))["estado"] == "RECHAZADA"


def test_interpretacion_con_duda_declarada_se_retiene():
    g = guion([{"id": "A1", "fuentes": ["F1"], "interpretativa": True, "duda": "alcance para deudas mercantiles"}], riesgo="bajo")
    assert v.verificar_guion(g, transporte_fijo(DOC))["decision"] == "RETENER"


def test_formato_v01_se_adapta():
    g = {"riesgo": "bajo", "fuentes": {"F1": {"nivel": "oficial", "url": URL, "documento": BASE["documento"], "articulo": "17", "texto_literal": LIT17}},
         "escenas": [{"afirmaciones": [{"id": "A1", "tipo": "hecho_normativo", "fuente": "F1"}]}]}
    assert v.verificar_guion(g, transporte_fijo(DOC))["decision"] == "APTA"
