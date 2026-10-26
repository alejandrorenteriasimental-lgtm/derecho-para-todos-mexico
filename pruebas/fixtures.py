"""Documentos de prueba que imitan la estructura de los PDF de LeyesBiblio (Cámara de Diputados):
encabezado repetido en cada página, leyenda de última reforma, artículos con encabezado «Artículo N.» al inicio de línea.
Sirven para probar la lógica del verificador sin red. NO son textos oficiales: el artículo 17 reproduce solo
la oración ya verificada en el documento oficial de la SCJN; el resto es relleno marcado como tal."""
from fpdf import FPDF

LIT17 = "Nadie puede ser aprisionado por deudas de carácter puramente civil."


def pdf_ley(titulo="CONSTITUCIÓN POLÍTICA DE LOS ESTADOS UNIDOS MEXICANOS", reforma="15-09-2024", articulos=None,
            abrogada=False, paginas_relleno=3):
    if articulos is None:
        articulos = [
            ("16", "Texto de relleno de prueba del artículo dieciséis. Conforme al"),
            ("", "artículo 17 de esta Constitución se remite a otro precepto (remisión interna de prueba)."),
            ("17", "Ninguna persona podrá hacerse justicia por sí misma (relleno de prueba). " + LIT17),
            ("17 Bis", "Texto de relleno de un artículo bis de prueba."),
            ("18", "Texto de relleno de prueba del artículo dieciocho."),
            ("170", "Texto de relleno de prueba del artículo ciento setenta."),
        ]
    pdf = FPDF(); pdf.set_auto_page_break(True, 20)
    cab = f"{titulo}\nCÁMARA DE DIPUTADOS DEL H. CONGRESO DE LA UNIÓN\nSecretaría General\nÚltima Reforma DOF {reforma}"
    def encabezado():
        pdf.add_page(); pdf.set_font("Helvetica", size=8); pdf.multi_cell(0, 4, cab, new_x="LMARGIN", new_y="NEXT"); pdf.ln(4); pdf.set_font("Helvetica", size=10)
    encabezado()
    pdf.set_font("Helvetica", "B", 12); pdf.multi_cell(0, 6, titulo, new_x="LMARGIN", new_y="NEXT")
    if abrogada: pdf.multi_cell(0, 6, "LEY ABROGADA", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=10)
    pdf.multi_cell(0, 5, f"Última reforma publicada DOF {reforma}", new_x="LMARGIN", new_y="NEXT")
    for _ in range(paginas_relleno):
        encabezado(); pdf.multi_cell(0, 5, "Texto de relleno de prueba. " * 40, new_x="LMARGIN", new_y="NEXT")
    encabezado()
    for num, txt in articulos:
        pdf.multi_cell(0, 5, (f"Artículo {num}. " if num else "") + txt, new_x="LMARGIN", new_y="NEXT"); pdf.ln(2)
    return bytes(pdf.output())


def transporte_fijo(datos, estado=200, ctype="application/pdf"):
    return lambda url, timeout=60: (estado, ctype, datos)
