"""Pruebas de publicación: simulación vs. real, idempotencia, recuperación tras fallas y respuestas ambiguas de Meta."""
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sistema"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import publicar, cola, presupuesto
from meta_falsa import MetaFalsa

ENV = {"PUBLICAR": "1", "LANZAMIENTO_AUTORIZADO": "SI", "META_PAGE_ID": "PAGE1", "META_PAGE_TOKEN": "TOKEN-SECRETO"}
HUELLA = "a1b2c3d4e5f6" * 5


@pytest.fixture
def entorno(tmp_path):
    mp4 = tmp_path / "x.mp4"; mp4.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"v" * 5000)
    return {"mp4": mp4, "libro": tmp_path / "ops.jsonl", "meta": MetaFalsa()}


def pub(e, **kw):
    return publicar.publicar_reel("T1", e["mp4"], "Título", HUELLA, kw.pop("prog", 1_900_000_000), modo=kw.pop("modo", "real"),
                                  env=ENV, http=e["meta"], libro=e["libro"], **kw)


# ---------- modo y separación de estados ----------
@pytest.mark.parametrize("env,esperado", [
    ({}, "simulacion"),
    ({"PUBLICAR": "1"}, "simulacion"),
    ({"PUBLICAR": "1", "LANZAMIENTO_AUTORIZADO": "SI"}, "simulacion"),           # faltan secretos
    ({"PUBLICAR": "0", **{k: v for k, v in ENV.items() if k != "PUBLICAR"}}, "simulacion"),
    (ENV, "real"),
])
def test_modo_operacion(env, esperado):
    assert publicar.modo_operacion(env)[0] == esperado


def test_simulacion_no_llama_a_meta_ni_guarda_ids(entorno):
    r = publicar.publicar_reel("T1", entorno["mp4"], "Título", HUELLA, 1_900_000_000, env={}, http=entorno["meta"], libro=entorno["libro"])
    assert r["estado"] == "SIMULADO" and not entorno["meta"].llamadas and "video_id" not in r
    assert publicar.operacion(r["marca"], "real", entorno["libro"]) is None   # nada cuenta como operación real


def test_cola_no_permite_programado_o_publicado_sin_modo_real(tmp_path):
    cola.COLA, cola.BITACORA = tmp_path / "c.json", tmp_path / "b.jsonl"
    c = cola.cargar(); cola.encolar(c, "X"); cola.mover(c, "X", "PRODUCIDO"); cola.mover(c, "X", "APROBADO")
    for destino in ("PUBLICANDO", "PROGRAMADO", "PUBLICADO"):
        with pytest.raises(ValueError):
            cola.mover(c, "X", destino)
    cola.mover(c, "X", "SIMULADO"); assert c["trabajos"]["X"]["estado"] == "SIMULADO" and c["trabajos"]["X"]["publicaciones"] == {}


# ---------- camino real ----------
def test_camino_real_programa_y_confirma(entorno):
    r = pub(entorno)
    assert r["estado"] == "PROGRAMADO" and r["video_id"] == "V1" and len(entorno["meta"].publicaciones_visibles()) == 1


def test_token_nunca_va_en_la_url(entorno):
    pub(entorno)
    assert all("access_token" not in u and "TOKEN-SECRETO" not in u for _, u in entorno["meta"].llamadas)


def test_usa_el_upload_url_devuelto_por_start(entorno):
    pub(entorno)
    assert any("sesion=x" in u for _, u in entorno["meta"].llamadas)


def test_segunda_ejecucion_no_duplica(entorno):
    pub(entorno); r = pub(entorno)
    assert r["origen"] == "libro" and entorno["meta"].llamadas_a("rupload") == 1 and len(entorno["meta"].videos) == 1


def test_libro_perdido_pero_marca_en_la_pagina_se_recupera(entorno):
    pub(entorno, prog=None)                     # publicado inmediato (aparece en /video_reels)
    entorno["libro"].unlink()
    r = pub(entorno, prog=None)
    assert r["origen"] == "recuperada_por_marca" and len(entorno["meta"].videos) == 1


def test_busqueda_de_marca_sigue_la_paginacion(entorno):
    m = entorno["meta"]; m.paginar_cada = 2
    for i in range(5):   # cinco reels ajenos publicados antes
        m.videos[f"V9{i}"] = {"bytes": 1, "total": 1, "estado": "published", "descripcion": f"otro {i}", "expirada": False}
    pub(entorno, prog=None); entorno["libro"].unlink()
    assert pub(entorno, prog=None)["origen"] == "recuperada_por_marca"


def test_caida_durante_la_subida_se_reanuda_en_la_misma_sesion(entorno):
    entorno["meta"].fallar("upload", "red_antes")
    with pytest.raises(publicar.SinRed):
        pub(entorno)
    r = pub(entorno)
    assert r["estado"] == "PROGRAMADO"
    assert len(entorno["meta"].videos) == 1                                                      # una sola sesión


def test_finish_aplicado_pero_respuesta_perdida_no_duplica(entorno):
    entorno["meta"].fallar("finish", "red_despues")
    with pytest.raises(publicar.PublicacionAmbigua):
        pub(entorno)
    assert publicar.operacion("#dpt-t1-" + HUELLA[:8], "real", entorno["libro"])["fase"] == "AMBIGUA"
    r = pub(entorno)
    assert r["origen"] == "recuperada_por_estado" and len(entorno["meta"].publicaciones_visibles()) == 1


def test_finish_no_aplicado_se_reintenta_sobre_el_mismo_video(entorno):
    entorno["meta"].fallar("finish", "red_antes")
    with pytest.raises(publicar.PublicacionAmbigua):
        pub(entorno)
    r = pub(entorno)
    assert r["estado"] == "PROGRAMADO" and len(entorno["meta"].videos) == 1


@pytest.mark.parametrize("efecto", ["500", "html", "vacio"])
def test_respuestas_ambiguas_de_finish(entorno, efecto):
    entorno["meta"].fallar("finish", efecto)
    with pytest.raises(publicar.PublicacionAmbigua):
        pub(entorno)
    assert pub(entorno)["estado"] == "PROGRAMADO" and len(entorno["meta"].publicaciones_visibles()) == 1


def test_subida_sin_success_no_finaliza(entorno):
    entorno["meta"].fallar("upload", "sin_exito")
    with pytest.raises(publicar.ErrorGraph):
        pub(entorno)
    assert entorno["meta"].publicaciones_visibles() == []


def test_token_invalido_es_error_permanente(entorno):
    entorno["meta"].fallar("start", "token")
    with pytest.raises(publicar.ErrorGraph) as e:
        pub(entorno)
    assert not e.value.transitorio and entorno["meta"].publicaciones_visibles() == []


def test_limite_de_tasa_es_transitorio(entorno):
    entorno["meta"].fallar("start", "limite")
    with pytest.raises(publicar.ErrorGraph) as e:
        pub(entorno)
    assert e.value.transitorio


def test_sesion_expirada_se_abandona_y_crea_una_nueva(entorno):
    entorno["meta"].fallar("upload", "red_antes")
    with pytest.raises(publicar.SinRed):
        pub(entorno)
    entorno["meta"].videos["V1"]["expirada"] = True
    r = pub(entorno)
    assert r["video_id"] == "V2" and len(entorno["meta"].publicaciones_visibles()) == 1


# ---------- imagen fija ----------
def pub_img(e, **kw):
    png = e["mp4"].with_suffix(".png"); png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"i" * 3000)
    return publicar.publicar_imagen("I1", png, "Copy de prueba", HUELLA, kw.pop("prog", 1_900_000_000), modo=kw.pop("modo", "real"),
                                    env=ENV, http=e["meta"], libro=e["libro"])


def test_imagen_simulada(entorno):
    assert pub_img(entorno, modo="simulacion")["estado"] == "SIMULADO" and not entorno["meta"].llamadas


def test_imagen_real_y_segunda_ejecucion(entorno):
    assert pub_img(entorno)["estado"] == "PROGRAMADO"
    assert pub_img(entorno)["origen"] == "libro" and len(entorno["meta"].fotos) == 1


def test_imagen_respuesta_perdida_se_recupera_por_marca(entorno):
    entorno["meta"].fallar("photos", "red_despues")
    with pytest.raises(publicar.PublicacionAmbigua):
        pub_img(entorno)
    assert pub_img(entorno)["origen"] == "recuperada_por_marca" and len(entorno["meta"].fotos) == 1


def test_imagen_ambigua_sin_rastro_no_se_reintenta_a_ciegas(entorno):
    entorno["meta"].fallar("photos", "red_antes")
    with pytest.raises(publicar.PublicacionAmbigua):
        pub_img(entorno)
    with pytest.raises(publicar.ErrorGraph):
        pub_img(entorno)
    assert entorno["meta"].fotos == []


# ---------- presupuesto ----------
def test_presupuesto_cero_rechaza_cualquier_gasto(tmp_path):
    with pytest.raises(presupuesto.PresupuestoExcedido):
        presupuesto.autorizar(0.01, "prueba", env={"TOPE_MXN_MES": "0"}, archivo=tmp_path / "g.jsonl")
    assert presupuesto.autorizar(0, "gratuito", env={}, archivo=tmp_path / "g.jsonl")


@pytest.mark.parametrize("valor", ["", "abc", "-50", None])
def test_tope_ilegible_o_negativo_es_cero(valor):
    assert presupuesto.tope({"TOPE_MXN_MES": valor} if valor is not None else {}) == 0.0
