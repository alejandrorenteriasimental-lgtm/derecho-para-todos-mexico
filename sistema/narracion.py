"""Narración local, sin costo por uso. Motor y voz se definen en config_voz.json (o en el guion, campo «voz» como objeto).
Cadena: normalización para lectura en voz alta (cifras, siglas, topónimos) → síntesis por oración con pausas
naturales → recorte de silencios → masterización de voz (EQ, de-esser, compresión suave, −16 LUFS)."""
import json, subprocess, time
from pathlib import Path
import numpy as np
import soundfile as sf
import voces

RAIZ = Path(__file__).resolve().parent.parent
CONFIG = Path(__file__).resolve().parent / "config_voz.json"
PAUSA_ESCENA = 0.45      # segundos entre escenas
INICIO = 0.25


def voz_activa(guion):
    v = guion.get("voz")
    return v if isinstance(v, dict) else json.loads(CONFIG.read_text())["voz"]


def sintetizar(guion: dict, salida: Path):
    salida.mkdir(parents=True, exist_ok=True)
    voz = voz_activa(guion)
    pistas, linea, t, sr0 = [], [], INICIO, None
    t0 = time.time()
    for i, esc in enumerate(guion["escenas"]):
        audio, sr, ors = voces.sintetizar(esc["texto"], voz, pausa=voz.get("pausa_oracion", 0.36), con_tiempos=True)
        if sr0 is None:
            sr0 = sr; pistas.append(np.zeros(int(INICIO * sr), np.float32))
        idx = np.where(np.abs(audio) > 0.006)[0]          # quita el silencio final que deja la última oración
        if len(idx): audio = audio[: idx[-1] + int(0.08 * sr)]
        dur = len(audio) / sr
        linea.append({"escena": i, "inicio": round(t, 3), "fin": round(t + dur, 3), "texto": esc["texto"],
                      "oraciones": [{"texto": o, "inicio": round(t + a, 3), "fin": round(t + b, 3)} for o, a, b in ors]})
        pistas += [audio, np.zeros(int(PAUSA_ESCENA * sr), np.float32)]
        t += dur + PAUSA_ESCENA
    crudo = salida / "voz_cruda.wav"; sf.write(crudo, np.concatenate(pistas), sr0)
    voces.postproceso(crudo, salida / "voz.wav"); crudo.unlink()   # misma duración; 48 kHz
    total = sf.info(str(salida / "voz.wav")).duration
    meta = {"duracion": round(total, 3), "segmentos": linea, "segundos_computo": round(time.time() - t0, 2),
            "caracteres": sum(len(e["texto"]) for e in guion["escenas"]), "voz": voz}
    (salida / "linea_tiempo.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    return meta
