"""Etapa 1 (análisis jurídico previo a la redacción): los errores reales del 26-10-2026 deben detenerse ANTES de que se
escriba la pieza, con citas auténticas del texto oficial vigente. Y una vez aprobado, el análisis no puede alterarse
durante la redacción. Estas pruebas complementan (no sustituyen) las de test_razonamiento.py, que revisan la pieza final.
"""
import copy, json, sys
from pathlib import Path
import pytest

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / "sistema")); sys.path.insert(0, str(AQUI))
import redactor
from test_redactor import simulador_con, SOL, transporte, BORRADOR, ANALISIS

DATOS = json.loads((AQUI / "datos" / "textos_oficiales.json").read_text())
ART = {(a["documento"], a["articulo"]): a["texto"] for a in DATOS["articulos"]}
LFPC, LFT = "Ley Federal de Protección al Consumidor", "Ley Federal del Trabajo"


def fuentes(*refs):
    out = {}
    for i, (doc, art) in enumerate(refs, 1):
        doc = next(d for (d, a) in ART if d.startswith(doc) and a == art)
        out[f"F{i}"] = {"sigla": "X", "documento": doc, "articulo": art, "url": "", "ambito": "federal", "texto_oficial": ART[(doc, art)]}
    return out


def errores(mapa, sol, fz):
    return " | ".join(redactor.validar_mapa(mapa, sol, fz))


SOL_T020 = {"titulo": "No hay cambios ni devoluciones", "gancho": "¿Es legal la frase «no hay cambios ni devoluciones»?", "formato": "imagen"}
SOL_T089 = {"titulo": "Renuncia y derechos", "gancho": "¿Renunciar significa perder tus derechos?", "formato": "imagen"}
SOL_T052 = {"titulo": "Fraude con tarjeta: cómo reclamar al banco", "gancho": "¿El banco tiene que devolverte un cargo que no hiciste?", "formato": "reel"}


def test_T020_condicion_omitida_se_detiene_en_el_analisis():
    fz = fuentes((LFPC, "77"))
    mapa = {"suficiente": True, "pregunta": SOL_T020["gancho"], "respuesta_corta": "No, la garantía mínima legal es de noventa días.",
            "reglas": [{"conclusion": "La garantía mínima legal es de noventa días.", "fuente": "F1",
                        "cita_literal": "la garantía no podrá se r inferior a noventa días contados a partir de la entrega del bien o la prestación del servicio.",
                        "condiciones": [], "excepciones": []}], "distinciones": [], "limites": ""}
    e = errores(mapa, SOL_T020, fz)
    assert "[condiciones]" in e and "[conceptos]" in e, e


def test_T089_otro_concepto_se_detiene_en_el_analisis():
    fz = fuentes((LFT, "53"))
    mapa = {"suficiente": True, "pregunta": SOL_T089["gancho"], "respuesta_corta": "No, el mutuo consentimiento de las partes termina la relación de trabajo.",
            "reglas": [{"conclusion": "El mutuo consentimiento termina la relación de trabajo.", "fuente": "F1",
                        "cita_literal": "Son causas de terminación de las relaciones de trabajo: I. El mutuo consentimiento de las partes", "condiciones": [], "excepciones": []}],
            "distinciones": [], "limites": ""}
    e = errores(mapa, SOL_T089, fz)
    assert "[conceptos]" in e and "mutuo_consentimiento" in e, e


def test_T052_otra_pregunta_se_detiene_en_el_analisis():
    fz = fuentes((LFPC, "1"))
    mapa = {"suficiente": True, "pregunta": "¿Quién designa al Presidente de la institución?",
            "respuesta_corta": "Depende: el Presidente lo designa el Secretario de Hacienda.",
            "reglas": [{"conclusion": "Las disposiciones de la ley son irrenunciables.", "fuente": "F1",
                        "cita_literal": "Sus disposiciones son irrenunciables y contra su observancia no podrán alegarse costumbres",
                        "condiciones": [], "excepciones": []}], "distinciones": [], "limites": ""}
    e = errores({**mapa}, {**SOL_T052, "gancho": SOL_T052["gancho"]}, fz)
    assert "[tema]" in e or "[respuesta]" in e, e


def test_cita_inexistente_o_fuente_inventada_se_detiene():
    fz = fuentes((LFPC, "92"))
    m = {"suficiente": True, "pregunta": SOL_T020["gancho"], "respuesta_corta": "Depende: si el producto falla tienes derecho a reposición o devolución.",
         "reglas": [{"conclusion": "Siempre puedes devolver cualquier producto.", "fuente": "F1", "cita_literal": "el consumidor siempre podrá devolver cualquier producto comprado",
                     "condiciones": [], "excepciones": []},
                    {"conclusion": "x", "fuente": "F9", "cita_literal": "texto de una fuente que no existe en la lista", "condiciones": []}]}
    e = errores(m, SOL_T020, fz)
    assert "[sustento]" in e and "F9" in e, e


def test_respuesta_indirecta_se_detiene():
    fz = fuentes((LFPC, "1"))
    m = {"suficiente": True, "pregunta": SOL_T020["gancho"], "respuesta_corta": "La ley protege a los consumidores en general.",
         "reglas": [{"conclusion": "Los derechos del consumidor son irrenunciables.", "fuente": "F1",
                     "cita_literal": "Sus disposiciones son irrenunciables y contra su observancia no podrán alegarse costumbres", "condiciones": [], "excepciones": []}]}
    assert "[respuesta]" in errores(m, SOL_T020, fz)


def test_analisis_correcto_de_T020v2_pasa():
    v2 = json.loads((AQUI / "datos" / "regresion" / "I20261026-T020v2.json").read_text())
    refs = []; ids = {}
    for r in v2["razonamiento"]["reglas"]:
        k = (r["ref"]["documento"], r["ref"]["articulo"])
        if k not in refs: refs.append(k)
    fz = fuentes(*[(d, a) for d, a in refs])
    inv = {(f["documento"], f["articulo"]): fid for fid, f in fz.items()}
    mapa = {"suficiente": True, **copy.deepcopy(v2["razonamiento"])}
    for r in mapa["reglas"]:
        r["fuente"] = inv[(r["ref"]["documento"], r["ref"]["articulo"])]; r.pop("ref")
    assert redactor.validar_mapa(mapa, SOL_T020, fz) == []


# ---------- integración con generar(): el análisis se valida antes de redactar y no se puede alterar ----------
def test_analisis_malo_no_llega_a_redaccion(tmp_path):
    malo = {**copy.deepcopy(ANALISIS), "pregunta": "¿Quién designa al Presidente de la institución?",
            "respuesta_corta": "Depende: lo designa el Secretario de Hacienda.", "reglas": []}
    sim = simulador_con(analizar=malo)
    with pytest.raises(redactor.Descartada) as e:
        redactor.generar(SOL, transporte, sim, env={}, archivo_uso=tmp_path / "u")
    assert "análisis jurídico" in str(e.value) and not e.value.transitoria
    assert len(sim.llamadas["analista"]) == 2 and sim.llamadas["redactor"] == []      # se corrigió una vez y nunca se redactó
    assert "corrígelos sin cambiar la pregunta" in sim.llamadas["analista"][1]


def test_textos_insuficientes_descartan_sin_redactar(tmp_path):
    sim = simulador_con(analizar={"suficiente": False, "limites": "el artículo no trata el tema"})
    with pytest.raises(redactor.Descartada) as e:
        redactor.generar(SOL, transporte, sim, env={}, archivo_uso=tmp_path / "u")
    assert "no bastan" in str(e.value) and sim.llamadas["redactor"] == []


def test_el_redactor_no_puede_cambiar_el_analisis(tmp_path):
    b = copy.deepcopy(BORRADOR); b["razonamiento"]["respuesta_corta"] = "Sí, siempre te pueden encarcelar."
    g = redactor.generar(SOL, transporte, simulador_con(redactar=b), env={}, archivo_uso=tmp_path / "u")
    assert g["razonamiento"]["respuesta_corta"] == ANALISIS["respuesta_corta"]
    assert g["generacion"]["metodo"] == "analisis_previo_v2_cobertura"


def test_objecion_del_auditor_al_analisis_lo_corrige(tmp_path):
    obj = {"veredicto": "con_objeciones", "conclusiones": [{"conclusion": "No hay prisión por deudas de carácter puramente civil.", "sostenida": "parcial", "motivo": "x"}],
           "objeciones": [{"problema": "conclusión parcial"}]}
    sim = simulador_con(auditar=lambda n: obj if n == 1 else {"veredicto": "sin_objeciones"})
    g = redactor.generar(SOL, transporte, sim, env={}, archivo_uso=tmp_path / "u")
    assert len(sim.llamadas["analista"]) == 2 and "corrige el ANÁLISIS" in sim.llamadas["analista"][1]
    assert g["auditoria_ia"]["veredicto"] == "sin_objeciones"


def test_suficiencia_se_juzga_contra_la_pregunta():
    """I20261212-T106 (31-10): «¿Te pueden negar un empleo por tu edad?» tiene respuesta literal en LFT 133 fr. I y el
    análisis la marcó insuficiente porque el texto no trae sanciones, denuncia ni prescripción (que la pregunta no pide)."""
    import redactor
    assert "NO marques false porque falten temas que la pregunta no pide" in redactor.ANALIZAR
