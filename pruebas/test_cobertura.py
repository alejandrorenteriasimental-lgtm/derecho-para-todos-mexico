"""Regresión del rechazo humano de R20261028-T068 (26-10-2026, versión c607942b03d912b6):
1) no respondía suficientemente la pregunta; 2) el art. 33 LFT solo no sustenta todas las consecuencias; 3) «recurso legal
específico» es vago; 4) los subtítulos tapaban la cita. Se prueba también con temas distintos (consumo, Constitución,
definiciones) para comprobar que las reglas son generales y no un parche de este Reel.
Los textos de la LFT son los oficiales extraídos en GitHub Actions el 27-10-2026 (última reforma DOF 14-05-2026)."""
import copy, json, sys
from pathlib import Path
import pytest

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / "sistema")); sys.path.insert(0, str(AQUI))
import razonamiento as R, redactor, render, auditoria
from test_redactor import simulador_con, BORRADOR, ANALISIS

DATOS = json.loads((AQUI / "datos" / "textos_oficiales.json").read_text())
ART = {(a["sigla"], a["articulo"]): a for a in DATOS["articulos"]}
TEXTOS = {(a["documento"], a["articulo"]): a["texto"] for a in DATOS["articulos"]}
LFT = "Ley Federal del Trabajo"
T068 = json.loads((AQUI / "datos" / "regresion" / "R20261028-T068.json").read_text())
PREGUNTA = "¿Qué pasa si te obligan a firmar tu renuncia?"
reglas = lambda hall: {x["regla"] for x in R.bloqueantes(hall)}


# ---------- 1-3: la versión rechazada se bloquea por las razones del revisor ----------
def test_version_rechazada_no_cubre_la_pregunta():
    hall = R.revisar(T068, TEXTOS, ia=True)
    det = " ".join(x["detalle"] for x in R.bloqueantes(hall))
    assert "cobertura" in reglas(hall)
    assert "que_hacer" in det and "ante_quien" in det and "plazo" in det


def test_version_rechazada_tiene_referencia_vaga():
    hall = R.revisar(T068, TEXTOS, ia=True)
    assert any(x["regla"] == "vaguedad" and "recurso legal" in x["detalle"] for x in R.bloqueantes(hall))


def test_consecuencias_que_el_articulo_33_no_establece():
    solo33 = [ART[("LFT", "33")]["texto"]]
    falsas = R.consecuencias_sin_sustento("Puedes pedir tu reinstalación o una indemnización de tres meses. Tienes dos meses para reclamar.", solo33)
    assert any("reinstalación" in x for x in falsas) and any("plazo (2 mes)" in x for x in falsas)
    con_48_518 = solo33 + [ART[("LFT", "48")]["texto"], ART[("LFT", "518")]["texto"]]
    assert R.consecuencias_sin_sustento("Puedes pedir tu reinstalación o una indemnización. Tienes dos meses para reclamar.", con_48_518) == []


def _mapa_correcto():
    f = lambda a: {"documento": LFT, "articulo": a}
    return {"pregunta": PREGUNTA, "respuesta_corta": "Depende: si te obligaron, la renuncia puede impugnarse como despido, pero tú debes aportar indicios de la presión.",
            "reglas": [{"conclusion": "Tienes dos meses desde la separación para reclamar.", "fuente": "F2", "ref": f("518"),
                        "cita_literal": "Prescriben en dos meses las acciones de los trabajadores que sean separados del trabajo", "condiciones": ["se suspende con la solicitud de conciliación"], "excepciones": []}],
            "elementos": [
                {"elemento": "efecto", "estado": "cubierto", "respuesta": "Es nula la renuncia a salarios devengados e indemnizaciones.", "fuente": "F1",
                 "cita_literal": "Es nula la renuncia que los trabajadores hagan de los salarios devengados, de las indemnizaciones"},
                {"elemento": "que_hacer", "estado": "cubierto", "respuesta": "Puedes pedir que te reinstalen o que te indemnicen con tres meses de salario.", "fuente": "F3",
                 "cita_literal": "que se le reinstale en el trabajo que desempeñaba, o que se le indemnice con el importe de tres meses de salario"},
                {"elemento": "ante_quien", "estado": "cubierto", "respuesta": "Primero ante el Centro de Conciliación y, si no hay arreglo, ante el Tribunal.", "fuente": "F4",
                 "cita_literal": "presentación de la solicitud de conciliación ante el Centro Federal de Conciliación y Registro Laboral o al Centro de Conciliación local que corresponda"},
                {"elemento": "plazo", "estado": "cubierto", "respuesta": "Tienes dos meses desde la separación.", "fuente": "F2",
                 "cita_literal": "Prescriben en dos meses las acciones de los trabajadores que sean separados del trabajo"}]}


def _fichas():
    return {"F1": {"documento": LFT, "articulo": "33"}, "F2": {"documento": LFT, "articulo": "518"},
            "F3": {"documento": LFT, "articulo": "48"}, "F4": {"documento": LFT, "articulo": "684-E"}}


def test_analisis_completo_cubre_los_cuatro_elementos():
    g = {"titulo": PREGUNTA, "pregunta_original": PREGUNTA, "razonamiento": _mapa_correcto(), "fuentes": _fichas(), "_solo_analisis": True}
    assert R.revisar_cobertura(g, TEXTOS) == []


def test_elemento_sin_sustento_bloquea_y_cita_falsa_tambien():
    m = _mapa_correcto(); m["elementos"][3] = {"elemento": "plazo", "estado": "no_cubierto"}
    g = {"titulo": PREGUNTA, "pregunta_original": PREGUNTA, "razonamiento": m, "fuentes": _fichas(), "_solo_analisis": True}
    assert any("Falta sustento" in x["detalle"] for x in R.revisar_cobertura(g, TEXTOS))
    m = _mapa_correcto(); m["elementos"][3]["cita_literal"] = "Prescriben en tres meses las acciones de los trabajadores despedidos"
    g["razonamiento"] = m
    assert any("no trae una cita literal" in x["detalle"] for x in R.revisar_cobertura(g, TEXTOS))


def test_elemento_del_analisis_que_no_se_dice_en_la_pieza():
    g = {"titulo": PREGUNTA, "pregunta_original": PREGUNTA, "razonamiento": _mapa_correcto(), "fuentes": _fichas(),
         "escenas": [{"tipo": "titular", "texto": "Es nula la renuncia a salarios devengados e indemnizaciones. Puedes pedir que te reinstalen o que te indemnicen con tres meses de salario."}]}
    faltan = " ".join(x["detalle"] for x in R.revisar_cobertura(g, TEXTOS))
    assert "ante qué autoridad" in faltan and "plazo" in faltan


# ---------- generalidad: otros temas ----------
def test_otros_tipos_de_pregunta():
    assert R.tipo_pregunta("¿Te pueden meter a la cárcel por deber dinero?")[0] == "legalidad"
    assert R.tipo_pregunta("¿Qué hago si la tienda no respeta la garantía?")[0] == "consecuencia"
    assert R.tipo_pregunta("¿Qué es la presunción de inocencia?")[0] == "definicion"


def test_consumo_vago_y_sin_sustento():
    cuerpo = "Si la tienda no respeta la garantía, acude a las autoridades competentes. Tienes treinta días para reclamar ante Profeco."
    assert R.vaguedades(cuerpo)
    lfpc77 = [a["texto"] for a in DATOS["articulos"] if a["sigla"] == "LFPC" and a["articulo"] == "77"]
    assert any("Profeco" in x or "plazo" in x for x in R.consecuencias_sin_sustento(cuerpo, lfpc77))


def test_reel_constitucional_correcto_sigue_pasando():
    # el Reel de prueba de prisión por deudas (pregunta de legalidad) solo necesita el efecto, y lo tiene
    g = redactor.construir_reel({"pieza_id": "X", "tema_id": "T073", "formato": "reel", "carril": "A", "titulo": "¿Cárcel por deber dinero?",
                                 "gancho": "¿Te pueden meter a la cárcel por deber dinero?"},
                                copy.deepcopy(BORRADOR), {"F1": {"sigla": "CPEUM", "documento": "Constitución Política de los Estados Unidos Mexicanos", "articulo": "17",
                                                                 "url": "https://www.diputados.gob.mx/LeyesBiblio/pdf/CPEUM.pdf", "ambito": "federal",
                                                                 "texto_oficial": "Nadie puede ser aprisionado por deudas de carácter puramente civil."}}) if hasattr(redactor, "construir_reel") else None
    if g:
        g["razonamiento"] = {**ANALISIS, "reglas": [{**ANALISIS["reglas"][0], "ref": {"documento": "Constitución Política de los Estados Unidos Mexicanos", "articulo": "17"}}]}
        textos = {("Constitución Política de los Estados Unidos Mexicanos", "17"): "Nadie puede ser aprisionado por deudas de carácter puramente civil."}
        assert "cobertura" not in reglas(R.revisar(g, textos, ia=True))


# ---------- el generador busca las fuentes que faltan ----------
def test_falta_de_sustento_dispara_investigacion_complementaria(tmp_path):
    textos = {("LFT", a): ART[("LFT", a)]["texto"] for a in ("33", "48", "518", "684-E")}
    class Biblio:
        def __init__(self, transporte=None): self.pedidos = []
        def articulo(self, sigla, num): self.pedidos.append((sigla, num)); return textos.get((sigla, num))
    sol = {"pieza_id": "R1", "tema_id": "T068", "formato": "reel", "carril": "A", "titulo": "Renuncia forzada", "gancho": PREGUNTA, "fuentes_sugeridas": "LFT 33"}
    sim = simulador_con(investigar=lambda n: {"articulos": [{"sigla": "LFT", "articulo": "33"}]} if n == 1 else
                        {"articulos": [{"sigla": "LFT", "articulo": "48"}, {"sigla": "LFT", "articulo": "518"}, {"sigla": "LFT", "articulo": "684-E"}]},
                        analizar=lambda n: {"suficiente": True, "pregunta": PREGUNTA, "respuesta_corta": "Depende: es nula la renuncia a salarios devengados.",
                                            "reglas": [{"conclusion": "Es nula la renuncia a salarios devengados.", "fuente": "F1",
                                                        "cita_literal": "Es nula la renuncia que los trabajadores hagan de los salarios devengados", "condiciones": [], "excepciones": []}],
                                            "elementos": [{"elemento": "efecto", "estado": "cubierto", "respuesta": "Es nula la renuncia a salarios devengados.", "fuente": "F1",
                                                           "cita_literal": "Es nula la renuncia que los trabajadores hagan de los salarios devengados"},
                                                          {"elemento": "que_hacer", "estado": "no_cubierto"}, {"elemento": "ante_quien", "estado": "no_cubierto"},
                                                          {"elemento": "plazo", "estado": "no_cubierto"}]})
    orig = redactor.Biblioteca; b = Biblio(); redactor.Biblioteca = lambda t: b
    try:
        with pytest.raises(redactor.Descartada) as e:
            redactor.generar(sol, None, sim, env={}, archivo_uso=tmp_path / "u")
    finally:
        redactor.Biblioteca = orig
    assert ("LFT", "518") in b.pedidos and ("LFT", "48") in b.pedidos        # buscó lo que faltaba
    assert len(sim.llamadas["investigador"]) == 2
    assert "no superó la revisión" in str(e.value)                            # y no inventó la respuesta


# ---------- 4: subtítulos ----------
def _medir(esc):
    from PIL import Image, ImageDraw
    capa = Image.new("RGBA", (render.W, render.H)); m = render.Medidor(ImageDraw.Draw(capa))
    render.escena(m, esc, 0.99, 5.0, {}); return m.abajo


def test_cita_larga_se_ajusta_y_queda_arriba_de_los_subtitulos():
    cita = " ".join(ART[("LFT", "33")]["texto"].split()[1:41])          # 40 palabras: el máximo que admite el redactor
    abajo = _medir({"tipo": "cita", "cita": cita, "etiqueta": "Ley Federal del Trabajo, art. 33", "afirmaciones": []})
    assert abajo <= render.CITA_Y_MAX
    y, cabe = render.posicion_subtitulos(abajo)
    assert cabe and y - 22 >= abajo + render.SUB_MARGEN - 1


def test_contenido_que_no_deja_lugar_se_reporta_y_falla_la_auditoria():
    y, cabe = render.posicion_subtitulos(render.SUB_Y_MAX)
    assert not cabe
    assert auditoria.subtitulos_sin_solape([{"t": 20.0, "escena": 2, "tipo": "cita", "contenido_hasta": 1600}])["resultado"] == "FALLA"
    assert auditoria.subtitulos_sin_solape([])["resultado"] == "APROBADO"
    assert auditoria.subtitulos_sin_solape(None)["resultado"] == "FALLA"


def test_cita_extrema_tampoco_queda_tapada():
    cita = ART[("LFT", "33")]["texto"][:700]
    abajo = _medir({"tipo": "cita", "cita": cita, "etiqueta": "Ley Federal del Trabajo, art. 33", "afirmaciones": []})
    y, cabe = render.posicion_subtitulos(abajo)
    assert (cabe and y - 22 >= abajo + render.SUB_MARGEN - 1) or not cabe     # o queda debajo, o se reporta como falla


# ---------- cuota ----------
def test_modelo_con_cuota_diaria_agotada_no_se_vuelve_a_llamar(tmp_path):
    import modelos
    from datetime import datetime, timezone
    u = tmp_path / "uso.jsonl"
    u.write_text(json.dumps({"ts": "2026-10-27T02:00:00+00:00", "rol": "redactor", "proveedor": "gemini", "modelo": "m1", "resultado": "error",
                             "error": "m1: HTTP 429 quota ... GenerateRequestsPerDayPerProjectPerModel-FreeTier"}) + "\n")
    assert modelos.agotado_hoy("m1", u, "gemini", ahora=datetime(2026, 10, 27, 5, 0, tzinfo=timezone.utc))
    assert not modelos.agotado_hoy("m1", u, "gemini", ahora=datetime(2026, 10, 27, 9, 17, tzinfo=timezone.utc))   # ya se reinició (00:00 del Pacífico)


# ---------- I20261030-T016 (27-10): copy con un «cambio reciente» sin fuente y un «ojo» vacío ----------
def test_cambio_legal_sin_decreto_y_ojo_vacio_se_bloquean():
    g = {"titulo": "¿Te dieron 6 días? Puede que te deban más", "plantilla": "dato",
         "pieza": {"titular": "¿Te dieron 6 días?", "bajada": "Depende: el periodo anual de vacaciones no puede ser inferior a doce días laborables.", "ojo": "Revisa tu ley"},
         "copy": "De acuerdo con la Ley Federal del Trabajo, las reglas sobre tus días de descanso cambiaron recientemente. Tus vacaciones no pueden ser menores a este límite.",
         "fuentes": {"F1": {"documento": LFT, "articulo": "76", "url": "https://www.diputados.gob.mx/LeyesBiblio/pdf/LFT.pdf"}}}
    det = " ".join(x["detalle"] for x in R.bloqueantes(R.revisar(g, {}, ia=False)))
    assert "cambio legal" in det and "Revisa tu ley" in det and "este límite" in det


def test_cita_casi_literal_se_sustituye_por_el_texto_oficial():
    fz = {"F1": {"texto_oficial": ART[("LFT", "48")]["texto"]}}
    m = {"elementos": [{"elemento": "que_hacer", "fuente": "F1",
                        "cita_literal": "que se le reinstale en el trabajo que desempeñaba o que se le indemnice con el importe de tres meses de salario"}]}
    redactor._citas_exactas(m, fz)
    import verificador
    assert verificador.contiene(ART[("LFT", "48")]["texto"], m["elementos"][0]["cita_literal"])
    m2 = {"elementos": [{"elemento": "plazo", "fuente": "F1", "cita_literal": "tienes un año para presentar la demanda ante el juez de lo civil"}]}
    redactor._citas_exactas(m2, fz)
    assert "cita_literal_original" not in m2["elementos"][0]            # no inventa una equivalencia
