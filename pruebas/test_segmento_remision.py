"""Una remisión que cae al inicio de línea («artículo 684-A de esta Ley») no es el encabezado del siguiente artículo.
LFT 48 (29-10): el texto se cortaba en «…procedimiento de conciliación previsto en el» y perdía «despido» y los salarios
vencidos, lo que hacía fallar el análisis («la LFT 48 no regula el despido»)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sistema"))
import verificador as V

CUERPO = """Artículo 47.- Son causas de rescisión de la relación de trabajo.
Artículo 48.- El trabajador podrá solicitar ante la Autoridad Conciliadora, o ante el Tribunal si no existe arreglo
conciliatorio, que se le reinstale, observando previamente las disposiciones relativas al procedimiento de conciliación previsto en el
artículo 684-A y subsiguientes.
Si en el juicio correspondiente no comprueba el patrón la causa de la rescisión, tendrá derecho a los salarios vencidos
computados desde la fecha del despido hasta por un período máximo de doce meses.
Artículo 48 Bis.- En los juicios derivados de las relaciones de trabajo.
Artículo 684-A.- Antes de acudir a los Tribunales.
"""


def test_remision_al_inicio_de_linea_no_corta_el_articulo():
    t = V.articulo_texto(CUERPO, "48", max_car=20000)
    assert "fecha del despido" in t and "684-A y subsiguientes" in t and "En los juicios derivados" not in t
    seg, _ = V.segmento_articulo(CUERPO, "48")
    assert "fecha del despido" in seg and "en los juicios derivados" not in seg


def test_encabezados_reales_siguen_cortando():
    assert V.articulo_texto(CUERPO, "47").endswith("Son causas de rescisión de la relación de trabajo.")
    assert V.articulo_texto(CUERPO, "48 Bis").endswith("En los juicios derivados de las relaciones de trabajo.")


TELETRABAJO = """Artículo 330-D.- Las personas trabajadoras bajo la modalidad de teletrabajo.
Artículo adicionado DOF 11-01-2021 Artículo 330 -E.- En modalidad de teletrabajo, los patrones tendrán las obligaciones especiales siguientes:
III. Asumir los costos derivados del trabajo a través de la modalidad de teletrabajo, incluyendo, en su caso, el pago de servicios de telecomunicación y la parte proporcional de electricidad;
Artículo 330 -F.- Las personas trabajadoras tendrán las obligaciones especiales siguientes.
"""


def test_articulo_con_letra_y_espacio_antes_del_guion():
    """LFT 29-10: el PDF oficial escribe «Artículo 330 -E.-»; «330-E» se daba por inexistente."""
    t = V.articulo_texto(TELETRABAJO.replace("Artículo adicionado DOF 11-01-2021 ", "\n"), "330-E", max_car=20000)
    assert t and "parte proporcional de electricidad" in t and "330 -F" not in t and "obligaciones especiales siguientes." not in t


def test_articulo_con_letra_en_texto_corrido():
    t = V.articulo_texto(TELETRABAJO, "330-E", max_car=20000)
    assert "parte proporcional de electricidad" in t and "330 -F" not in t
