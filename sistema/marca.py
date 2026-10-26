"""Identidad de Derecho para Todos México generada por código (sin herramientas de diseño de pago).
Fuente única de verdad: marca/tokens.json. Este script produce logotipos, avatar, portadas e identidad sonora."""
import json, math, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

RAIZ = Path(__file__).resolve().parent.parent
FD = RAIZ / "fuentes"
TOK = json.loads((RAIZ / "marca" / "tokens.json").read_text())
C = {k: tuple(int(v[i:i + 2], 16) for i in (1, 3, 5)) for k, v in TOK["color"].items()}
F = lambda k, s: ImageFont.truetype(str(FD / TOK["tipografia"][k]), s)


def simbolo(lado=512, fondo="noche", glifo="cempasuchil", cola=True):
    """Burbuja de diálogo con el signo de sección (§): «el Derecho, explicado en voz clara». Sin balanzas ni columnas."""
    k = 4; L = lado * k
    im = Image.new("RGBA", (L, L), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    r = int(L * 0.22); m = int(L * 0.04)
    caja = [m, m, L - m, L - m - (int(L * 0.10) if cola else 0)]
    d.rounded_rectangle(caja, r, fill=C[fondo])
    if cola:   # cola de la burbuja, abajo a la izquierda
        x0 = int(L * 0.20); y0 = caja[3] - 2
        d.polygon([(x0, y0 - int(L * .08)), (x0 + int(L * .20), y0 - int(L * .02)), (x0 - int(L * .02), L - m)], fill=C[fondo])
    f = F("display_black", int(L * 0.62)); t = "§"
    bb = d.textbbox((0, 0), t, font=f); w, h = bb[2] - bb[0], bb[3] - bb[1]
    cx, cy = (caja[0] + caja[2]) / 2, (caja[1] + caja[3]) / 2
    d.text((cx - w / 2 - bb[0], cy - h / 2 - bb[1]), t, font=f, fill=C[glifo])
    return im.resize((lado, lado), Image.LANCZOS)


def logo_horizontal(alto=300, tema="claro"):
    fg = C["noche"] if tema == "claro" else C["papel"]; bg = (0, 0, 0, 0)
    s = simbolo(alto, "noche" if tema == "claro" else "cempasuchil", "cempasuchil" if tema == "claro" else "noche")
    f1 = F("display_black", int(alto * 0.36)); f2 = F("semi", int(alto * 0.15))
    t1, t2 = "Derecho para Todos", "M É X I C O"
    w = int(alto * 1.18 + max(f1.getlength(t1), f2.getlength(t2)) + alto * 0.1)
    im = Image.new("RGBA", (w, alto), bg); im.alpha_composite(s, (0, 0)); d = ImageDraw.Draw(im)
    x = int(alto * 1.12); d.text((x, int(alto * 0.13)), t1, font=f1, fill=fg)
    d.text((x + 4, int(alto * 0.60)), t2, font=f2, fill=C["cempasuchil"] if tema == "oscuro" else C["tinta_suave"])
    return im


def avatar(lado=1080):
    im = Image.new("RGBA", (lado, lado), C["cempasuchil"] + (255,))
    s = simbolo(int(lado * 0.70), "noche", "cempasuchil", cola=True)
    im.alpha_composite(s, ((lado - s.width) // 2, int(lado * 0.17)))
    return im


def portada(w, h, zona_segura=None):
    """Portada sobria: fondo noche con resplandor cálido, lema y logotipo. zona_segura = (w, h) centrada."""
    y = np.linspace(0, 1, h)[:, None, None]
    base = (np.array(C["noche"]) * (1 - y) + np.array(C["noche_2"]) * y)
    im = Image.fromarray(np.repeat(base, w, axis=1).astype(np.uint8)).convert("RGBA")
    capa = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(capa)
    d.ellipse([w * 0.62, -h * 0.4, w * 1.15, h * 0.9], fill=C["cempasuchil"] + (60,))
    im.alpha_composite(capa.filter(ImageFilter.GaussianBlur(h * 0.18)))
    zw, zh = zona_segura or (w, h); x0, y0 = (w - zw) // 2, (h - zh) // 2
    lg = logo_horizontal(int(zh * 0.30), "oscuro"); im.alpha_composite(lg, (x0 + int(zw * 0.04), y0 + int(zh * 0.18)))
    d = ImageDraw.Draw(im); f = F("serif_it", int(zh * 0.11))
    d.text((x0 + int(zw * 0.04), y0 + int(zh * 0.62)), TOK["lema"], font=f, fill=C["papel"])
    return im


def mnemonico(salida, sr=48000):
    """Firma sonora de 1.6 s: dos notas que suben (La → Mi) y un acorde abierto en Do mayor. Procedural, sin muestras."""
    def nota(f, dur, ini, vol=0.25):
        t = np.arange(int(dur * sr)) / sr
        env = np.minimum(1, t / 0.01) * np.exp(-t * 3.2)
        x = sum(a * np.sin(2 * np.pi * f * m * t) for m, a in ((1, 1), (2, .35), (3, .12)))
        out = np.zeros(int(2.0 * sr)); s = int(ini * sr); out[s:s + len(t)] += vol * env * x; return out
    y = nota(440.0, 0.6, 0.0) + nota(659.25, 0.6, 0.22) + sum(nota(f, 1.3, 0.48, 0.16) for f in (523.25, 659.25, 783.99, 1046.5))
    y = y / np.max(np.abs(y)) * 0.6
    import soundfile as sf; sf.write(salida, y.astype(np.float32), sr)


if __name__ == "__main__":
    out = RAIZ / "marca"; (out / "png").mkdir(parents=True, exist_ok=True)
    simbolo(1024).save(out / "png/simbolo.png"); simbolo(1024, "cempasuchil", "noche").save(out / "png/simbolo_inverso.png")
    logo_horizontal(300, "claro").save(out / "png/logo_horizontal_claro.png"); logo_horizontal(300, "oscuro").save(out / "png/logo_horizontal_oscuro.png")
    avatar().convert("RGB").save(out / "png/perfil_1080.png")
    portada(1640, 624, (1640, 470)).convert("RGB").save(out / "png/portada_facebook_1640x624.png")
    portada(2560, 1440, (1546, 423)).convert("RGB").save(out / "png/banner_youtube_2560x1440.png")
    mnemonico(out / "firma_sonora.wav")
    print("listo")
