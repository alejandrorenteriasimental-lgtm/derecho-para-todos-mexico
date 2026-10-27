"""Verificación de jurisprudencia (sin red) y bloqueo de criterios judiciales no verificados en las piezas."""
import json, sys
from pathlib import Path
AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / "sistema"))
import tesis, razonamiento as R

T = {"registro": "2024400", "clave_esperada": "I.5o.T. J/1 L (11a.)", "rubro_esperado": "RENUNCIA. ESTÁNDARES DE VALORACIÓN DE PRUEBAS"}


def test_tesis_que_coincide_se_verifica(tmp_path, monkeypatch):
    monkeypatch.setattr(tesis, "CARPETA", tmp_path)
    d = {"rubro": "RENUNCIA. ESTÁNDARES DE VALORACIÓN DE PRUEBAS QUE LOS ÓRGANOS…", "tesis": "I.5o.T. J/1 L (11a.)", "epoca": "Undécima Época"}
    assert tesis.verificar(T, lambda u, timeout=40: (200, json.dumps(d).encode()))["dictamen"] == "VERIFICADA"


def test_tesis_distinta_o_inaccesible_no_se_verifica(tmp_path, monkeypatch):
    monkeypatch.setattr(tesis, "CARPETA", tmp_path)
    d = {"rubro": "OTRO RUBRO", "tesis": "I.5o.T. J/1 L (11a.)"}
    assert tesis.verificar(T, lambda u, timeout=40: (200, json.dumps(d).encode()))["dictamen"] == "DISCREPANTE"
    assert tesis.verificar(T, lambda u, timeout=40: (None, b"timeout"))["dictamen"] == "SIN_ACCESO"


def test_pieza_que_cita_jurisprudencia_no_verificada_se_bloquea():
    g = {"titulo": "¿Qué pasa si te obligan a firmar tu renuncia?", "escenas": [
        {"tipo": "titular", "texto": "Según la jurisprudencia con registro digital 2024400, el patrón debe probar que fue voluntaria."}]}
    assert any(x["regla"] == "jurisprudencia" for x in R.bloqueantes(R.revisar(g, {}, ia=False)))
    g["tesis_verificadas"] = ["2024400"]
    assert not any(x["regla"] == "jurisprudencia" for x in R.bloqueantes(R.revisar(g, {}, ia=False)))
