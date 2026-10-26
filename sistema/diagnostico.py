"""Diagnóstico de fuentes rechazadas: guarda el texto OFICIAL del artículo citado y el fragmento más parecido a la
cita esperada, para corregir el guion con el texto real (nunca con un espejo privado ni de memoria).
Salida: registro/diagnostico/<pieza>_<fuente>.txt (se versiona en el repositorio)."""
import difflib, json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verificador

RAIZ = Path(__file__).resolve().parent.parent


def mas_parecido(texto, cita, ventana_extra=40):
    plano = verificador._plano(texto); c = verificador._plano(cita)
    if not plano or not c: return 0.0, ""
    paso = max(10, len(c) // 4); mejor = (0.0, "")
    for i in range(0, max(1, len(plano) - len(c)) + 1, paso):
        trozo = plano[i:i + len(c) + ventana_extra]
        r = difflib.SequenceMatcher(None, c, trozo).ratio()
        if r > mejor[0]: mejor = (r, trozo)
    return round(mejor[0], 3), mejor[1]


def diagnosticar(transporte=verificador.transporte_http):
    out = RAIZ / "registro" / "diagnostico"; out.mkdir(parents=True, exist_ok=True)
    docs = {}
    for vf in sorted((RAIZ / "piezas").glob("*/salida/verificacion.json")):
        pieza = vf.parent.parent.name; v = json.loads(vf.read_text())
        g = verificador.adaptar(json.loads((vf.parent.parent / "guion.json").read_text()))
        fichas = {f["id"]: f for f in g["fuentes"]}
        for fid, ev in v["fuentes"].items():
            if ev["estado"] in ("VERIFICADA", "NO_VERIFICABLE"): continue
            f = fichas.get(fid)
            if not f or not f.get("url"): continue
            if f["url"] not in docs:
                try:
                    docs[f["url"]] = verificador.texto_de(*transporte(f["url"])[1:])
                except Exception as e:
                    docs[f["url"]] = None; print(f"{pieza} {fid}: no se pudo descargar ({e})"); continue
            if not docs[f["url"]]: continue
            cab, cuerpo = docs[f["url"]]
            art = verificador.articulo_texto(cuerpo, f["articulo"], max_car=20000) or "(no se encontró el encabezado del artículo)"
            ratio, trozo = mas_parecido(art, f.get("literal", ""))
            (out / f"{pieza}_{fid}.txt").write_text(
                f"Pieza: {pieza}\nFuente: {fid} — {f['documento']}, artículo {f['articulo']}\nURL: {f['url']}\n"
                f"Estado: {ev['estado']} — {ev['motivo']}\nÚltima reforma del documento: {ev.get('ultima_reforma_documento')}\n\n"
                f"CITA ESPERADA:\n{f.get('literal')}\n\nFRAGMENTO OFICIAL MÁS PARECIDO (similitud {ratio}):\n{trozo}\n\n"
                f"TEXTO OFICIAL DEL ARTÍCULO:\n{art}\n")
            print(f"{pieza} {fid}: similitud {ratio}")


if __name__ == "__main__":
    diagnosticar()
