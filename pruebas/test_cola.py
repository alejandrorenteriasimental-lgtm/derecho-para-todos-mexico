"""Pruebas de la cola persistente: transiciones, duplicados, bloqueo, reintentos y persistencia."""
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sistema"))
import cola


@pytest.fixture
def c(tmp_path, monkeypatch):
    monkeypatch.setattr(cola, "COLA", tmp_path / "cola.json"); monkeypatch.setattr(cola, "BITACORA", tmp_path / "b.jsonl")
    monkeypatch.setattr(cola, "LOCK", tmp_path / "lock.json")
    return cola.cargar()


def test_encolar_y_rechazar_duplicado(c):
    assert cola.encolar(c, "X1") is True and cola.encolar(c, "X1") is False


def test_transicion_invalida(c):
    cola.encolar(c, "X1")
    with pytest.raises(ValueError):
        cola.mover(c, "X1", "SIMULADO")


def test_bloqueo(c):
    assert cola.adquirir_lock("A") and not cola.adquirir_lock("B")
    cola.liberar_lock("A"); assert cola.adquirir_lock("B")


def test_tres_fallos_llevan_a_fallido(c):
    cola.encolar(c, "X1")
    r = [cola.fallo(c, "X1", "error simulado") for _ in range(3)]
    assert r[-1] == "alerta" and c["trabajos"]["X1"]["estado"] == "FALLIDO"


def test_reintento_respeta_la_espera(c):
    cola.encolar(c, "X1"); cola.fallo(c, "X1", "x")
    assert cola.siguientes(c, "PENDIENTE") == []


def test_persistencia_atomica(c):
    cola.encolar(c, "X2"); cola.mover(c, "X2", "PRODUCIDO"); cola.guardar(c)
    assert cola.cargar()["trabajos"]["X2"]["estado"] == "PRODUCIDO"


def test_filtrado_por_formato(c):
    cola.encolar(c, "R1", formato="reel"); cola.encolar(c, "I1", formato="imagen")
    assert [t["id"] for t in cola.siguientes(c, "PENDIENTE", n=5, formato="imagen")] == ["I1"]
