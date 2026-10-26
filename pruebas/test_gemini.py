"""Cliente de la API de Gemini (nivel gratuito) sin red: formato de la solicitud, clave fuera de la URL y de los
registros, cercas ```json, reintento ante 429 por minuto, paso al siguiente modelo, modelos sin modo JSON (Gemma)."""
import io, json, sys, urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sistema"))
import modelos

CLAVE = "AIzaFALSA-0123456789"
CFG = {"proveedor": "github_models", "endpoint_gemini": "https://gen.example/v1beta", "pausa_429_s": 0,
       "roles": {"redactor": {"modelos": ["gemini:gemini-a", "gemini:gemini-b"], "tope_diario": 5, "max_tokens": 100, "temperatura": 0.2}}}


def resp(texto, thought=None):
    partes = ([{"text": thought, "thought": True}] if thought else []) + [{"text": texto}]
    return json.dumps({"candidates": [{"content": {"parts": partes}, "finishReason": "STOP"}],
                       "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5, "thoughtsTokenCount": 3}}).encode()


class R:
    def __init__(self, b): self.b = b
    def read(self): return self.b
    def __enter__(self): return self
    def __exit__(self, *a): pass


def http_error(code, cuerpo):
    return urllib.error.HTTPError("u", code, "x", {}, io.BytesIO(cuerpo.encode()))


@pytest.fixture
def llamadas(monkeypatch, tmp_path):
    log = []; guion = []
    def fake(req, timeout=0):
        log.append(req)
        acc = guion.pop(0)
        if isinstance(acc, Exception): raise acc
        return R(acc)
    monkeypatch.setattr(modelos.urllib.request, "urlopen", fake)
    monkeypatch.setattr(modelos, "USO", tmp_path / "uso.jsonl")
    return log, guion, tmp_path / "uso.jsonl"


def modelo(uso):
    return modelos.Modelo("redactor", CFG, {"GEMINI_API_KEY": CLAVE}, archivo_uso=uso)


def test_solicitud_bien_formada_y_clave_solo_en_encabezado(llamadas):
    log, guion, uso = llamadas; guion.append(resp('```json\n{"ok": 1}\n```', thought="pensando…"))
    assert modelo(uso).completar("SIS", "USR") == {"ok": 1}
    req = log[0]; cuerpo = json.loads(req.data)
    assert req.full_url == "https://gen.example/v1beta/models/gemini-a:generateContent" and CLAVE not in req.full_url
    assert req.get_header("X-goog-api-key") == CLAVE
    assert cuerpo["systemInstruction"]["parts"][0]["text"] == "SIS" and cuerpo["contents"][0]["parts"][0]["text"] == "USR"
    assert cuerpo["generationConfig"]["responseMimeType"] == "application/json"
    reg = json.loads(uso.read_text().splitlines()[-1])
    assert reg["proveedor"] == "gemini" and reg["modelo"] == "gemini-a" and reg["tokens_razonamiento"] == 3


def test_429_por_minuto_reintenta_y_luego_funciona(llamadas):
    log, guion, uso = llamadas
    guion += [http_error(429, '{"error": "RESOURCE_EXHAUSTED GenerateRequestsPerMinute"}'), resp('{"ok": 2}')]
    assert modelo(uso).completar("s", "u") == {"ok": 2} and len(log) == 2


def test_cuota_diaria_pasa_al_siguiente_modelo_sin_reintentar(llamadas):
    log, guion, uso = llamadas
    guion += [http_error(429, "quota GenerateRequestsPerDay exceeded"), resp('{"ok": 3}')]
    m = modelo(uso); assert m.completar("s", "u") == {"ok": 3} and m.ultimo_modelo == "gemini-b"
    assert [r.full_url.split("/")[-1] for r in log] == ["gemini-a:generateContent", "gemini-b:generateContent"]


def test_la_clave_nunca_queda_en_errores_ni_registros(llamadas):
    log, guion, uso = llamadas
    guion += [http_error(403, f"API key {CLAVE} not valid"), http_error(403, f"API key {CLAVE} not valid")]
    with pytest.raises(modelos.FallaModelo) as e:
        modelo(uso).completar("s", "u")
    assert CLAVE not in str(e.value) and CLAVE not in uso.read_text()


def test_modelo_sin_modo_json_se_reintenta_sin_el(llamadas):
    log, guion, uso = llamadas
    guion += [http_error(400, "JSON mode is not enabled for models/gemma-4-31b-it"), resp('Claro: {"veredicto": "sin_objeciones"}')]
    assert modelo(uso).completar("s", "u") == {"veredicto": "sin_objeciones"}
    assert "responseMimeType" not in json.loads(log[1].data)["generationConfig"]


def test_sin_clave_es_falla_transitoria_clara(llamadas):
    log, guion, uso = llamadas
    with pytest.raises(modelos.FallaModelo, match="GEMINI_API_KEY"):
        modelos.Modelo("redactor", CFG, {}, archivo_uso=uso).completar("s", "u")
    assert not log


def test_respuesta_bloqueada_o_vacia(llamadas):
    log, guion, uso = llamadas
    guion += [json.dumps({"promptFeedback": {"blockReason": "SAFETY"}}).encode(), resp("   ")]
    with pytest.raises(modelos.FallaModelo):
        modelo(uso).completar("s", "u")


def test_tope_propio_diario(llamadas):
    log, guion, uso = llamadas
    cfg = {**CFG, "roles": {"redactor": {**CFG["roles"]["redactor"], "tope_diario": 1, "modelos": ["gemini:gemini-a"]}}}
    guion.append(resp('{"a": 1}'))
    m = modelos.Modelo("redactor", cfg, {"GEMINI_API_KEY": CLAVE}, archivo_uso=uso)
    m.completar("s", "u")
    with pytest.raises(modelos.CuotaAgotada):
        m.completar("s", "u")
    assert len(log) == 1
