"""Pruebas de la línea de imagen fija: plantillas, legibilidad, OCR, duplicados y validación de fichas."""
import copy, json, sys
from pathlib import Path
import pytest
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sistema"))
import imagen, esquema

BASE = json.loads((Path(__file__).resolve().parent.parent / "piezas/I001/guion.json").read_text())
VARIANTES = {
    "tres_claves": {"titular": "Tres cosas que debes saber sobre el amparo", "bajada": "Un juicio para defender tus derechos frente a actos de autoridad.",
                    "puntos": ["Protege derechos humanos frente a la autoridad", "Lo resuelven tribunales federales", "Tiene plazos para presentarse"]},
    "mito_realidad": {"titular": "«Si no firmo, no me pueden despedir»", "mito": "Negarte a firmar impide que te despidan.",
                      "realidad": "Firmar o no firmar no cambia si el despido fue justificado; eso lo decide la autoridad laboral."},
    "diferencia": {"titular": "¿Denuncia o demanda?", "columnas": [["Denuncia", "Informas a la autoridad de un posible delito para que se investigue."],
                                                                 ["Demanda", "Pides a un juez que resuelva un conflicto entre particulares."]]},
}


@pytest.mark.parametrize("plantilla", ["concepto", *VARIANTES])
def test_plantillas_pasan_la_auditoria_tecnica(tmp_path, plantilla):
    g = copy.deepcopy(BASE); g["plantilla"] = plantilla
    if plantilla in VARIANTES: g["pieza"] = {**VARIANTES[plantilla], "fuente_visible": "Prueba de plantilla"}
    png = tmp_path / "x.png"; textos, y_fin = imagen.dibujar(g, png)
    r, _, _ = imagen.auditar(png, textos, y_fin)
    fallas = [x for x in r if x["resultado"] == "FALLA"]
    assert not fallas, fallas


def test_contraste_wcag():
    assert round(imagen.contraste((0, 0, 0), (255, 255, 255)), 1) == 21.0
    assert imagen.contraste((242, 181, 68), (246, 241, 230)) < 4.5     # el amarillo de marca no sirve para texto sobre papel


def test_texto_ilegible_falla_el_ocr(tmp_path):
    png = tmp_path / "vacia.png"; Image.new("RGB", (1080, 1350), (246, 241, 230)).save(png)
    textos = [{"texto": "Derecho para todos presunción inocencia", "px": 40, "color": (0, 0, 0), "fondo": (255, 255, 255), "caja": (80, 80, 900, 120), "zona": "contenido"}]
    r, _, _ = imagen.auditar(png, textos, 500)
    assert any(x["control"].startswith("OCR") and x["resultado"] == "FALLA" for x in r)


def test_imagen_duplicada_se_detecta(tmp_path):
    png = tmp_path / "a.png"; textos, y = imagen.dibujar(BASE, png)
    r, h, _ = imagen.auditar(png, textos, y, previos_hash=[imagen.ahash(png)])
    assert any("idéntica" in x["control"] and x["resultado"] == "FALLA" for x in r)


@pytest.mark.parametrize("cambio,error", [
    (lambda g: g["pieza"].update(titular="¿" + "Muy largo " * 10 + "?"), "titular demasiado largo"),
    (lambda g: g["pieza"].update(puntos=["a", "b", "c", "d"]), "más de tres puntos"),
    (lambda g: g.update(copy="Texto sin aviso"), "aviso"),
    (lambda g: g.update(plantilla="infografia_libre"), "plantilla desconocida"),
    (lambda g: g.update(afirmaciones=[]), "sin afirmaciones"),
    (lambda g: g["afirmaciones"][0].update(fuente="F9"), "fuente inexistente"),
])
def test_fichas_invalidas(cambio, error):
    g = copy.deepcopy(BASE); cambio(g)
    assert any(error in e for e in esquema.validar(g)), esquema.validar(g)


def test_pie_con_nombre_largo_cabe_en_una_linea(tmp_path):
    # Regresión 09-11-2026 (I20270115-T140): la fuente de la LGDNNA se partía en dos líneas pegadas al aviso.
    import imagen
    g = {"id": "I1", "formato": "imagen", "plantilla": "mito_realidad", "titulo": "¿Un medio puede publicar la foto de un menor?",
         "pieza": {"titular": "¿Un medio puede publicar la foto de un menor?", "mito": "Los medios pueden publicar la imagen de un menor sin restricciones.",
                   "realidad": "Hay límites: es violación a su intimidad si menoscaba su honra o reputación.",
                   "fuente_visible": "Ley General de los Derechos de Niñas, Niños y Adolescentes, art. 77"}}
    textos, _ = imagen.dibujar(g, tmp_path / "p.png")
    pie = [t for t in textos if t["texto"].startswith("Fuente:")]
    assert len(pie) == 1 and pie[0]["texto"].endswith("art. 77") and pie[0]["px"] >= 24
