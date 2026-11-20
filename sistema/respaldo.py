"""Respaldo persistente y PRIVADO de las piezas producidas (sin costo).

Los archivos de cada pieza (MP4/PNG final, subtítulos, auditorías) se suben como «assets» de un release del propio
repositorio privado (GitHub Releases). Un release de un repositorio privado solo lo ven quienes tienen acceso al
repositorio; no ocupa minutos de Actions ni tiene costo en el plan gratuito. Los artefactos de Actions vencen a los
14 días; los assets del release no vencen.

Cada archivo queda en estado/respaldo.json con su sha256, tamaño e id del asset. Ese sha256 es la «versión exacta»
que se envía a revisión humana y la que se descarga después para publicar: si el archivo cambia, la huella cambia
y una aprobación anterior ya no aplica (ver revision.py).
"""
import hashlib, json, os, urllib.error, urllib.parse, urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
MANIFIESTO = RAIZ / "estado" / "respaldo.json"
API = "https://api.github.com"
LIMITE_ASSETS = 1000          # límite de GitHub por release
MAX_RELEASES_MES = 9
PATRONES = ("*_final.mp4", "*_final.srt", "*.png", "verificacion.json", "auditoria.json", "*_copy.txt")


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()


def cargar():
    return json.loads(MANIFIESTO.read_text()) if MANIFIESTO.exists() else {}


def guardar(m):
    MANIFIESTO.parent.mkdir(parents=True, exist_ok=True)
    MANIFIESTO.write_text(json.dumps(m, ensure_ascii=False, indent=2, sort_keys=True))


def http_real(metodo, url, token, datos=None, tipo="application/json"):
    req = urllib.request.Request(url, data=datos, method=metodo, headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "Content-Type": tipo,
        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "aqui-dice-la-ley"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            cuerpo = r.read(); return r.status, (json.loads(cuerpo) if cuerpo[:1] in (b"{", b"[") else cuerpo)
    except urllib.error.HTTPError as e:
        cuerpo = e.read(); return e.code, (json.loads(cuerpo) if cuerpo[:1] in (b"{", b"[") else cuerpo)


def archivos_de(carpeta_salida):
    vistos = []
    for pat in PATRONES:
        for p in sorted(Path(carpeta_salida).glob(pat)):
            if p.is_file() and p not in vistos and p.name != "cuadros_final.png": vistos.append(p)
    return vistos


def _release(repo, token, http, etiqueta):
    st, r = http("GET", f"{API}/repos/{repo}/releases/tags/{etiqueta}", token)
    if st == 200: return r
    st, r = http("POST", f"{API}/repos/{repo}/releases", token, json.dumps({
        "tag_name": etiqueta, "name": f"Respaldo privado de piezas ({etiqueta})", "draft": False, "prerelease": True,
        "body": "Respaldo automático de las piezas producidas por el ciclo. Repositorio privado: no es público."}).encode())
    if st not in (200, 201): raise RuntimeError(f"no se pudo crear el release {etiqueta}: HTTP {st} {str(r)[:200]}")
    return r


def respaldar(pid, carpeta_salida, env=os.environ, http=http_real, etiqueta=None):
    """Sube (o confirma) los archivos de la pieza. Idempotente: si el asset con el mismo sha256 ya existe, no lo repite.
    Devuelve {archivo: {sha256, bytes, asset_id, release}}; sin token (pruebas locales) solo calcula las huellas."""
    repo, token = env.get("GITHUB_REPOSITORY"), env.get("GITHUB_TOKEN")
    m = cargar(); reg = m.setdefault(pid, {})
    arch = archivos_de(carpeta_salida)
    if not arch: return reg
    if not (repo and token):
        for p in arch: reg[p.name] = {**reg.get(p.name, {}), "sha256": sha256(p), "bytes": p.stat().st_size, "asset_id": reg.get(p.name, {}).get("asset_id")}
        guardar(m); return reg
    from datetime import datetime, timezone
    base = etiqueta or "piezas-" + datetime.now(timezone.utc).strftime("%Y-%m")
    # 20-11-2026: GitHub admite como máximo 1,000 assets por release; al llenarse «piezas-2026-11» cada subida
    # respondía HTTP 422 y las piezas quedaban sin versión aprobable. Si el release está lleno se usa el siguiente
    # («<base>-2», «<base>-3», …); los assets ya subidos se reconocen en cualquiera de ellos (idempotencia).
    existentes, etiqueta, rel = {}, None, None
    for i in range(1, MAX_RELEASES_MES + 1):
        etq = base if i == 1 else f"{base}-{i}"
        r = _release(repo, token, http, etq)
        for a in r.get("assets", []): existentes.setdefault(a["name"], (etq, a))
        if len(r.get("assets", [])) + len(arch) <= LIMITE_ASSETS:
            etiqueta, rel = etq, r; break
    if rel is None: raise RuntimeError(f"los releases {base} a {base}-{MAX_RELEASES_MES} están llenos")
    for p in arch:
        h = sha256(p); nombre = f"{pid}__{h[:12]}__{p.name}"
        if reg.get(p.name, {}).get("sha256") == h and reg[p.name].get("asset_id"): continue
        if nombre in existentes:
            etq_a, a = existentes[nombre]
            reg[p.name] = {"sha256": h, "bytes": p.stat().st_size, "asset_id": a["id"], "asset": nombre, "release": etq_a}
            continue
        else:
            url = rel["upload_url"].split("{")[0] + "?" + urllib.parse.urlencode({"name": nombre})
            tipo = "video/mp4" if p.suffix == ".mp4" else "image/png" if p.suffix == ".png" else "application/json" if p.suffix == ".json" else "text/plain"
            st, a = http("POST", url, token, p.read_bytes(), tipo)
            if st not in (200, 201): raise RuntimeError(f"no se pudo respaldar {p.name}: HTTP {st} {str(a)[:200]}")
        reg[p.name] = {"sha256": h, "bytes": p.stat().st_size, "asset_id": a["id"], "asset": nombre, "release": etiqueta}
    guardar(m); return reg


def descargar(pid, archivo, destino, env=os.environ, http=http_real):
    """Recupera del respaldo el archivo EXACTO (verifica el sha256) para publicar o revisar en otro runner."""
    repo, token = env["GITHUB_REPOSITORY"], env["GITHUB_TOKEN"]
    reg = cargar()[pid][archivo]
    req = urllib.request.Request(f"{API}/repos/{repo}/releases/assets/{reg['asset_id']}",
                                 headers={"Authorization": f"Bearer {token}", "Accept": "application/octet-stream", "User-Agent": "aqui-dice-la-ley"})
    with urllib.request.urlopen(req, timeout=300) as r: datos = r.read()
    if hashlib.sha256(datos).hexdigest() != reg["sha256"]:
        raise RuntimeError(f"el respaldo de {pid}/{archivo} no coincide con su huella registrada")
    Path(destino).write_bytes(datos); return Path(destino)
