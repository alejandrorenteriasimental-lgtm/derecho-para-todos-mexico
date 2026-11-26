"""Render del cuerpo del DOCUMENTAL semanal (1920x1080, 30 cps) con gráficos animados generados por código.

Solo gráficos originales de la marca (marca/tokens.json): tipografía Inter/Lora, colores de la marca, íconos e ilustraciones
vectoriales simples, mapas esquemáticos, líneas de tiempo y citas en tarjeta. Sin fotos, sin videos de terceros y sin rostros:
las figuras de las recreaciones son siluetas planas (círculo y cuerpo redondeado), nunca caras.

Movimiento para que no parezca una presentación estática: fondo que se desplaza despacio con un resplandor que deriva, entradas
escalonadas, la tarjeta de cita que sube y se resalta línea por línea al ritmo de la narración, la línea de tiempo que avanza
nodo por nodo, el documento que se desplaza, cifras que crecen, siluetas que caminan, y cortinillas de capítulo.

Elementos fijos: barra de avance, firma «AQUÍ DICE LA LEY» con el capítulo en curso, «Voz generada con IA», subtítulos
quemados (palabra resaltada al decirse) y, en cada escena «recreacion», el rótulo «RECREACIÓN · Ilustración, no es material
auténtico» visible durante TODA la escena (sin fundido: la auditoría lo comprueba en los píxeles del video final).
"""
import math, re, subprocess, time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

import marca, render
from render import ease, wrap, tiempos_palabras, bloques

W, H, FPS = 1920, 1080, 30
C = marca.C
MARGEN = 120
CONTENIDO_Y = (150, 830)          # todo el contenido de la escena queda aquí: arriba el encabezado, abajo fuente y subtítulos
FUENTE_Y = 858
SUB_Y = 922                       # línea base aproximada de los subtítulos (caja de 900 a 1000)
PAN_PX = 480                      # desplazamiento horizontal total del fondo
ROTULO = "RECREACIÓN"
ROTULO_NOTA = "Ilustración, no es material auténtico"
ROTULO_CAJA = (MARGEN, 118, MARGEN + 260, 168)     # se calcula en _rotulo(); este es el valor de referencia para la auditoría
SUB_MAX_CAR = 52
font = render.font


def a(c, al):
    return (*c[:3], int(max(0.0, min(1.0, al)) * 255))


def _clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


class Lienzo:
    """ImageDraw en modo RGBA sobre el cuadro RGB. Las figuras se mezclan con su alfa, pero el texto de Pillow ignora el alfa
    (lo pinta opaco): aquí el texto translúcido se pinta con una máscara escalada, para que los fundidos funcionen."""
    def __init__(self, im):
        self.im = im; self.d = ImageDraw.Draw(im, "RGBA"); self.off = (0, 0)

    # desplazamiento lento de todo el contenido de la escena («cámara» que flota): se aplica a cada figura y texto
    def _p(self, xy): return (xy[0] + self.off[0], xy[1] + self.off[1])
    def _c(self, c): return [c[0] + self.off[0], c[1] + self.off[1], c[2] + self.off[0], c[3] + self.off[1]]
    def rectangle(self, c, **k): return self.d.rectangle(self._c(c), **k)
    def rounded_rectangle(self, c, r=0, **k): return self.d.rounded_rectangle(self._c(c), r, **k)
    def ellipse(self, c, **k): return self.d.ellipse(self._c(c), **k)
    def polygon(self, pts, **k): return self.d.polygon([self._p(x) for x in pts], **k)

    def text(self, xy, txt, font=None, fill=None, **k):
        xy = self._p(xy)
        if fill is None or len(fill) < 4 or fill[3] >= 250:
            return self.d.text(xy, txt, font=font, fill=tuple(fill[:3]) if fill else None, **k)
        if fill[3] <= 2 or not txt.strip(): return
        x0, y0, x1, y1 = (int(math.floor(v)) for v in self.d.textbbox(xy, txt, font=font))
        w, h = x1 - x0 + 2, y1 - y0 + 2
        m = Image.new("L", (w, h), 0); ImageDraw.Draw(m).text((xy[0] - x0, xy[1] - y0), txt, font=font, fill=fill[3])
        self.im.paste(tuple(fill[:3]), (x0, y0, x0 + w, y0 + h), m)

    def __getattr__(self, n):
        return getattr(self.d, n)


# ── fondo ────────────────────────────────────────────────────────────────────────────────────────────────────────
def fondo_ancho():
    """Fondo de marca (el del video semanal y las portadas), más ancho que la pantalla para desplazarse despacio."""
    import youtube_semanal as ys
    return ys._fondo(W + PAN_PX, H).convert("RGB")


def _orbe(r=360, color=None):
    col = color or C["cempasuchil"]
    im = Image.new("RGBA", (r * 2, r * 2), (*col, 0)); d = ImageDraw.Draw(im)      # mismo color en todo: el desenfoque no oscurece el borde
    d.ellipse([r * 0.35, r * 0.35, r * 1.65, r * 1.65], fill=a(col, 0.10))
    return im.filter(ImageFilter.GaussianBlur(r * 0.28))


# ── utilidades de texto ──────────────────────────────────────────────────────────────────────────────────────────
def ajustar(texto, k, tam, ancho, max_lineas, minimo=34, paso=4):
    while True:
        f = font(k, tam); ls = wrap(texto, f, ancho)
        if (len(ls) <= max_lineas and all(f.getlength(l) <= ancho for l in ls)) or tam <= minimo: return f, ls
        tam -= paso


def centrado(d, y, lineas, f, col, inter=1.12, dy=0.0, x_centro=W / 2):
    for l in lineas:
        d.text((x_centro - f.getlength(l) / 2, y + dy), l, font=f, fill=col); y += int(f.size * inter)
    return y


def chip(d, x, y, texto, f, fg, bg, pad=(22, 10)):
    w = f.getlength(texto); alto = f.size + 2 * pad[1]
    d.rounded_rectangle([x, y, x + w + 2 * pad[0], y + alto], alto // 2, fill=bg)
    d.text((x + pad[0], y + pad[1] - 2), texto, font=f, fill=fg)
    return [x, y, x + w + 2 * pad[0], y + alto]


def entrada(tl, dur, ent=0.45, sal=0.35):
    """Opacidad de la escena: entra en `ent` s y sale en los últimos `sal` s."""
    return min(ease(tl / ent), 1 - ease((tl - (dur - sal)) / sal) if dur > sal else 1.0)


def partir_momento(t):
    """«etiqueta | detalle» o «etiqueta · detalle» (primera aparición) → (etiqueta, detalle)."""
    for sep in ("|", " · ", " — ", " – "):
        if sep in t:
            x, y = t.split(sep, 1); return x.strip(), y.strip()
    return t.strip(), ""


def capitulo_partes(titulo):
    """«Capítulo 1 · La detención» → («CAPÍTULO 1», «La detención»); «Prólogo» → («», «Prólogo»)."""
    m = re.match(r"\s*cap[ií]tulo\s+(\w+)\s*[·:.\-–—]\s*(.+)", titulo or "", re.I)
    return (f"CAPÍTULO {m.group(1).upper()}", m.group(2).strip()) if m else ("", (titulo or "").strip())


def textos_visibles(esc):
    """Los textos de pantalla; en una recreación se quita un «RECREACIÓN» escrito en el guion (el rótulo lo pone el render)."""
    tx = list(esc["pantalla"].get("textos") or [])
    if esc["pantalla"]["tipo"] == "recreacion": tx = [x for x in tx if x.strip().strip("«»\"'").lower() not in ("recreación", "recreacion")]
    return tx


# ── escenas ──────────────────────────────────────────────────────────────────────────────────────────────────────
def esc_titulo(d, im, tx, p, tl, dur, al):
    f, ls = ajustar(tx[0], "black", 124, 1560, 3, minimo=64)
    sub = tx[1:]
    fs = font("semi", 44)
    alto = len(ls) * int(f.size * 1.08) + (70 + 58 * len(sub) if sub else 0)
    y = (CONTENIDO_Y[0] + CONTENIDO_Y[1]) / 2 - alto / 2 - 14 * p
    for i, l in enumerate(ls):
        e = ease((tl - 0.12 * i) / 0.5) * al
        d.text(((W - f.getlength(l)) / 2, y + (1 - e) * 50), l, font=f, fill=a(C["cempasuchil"] if i == len(ls) - 1 else C["papel"], e))
        y += int(f.size * 1.08)
    barra = ease((tl - 0.4) / 0.7) * 300
    d.rounded_rectangle([(W - barra) / 2, y + 20, (W + barra) / 2, y + 30], 5, fill=a(C["cempasuchil"], al))
    y += 70
    for j, s in enumerate(sub):
        e = ease((tl - 0.7 - 0.15 * j) / 0.5) * al
        y = centrado(d, y, wrap(s, fs, 1400), fs, a(C["bruma"], e))


def esc_pregunta(d, im, tx, p, tl, dur, al):
    e = ease(tl / 0.6) * al
    cx, cy = 400, 490
    r = 160 + 6 * math.sin(tl * 2.2)
    d.ellipse([cx - r - 26, cy - r - 26, cx + r + 26, cy + r + 26], outline=a(C["cempasuchil"], 0.35 * e), width=4)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=a(C["cempasuchil"], e))
    fq = font("black", 250); d.text((cx - fq.getlength("?") / 2, cy - 168), "?", font=fq, fill=a(C["noche"], e))
    f, ls = ajustar(tx[0], "xbold", 80, 1180, 5, minimo=48)
    y = (CONTENIDO_Y[0] + CONTENIDO_Y[1]) / 2 - len(ls) * f.size * 1.16 / 2
    for i, l in enumerate(ls):
        el = ease((tl - 0.25 - 0.14 * i) / 0.5) * al
        d.text((660 + (1 - el) * 80, y), l, font=f, fill=a(C["papel"], el)); y += int(f.size * 1.16)
    fs = font("semi", 38)
    for s in tx[1:]:
        el = ease((tl - 0.9) / 0.5) * al
        for l in wrap(s, fs, 1180): d.text((660, y + 24), l, font=fs, fill=a(C["bruma"], el)); y += 48


def _comillas(t):
    t = t.strip()
    return t if t[:1] in "«\"“'…" or t.startswith("«") else f"«{t}»"


def esc_cita(d, im, tx, p, tl, dur, al, fuente_corta=None):
    e = ease(tl / 0.6) * al
    x0, x1 = 230, W - 230
    cita = _comillas(tx[0]); attr = tx[1:]
    fa = font("semi", 32)
    attr_l = [l for s in attr for l in wrap(s, fa, x1 - x0 - 160)]
    tam = 66
    while True:
        f = font("serif_it", tam); ls = wrap(cita, f, x1 - x0 - 160); paso = int(tam * 1.38)
        alto = 130 + len(ls) * paso + (30 + 42 * len(attr_l) if attr_l else 0) + 60
        if alto <= CONTENIDO_Y[1] - CONTENIDO_Y[0] - 20 or tam <= 38: break
        tam -= 2
    y0 = (CONTENIDO_Y[0] + CONTENIDO_Y[1]) / 2 - alto / 2 + (1 - e) * 70 - 10 * p
    d.rounded_rectangle([x0 + 10, y0 + 14, x1 + 10, y0 + alto + 14], 34, fill=a((0, 0, 0), 0.25 * e))      # sombra
    d.rounded_rectangle([x0, y0, x1, y0 + alto], 34, fill=a(C["papel"], e))
    d.rectangle([x0, y0 + 40, x0 + 10, y0 + alto - 40], fill=a(C["cempasuchil"], e))
    etq = (fuente_corta or "CITA").upper()
    fe = font("bold", 28)
    while fe.size > 20 and fe.getlength(etq) > x1 - x0 - 200: fe = font("bold", fe.size - 2)
    chip(d, x0 + 80, y0 + 40, etq, fe, a(C["papel"], e), a(C["tinta"], e))
    yy = y0 + 130; n = max(1, len(ls))
    for i, l in enumerate(ls):
        lw = f.getlength(l)
        prog = _clamp((p - 0.10) * n / 0.72 - i)       # resaltado progresivo al ritmo de la narración
        if prog > 0:
            d.rectangle([x0 + 80, yy + int(tam * 0.26), x0 + 80 + lw * ease(prog), yy + int(tam * 1.14)], fill=a(C["cempasuchil"], 0.55 * e))
        d.text((x0 + 80, yy), l, font=f, fill=a(C["tinta"], e)); yy += paso
    if attr_l:
        yy += 30
        for l in attr_l: d.text((x0 + 80, yy), l, font=fa, fill=a(C["tinta_suave"], e)); yy += 42


def esc_dato(d, im, tx, p, tl, dur, al):
    e = ease(tl / 0.7)
    f0, ls = ajustar(tx[0], "black", 190, 1560, 2, minimo=72, paso=6)
    escala = 0.86 + 0.14 * e
    tam = max(40, int(f0.size * escala / 2) * 2); f = font("black", tam)
    fs = font("semi", 50); fx = font("serif_it", 52)
    resto = [(wrap(s, fs if i == 0 else fx, 1450), fs if i == 0 else fx) for i, s in enumerate(tx[1:])]
    alto = len(ls) * int(f0.size * 1.05) + 70 + sum(len(x) * int(ff.size * 1.25) + 26 for x, ff in resto)
    y = (CONTENIDO_Y[0] + CONTENIDO_Y[1]) / 2 - alto / 2 - 10 * p
    yb = y
    for l in ls:
        d.text(((W - f.getlength(l)) / 2, y + (f0.size - tam) * 0.5), l, font=f, fill=a(C["cempasuchil"], e * al)); y += int(f0.size * 1.05)
    lw = (0.25 * ease((tl - 0.35) / 0.8) + 0.75 * _clamp(p)) * min(900, max(f0.getlength(l) for l in ls))   # crece durante toda la escena
    d.rounded_rectangle([(W - lw) / 2, y + 14, (W + lw) / 2, y + 22], 4, fill=a(C["papel"], 0.8 * al))
    y += 70
    for j, (lineas, ff) in enumerate(resto):
        ej = ease((tl - 0.6 - 0.35 * j) / 0.6) * al
        y = centrado(d, y, lineas, ff, a(C["papel"] if j == 0 else C["bruma"], ej), inter=1.25, dy=(1 - ej) * 30) + 26
    return yb


def esc_linea_tiempo(d, im, tx, p, tl, dur, al):
    momentos = [partir_momento(t) for t in tx]
    n = len(momentos); yl = 500
    paso_x = (W - 2 * MARGEN) / n                          # cada momento tiene su columna: las etiquetas no se enciman
    x0, x1 = MARGEN + paso_x / 2, W - MARGEN - paso_x / 2
    xs = [x0 + (x1 - x0) * i / max(1, n - 1) for i in range(n)]
    cabeza = _clamp((p - 0.05) / 0.78) * (n - 1)              # avanza de un momento al siguiente durante la narración
    xh = x0 + (x1 - x0) * cabeza / max(1, n - 1)
    e = ease(tl / 0.5) * al
    d.rounded_rectangle([x0, yl - 4, x1, yl + 4], 4, fill=a(C["bruma"], 0.30 * e))
    d.rounded_rectangle([x0, yl - 4, xh, yl + 4], 4, fill=a(C["cempasuchil"], e))
    hueco = paso_x - 40
    fe, fd = font("xbold", 40 if n <= 4 else 34), font("semi", 30 if n <= 4 else 26)
    for i, (x, (etq, det)) in enumerate(zip(xs, momentos)):
        act = cabeza >= i - 1e-6
        ei = ease((cabeza - i + 0.35) / 0.45) * al if i else e
        r = 20
        if act:
            d.ellipse([x - r - 10, yl - r - 10, x + r + 10, yl + r + 10], fill=a(C["cempasuchil"], 0.25 * ei))
            d.ellipse([x - r, yl - r, x + r, yl + r], fill=a(C["cempasuchil"], max(ei, 0.001)))
        else:
            d.ellipse([x - r, yl - r, x + r, yl + r], fill=a(C["noche"], e), outline=a(C["bruma"], 0.6 * e), width=4)
        ancho = min(hueco, 600); xc = x
        ef, le = ajustar(etq, "xbold", fe.size, ancho, 2, minimo=26, paso=2)
        y = yl - 70 - len(le) * int(ef.size * 1.1)
        y = centrado(d, y, le, ef, a(C["cempasuchil"] if act else C["papel"], max(ei, 0.35 * e)), inter=1.1, x_centro=xc, dy=(1 - ei) * 20)
        if det:
            dl = wrap(det, fd, ancho)[:4]
            centrado(d, yl + 64, dl, fd, a(C["papel"], ei), inter=1.25, x_centro=xc, dy=(1 - ei) * -20)
    pulso = 0.5 + 0.5 * math.sin(tl * 5)
    d.ellipse([xh - 9, yl - 9, xh + 9, yl + 9], fill=a(C["papel"], (0.6 + 0.4 * pulso) * e))


def esc_documento(d, im, tx, p, tl, dur, al, fuente_corta=None):
    e = ease(tl / 0.6) * al
    sx0, sx1 = 250, 1060
    desp = 70 * ease(p)                                   # la hoja se desplaza hacia arriba durante la escena
    sy0 = 175 + (1 - e) * 90 - desp
    d.rectangle([sx0 + 14, sy0 + 16, sx1 + 14, H + 40], fill=a((0, 0, 0), 0.28 * e))
    d.rectangle([sx0, sy0, sx1, H + 40], fill=a(C["papel"], e))
    d.ellipse([sx1 - 140, sy0 + 40, sx1 - 50, sy0 + 130], outline=a(C["cempasuchil"], e), width=6)
    fs = font("black", 58); d.text((sx1 - 95 - fs.getlength("§") / 2, sy0 + 50), "§", font=fs, fill=a(C["cempasuchil"], e))
    ft, lt = ajustar(tx[0], "serif", 46, sx1 - sx0 - 220, 3, minimo=30, paso=2)
    y = sy0 + 60
    for l in lt: d.text((sx0 + 70, y), l, font=ft, fill=a(C["tinta"], e)); y += int(ft.size * 1.25)
    d.rectangle([sx0 + 70, y + 18, sx1 - 70, y + 21], fill=a(C["tinta"], 0.5 * e)); y += 60
    fl = font("semi", 32); n = max(1, len(tx) - 1)
    for i, s in enumerate(tx[1:]):
        for l in wrap(s, fl, sx1 - sx0 - 160):
            prog = _clamp((p - 0.12) * n / 0.7 - i)
            if prog > 0:
                d.rectangle([sx0 + 66, y + 4, sx0 + 74 + fl.getlength(l) * ease(prog), y + 44], fill=a(C["cempasuchil"], 0.5 * e))
            d.text((sx0 + 70, y), l, font=fl, fill=a(C["tinta"], e)); y += 50
        y += 18
    import random
    rnd = random.Random(len(tx[0]))
    while y < H + 20:                                      # renglones esquemáticos (textura de documento, sin texto real)
        d.rounded_rectangle([sx0 + 70, y + 10, sx0 + 70 + rnd.uniform(0.45, 1.0) * (sx1 - sx0 - 140), y + 22], 6, fill=a(C["tinta_suave"], 0.18 * e))
        y += 40
    # columna derecha
    xr = 1180; er = ease((tl - 0.3) / 0.6) * al
    d.text((xr, 300), "DOCUMENTO", font=font("semi", 30), fill=a(C["cempasuchil"], er))
    y = 352
    if fuente_corta:
        fr, lr = ajustar(fuente_corta, "xbold", 52, W - xr - MARGEN, 3, minimo=34, paso=2)
        for l in lr: d.text((xr, y), l, font=fr, fill=a(C["papel"], er)); y += int(fr.size * 1.2)
    d.rectangle([xr, y + 20, xr + 120, y + 27], fill=a(C["cempasuchil"], er))
    for l in wrap("Representación gráfica; no es una imagen del documento original.", font("med", 26), W - xr - MARGEN):
        d.text((xr, y + 58), l, font=font("med", 26), fill=a(C["bruma"], er)); y += 36


# Ilustraciones esquemáticas para las recreaciones: formas planas, sin rostros ni rasgos.
def _silueta(d, x, y, esc, col, al):
    r = 26 * esc
    d.ellipse([x - r, y - 150 * esc - r, x + r, y - 150 * esc + r], fill=a(col, al))
    d.rounded_rectangle([x - 40 * esc, y - 112 * esc, x + 40 * esc, y], int(34 * esc), fill=a(col, al))


def _escenario(d, tipo, al, t):
    suelo = 640
    tenue, medio = C["noche_2"], (54, 82, 118)
    d.rectangle([0, suelo, W, suelo + 6], fill=a(C["bruma"], 0.35 * al))
    if tipo == "tribunal":
        x0, x1 = 620, 1300
        d.polygon([(x0 - 40, 330), ((x0 + x1) / 2, 230), (x1 + 40, 330)], fill=a(medio, al))
        d.rectangle([x0 - 40, 330, x1 + 40, 352], fill=a(medio, al))
        for i in range(6):
            cx = x0 + 20 + i * (x1 - x0 - 40) / 5
            d.rectangle([cx - 18, 360, cx + 18, suelo - 20], fill=a(medio, al))
        d.rectangle([x0 - 60, suelo - 20, x1 + 60, suelo], fill=a(medio, al))
    elif tipo == "oficina":
        d.rectangle([700, 470, 1220, 500], fill=a(medio, al)); d.rectangle([730, 500, 750, suelo], fill=a(medio, al)); d.rectangle([1170, 500, 1190, suelo], fill=a(medio, al))
        d.rounded_rectangle([860, 330, 1060, 450], 10, fill=a(medio, al)); d.rectangle([950, 450, 970, 470], fill=a(medio, al))
        d.rounded_rectangle([878, 348, 1042, 432], 6, fill=a(C["cempasuchil"], 0.25 * al))
    elif tipo == "casa":
        d.polygon([(720, 420), (960, 260), (1200, 420)], fill=a(medio, al)); d.rectangle([760, 420, 1160, suelo], fill=a(medio, al))
        d.rectangle([920, 510, 1000, suelo], fill=a(C["noche"], al)); d.rectangle([800, 460, 870, 520], fill=a(C["cempasuchil"], 0.35 * al))
    else:                                                  # «calle» y «generico»: perfil urbano esquemático que se desplaza
        off = (t * 12) % 220
        for i in range(-1, 11):
            x = i * 220 - off; h = 160 + ((i * 53) % 5) * 45
            d.rectangle([x, suelo - h, x + 170, suelo], fill=a(medio if i % 2 else tenue, al))
            for k in range(2, h // 50):
                if (i + k) % 3: d.rectangle([x + 30, suelo - k * 46, x + 60, suelo - k * 46 + 18], fill=a(C["cempasuchil"], 0.18 * al))
    # foco de luz
    d.polygon([(960, 170), (760, suelo), (1160, suelo)], fill=a(C["cempasuchil"], 0.05 * al))


def _rotulo(d):
    """Rótulo de recreación, siempre opaco (no se desvanece): la auditoría lo busca en los píxeles."""
    caja = chip(d, MARGEN, 118, ROTULO, font("bold", 30), C["papel"], C["coral_texto"], pad=(24, 10))
    d.text((caja[2] + 20, 128), ROTULO_NOTA, font=font("semi", 26), fill=a(C["papel"], 0.95))
    return caja


def esc_recreacion(d, im, tx, p, tl, dur, al, escenario="generico"):
    e = ease(tl / 0.6) * al
    _escenario(d, escenario or "generico", e, tl)
    for k, (x, col, esc) in enumerate(((560, C["bruma"], 1.0), (960, C["cempasuchil"], 1.12), (1360, C["bruma"], 0.92))):
        paso = 110 * math.sin(tl / (5.5 + k) + k * 1.7)   # las siluetas se mueven despacio, sin salir de su lugar
        _silueta(d, x + paso, 640, esc, col, 0.9 * e)
    if tx:
        f, ls = ajustar(tx[0], "xbold", 54, 1500, 2, minimo=36, paso=2)
        y = 690
        for i, l in enumerate(ls):
            el = ease((tl - 0.4) / 0.5) * al
            w = f.getlength(l)
            d.rounded_rectangle([(W - w) / 2 - 26, y - 8, (W + w) / 2 + 26, y + f.size + 16], 14, fill=a((8, 14, 24), 0.55 * el))
            d.text(((W - w) / 2, y), l, font=f, fill=a(C["papel"], el)); y += int(f.size * 1.4)
        fs = font("semi", 34)
        for s in tx[1:2]:
            el = ease((tl - 0.7) / 0.5) * al
            centrado(d, y + 4, wrap(s, fs, 1400), fs, a(C["bruma"], el))


_SIMBOLO = {}


def esc_cierre(d, im, tx, p, tl, dur, al):
    if "s" not in _SIMBOLO: _SIMBOLO["s"] = marca.simbolo(170, "cempasuchil", "noche")
    e = ease(tl / 0.6) * al
    s = _SIMBOLO["s"]
    if e > 0.02:
        sm = s.copy(); sm.putalpha(sm.getchannel("A").point(lambda v: int(v * e)))
        im.paste(sm, ((W - s.width) // 2, int(170 + (1 - e) * 30)), sm)
    f, ls = ajustar(tx[0], "black", 96, 1500, 2, minimo=56)
    y = centrado(d, 390, ls, f, a(C["papel"], e), inter=1.08, dy=(1 - e) * 30) + 60
    fb = font("semi", 42)
    items = [wrap(s_, fb, 1300) for s_ in tx[1:]]
    bloque = max((fb.getlength(l) for lns in items for l in lns), default=0)
    if len(items) == 1: bloque = fb.getlength(items[0][0]) if items[0] else 0
    for i, lns in enumerate(items):                       # viñetas alineadas a la izquierda, bloque centrado
        ei = ease((p - 0.12 - i * 0.16) / 0.12) * al
        x = (W - bloque) / 2 + 22 + (1 - ei) * 60
        d.ellipse([x - 44, y + 14, x - 24, y + 34], fill=a(C["cempasuchil"], ei))
        for l in lns: d.text((x, y), l, font=fb, fill=a(C["papel"], ei)); y += 54
        y += 18


def cortinilla(d, titulo, tl, dur):
    """Tarjeta de inicio de capítulo (sin narración, sobre la música)."""
    al = entrada(tl, dur, 0.4, 0.4)
    etq, tit = capitulo_partes(titulo)
    m = re.search(r"\d+", etq)
    if m:
        fn = font("black", 560); n = m.group()
        d.text((W - 260 - fn.getlength(n), 140), n, font=fn, fill=a(C["papel"], 0.05 * al))
    f, ls = ajustar(tit, "black", 120, 1500, 2, minimo=64)
    alto = len(ls) * int(f.size * 1.06)
    y = 520 - alto / 2
    if etq:
        fe = font("semi", 38); e1 = ease(tl / 0.5) * al
        d.text(((W - fe.getlength(etq)) / 2, y - 80), etq, font=fe, fill=a(C["cempasuchil"], e1))
    for i, l in enumerate(ls):
        ei = ease((tl - 0.12 - 0.1 * i) / 0.5) * al
        d.text(((W - f.getlength(l)) / 2 + (1 - ei) * 90, y), l, font=f, fill=a(C["papel"], ei)); y += int(f.size * 1.06)
    barra = ease((tl - 0.3) / 0.9)
    d.rounded_rectangle([W / 2 - 260 * barra, y + 30, W / 2 + 260 * barra, y + 40], 5, fill=a(C["cempasuchil"], al))


def escenario_de(esc):
    """Si el guion no indica «escenario»: tribunal para escenas de juicio, calle para lo demás (solo cambia la ilustración)."""
    t = " ".join([esc.get("narracion", "")] + list(esc["pantalla"].get("textos") or [])).lower()
    return "tribunal" if re.search(r"\b(juicio|juez|jueza|tribunal|corte|sentencia|inocencia|proceso penal|sala)\b", t) else "calle"


DIBUJAR = {"titulo": esc_titulo, "pregunta": esc_pregunta, "cita": esc_cita, "dato": esc_dato, "linea_tiempo": esc_linea_tiempo,
           "documento": esc_documento, "recreacion": esc_recreacion, "cierre": esc_cierre}


def dibujar_escena(d, im, esc, p, tl, dur):
    pan = esc["pantalla"]; tipo = pan["tipo"]; tx = textos_visibles(esc) or [""]
    al = entrada(tl, dur)
    if hasattr(d, "off"):                                   # sube 36 px y oscila 10 px en horizontal durante la escena
        d.off = (10 * math.sin(tl / 4.0) * min(1.0, tl / 2), 18 - 36 * _clamp(p))
    if tipo in ("cita", "documento"): DIBUJAR[tipo](d, im, tx, p, tl, dur, al, fuente_corta=pan.get("fuente_corta"))
    elif tipo == "recreacion": DIBUJAR[tipo](d, im, tx, p, tl, dur, al, escenario=pan.get("escenario") or escenario_de(esc))
    else: DIBUJAR[tipo](d, im, tx, p, tl, dur, al)
    if hasattr(d, "off"): d.off = (0, 0)
    fc = pan.get("fuente_corta")
    if fc and tipo not in ("documento",):
        d.text((MARGEN, FUENTE_Y), "Fuente: " + fc, font=font("med", 28), fill=a(C["bruma"], al))


# ── subtítulos y elementos fijos ─────────────────────────────────────────────────────────────────────────────────
def bloques_subtitulos(linea):
    palabras = [w for s in linea["escenas"] for w in tiempos_palabras({"texto": s["texto"], "inicio": s["voz_inicio"], "fin": s["voz_fin"],
                                                                      "oraciones": s.get("oraciones")})]
    return bloques(palabras, max_car=SUB_MAX_CAR)


def dibujar_subtitulos(d, t, bls, cursor):
    """cursor: [índice] del bloque actual (avanza en orden, sin buscar desde el principio en cada cuadro)."""
    i = cursor[0]
    while i < len(bls) and bls[i][-1][2] + 0.15 < t: i += 1
    cursor[0] = i
    if i >= len(bls) or bls[i][0][1] - 0.05 > t: return False
    b = bls[i]
    f = font("xbold", 44)
    texto = " ".join(x[0] for x in b); ancho = f.getlength(texto); x0 = (W - ancho) / 2
    d.rounded_rectangle([x0 - 30, SUB_Y - 20, x0 + ancho + 30, SUB_Y + 66], 22, fill=(8, 14, 24, 205))
    x = x0
    for (pal, ti, tf) in b:
        d.text((x, SUB_Y), pal, font=f, fill=C["cempasuchil"] if ti <= t else C["papel"]); x += f.getlength(pal + " ")
    return True


def encabezado(d, t, total, capitulo):
    d.rectangle([0, 0, W, 6], fill=(255, 255, 255, 26)); d.rectangle([0, 0, W * t / total, 6], fill=C["cempasuchil"])
    fh = font("bold", 26); d.text((MARGEN, 58), marca.TOK["firma"], font=fh, fill=a(C["papel"], 0.9))
    if capitulo:
        etq, tit = capitulo_partes(capitulo)
        txt = "  ·  " + (f"{etq.title()} · {tit}" if etq else tit)
        d.text((MARGEN + fh.getlength(marca.TOK["firma"]), 59), txt, font=font("semi", 25), fill=a(C["bruma"], 0.9))
    lab = "Voz generada con IA"; fl = font("med", 24)
    d.text((W - MARGEN - fl.getlength(lab), 60), lab, font=fl, fill=a(C["bruma"], 0.9))


# ── render ───────────────────────────────────────────────────────────────────────────────────────────────────────
def render(guion, linea, salida_mp4, preset="veryfast", cuadros=None):
    """Cuerpo mudo del documental. linea = documental.linea_tiempo(...). Devuelve el registro del render (cuadros con
    subtítulo, cuadros con rótulo por escena «recreacion», posición del rótulo). cuadros: {t: ruta} para guardar algunos
    fotogramas de muestra (revisión visual)."""
    total = linea["total_s"]; n = int(math.ceil(total * FPS))
    base = fondo_ancho(); orbe = _orbe()
    escenas = guion["escenas"]; tramos = linea["escenas"]
    bls = bloques_subtitulos(linea); cursor = [0]
    cmd = ["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-c:v", "libx264", "-preset", preset, "-crf", "20", "-r", str(FPS), "-pix_fmt", "yuv420p", "-g", "60", str(salida_mp4)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    t0 = time.time(); con_sub = 0; rotulos = {}; caja_rotulo = None
    cuadros = dict(cuadros or {}); pedidos = sorted(cuadros)
    k = 0
    try:
        for i in range(n):
            t = i / FPS
            off = int(PAN_PX * t / total)
            fr = base.crop((off, 0, off + W, H))
            ox = 1200 + 380 * math.sin(t / 23.0); oy = 300 + 160 * math.cos(t / 17.0)       # resplandor que deriva
            fr.paste(orbe, (int(ox - orbe.width / 2), int(oy - orbe.height / 2)), orbe)
            d = Lienzo(fr)
            while k + 1 < len(tramos) and t >= tramos[k + 1]["inicio"]: k += 1
            s = tramos[k]; esc = escenas[k]
            if s.get("cortinilla") and s["cortinilla"][0] <= t < s["cortinilla"][1]:
                encabezado(d, t, total, None)
                cortinilla(d, s["capitulo"], t - s["cortinilla"][0], s["cortinilla"][1] - s["cortinilla"][0])
            else:
                ini = s["cortinilla"][1] if s.get("cortinilla") else s["inicio"]
                dur = s["fin"] - ini; tl = t - ini
                encabezado(d, t, total, s.get("capitulo"))
                dibujar_escena(d, fr, esc, _clamp(tl / max(0.1, dur)), tl, dur)
                if esc["pantalla"]["tipo"] == "recreacion":
                    caja_rotulo = _rotulo(d); rotulos.setdefault(esc["n"], 0); rotulos[esc["n"]] += 1
            if dibujar_subtitulos(d, t, bls, cursor): con_sub += 1
            while pedidos and pedidos[0] <= t:
                fr.save(cuadros[pedidos.pop(0)])
            proc.stdin.write(fr.tobytes())
        proc.stdin.close()
        if proc.wait(): raise RuntimeError(f"ffmpeg (render): {proc.stderr.read().decode(errors='replace')[-400:]}")
    finally:
        if proc.poll() is None: proc.kill()
    esperados = {e["n"]: int(round((s["fin"] - (s["cortinilla"][1] if s.get("cortinilla") else s["inicio"])) * FPS))
                 for e, s in zip(escenas, tramos) if e["pantalla"]["tipo"] == "recreacion"}
    return {"cuadros": n, "segundos_render": round(time.time() - t0, 1), "cuadros_con_subtitulo": con_sub,
            "cuadros_rotulo": rotulos, "cuadros_recreacion": esperados, "caja_rotulo": caja_rotulo or list(ROTULO_CAJA),
            "bloques_subtitulo": len(bls)}


# ── tarjetas de entrada y cierre (identidad del video semanal: fondo, logotipo, firma sonora) ───────────────────────
def tarjeta(tipo, guion, aviso):
    import youtube_semanal as ys
    im = ys._fondo(); d = ImageDraw.Draw(im); F = marca.F
    logo = marca.logo_horizontal(150 if tipo == "intro" else 170, "oscuro"); im.alpha_composite(logo, ((W - logo.width) // 2, 170 if tipo == "intro" else 200))
    dibujados = []
    if tipo == "intro":
        f = F("semi", 34); l = "DOCUMENTAL"; d.text(((W - d.textlength(l, font=f)) / 2, 400), l, font=f, fill=C["cempasuchil"]); dibujados.append(l)
        tam = 76
        while True:
            ft = F("display_black", tam); ls = wrap(guion["titulo"].replace("[PRUEBA] ", "[PRUEBA] "), ft, 1560)
            if len(ls) <= 3 or tam <= 48: break
            tam -= 4
        y = 470
        for l in ls: d.text(((W - d.textlength(l, font=ft)) / 2, y), l, font=ft, fill=C["papel"]); y += int(tam * 1.15); dibujados.append(l)
        fa = F("semi", 38); d.text(((W - d.textlength(aviso, font=fa)) / 2, 900), aviso, font=fa, fill=C["bruma"]); dibujados.append(aviso)
    else:
        y = 480
        for l, f, c in ((aviso, F("display_xbold", 58), C["papel"]),
                        ("Las fuentes oficiales están en la descripción del video.", F("semi", 36), C["bruma"]),
                        ("Síguenos para entender tus derechos.", F("semi", 42), C["cempasuchil"])):
            d.text(((W - d.textlength(l, font=f)) / 2, y), l, font=f, fill=c); y += int(f.size * 1.9); dibujados.append(l)
    return im.convert("RGB"), dibujados
