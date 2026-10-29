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
