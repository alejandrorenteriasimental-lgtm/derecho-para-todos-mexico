"""Render de video vertical 1080x1920 con gráficos animados generados por código.
Sin generadores de video de pago: tipografía cinética, tarjetas, resaltados y fondo en movimiento."""
import json, math, subprocess, time
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H, FPS = 1080, 1920, 30
FD = str(Path(__file__).resolve().parent.parent / "fuentes") + "/"
F = {
    "black": FD + "InterDisplay-Black.otf", "xbold": FD + "InterDisplay-ExtraBold.otf", "bold": FD + "Inter-Bold.otf",
    "semi": FD + "Inter-SemiBold.otf", "med": FD + "Inter-Medium.otf", "reg": FD + "Inter-Regular.otf",
    "serif": FD + "Lora-Variable.ttf", "serif_it": FD + "Lora-Italic-Variable.ttf",
}
C = {"bg1": (11, 22, 38), "bg2": (21, 41, 66), "acc": (242, 181, 68), "txt": (245, 241, 232), "mut": (159, 176, 195),
     "paper": (245, 239, 226), "ink": (16, 28, 46), "red": (229, 100, 90), "green": (91, 192, 138)}
_fc = {}


def font(k, s):
    key = (k, s)
    if key not in _fc:
        _fc[key] = ImageFont.truetype(F[k], s)
    return _fc[key]


def ease(x):
    x = max(0.0, min(1.0, x)); return 1 - (1 - x) ** 3


def a(c, al):
    return (*c, int(max(0, min(1, al)) * 255))


def wrap(texto, f, ancho):
    lineas, actual = [], ""
    for w in texto.split():
        prueba = (actual + " " + w).strip()
        if f.getlength(prueba) <= ancho:
            actual = prueba
        else:
            if actual: lineas.append(actual)
            actual = w
    if actual: lineas.append(actual)
    return lineas


def fondo():
    alto = H + 700
    y = np.linspace(0, 1, alto)[:, None]
    g = (np.array(C["bg1"])[None, None, :] * (1 - y[..., None]) + np.array(C["bg2"])[None, None, :] * y[..., None])
    img = np.repeat(g, W, axis=1).astype(np.float32)
    rng = np.random.default_rng(3)
    capa = Image.new("RGBA", (W, alto), (0, 0, 0, 0)); d = ImageDraw.Draw(capa)
    for _ in range(14):
        cx, cy, r = rng.uniform(0, W), rng.uniform(0, alto), rng.uniform(120, 380)
        col = C["acc"] if rng.random() < 0.35 else (70, 110, 160)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=a(col, rng.uniform(0.05, 0.12)))
    capa = capa.filter(ImageFilter.GaussianBlur(90))
    base = Image.fromarray(img.astype(np.uint8)).convert("RGBA")
    base = Image.alpha_composite(base, capa)
    lin = Image.new("RGBA", (W, alto), (0, 0, 0, 0)); d = ImageDraw.Draw(lin)
    for x in range(-alto, W, 120):  # líneas diagonales tenues (papel legal)
        d.line([(x, 0), (x + alto, alto)], fill=(255, 255, 255, 9), width=2)
    return Image.alpha_composite(base, lin)


def tiempos_palabras(seg):
    """Reparte el tiempo de cada oración entre sus palabras según su longitud. Si la narración trae tiempos
    medidos por oración (v0.2), el reparto se hace dentro de cada oración y los subtítulos no se desfasan."""
    if seg.get("oraciones"):
        return [w for o in seg["oraciones"] for w in tiempos_palabras({"texto": o["texto"], "inicio": o["inicio"], "fin": o["fin"]})]
    palabras = seg["texto"].split()
    pesos = [len(p) + 1 + (3 if p[-1] in ",.:;?" else 0) for p in palabras]
    tot = sum(pesos); t = seg["inicio"]; dur = seg["fin"] - seg["inicio"]; out = []
    for p, w in zip(palabras, pesos):
        d = dur * w / tot; out.append((p, t, t + d)); t += d
    return out


def bloques(palabras, max_car=24):
    res, cur = [], []
    for item in palabras:
        if cur and (len(" ".join(x[0] for x in cur + [item])) > max_car or cur[-1][0][-1] in ".?:"):
            res.append(cur); cur = []
        cur.append(item)
    if cur: res.append(cur)
    return res


def dibujar_subtitulos(d, t, bls):
    actual = None
    for b in bls:
        if b[0][1] - 0.05 <= t <= b[-1][2] + 0.15:
            actual = b
    if not actual:
        return
    f = font("xbold", 66)
    texto = " ".join(x[0] for x in actual)
    ancho = f.getlength(texto); x0 = (W - ancho) / 2; y0 = 1380
    d.rounded_rectangle([x0 - 34, y0 - 22, x0 + ancho + 34, y0 + 100], 26, fill=(8, 14, 24, 200))
    x = x0
    for (p, ti, tf) in actual:
        col = C["acc"] if ti <= t else C["txt"]
        d.text((x, y0), p, font=f, fill=a(col, 1))
        x += f.getlength(p + " ")


def chip(d, x, y, texto, f, fg, bg, alpha=1.0, pad=(22, 12)):
    w = f.getlength(texto)
    d.rounded_rectangle([x, y, x + w + 2 * pad[0], y + f.size + 2 * pad[1]], (f.size + 2 * pad[1]) // 2, fill=a(bg, alpha))
    d.text((x + pad[0], y + pad[1] - 2), texto, font=f, fill=a(fg, alpha))
    return w + 2 * pad[0]


def escena(d, esc, p, tl, fuentes):
    tipo = esc["tipo"]
    if tipo in ("gancho", "titular"):
        lineas = esc["titulo"]; tam = 150 if tipo == "gancho" else 124
        while max(font("black", tam).getlength(l) for l in lineas) > 940: tam -= 4
        f = font("black", tam)
        alto = len(lineas) * (tam + 22); y = 760 - alto / 2
        for i, ln in enumerate(lineas):
            e = ease((tl - 0.12 * i) / 0.45)
            col = C["acc"] if (i == len(lineas) - 1) else C["txt"]
            w = f.getlength(ln)
            d.text(((W - w) / 2, y + (1 - e) * 60), ln, font=f, fill=a(col, e))
            y += tam + 22
        barra = ease((tl - 0.35) / 0.6) * 260
        d.rounded_rectangle([(W - barra) / 2, y + 20, (W + barra) / 2, y + 32], 6, fill=a(C["acc"], 1))
        if tipo == "gancho":
            fq = font("black", 620); e = ease(tl / 0.8)
            d.text((W - 380, 820 - (1 - e) * 80), "?", font=fq, fill=(242, 181, 68, int(18 * e)))
    elif tipo == "cita":
        e = ease(tl / 0.5)
        x0, y0, x1 = 90, 470 + (1 - e) * 80, W - 90
        f = font("serif_it", 74); lineas = wrap("«" + esc["cita"] + "»", f, x1 - x0 - 120)
        alto = 220 + len(lineas) * 100
        d.rounded_rectangle([x0, y0, x1, y0 + alto], 36, fill=a(C["paper"], e))
        chip(d, x0 + 60, y0 + 56, esc["etiqueta"].upper(), font("bold", 34), C["paper"], C["ink"], e)
        yy = y0 + 160
        for i, ln in enumerate(lineas):
            lw = f.getlength(ln)
            prog = max(0.0, min(1.0, (p - 0.32 - i * 0.12) / 0.25))
            if prog > 0:
                d.rectangle([x0 + 60, yy + 18, x0 + 60 + lw * prog, yy + 86], fill=(242, 181, 68, int(150 * e)))
            d.text((x0 + 60, yy), ln, font=f, fill=a(C["ink"], e))
            yy += 100
    elif tipo == "lista":
        f = font("bold", 60); y = 520
        for i, it in enumerate(esc["items"]):
            e = ease((p - 0.08 - i * 0.26) / 0.18)
            ultimo = i == len(esc["items"]) - 1
            col = C["acc"] if ultimo else C["txt"]
            x = 110 + (1 - e) * 120
            d.ellipse([x, y + 4, x + 72, y + 76], fill=a(col if ultimo else (40, 66, 100), e))
            d.text((x + 36 - font("black", 44).getlength(str(i + 1)) / 2, y + 12), str(i + 1), font=font("black", 44), fill=a(C["ink"] if ultimo else C["txt"], e))
            for j, ln in enumerate(wrap(it, f, 760)):
                d.text((x + 110, y + j * 70), ln, font=f, fill=a(col, e))
            y += 70 * max(1, len(wrap(it, f, 760))) + 90
    elif tipo == "excepcion":
        e = ease(tl / 0.5)
        r = 120; cx, cy = W / 2, 500
        d.ellipse([cx - r, cy - r + (1 - e) * 40, cx + r, cy + r + (1 - e) * 40], fill=a(C["red"], e))
        fn = font("black", 150); n = str(esc["numero"])
        d.text((cx - fn.getlength(n) / 2, cy - 92 + (1 - e) * 40), n, font=fn, fill=a(C["txt"], e))
        fe = font("xbold", 74); y = 690
        for ln in wrap(esc["encabezado"], fe, 900):
            e2 = ease((tl - 0.2) / 0.5)
            d.text(((W - fe.getlength(ln)) / 2, y + (1 - e2) * 40), ln, font=fe, fill=a(C["txt"], e2)); y += 92
        e3 = ease((p - 0.45) / 0.15)
        fd = font("bold", 54); w = fd.getlength(esc["detalle"]) + 70
        d.rounded_rectangle([(W - w) / 2, y + 40, (W + w) / 2, y + 150], 55, fill=a(C["red"], 0.25 * e3), outline=a(C["red"], e3), width=4)
        d.text(((W - w) / 2 + 35, y + 64), esc["detalle"], font=fd, fill=a(C["txt"], e3))
    elif tipo == "cierre":
        e = ease(tl / 0.6)
        fw = font("black", 112); y = 520
        for i, ln in enumerate(["DERECHO", "PARA TODOS"]):
            d.text(((W - fw.getlength(ln)) / 2, y + (1 - e) * 50), ln, font=fw, fill=a(C["acc"] if i else C["txt"], e)); y += 118
        fa = font("med", 46); y += 60
        for ln in wrap(esc["aviso"], fa, 820):
            d.text(((W - fa.getlength(ln)) / 2, y), ln, font=fa, fill=a(C["mut"], e)); y += 58
        e2 = ease((p - 0.6) / 0.2)
        chip(d, (W - font("bold", 46).getlength("Síguenos") - 60) / 2, y + 60, "Síguenos", font("bold", 46), C["ink"], C["acc"], e2, pad=(30, 18))
    # fuente al pie
    fid = next((af["fuente"] for af in esc.get("afirmaciones", [])), None)
    if fid:
        fu = fuentes[fid]
        txt = "Fuente: " + fu["cita"]
        fs = font("med", 36); e = ease(tl / 0.6)
        lines = wrap(txt, fs, 900); y = 1250
        for ln in lines:
            d.text(((W - fs.getlength(ln)) / 2, y), ln, font=fs, fill=a(C["mut"], e)); y += 44


def render(guion, linea, salida_mp4, t_total):
    base = fondo()
    segs = linea["segmentos"]
    bls = bloques([w for s in segs for w in tiempos_palabras(s)])
    n = int(math.ceil(t_total * FPS))
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(salida_mp4)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    t0 = time.time()
    fh, fs_ = font("bold", 30), font("med", 26)
    for i in range(n):
        t = i / FPS
        off = int(600 * t / t_total)
        frame = base.crop((0, off, W, off + H)).copy()
        capa = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(capa)
        k = 0
        for j, s in enumerate(segs):
            if t >= s["inicio"] - 0.2: k = j
        s = segs[k]
        inicio = s["inicio"] - 0.2
        fin = segs[k + 1]["inicio"] - 0.2 if k + 1 < len(segs) else t_total
        p = (t - inicio) / max(0.1, fin - inicio); tl = t - inicio
        escena(d, guion["escenas"][k], p, tl, guion["fuentes"])
        # barra superior
        d.rectangle([0, 0, W, 10], fill=(255, 255, 255, 30)); d.rectangle([0, 0, W * t / t_total, 10], fill=a(C["acc"], 1))
        d.text((60, 140), "DERECHO PARA TODOS", font=fh, fill=a(C["txt"], 0.9))
        lab = "Voz generada con IA"
        d.text((W - 60 - fs_.getlength(lab), 144), lab, font=fs_, fill=a(C["mut"], 0.9))
        dibujar_subtitulos(d, t, bls)
        frame = Image.alpha_composite(frame, capa).convert("RGB")
        proc.stdin.write(frame.tobytes())
    proc.stdin.close(); proc.wait()
    srt = salida_mp4.with_suffix(".srt")
    def ts(x):
        h = int(x // 3600); m = int(x % 3600 // 60); s_ = x % 60
        return f"{h:02d}:{m:02d}:{int(s_):02d},{int((s_ % 1) * 1000):03d}"
    with open(srt, "w") as fh_:
        for idx, b in enumerate(bls, 1):
            fh_.write(f"{idx}\n{ts(b[0][1])} --> {ts(b[-1][2])}\n{' '.join(x[0] for x in b)}\n\n")
    return {"frames": n, "segundos_render": round(time.time() - t0, 1), "srt": str(srt)}
