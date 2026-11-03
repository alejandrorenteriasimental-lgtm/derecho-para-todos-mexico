"""Versiones cortas SOLO para Instagram de Reels aprobados de más de IG_REEL_MAX_S (opción c del responsable, 3-11-2026).

· El guion corto vive en piezas/<ID>-IG/guion.json (lo redacta Claude a partir del guion aprobado: mismas fuentes y misma
  cita literal; solo se quita repetición). El Reel aprobado original NO se toca y sigue siendo el de Facebook, YouTube y TikTok.
· Este script verifica cada guion corto contra la fuente oficial (verificador, igual que el ciclo), lo produce con la misma
  voz, plantillas y música, lo respalda en el release privado y lo deja en estado/versiones_ig.json como
  PENDIENTE_APROBACION. Nada se publica hasta que el responsable apruebe cada versión (decidir.py aprobar <ID>-IG <versión>).
· Sin IA: no consume Gemini.
"""
import hashlib, json, os, sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import producir, verificador, respaldo

RAIZ = Path(__file__).resolve().parent.parent
REG = RAIZ / "estado" / "versiones_ig.json"


def huella(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    reg = json.loads(REG.read_text()) if REG.exists() else {}
    for gfile in sorted(RAIZ.glob("piezas/*-IG/guion.json")):
        pid = gfile.parent.name; hg = huella(gfile)
        if reg.get(pid, {}).get("huella_guion") == hg and reg[pid].get("estado") in ("PENDIENTE_APROBACION", "APROBADA", "RETENIDA"):
            continue                                   # ya producido con este mismo guion
        g = json.loads(gfile.read_text())
        ver = verificador.verificar_guion(g)
        r = {"de": g.get("version_instagram", {}).get("de"), "huella_guion": hg, "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        if ver["decision"] in ("RETENER", "RECHAZADA"):
            reg[pid] = {**r, "estado": "RETENIDA", "motivo": f'verificación: {ver["decision"]}'}; continue
        info, tec, jur = producir.producir(gfile.parent, ver)
        falla = [c["control"] for c in tec if c["resultado"] == "FALLA" and "TikTok" not in c["control"]]
        resp = respaldo.respaldar(pid, gfile.parent / "salida", os.environ)
        mp4 = f"{pid}_final.mp4"
        reg[pid] = {**r, "estado": "RETENIDA" if (falla or jur["decision"] not in ("APTO", "APTO_CON_CRITERIO")) else "PENDIENTE_APROBACION",
                    "duracion_s": info.get("duracion_s"), "sha256": info.get("sha256"), "asset_id": resp.get(mp4, {}).get("asset_id"),
                    "release": resp.get(mp4, {}).get("release"), "dictamen": jur["decision"], "fallas_tecnicas": falla}
        REG.write_text(json.dumps(reg, ensure_ascii=False, indent=1))
    REG.write_text(json.dumps(reg, ensure_ascii=False, indent=1))
    print(json.dumps({k: (v["estado"], v.get("duracion_s")) for k, v in reg.items()}, ensure_ascii=False, indent=1))


def aprobar(pid, sha12, por):
    """Registra la aprobación del responsable de una versión corta: estado APROBADA y entrada en estado/aprobaciones.jsonl
    (misma forma que decidir.py), con la versión = primeros 16 caracteres del SHA-256 del MP4 aprobado."""
    reg = json.loads(REG.read_text()); v = reg[pid]
    if not v.get("sha256", "").startswith(sha12) or len(sha12) < 12: raise SystemExit(f"{pid}: la huella {sha12} no es la del archivo producido")
    if v.get("estado") != "PENDIENTE_APROBACION": raise SystemExit(f"{pid}: estado {v.get('estado')}, no se puede aprobar")
    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    d = {"pieza": pid, "decision": "APROBADA", "version": v["sha256"][:16], "huella_archivo": v["sha256"], "por": {"nombre": por},
         "fecha": ahora, "canal": "chat", "nota": f"versión corta solo para Instagram de {v.get('de')}"}
    with (RAIZ / "estado" / "aprobaciones.jsonl").open("a") as h: h.write(json.dumps(d, ensure_ascii=False) + "\n")
    v.update(estado="APROBADA", aprobada=ahora, aprobada_por=por); REG.write_text(json.dumps(reg, ensure_ascii=False, indent=1))
    print(json.dumps(d, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "aprobar":
        aprobar(sys.argv[2], sys.argv[3], " ".join(sys.argv[4:]) or "responsable")
    else:
        main()
