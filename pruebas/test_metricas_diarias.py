"""Métricas diarias: solo lectura de registros; separan solicitudes, piezas producidas, auditadas y APROBADAS; la guardia
detiene el ciclo al llegar al tope propio de minutos."""
import json, sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sistema"))
import metricas_diarias as m


def _raiz(tmp_path):
    (tmp_path / "estado" / "solicitudes").mkdir(parents=True); (tmp_path / "registro").mkdir()
    for i, e in enumerate(["DESCARTADA", "GUION_LISTO", "SUPERSEDIDA", "PENDIENTE_GUION"]):
        (tmp_path / "estado" / "solicitudes" / f"s{i}.json").write_text(json.dumps({"estado": e}))
    h = lambda a, ts: {"a": a, "ts": ts}
    cola = {"trabajos": {
        "R1": {"formato": "reel", "estado": "REVISION_HUMANA", "historial": [h("PRODUCIDO", "2026-10-28T10:00:00+00:00"), h("REVISION_HUMANA", "2026-10-28T10:01:00+00:00")]},
        "I1": {"formato": "imagen", "estado": "APROBADO", "historial": [h("PRODUCIDO", "2026-10-28T10:05:00+00:00"), h("REVISION_HUMANA", "2026-10-28T10:06:00+00:00")]},
        "I0": {"formato": "imagen", "estado": "RETENIDO", "historial": [h("PRODUCIDO", "2026-10-26T10:00:00+00:00")]}}}
    (tmp_path / "estado" / "cola.json").write_text(json.dumps(cola))
    (tmp_path / "estado" / "aprobaciones.jsonl").write_text(
        json.dumps({"pieza": "I0", "decision": "RECHAZADA", "fecha": "2026-10-27T12:00:00+00:00"}) + "\n" +
        json.dumps({"pieza": "I1", "decision": "APROBADA", "fecha": "2026-10-28T15:00:00+00:00"}) + "\n")
    (tmp_path / "estado" / "uso_ia.jsonl").write_text("".join(json.dumps(x) + "\n" for x in [
        {"ts": "2026-10-28T10:00:00+00:00", "proveedor": "gemini", "resultado": "ok"},
        {"ts": "2026-10-28T10:00:01+00:00", "proveedor": "gemini", "resultado": "error", "error": "HTTP 429"},
        {"ts": "2026-10-28T10:00:02+00:00", "proveedor": "gemini", "resultado": "error", "error": "HTTP 500"},
        {"ts": "2026-10-28T10:00:03+00:00", "proveedor": "simulado", "resultado": "ok"}]))
    (tmp_path / "registro" / "consumo.jsonl").write_text(json.dumps({"ts": "2026-10-28T10:20:00Z", "segundos_ciclo": 1200, "costo_mxn": 0}) + "\n")
    return tmp_path


def test_distingue_etapas_y_cuenta_el_dia(tmp_path):
    r = m.calcular(hoy=date(2026, 10, 28), raiz=_raiz(tmp_path))
    assert r["1_producidas_nuevas"] == 2 and r["2_superaron_auditoria"] == 2 and r["3_aprobadas_por_responsable"] == 1
    assert r["4_tasa_aprobacion_acumulada"] == 0.5 and r["9_aprobadas_disponibles"] == {"reel": 0, "imagen": 1}
    assert r["6_gemini"] == {"utiles": 1, "rechazadas": 2, "cuota": 1, "errores_proveedor": 1}
    assert r["7_minutos_por_pieza_producida"] == 10.0 and r["8_costo_externo_mxn"] == 0
    e = r["embudo_acumulado"]
    assert e["solicitudes_efectivas"] == 3 and e["descartadas"] == 1 and e["borradores_guion_listo"] == 1 and e["aprobadas"] == 1 and e["rechazadas"] == 1
    assert r["10_lanzamiento_estimado"] is None          # sin aprobaciones de Reel no hay ritmo para estimar


def test_guardar_reemplaza_la_linea_del_mismo_dia(tmp_path):
    raiz = _raiz(tmp_path)
    for _ in range(2): m.guardar(m.calcular(hoy=date(2026, 10, 28), raiz=raiz), raiz=raiz)
    assert len((raiz / "registro" / "metricas_diarias.jsonl").read_text().splitlines()) == 1


def test_minutos_por_trabajo_redondeados_y_guardia(tmp_path, monkeypatch):
    class R:
        def __init__(s, d): s.d = d
        def __enter__(s): return s
        def __exit__(s, *a): pass
        def read(s): return json.dumps(s.d).encode()
    def abrir(req, timeout=30):
        u = req.full_url
        if "/jobs" in u:
            return R({"jobs": [{"started_at": "2026-10-28T10:00:00Z", "completed_at": "2026-10-28T10:06:10Z"},
                               {"started_at": "2026-10-28T10:07:00Z", "completed_at": None}]})
        return R({"workflow_runs": [{"id": 1}, {"id": 2}]})
    a = m.minutos_actions("o/r", "t", ahora=datetime(2026, 10, 28, tzinfo=timezone.utc), abrir=abrir)
    assert a["minutos"] == 14 and a["ejecuciones"] == 2 and a["dias_restantes"] == 4
    out = tmp_path / "out"; monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setenv("GITHUB_TOKEN", "t"); monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.setattr(m, "minutos_actions", lambda *x, **k: {"minutos": m.TOPE_PROPIO})
    monkeypatch.setattr(m, "guardar", lambda *x, **k: None); monkeypatch.setattr(m, "calcular", lambda **k: {k2: None for k2 in ("fecha", "1_producidas_nuevas", "2_superaron_auditoria", "9_aprobadas_disponibles", "10_lanzamiento_estimado")})
    m.main(["--guardia"])
    assert out.read_text().strip() == "continuar=false"
