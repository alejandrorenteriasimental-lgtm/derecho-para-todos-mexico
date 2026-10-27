"""Verificación de tesis y jurisprudencia en el Semanario Judicial de la Federación (sjf2.scjn.gob.mx), sin IA.
Corre dentro del ciclo en GitHub Actions (el entorno de desarrollo no tiene acceso a ese sitio). Para cada registro de
registro/tesis/por_verificar.json consulta el servicio público del Semanario, guarda la respuesta cruda y un dictamen:
VERIFICADA (existe y coinciden clave y rubro), DISCREPANTE (existe pero no coincide), NO_ENCONTRADA o SIN_ACCESO.
Una pieza solo puede citar una tesis VERIFICADA (razonamiento: regla «jurisprudencia»). La vigencia (si fue superada o
interrumpida) y la aplicabilidad quedan anotadas para la revisión humana: el servicio no siempre las informa."""
import json, re, sys, unicodedata, urllib.error, urllib.request
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CARPETA = RAIZ / "registro" / "tesis"
UA = "AquiDiceLaLey-verificador/0.1 (divulgación jurídica)"
URLS = ("https://sjf2.scjn.gob.mx/services/sjftesismicroservice/api/public/tesis/{r}?isSemanal=true&hostName=https://sjf2.scjn.gob.mx",
        "https://sjf2.scjn.gob.mx/services/sjftesismicroservice/api/public/tesis/{r}")


def _plano(t):
    t = unicodedata.normalize("NFD", str(t or "").lower())
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", "".join(c for c in t if unicodedata.category(c) != "Mn"))).strip()


def _get(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r: return r.status, r.read()
    except urllib.error.HTTPError as e: return e.code, e.read() if hasattr(e, "read") else b""
    except (urllib.error.URLError, TimeoutError, OSError) as e: return None, str(e).encode()


def _campo(d, *nombres):
    for n in nombres:
        for k, v in (d.items() if isinstance(d, dict) else []):
            if k.lower() == n.lower() and v: return v
    return None


def verificar(t, get=_get):
    r = str(t["registro"]); res = {"registro": r, "consultado": datetime.now(timezone.utc).isoformat(timespec="seconds"), "intentos": []}
    for u in URLS:
        st, cuerpo = get(u.format(r=r)); res["intentos"].append({"url": u.format(r=r), "http": st, "bytes": len(cuerpo or b"")})
        if st != 200: continue
        try: d = json.loads(cuerpo)
        except ValueError: continue
        if isinstance(d, list): d = d[0] if d else {}
        (CARPETA / f"{r}_crudo.json").write_text(json.dumps(d, ensure_ascii=False, indent=1)[:200000])
        rubro = _campo(d, "rubro", "titulo"); clave = _campo(d, "tesis", "clave", "claveTesis")
        res.update(rubro=rubro, clave=clave, instancia=_campo(d, "instancia", "organoJuris", "organo"), epoca=_campo(d, "epoca"),
                   tipo=_campo(d, "tipoTesis", "tipo"), publicacion=_campo(d, "fechaPublicacion", "fecha"), materia=_campo(d, "materias", "materia"))
        ok_rubro = bool(rubro) and _plano(t.get("rubro_esperado", ""))[:80] in _plano(rubro)
        ok_clave = bool(clave) and _plano(t.get("clave_esperada", "")) == _plano(clave)
        res["dictamen"] = "VERIFICADA" if (ok_rubro and ok_clave) else "DISCREPANTE" if rubro else "NO_ENCONTRADA"
        res["pendiente_humano"] = "Confirmar vigencia (que no esté superada o interrumpida) y aplicabilidad (obliga solo a su circuito si es de un tribunal colegiado)."
        return res
    res["dictamen"] = "NO_ENCONTRADA" if any(i["http"] == 404 for i in res["intentos"]) else "SIN_ACCESO"
    return res


def main():
    CARPETA.mkdir(parents=True, exist_ok=True)
    lista = json.loads((CARPETA / "por_verificar.json").read_text())["tesis"]
    out = {}
    for t in lista:
        out[t["registro"]] = verificar(t)
        (CARPETA / f'{t["registro"]}.json').write_text(json.dumps(out[t["registro"]], ensure_ascii=False, indent=1))
    print(json.dumps({k: v["dictamen"] for k, v in out.items()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
