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


def test_titular_parecido_con_otro_articulo_no_cuenta():
    """I20270119-T144 (LFT 100, pago a otra persona) se retuvo por parecerse en diseño a I20261214-T108 (LFT 101, vales):
    los titulares comparten «pueden pagar sueldo», pero los fundamentos son distintos (10-11-2026)."""
    lft = lambda n: {"F1": {"documento": "Ley Federal del Trabajo", "articulo": n}}
    g = {"id": "I20270119-T144", "tema_id": "T144", "titulo": "¿Le pueden pagar tu sueldo a otra persona?", "fuentes": lft("100")}
    assert not imagen._mismo_tema(g, "I20261214-T108")
    assert imagen._mismo_tema({**g, "fuentes": lft("101")}, "I20261214-T108")       # mismo artículo: se compara
    assert imagen._mismo_tema({k: v for k, v in g.items() if k != "fuentes"}, "I20261214-T108")   # sin fuentes: se compara
