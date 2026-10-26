"""Pruebas EN VIVO de la infraestructura editorial: modelos de Gemini disponibles para la clave del proyecto, una
llamada real mínima por rol y la disponibilidad de cada PDF oficial de data/ordenamientos.json. Requieren red y el
secreto GEMINI_API_KEY (GitHub Actions). Las pruebas de GitHub Models solo corren si algún rol lo usa."""
import json, os, sys, urllib.request
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sistema"))
import modelos, verificador

pytestmark = pytest.mark.vivo
RAIZ = Path(__file__).resolve().parent.parent


def _entradas():
    return [(rol, m.split(":", 1) if ":" in m else (modelos.config()["proveedor"], m))
            for rol, r in modelos.config()["roles"].items() for m in r["modelos"]]


USA_GITHUB = any(p == "github_models" for _, (p, _) in _entradas())
sin_clave = pytest.mark.skipif(not os.environ.get("GEMINI_API_KEY"), reason="falta el secreto GEMINI_API_KEY")


def _catalogo_gemini():
    """Nombres de modelo visibles para la clave (la clave va en el encabezado; el registro solo guarda nombres)."""
    nombres, token = [], ""
    for _ in range(10):
        url = modelos.config()["endpoint_gemini"] + "/models?pageSize=200" + (f"&pageToken={token}" if token else "")
        req = urllib.request.Request(url, headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]})
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read())
        nombres += [m["name"].split("/", 1)[1] for m in d.get("models", []) if "generateContent" in m.get("supportedGenerationMethods", [])]
        token = d.get("nextPageToken")
        if not token: break
    Path("registro").mkdir(exist_ok=True); Path("registro/catalogo_gemini.json").write_text(json.dumps(sorted(nombres), indent=1))
    return set(nombres)


@sin_clave
def test_cada_rol_tiene_al_menos_un_modelo_gemini_disponible():
    ids = _catalogo_gemini()
    for rol, r in modelos.config()["roles"].items():
        g = [m.split(":", 1)[1] for m in r["modelos"] if m.startswith("gemini:")]
        assert any(m in ids for m in g), f"{rol}: ninguno de {g} aparece para esta clave"


@sin_clave
@pytest.mark.parametrize("rol", ["investigador", "redactor", "auditor"])
def test_llamada_real_minima_devuelve_json(rol):
    m = modelos.Modelo(rol)
    r = m.completar("Responde solo con JSON.", 'Devuelve exactamente {"ok": true}')
    assert r.get("ok") is True, r


@pytest.mark.skipif(not USA_GITHUB, reason="ningún rol usa GitHub Models")
def test_github_models_responde():
    m = modelos.Modelo("investigador", {**modelos.config(), "roles": {"investigador": {"modelos": ["github_models:openai/gpt-4.1-mini"], "tope_diario": 3}}})
    assert m.completar("Responde solo con JSON.", 'Devuelve {"ok": true}').get("ok") is True


@pytest.mark.parametrize("o", json.loads((RAIZ / "data/ordenamientos.json").read_text())["ordenamientos"], ids=lambda o: o["sigla"])
def test_pdf_oficial_existe_y_es_el_ordenamiento(o):
    estado, ctype, datos = verificador.transporte_http(o["url"], 120)
    assert estado == 200, f"{o['url']} → HTTP {estado}"
    cab, _ = verificador.texto_de(ctype, datos)
    assert verificador._plano(o["documento"]) in verificador._plano(cab), f"{o['url']} no parece «{o['documento']}»"
