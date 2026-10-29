"""«Casi idéntica» compara solo piezas del mismo tema o con titulares parecidos (I20261204-T031 retenida por parecerse
en diseño, no en contenido, a I20261126-T025 — 29-10)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sistema"))
import imagen


def test_misma_plantilla_distinto_tema_no_cuenta():
    g = {"id": "I20261204-T031", "tema_id": "T031", "titulo": "¿Cuántas instancias puede tener un juicio penal?"}
    assert not imagen._mismo_tema(g, "I20261126-T025")          # paternidad: otro tema
    assert imagen._mismo_tema(g, "R20261123-T031")              # mismo tema
    assert imagen._mismo_tema({"id": "X", "titulo": "¿Cuántos días de permiso de paternidad te corresponden?"}, "I20261126-T025")
