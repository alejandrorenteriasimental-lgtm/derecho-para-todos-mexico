import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sistema"))
import publicar


def test_token_de_pagina_desde_usuario_del_sistema():
    publicar._TOKEN_CACHE.clear(); llamadas = []
    def http(m, url, *a, **k):
        llamadas.append(url); return 200, json.dumps({"access_token": "PAGINA", "id": "1"}).encode()
    env = {"META_SYSTEM_TOKEN": "SIS", "META_PAGE_ID": "1", "META_PAGE_TOKEN": "VIEJO"}
    assert publicar.token_pagina(env, http) == "PAGINA"
    assert publicar.token_pagina(env, http) == "PAGINA" and len(llamadas) == 1      # se reutiliza en la ejecución
    assert "fields=access_token" in llamadas[0]


def test_sin_usuario_del_sistema_usa_el_token_de_pagina():
    publicar._TOKEN_CACHE.clear()
    assert publicar.token_pagina({"META_PAGE_TOKEN": "T", "META_PAGE_ID": "1"}) == "T"


def test_error_si_el_usuario_del_sistema_no_tiene_la_pagina():
    publicar._TOKEN_CACHE.clear()
    import pytest
    with pytest.raises(publicar.ErrorGraph):
        publicar.token_pagina({"META_SYSTEM_TOKEN": "S", "META_PAGE_ID": "1"}, lambda *a, **k: (200, b'{"id": "1"}'))


def test_modo_real_acepta_token_del_sistema():
    env = {"PUBLICAR": "1", "LANZAMIENTO_AUTORIZADO": "SI", "META_PAGE_ID": "1", "META_SYSTEM_TOKEN": "S"}
    assert publicar.modo_operacion(env)[0] == "real"
