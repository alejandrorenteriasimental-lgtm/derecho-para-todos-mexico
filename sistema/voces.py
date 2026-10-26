"""Motores de voz intercambiables + banco de pruebas comparativas.
Motores: Kokoro (Apache-2.0) y Piper vía sherpa-onnx (motor Apache-2.0; licencia de cada voz en su MODEL_CARD)."""
import json, re, subprocess, sys, time, unicodedata
from pathlib import Path
import numpy as np
import soundfile as sf

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from normalizar import normalizar

_cache = {}


def _kokoro():
    if "k" not in _cache:
        from kokoro_onnx import Kokoro
        _cache["k"] = Kokoro(str(RAIZ / "models/kokoro-v1.0.int8.onnx"), str(RAIZ / "models/voices-v1.0.bin"))
    return _cache["k"]


def _piper(nombre):
    """Inferencia directa del modelo Piper (VITS) con onnxruntime; fonetización espeak-ng es-419."""
    if nombre not in _cache:
        import onnxruntime as ort
        d = RAIZ / "models/piper" / f"vits-piper-{nombre}"
        conf = json.loads((d / f"{nombre}.onnx.json").read_text())
        so = ort.SessionOptions(); so.intra_op_num_threads = 2
        _cache[nombre] = (ort.InferenceSession(str(d / f"{nombre}.onnx"), so, providers=["CPUExecutionProvider"]), conf)
    return _cache[nombre]


def _fonemas(texto, lang):
    from kokoro_onnx.tokenizer import Tokenizer
    if "tok" not in _cache: _cache["tok"] = Tokenizer()
    return _cache["tok"].phonemize(texto, lang=lang)


def sintetizar_frase(texto, voz):
    """voz: dict con motor, id y parámetros. Devuelve (audio float32, sr)."""
    t = normalizar(texto)
    if voz["motor"] == "kokoro":
        k = _kokoro()
        if "mezcla" in voz:   # mezcla de estilos de voz, p. ej. {"em_alex": 0.5, "em_santa": 0.5}
            estilo = sum(k.get_voice_style(n) * w for n, w in voz["mezcla"].items())
        else:
            estilo = voz["id"]
        a, sr = k.create(t, voice=estilo, speed=voz.get("velocidad", 1.0), lang=voz.get("lang", "es-419"))
        return np.asarray(a, np.float32), sr
    sess, conf = _piper(voz["id"])
    mapa = conf["phoneme_id_map"]
    ids = list(mapa["^"]) + list(mapa["_"])
    for ch in _fonemas(t, conf["espeak"]["voice"]):
        if ch in mapa: ids += list(mapa[ch]) + list(mapa["_"])
    ids += list(mapa["$"])
    escalas = np.array([voz.get("noise_scale", 0.667), 1.0 / voz.get("velocidad", 1.0), voz.get("noise_w", 0.8)], np.float32)
    out = sess.run(None, {"input": np.array([ids], np.int64), "input_lengths": np.array([len(ids)], np.int64), "scales": escalas})[0]
    return np.asarray(out, np.float32).squeeze(), conf["audio"]["sample_rate"]


def frases(texto, minimo=28):
    """Divide en oraciones (. ? !) y une las muy cortas con la siguiente: los modelos pronuncian mal
    los enunciados aislados de una o dos palabras («Pero ojo:», «¿Neta?»)."""
    partes = [f.strip() for f in re.split(r"(?<=[.?!])\s+", texto) if f.strip()]
    out = []
    for f in partes:
        if out and len(out[-1]) < minimo:
            out[-1] = out[-1] + " " + f
        else:
            out.append(f)
    return out


def sintetizar(texto, voz, pausa=0.42, con_tiempos=False):
    """Sintetiza oración por oración. Con con_tiempos=True devuelve también [(oración, inicio_s, fin_s)]
    medidos sobre el audio real, para sincronizar subtítulos por oración."""
    piezas, sr0, tiempos, t = [], None, [], 0.0
    for f in frases(texto):
        a, sr = sintetizar_frase(f, voz); sr0 = sr
        idx = np.where(np.abs(a) > 0.006)[0]
        if len(idx): a = a[max(0, idx[0] - int(0.03 * sr)): idx[-1] + int(0.08 * sr)]
        p = pausa * (1.25 if f.endswith("?") else 1.0)
        tiempos.append((f, round(t, 3), round(t + len(a) / sr, 3)))
        piezas += [a, np.zeros(int(p * sr), np.float32)]; t += len(a) / sr + p
    audio = np.concatenate(piezas)
    return (audio, sr0, tiempos) if con_tiempos else (audio, sr0)


CADENA = ("highpass=f=75,equalizer=f=250:t=q:w=1.2:g=-2,equalizer=f=3500:t=q:w=1.5:g=1.5,"
          "deesser=i=0.35,acompressor=threshold=0.12:ratio=2.5:attack=8:release=120:makeup=1.3,"
          "loudnorm=I=-16:TP=-1.5:LRA=9,aresample=48000")


def postproceso(wav_in, wav_out):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav_in), "-af", CADENA, "-ac", "1", str(wav_out)], check=True)


# ---------- medición ----------
def _asr():
    if "asr" not in _cache:
        import sherpa_onnx
        d = RAIZ / "models/asr/sherpa-onnx-whisper-small"
        _cache["asr"] = sherpa_onnx.OfflineRecognizer.from_whisper(encoder=str(d / "small-encoder.int8.onnx"), decoder=str(d / "small-decoder.int8.onnx"),
                                                                    tokens=str(d / "small-tokens.txt"), language="es", task="transcribe", num_threads=2)
    return _cache["asr"]


def transcribir(wav):
    a, sr = sf.read(wav, dtype="float32")
    if a.ndim > 1: a = a.mean(1)
    if sr != 16000:
        import math
        n = int(len(a) * 16000 / sr); a = np.interp(np.linspace(0, len(a) - 1, n), np.arange(len(a)), a).astype(np.float32); sr = 16000
    textos = []
    for i in range(0, len(a), sr * 28):  # Whisper procesa ventanas de 30 s
        s = _asr().create_stream(); s.accept_waveform(sr, a[i:i + sr * 28]); _asr().decode_stream(s); textos.append(s.result.text)
    return " ".join(textos).strip()


def _toks(t):
    t = unicodedata.normalize("NFD", normalizar(t).lower()); t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9ñ ]", " ", t).split()


def wer(ref, hyp):
    r, h = _toks(ref), _toks(hyp)
    d = np.zeros((len(r) + 1, len(h) + 1), int); d[:, 0] = range(len(r) + 1); d[0, :] = range(len(h) + 1)
    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            d[i, j] = min(d[i - 1, j] + 1, d[i, j - 1] + 1, d[i - 1, j - 1] + (r[i - 1] != h[j - 1]))
    return d[len(r), len(h)] / max(1, len(r))


def prosodia(wav):
    import parselmouth
    snd = parselmouth.Sound(str(wav)); pitch = snd.to_pitch(time_step=0.01, pitch_floor=60, pitch_ceiling=400)
    f0 = pitch.selected_array["frequency"]; f0 = f0[f0 > 0]
    st = 12 * np.log2(f0 / np.median(f0))
    return {"f0_mediana_hz": round(float(np.median(f0)), 1), "variacion_entonacion_st": round(float(np.std(st)), 2),
            "rango_entonacion_st": round(float(np.percentile(st, 95) - np.percentile(st, 5)), 2)}
