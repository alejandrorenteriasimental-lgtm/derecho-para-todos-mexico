"""Pruebas de extremo a extremo del ciclo autónomo con fuentes y Meta simuladas (sin red, sin costo).
La producción audiovisual se sustituye por un doble que escribe un MP4 ficticio: aquí se prueba el flujo de estados,
no el render (el render se prueba con la pieza real T073)."""
import copy, json, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sistema"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ciclo, cola, publicar, producir, auditoria, verificador
from fixtures import pdf_ley, LIT17
from meta_falsa import MetaFalsa
from test_publicacion import ENV

URL = "https://www.diputados.gob.mx/LeyesBiblio/pdf/CPEUM.pdf"
GUION = {
    "id": "X1", "formato": "reel", "titulo": "¿Cárcel por deudas?", "riesgo": "bajo",
    "fuentes": {"F1": {"nivel": "oficial", "url": URL, "documento": "Constitución Política de los Estados Unidos Mexicanos",
                       "articulo": "17", "texto_literal": LIT17, "cita": "CPEUM, artículo 17", "consultado": "2026-10-25"}},
    "escenas": [
        {"tipo": "gancho", "texto": "¿Te pueden meter a la cárcel por deber dinero? La respuesta está en la Constitución.", "titulo": ["¿CÁRCEL", "POR DEUDAS?"], "afirmaciones": []},
        {"tipo": "cita", "texto": "El artículo diecisiete dice: nadie puede ser aprisionado por deudas de carácter puramente civil.",
         "cita": LIT17, "etiqueta": "Constitución, artículo 17",
         "afirmaciones": [{"id": "A1", "tipo": "hecho_normativo", "fuente": "F1", "comparar_literal": True}]},
        {"tipo": "titular", "texto": "Es una de las garantías más antiguas de nuestro sistema jurídico y sigue vigente hoy.", "titulo": ["SIGUE", "VIGENTE"], "afirmaciones": []},
        {"tipo": "cierre", "texto": "Esto es información general, no asesoría legal. Síguenos para entender tus derechos y compartir lo que aprendes.",
         "aviso": "Información general, no asesoría legal.", "afirmaciones": []},
    ],
}
DOC = pdf_ley()


def fuentes_ok(url, timeout=60): return 200, "application/pdf", DOC
def fuentes_caidas(url, timeout=60): raise verificador.SinConexion("sin red (simulada)")


@pytest.fixture
def raiz(tmp_path, monkeypatch):
    (tmp_path / "piezas" / "X1").mkdir(parents=True)
    (tmp_path / "piezas" / "X1" / "guion.json").write_text(json.dumps(GUION, ensure_ascii=False))
    monkeypatch.setattr(ciclo, "RAIZ", tmp_path)
    monkeypatch.setattr(cola, "COLA", tmp_path / "estado" / "cola.json")
    monkeypatch.setattr(cola, "BITACORA", tmp_path / "estado" / "bitacora.jsonl")
    monkeypatch.setattr(cola, "LOCK", tmp_path / "estado" / "lock.json")
    monkeypatch.setattr(publicar, "LIBRO", tmp_path / "estado" / "operaciones.jsonl")
    llamadas = []
    def producir_doble(carpeta, verificacion=None):
        g = json.loads((carpeta / "guion.json").read_text()); llamadas.append(g["id"])
        out = carpeta / "salida"; out.mkdir(exist_ok=True); (out / f'{g["id"]}_final.mp4').write_bytes(b"\x00" * 4096)
        jur = auditoria.dictamen(g, verificacion or verificador.verificar_guion(g, fuentes_ok), datetime.now(timezone.utc).date())
        return {"duracion_s": 30.0, "estado": jur["decision"]}, [], jur
    monkeypatch.setattr(producir, "producir", producir_doble)
    class R(type(tmp_path)): pass
    r = R(tmp_path); r.producidas = llamadas
    return r


def estado(r, pid="X1"): return cola.cargar()["trabajos"][pid]


def test_flujo_completo_en_simulacion(raiz):
    r = ciclo.ciclo("t", fuentes_ok, env={})
    t = estado(raiz)
    assert r["simuladas"] == ["X1"] and t["estado"] == "SIMULADO" and t["publicaciones"] == {}
    assert (raiz / "piezas/X1/salida/verificacion.json").exists()


def test_segundo_ciclo_no_reproduce_ni_republica(raiz):
    ciclo.ciclo("t", fuentes_ok, env={}); ciclo.ciclo("t", fuentes_ok, env={})
    assert raiz.producidas == ["X1"] and estado(raiz)["estado"] == "SIMULADO"


def test_guion_incompleto_se_retiene_sin_producir(raiz):
    g = copy.deepcopy(GUION); del g["escenas"][-1]; g["escenas"][0]["texto"] = ""
    (raiz / "piezas/X1/guion.json").write_text(json.dumps(g, ensure_ascii=False))
    ciclo.ciclo("t", fuentes_ok, env={})
    t = estado(raiz)
    assert t["estado"] == "RETENIDO" and "guion incompleto" in t["historial"][-1]["motivo"] and raiz.producidas == []


def test_guion_corregido_vuelve_a_pendiente(raiz):
    g = copy.deepcopy(GUION); del g["escenas"][-1]
    (raiz / "piezas/X1/guion.json").write_text(json.dumps(g, ensure_ascii=False))
    ciclo.ciclo("t", fuentes_ok, env={})
    (raiz / "piezas/X1/guion.json").write_text(json.dumps(GUION, ensure_ascii=False))
    ciclo.ciclo("t", fuentes_ok, env={})
    assert estado(raiz)["estado"] == "SIMULADO"


def test_red_caida_retiene_y_reverifica_despues(raiz):
    ciclo.ciclo("t", fuentes_caidas, env={})
    t = estado(raiz); assert t["estado"] == "RETENIDO" and t["retencion"]["tipo"] == "transitorio" and raiz.producidas == []
    c = cola.cargar(); c["trabajos"]["X1"]["retencion"]["desde"] = (datetime.now(timezone.utc) - timedelta(hours=7)).isoformat(); cola.guardar(c)
    ciclo.ciclo("t", fuentes_ok, env={})
    assert estado(raiz)["estado"] == "SIMULADO"


def test_fuente_falsa_retiene_de_forma_sustantiva(raiz):
    g = copy.deepcopy(GUION); g["fuentes"]["F1"]["url"] = "https://diputados.gob.mx.copia-falsa.net/CPEUM.pdf"
    (raiz / "piezas/X1/guion.json").write_text(json.dumps(g, ensure_ascii=False))
    ciclo.ciclo("t", fuentes_ok, env={})
    t = estado(raiz)
    assert t["estado"] == "RETENIDO" and t["retencion"]["tipo"] == "sustantivo" and raiz.producidas == []


def test_cita_incorrecta_no_se_produce(raiz):
    g = copy.deepcopy(GUION); g["fuentes"]["F1"]["texto_literal"] = "Nadie puede ser aprisionado por deudas de ninguna clase."
    (raiz / "piezas/X1/guion.json").write_text(json.dumps(g, ensure_ascii=False))
    ciclo.ciclo("t", fuentes_ok, env={})
    assert estado(raiz)["estado"] == "RETENIDO" and raiz.producidas == []


def test_modo_real_programa_y_no_duplica(raiz):
    meta = MetaFalsa()
    ciclo.ciclo("t", fuentes_ok, meta, env=ENV)
    t = estado(raiz)
    assert t["estado"] == "PROGRAMADO" and t["publicaciones"]["facebook"]["video_id"] == "V1"
    n = len(meta.llamadas); ciclo.ciclo("t", fuentes_ok, meta, env=ENV)
    assert len(meta.llamadas) == n and len(meta.publicaciones_visibles()) == 1


def test_modo_real_respuesta_ambigua_se_resuelve_en_el_siguiente_ciclo(raiz):
    meta = MetaFalsa(); meta.fallar("finish", "red_despues")
    ciclo.ciclo("t", fuentes_ok, meta, env=ENV)
    assert estado(raiz)["estado"] == "PUBLICANDO"
    ciclo.ciclo("t", fuentes_ok, meta, env=ENV)
    assert estado(raiz)["estado"] == "PROGRAMADO" and len(meta.publicaciones_visibles()) == 1


def test_sin_autorizacion_de_lanzamiento_aunque_haya_secretos(raiz):
    meta = MetaFalsa(); env = {k: v for k, v in ENV.items() if k != "LANZAMIENTO_AUTORIZADO"}
    ciclo.ciclo("t", fuentes_ok, meta, env=env)
    assert estado(raiz)["estado"] == "SIMULADO" and meta.llamadas == []


def test_bloqueo_impide_dos_ciclos_simultaneos(raiz):
    assert cola.adquirir_lock("otro")
    assert ciclo.ciclo("t", fuentes_ok, env={})["resultado"] == "bloqueado"


# ---------- redacción autónoma dentro del ciclo ----------
import imagen as _imagen
from test_redactor import simulador_con, BORRADOR


def _sim_dos_formatos():
    img = {"titular": "¿Te pueden encarcelar por una deuda?", "bajada": "La Constitución prohíbe la prisión por deudas de carácter puramente civil.",
           "cita_literal_destacada": "Nadie puede ser aprisionado por deudas de carácter puramente civil", "fuente_cita": "F1",
           "ojo": "Cobrar una deuda por la vía legal sí es válido.", "puntos": ["Una deuda civil no es delito", "Pueden cobrarte ante un juez", "Engañar sí puede ser delito"],
           "mito": "Si debo dinero me pueden meter a la cárcel.", "realidad": "La Constitución prohíbe la prisión por deudas de carácter puramente civil.",
           "columnas": [["Deuda civil", "Se cobra ante un juez; no lleva a prisión."], ["Fraude", "Engañar para obtener dinero puede ser delito."]],
           "copy": "Una deuda civil no te lleva a la cárcel.\n\nLo dice el artículo 17 de la Constitución.\n\nGuárdalo y compártelo.", "alt": "Pieza sobre deudas",
           "razonamiento": {"pregunta": "¿Te pueden encarcelar por una deuda?", "respuesta_corta": "No, la Constitución prohíbe la prisión por deudas de carácter puramente civil.", "reglas": [{"conclusion": "No hay prisión por deudas de carácter puramente civil.", "fuente": "F1", "cita_literal": "Nadie puede ser aprisionado por deudas de carácter puramente civil", "condiciones": [], "excepciones": []}], "distinciones": [{"a": "deuda civil", "b": "fraude", "diferencia": "El fraude es un delito; no pagar no lo es."}], "limites": "", "elementos": [{"elemento": "efecto", "estado": "cubierto", "respuesta": "La Constitución prohíbe la prisión por deudas de carácter puramente civil.", "fuente": "F1", "cita_literal": "Nadie puede ser aprisionado por deudas de carácter puramente civil"}]},
           "afirmaciones": [{"fuente": "F1", "tipo": "hecho_normativo", "texto": "No hay cárcel por deudas civiles",
                             "cita_literal": "Nadie puede ser aprisionado por deudas de carácter puramente civil"}]}
    return simulador_con(investigar={"articulos": [{"sigla": "CPEUM", "articulo": "17"}]},
                         redactar=lambda n: img if "imagen fija" in sim_ultimo[0] else BORRADOR)


sim_ultimo = [""]


@pytest.fixture
def raiz_vacia(raiz, monkeypatch):
    (raiz / "piezas" / "X1" / "guion.json").unlink(); (raiz / "piezas" / "X1").rmdir()
    monkeypatch.setattr(_imagen, "RAIZ", raiz)
    from datetime import date
    monkeypatch.setattr(ciclo, "_hoy_mx", lambda: date(2026, 10, 26))   # planeación determinista (los temas dependen de la fecha)
    return raiz


def test_ciclo_redacta_produce_y_simula_ambos_formatos(raiz_vacia):
    base = _sim_dos_formatos()
    def sim(rol, sistema, usuario):
        sim_ultimo[0] = usuario; return base(rol, sistema, usuario)
    r = ciclo.ciclo("t", fuentes_ok, env={}, simulador=sim)
    assert len(r["redactadas"]) == 2 and not r["errores"], r
    assert sorted(t["formato"] for t in cola.cargar()["trabajos"].values()) == ["imagen", "reel"]
    assert all(t["estado"] == "REVISION_HUMANA" for t in cola.cargar()["trabajos"].values()), [(t["id"], t["estado"], t["historial"][-1:]) for t in cola.cargar()["trabajos"].values()]
    assert any((raiz_vacia / "piezas").glob("I*/salida/*.png"))
    # sin aprobación humana no avanza (la aprobación por Telegram se prueba en test_revision.py)
    ciclo.ciclo("t", fuentes_ok, env={}, simulador=sim)
    assert all(t["estado"] == "REVISION_HUMANA" for t in cola.cargar()["trabajos"].values())
    m = json.loads((raiz_vacia / "estado" / "respaldo.json").read_text())        # respaldo con huella de cada archivo
    assert all(any(k.endswith((".png", ".mp4")) for k in v) for v in m.values()), m


def test_sin_revision_obligatoria_va_directo_a_simulacion(raiz_vacia):
    base = _sim_dos_formatos()
    def sim(rol, sistema, usuario):
        sim_ultimo[0] = usuario; return base(rol, sistema, usuario)
    ciclo.ciclo("t", fuentes_ok, env={"REVISION_HUMANA_OBLIGATORIA": "0"}, simulador=sim)
    assert all(t["estado"] == "SIMULADO" for t in cola.cargar()["trabajos"].values())


def test_tema_que_no_supera_la_auditoria_se_descarta_y_se_intenta_otro(raiz_vacia):
    base = simulador_con(investigar={"articulos": [{"sigla": "CPEUM", "articulo": "17"}]},
                         auditar={"veredicto": "con_objeciones", "objeciones": [{"problema": "no sustentado"}]})
    r = ciclo.ciclo("t", fuentes_ok, env={}, simulador=base)
    assert r["redactadas"] == [] and len(r["descartadas"]) == 6      # 3 temas por formato, todos descartados
    assert not any(t["estado"] in ("SIMULADO", "APROBADO") for t in cola.cargar()["trabajos"].values())


def test_sin_red_no_quema_temas(raiz_vacia):
    r = ciclo.ciclo("t", fuentes_caidas, env={}, simulador=_sim_dos_formatos())
    sols = [json.loads(f.read_text()) for f in (raiz_vacia / "estado" / "solicitudes").glob("*.json")]
    assert r["descartadas"] == [] and all(s["estado"] == "PENDIENTE_GUION" for s in sols)


def test_version_corta_ig_no_entra_a_la_cola_ni_se_reproduce(raiz):
    """Regresión 3-11-2026: piezas/<ID>-IG las gestiona version_ig.py; el ciclo no debe encolarlas, re-producirlas ni sobrescribir su salida."""
    g = copy.deepcopy(GUION); g["id"] = "X1-IG"
    (raiz / "piezas" / "X1-IG").mkdir(); (raiz / "piezas/X1-IG/guion.json").write_text(json.dumps(g, ensure_ascii=False))
    ciclo.ciclo("t", fuentes_ok, env={})
    assert "X1-IG" not in cola.cargar()["trabajos"] and "X1-IG" not in raiz.producidas
    assert not (raiz / "piezas/X1-IG/salida").exists()


def test_version_corta_ig_ya_encolada_sale_de_la_cola(raiz):
    c = cola.cargar(); cola.encolar(c, "X1-IG"); cola.guardar(c)
    ciclo.ciclo("t", fuentes_ok, env={})
    assert "X1-IG" not in cola.cargar()["trabajos"]


def test_version_larga_tiktok_no_entra_a_la_cola_ni_se_publica(raiz):
    """16-11-2026: piezas/<ID>-TT las produce y registra tiktok_largo.py; si el ciclo las encolara, al aprobarse las
    publicaría como pieza suelta en Facebook. No se encolan, no se re-producen y salen de la cola si ya estaban."""
    g = copy.deepcopy(GUION); g["id"] = "X1-TT"; g["variante"] = "tiktok"
    (raiz / "piezas" / "X1-TT").mkdir(); (raiz / "piezas/X1-TT/guion.json").write_text(json.dumps(g, ensure_ascii=False))
    c = cola.cargar(); cola.encolar(c, "X2-TT"); cola.guardar(c)
    ciclo.ciclo("t", fuentes_ok, env={})
    trabajos = cola.cargar()["trabajos"]
    assert "X1-TT" not in trabajos and "X2-TT" not in trabajos and "X1-TT" not in raiz.producidas
    assert not (raiz / "piezas/X1-TT/salida").exists()
    assert ciclo.es_derivada("R20261214-T108-TT") and ciclo.es_derivada("R20261123-T031-IG") and not ciclo.es_derivada("R20261214-T108")
