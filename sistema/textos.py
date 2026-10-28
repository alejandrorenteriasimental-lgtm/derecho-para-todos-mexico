"""Extrae el texto OFICIAL de artículos concretos (PDF de la Cámara de Diputados) y lo guarda en registro/textos/.
Sirve para que la redacción y la revisión editorial trabajen sobre el texto vigente, nunca de memoria.
Uso (en GitHub Actions, que sí tiene acceso a diputados.gob.mx): python sistema/textos.py "LFPC:56,77,79,92;LFT:53,87,162"
"""
import json, sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import redactor, verificador

RAIZ = Path(__file__).resolve().parent.parent


def extraer(espec, transporte=verificador.transporte_resiliente):   # reintentos (el portal falla seguido desde GitHub)
    out = RAIZ / "registro" / "textos"; out.mkdir(parents=True, exist_ok=True)
    resumen = []
    for grupo in [g for g in espec.split(";") if g.strip()]:
        sigla, arts = grupo.split(":")
        o = redactor.ORDEN[sigla.strip()]
        estado, ctype, datos = transporte(o["url"])
        cab, cuerpo = verificador.texto_de(ctype, datos)
        reforma = verificador.ultima_reforma(cab) if hasattr(verificador, "ultima_reforma") else None
        for a in [x.strip() for x in arts.split(",") if x.strip()]:
            if a.startswith("?"):                           # búsqueda de un término (p. ej., en los transitorios)
                import re as _re
                plano = _re.sub(r"\s+", " ", cuerpo); term = a[1:].lower(); hallazgos = []
                for m in _re.finditer(_re.escape(term), plano.lower()):
                    hallazgos.append(plano[max(0, m.start() - 600): m.end() + 600])
                reg = {"sigla": sigla.strip(), "documento": o["documento"], "busqueda": term, "url": o["url"], "ultima_reforma": reforma,
                       "consultado": datetime.now(timezone.utc).isoformat(timespec="seconds"), "hallazgos": hallazgos[-12:]}
                (out / f"{sigla.strip()}_buscar_{term.replace(' ', '_')[:30]}.json").write_text(json.dumps(reg, ensure_ascii=False, indent=1))
                resumen.append(f"{sigla} ?{term}: {len(hallazgos)} hallazgos"); continue
            t = verificador.articulo_texto(cuerpo, a, max_car=20000)
            reg = {"sigla": sigla.strip(), "documento": o["documento"], "articulo": a, "url": o["url"], "ultima_reforma": reforma,
                   "consultado": datetime.now(timezone.utc).isoformat(timespec="seconds"), "texto": t}
            (out / f"{sigla.strip()}_{a.replace(' ', '_')}.json").write_text(json.dumps(reg, ensure_ascii=False, indent=1))
            resumen.append(f"{sigla} {a}: {'OK' if t else 'NO ENCONTRADO'} ({len(t or '')} car.)")
    print("\n".join(resumen))


if __name__ == "__main__":
    extraer(sys.argv[1])
