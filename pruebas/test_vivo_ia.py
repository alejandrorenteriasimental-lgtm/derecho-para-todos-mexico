"""Pruebas EN VIVO de la infraestructura editorial: catálogo de GitHub Models, una llamada real mínima y la
disponibilidad de cada PDF oficial de data/ordenamientos.json. Requieren red y GITHUB_TOKEN (GitHub Actions)."""
import json, os, sys, urllib.request
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sistema"))
import modelos, verificador

pytestmark = pytest.mark.vivo
RAIZ = Path(__file__).resolve().parent.parent


def _catalogo():
    req = urllib.request.Request(modelos.config()["catalogo"], headers={"Authorization": f"Bearer {os.environ.get('GITHUB_TOKEN', '')}",
                                 "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(req, timeout=60) as r:
        crudo = r.read()
    Path("registro").mkdir(exist_ok=True); Path("registro/catalogo_crudo.txt").write_bytes(crudo[:4000])
    return {m["id"] for m in json.loads(crudo)}


def test_cada_rol_tiene_al_menos_un_modelo_del_catalogo():
    ids = _catalogo()
    Path("registro").mkdir(exist_ok=True); Path("registro/catalogo_modelos.json").write_text(json.dumps(sorted(ids), indent=1))
    for rol, r in modelos.config()["roles"].items():
        assert any(m in ids for m in r["modelos"]), f"{rol}: ninguno de {r['modelos']} está en el catálogo"


def test_llamada_real_minima_devuelve_json():
    m = modelos.Modelo("investigador")
    r = m.completar("Responde solo con JSON.", 'Devuelve {"ok": true}')
    assert r.get("ok") is True


@pytest.mark.parametrize("o", json.loads((RAIZ / "data/ordenamientos.json").read_text())["ordenamientos"], ids=lambda o: o["sigla"])
def test_pdf_oficial_existe_y_es_el_ordenamiento(o):
    estado, ctype, datos = verificador.transporte_http(o["url"], 120)
    assert estado == 200, f"{o['url']} → HTTP {estado}"
    cab, _ = verificador.texto_de(ctype, datos)
    assert verificador._plano(o["documento"]) in verificador._plano(cab), f"{o['url']} no parece «{o['documento']}»"
