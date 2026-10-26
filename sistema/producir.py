"""Orquestador de una pieza: narración → música → render → mezcla → auditorías → registro.
Uso: python3 sistema/producir.py piezas/T073"""
import json, subprocess, sys, time
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import narracion, musica, render, auditoria, verificador

RAIZ = Path(__file__).resolve().parent.parent
REGISTRO = RAIZ / "registro" / "piezas.jsonl"
COSTO_MIN_RUNNER = 0.006  # USD por minuto, runner Linux de GitHub fuera de los 2,000 min gratis


def etapa(nombre, tiempos):
    class _E:
        def __enter__(s): s.t = time.time()
        def __exit__(s, *x): tiempos[nombre] = round(time.time() - s.t, 1)
    return _E()


def huella_guion(guion: dict) -> str:
    """Huella estable del contenido aprobado (no del MP4): identifica la pieza en el libro de operaciones."""
    import hashlib
    return hashlib.sha256(json.dumps(guion, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def producir(carpeta: Path, verificacion=None):
    guion = json.loads((carpeta / "guion.json").read_text())
    out = carpeta / "salida"; out.mkdir(exist_ok=True)
    tiempos = {}
    with etapa("auditoria_juridica", tiempos):
        if verificacion is None:
            verificacion = verificador.verificar_guion(guion)
        jur = auditoria.dictamen(guion, verificacion, date.today())
        (out / "verificacion.json").write_text(json.dumps(verificacion, ensure_ascii=False, indent=2))
    with etapa("narracion", tiempos):
        linea = narracion.sintetizar(guion, out)
    total = linea["duracion"] + 2.0   # 0.3 s de aire + 1.7 s para la firma sonora sobre la tarjeta de cierre
    with etapa("musica", tiempos):
        musica.pad(total, salida=str(out / "musica.wav"))
    with etapa("render_video", tiempos):
        info = render.render(guion, linea, out / "video_mudo.mp4", total)
    final = out / f'{guion["id"]}_final.mp4'
    with etapa("mezcla_audio", tiempos):
        firma = RAIZ / "marca" / "firma_sonora.wav"          # identidad sonora: firma de 1.6 s al cierre de cada Reel
        retardo = int((linea["duracion"] + 0.3) * 1000)
        filtro = ("[0:a]aresample=48000,pan=stereo|c0=c0|c1=c0,asplit=2[v][vsc];"
                  "[1:a]volume=0.22[m];[m][vsc]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[md];"
                  f"[3:a]aresample=48000,pan=stereo|c0=c0|c1=c0,volume=0.35,adelay={retardo}|{retardo}[f];"
                  "[v][md][f]amix=inputs=3:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[a]")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(out / "voz.wav"), "-i", str(out / "musica.wav"), "-i", str(out / "video_mudo.mp4"),
                        "-i", str(firma), "-filter_complex", filtro, "-map", "2:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
                        "-shortest", "-movflags", "+faststart", str(final)], check=True)
        srt_final = final.with_suffix(".srt"); srt_final.write_text((out / "video_mudo.srt").read_text())
    previos = set()
    if REGISTRO.exists():
        previos = {json.loads(l)["sha256"] for l in REGISTRO.read_text().splitlines() if l.strip() and json.loads(l)["id"] != guion["id"]}
    with etapa("auditoria_tecnica", tiempos):
        tec, sha, dur = auditoria.tecnica(final, srt_final, previos)
        tec.append(auditoria.sincronia(out))
    seg_total = sum(tiempos.values())
    costo = {
        "apis_de_pago_usd": 0.0,
        "computo_minutos": round(seg_total / 60, 2),
        "computo_equivalente_runner_usd": round(seg_total / 60 * COSTO_MIN_RUNNER, 4),
        "nota": "Producción 100% local con herramientas gratuitas. El cómputo equivale al costo de un runner de GitHub Actions solo si se exceden los 2,000 minutos gratuitos al mes. No incluye el uso de Claude para investigación y guion (cubierto por la suscripción existente).",
    }
    tec_ok = all(r["resultado"] == "APROBADO" for r in tec if "TikTok" not in r["control"])
    estado = jur["decision"] if tec_ok else "RETENIDO"
    if not tec_ok: jur = {**jur, "motivos": jur["motivos"] + ["falla técnica"], "tipo_retencion": "sustantivo"}
    reg = {"id": guion["id"], "titulo": guion["titulo"], "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds"), "sha256": sha,
           "duracion_s": round(dur, 1), "estado": estado, "huella_guion": huella_guion(guion), "carril": jur["carril"], "tiempos_s": tiempos, "costo": costo,
           "frames": info["frames"], "caracteres_narrados": linea["caracteres"]}
    REGISTRO.parent.mkdir(exist_ok=True)
    lineas = [l for l in (REGISTRO.read_text().splitlines() if REGISTRO.exists() else []) if l.strip() and json.loads(l)["id"] != guion["id"]]
    REGISTRO.write_text("\n".join(lineas + [json.dumps(reg, ensure_ascii=False)]) + "\n")
    (out / "auditoria.json").write_text(json.dumps({"tecnica": tec, "juridica": jur, "registro": reg}, ensure_ascii=False, indent=2))
    return reg, tec, jur


if __name__ == "__main__":
    reg, tec, jur = producir(Path(sys.argv[1]))
    print(json.dumps(reg, ensure_ascii=False, indent=2))
    for r in tec: print(r["resultado"], "|", r["control"], "|", r["detalle"])
    print("JURÍDICA:", jur["decision"], jur["tipo_retencion"] or "")
    for m in jur["motivos"]: print("  ·", m)
    for r in jur["reglas"]: print(" ", r["resultado"], r["control"], r["detalle"])
