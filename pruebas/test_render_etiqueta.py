"""La etiqueta de la tarjeta de cita no se corta (R20261201-T019, 28-10: «LEY FEDERAL DE PROTECCIÓN AL CONSUMIDOR, ARTÍ»)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sistema"))
import render


def test_etiqueta_larga_cabe_en_la_tarjeta():
    ancho = render.W - 180 - 120
    for et in ("Ley Federal de Protección al Consumidor, artículo 7 Bis", "Constitución Política de los Estados Unidos Mexicanos, artículo 20, apartado B, fracción II", "Ley Federal del Trabajo, artículo 87"):
        ls, f = render.etiqueta_ajustada(et, ancho)
        assert all(f.getlength(t) + 44 <= ancho for t in ls), (et, ls)
        assert " ".join(ls).replace(" ,", ",") .replace(", ", " ") == et.upper().replace(", ", " ")   # nada se pierde
        assert len(ls) <= 2 and 28 + (len(ls) - 1) * (f.size + 30) + f.size + 24 <= 160    # no invade la cita
    assert render.etiqueta_ajustada("Ley Federal del Trabajo, artículo 87", ancho)[0] == ["LEY FEDERAL DEL TRABAJO, ARTÍCULO 87"]


def test_capsula_de_detalle_cabe_en_pantalla():
    """R20270103-T128 (7-11): «Protección contra la cesión de menores» (38 caracteres, el máximo del esquema) se salía de los bordes."""
    for det in ("Protección contra la cesión de menores", "Más días de vacaciones por antigüedad", "Corto"):
        f = render.font_detalle(det)
        assert f.getlength(det) + 70 <= render.DETALLE_MAX <= render.W - 2 * 60, det
    assert render.font_detalle("Corto").size == 54          # los detalles cortos no cambian
