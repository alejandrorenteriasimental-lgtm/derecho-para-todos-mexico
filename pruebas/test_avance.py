import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sistema"))
import avance

OK = {"version": "v", "sha256": "s", "asset_id": 1}


def test_cuenta_solo_piezas_completas_y_huecos():
    cal = {"dias": [{"fecha": "2026-11-23", "imagen": OK, "reel": OK},
                    {"fecha": "2026-11-24", "imagen": OK, "reel": {"version": "v"}},   # Reel sin huella: no cuenta
                    {"fecha": "2026-11-25", "imagen": OK, "reel": OK}]}
    r = avance.calcular(cal, {"trabajos": {"a": {"estado": "PENDIENTE"}}})
    assert r["terminadas"] == {"imagen": 3, "reel": 2}
    assert r["faltan"] == {"imagen": 87, "reel": 88}
    assert r["total"] == "5/180"
    assert r["cubierto_sin_huecos_hasta"] == "2026-11-23"
    assert "2026-11-24 reel" in r["huecos_proximos"]
    assert len(r["quincenas"]) == 6 and r["quincenas"][0]["imagen"] == 3
    assert "Terminadas: 5/180" in avance.markdown(r)


def test_fuera_del_periodo_no_cuenta():
    r = avance.calcular({"dias": [{"fecha": "2027-02-21", "imagen": OK, "reel": OK}]}, {})
    assert r["total"] == "0/180" and r["cubierto_sin_huecos_hasta"] is None
