"""Música de fondo original generada por código (sin licencias de terceros).
Pad armónico lento: acordes menores/mayores con LFO; determinista por semilla."""
import numpy as np
import soundfile as sf

SR = 48000


def nota(m):  # MIDI a Hz
    return 440.0 * 2 ** ((m - 69) / 12)


def pad(duracion, semilla=7, salida=None):
    rng = np.random.default_rng(semilla)
    n = int(duracion * SR); t = np.arange(n) / SR
    progresion = [[57, 60, 64, 69], [53, 57, 60, 65], [55, 59, 62, 67], [52, 55, 59, 64]]  # Am F G Em
    dur_acorde = 6.0
    y = np.zeros(n, dtype=np.float64)
    for k in range(int(np.ceil(duracion / dur_acorde)) + 1):
        acorde = progresion[k % len(progresion)]
        a = k * dur_acorde - 1.5; b = a + dur_acorde + 3.0
        ia, ib = max(0, int(a * SR)), min(n, int(b * SR))
        if ia >= ib:
            continue
        tt = t[ia:ib]
        env = np.sin(np.clip((tt - a) / (b - a), 0, 1) * np.pi) ** 2
        seg = np.zeros_like(tt)
        for m in acorde:
            f = nota(m - 12)
            det = 1 + rng.uniform(-0.002, 0.002)
            seg += np.sin(2 * np.pi * f * det * tt) * 0.5 + np.sin(2 * np.pi * f * 2.0 * tt) * 0.12
        y[ia:ib] += seg * env
    # pulso suave de bajo cada 2 s para ritmo
    bajo = np.sin(2 * np.pi * nota(33) * t) * (0.5 + 0.5 * np.cos(2 * np.pi * 0.5 * t)) ** 6 * 0.35
    y = y + bajo
    # ruido rosa muy leve (textura)
    ruido = np.cumsum(rng.normal(0, 1, n)); ruido -= np.convolve(ruido, np.ones(4800) / 4800, mode="same")
    y += ruido / (np.max(np.abs(ruido)) + 1e-9) * 0.02
    fade = int(2.0 * SR)
    y[:fade] *= np.linspace(0, 1, fade); y[-fade:] *= np.linspace(1, 0, fade)
    y = y / (np.max(np.abs(y)) + 1e-9) * 0.6
    est = np.stack([y, np.roll(y, 240)], axis=1).astype(np.float32)  # leve ancho estéreo
    if salida:
        sf.write(salida, est, SR)
    return est
