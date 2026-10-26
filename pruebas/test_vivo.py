"""Pruebas EN VIVO contra los documentos oficiales publicados (Cámara de Diputados · LeyesBiblio).
Requieren red: en este entorno de trabajo el acceso a diputados.gob.mx está bloqueado, por eso se ejecutan en
GitHub Actions. Incluyen casos que el sistema DEBE rechazar usando el documento oficial real."""
import json, sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sistema"))
import verificador as v

pytestmark = pytest.mark.vivo
CPEUM = {"id": "F1", "nivel": "oficial", "url": "https://www.diputados.gob.mx/LeyesBiblio/pdf/CPEUM.pdf",
         "documento": "Constitución Política de los Estados Unidos Mexicanos", "articulo": "17",
         "literal": "Nadie puede ser aprisionado por deudas de carácter puramente civil."}
CPF = {"id": "F3", "nivel": "oficial", "url": "https://www.diputados.gob.mx/LeyesBiblio/pdf/CPF.pdf", "documento": "Código Penal Federal",
       "articulo": "336", "literal": "Al que sin motivo justificado abandone a sus hijos o a su cónyuge, sin recursos para atender a sus necesidades de subsistencia"}
_cache = {}
def tr(url, timeout=90):
    if url not in _cache: _cache[url] = v.transporte_http(url, timeout)
    return _cache[url]


def _evidencia(r):
    Path("registro").mkdir(exist_ok=True)
    with open("registro/verificacion_en_vivo.jsonl", "a") as f: f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return r


def test_cpeum_17_verificado_en_el_documento_oficial():
    r = _evidencia(v.verificar_fuente(CPEUM, tr))
    assert r["estado"] == "VERIFICADA", r
    assert r["ultima_reforma_documento"] and len(r["sha256"]) == 64


def test_cpf_336_verificado_en_el_documento_oficial():
    r = _evidencia(v.verificar_fuente(CPF, tr))
    assert r["estado"] == "VERIFICADA", r


def test_oficial_real_con_cita_alterada_se_rechaza():
    r = v.verificar_fuente({**CPEUM, "literal": "Nadie puede ser aprisionado por deudas de carácter mercantil."}, tr)
    assert r["estado"] == "RECHAZADA"


def test_oficial_real_con_articulo_equivocado_se_rechaza():
    r = v.verificar_fuente({**CPEUM, "articulo": "16"}, tr)
    assert r["estado"] == "RECHAZADA" and "no en el artículo 16" in r["motivo"]


def test_oficial_real_con_documento_equivocado_se_rechaza():
    r = v.verificar_fuente({**CPEUM, "documento": "Ley Federal del Trabajo"}, tr)
    assert r["estado"] == "RECHAZADA"


def test_cambio_normativo_simulado_sobre_documento_real():
    r = v.verificar_fuente({**CPEUM, "huella_articulo": "0" * 64}, tr)
    assert r["estado"] == "CAMBIO_NORMATIVO"
