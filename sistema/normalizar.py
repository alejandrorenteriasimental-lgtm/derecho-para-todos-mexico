"""Normalización de texto para narración en español de México.
Convierte cifras, artículos, siglas y símbolos a la forma en que se dicen en voz alta."""
import re
from num2words import num2words

SIGLAS = {
    "SCJN": "Suprema Corte", "CPEUM": "Constitución", "CDMX": "Ciudad de México", "DOF": "Diario Oficial de la Federación",
    "LFT": "Ley Federal del Trabajo", "CNPP": "Código Nacional de Procedimientos Penales", "CPF": "Código Penal Federal",
    "IMSS": "ims", "INFONAVIT": "infonavit", "PTU": "pe te u", "UMA": "uma", "SAT": "sat", "FGR": "efe ge erre",
    "Profeco": "Profeco", "PROFECO": "Profeco", "Condusef": "Condusef", "CONDUSEF": "Condusef",
}
# Respelling fonético para topónimos con «x» náhuatl y otras trampas de espeak-ng (se amplía con cada error detectado)
LEXICO = {"Oaxaca": "Oajaca", "Xalapa": "Jalapa", "Texcoco": "Tescoco", "Mixcoac": "Miscoac", "Ixtapaluca": "Istapaluca",
          "Ixtapa": "Istapa", "Taxco": "Tasco", "Xalisco": "Jalisco", "Tuxtla": "Tustla",
          "Ixtepec": "Istepec", "Xoxocotlán": "Jojocotlán"}
ABREV = {r"\bart\.\s*": "artículo ", r"\barts\.\s*": "artículos ", r"\bfr\.\s*": "fracción ", r"\bNo\.\s*": "número ",
         r"\bLic\.\s*": "licenciado ", r"\bDr\.\s*": "doctor ", r"\bEE\.\s*UU\.": "Estados Unidos"}


def _num(m):
    s = m.group(0).replace(",", "")
    if "." in s:
        e, d = s.split(".")
        return num2words(int(e), lang="es") + " punto " + " ".join(num2words(int(c), lang="es") for c in d)
    return num2words(int(s), lang="es") + "\u2063"  # marca: cifra original (solo estas reciben apócope)


NO_SUST = {"y", "o", "u", "de", "del", "a", "al", "en", "por", "punto", "con", "que", "para", "sin", "entre", "es", "son", "e", "más", "menos", "solo", "sólo"}
MASC_EN_A = {"día", "días", "mapa", "problema", "sistema", "tema", "programa", "idioma", "clima", "planeta"}
FEM = {"vez", "ley", "fracción", "parte", "mujer", "persona", "sede", "red", "llave", "noche", "tarde", "fe", "clase", "suerte"}


def _apocope(m):
    """«uno mes» → «un mes»; «veintiuno semanas» → «veintiuna semanas» (concordancia del numeral ante sustantivo)."""
    pre, sig = m.group(1), m.group(2)
    if sig.lower() in NO_SUST or sig[0].isdigit():
        return m.group(0)
    s = sig.lower()
    fem = s in FEM or s.endswith(("ción", "sión", "dad", "tad", "tud")) or (s.endswith(("a", "as")) and s not in MASC_EN_A)
    if fem:
        return f"{pre}una {sig}"
    return f"{pre}{'ún' if pre else 'un'} {sig}" if pre else f"un {sig}"


def normalizar(texto: str) -> str:
    t = texto
    for patron, rep in ABREV.items():
        t = re.sub(patron, rep, t)
    for sigla, rep in SIGLAS.items():
        t = re.sub(rf"\b{sigla}\b", rep, t)
    for pal, rep in LEXICO.items():
        t = re.sub(rf"\b{pal}\b", rep, t)
    def _pesos(m):
        e, _, c = m.group(1).replace(",", "").partition(".")
        out = re.sub(r"uno$", "ún" if int(e) % 100 not in (1,) and int(e) % 10 == 1 else "un", num2words(int(e), lang="es")) + (" peso" if int(e) == 1 else " pesos")
        if c and int(c): out += " con " + num2words(int(c.ljust(2, "0")[:2]), lang="es") + " centavos"
        return out
    t = re.sub(r"\$\s?([\d,]+(?:\.\d+)?)", _pesos, t)
    t = re.sub(r"([\d,]+(?:\.\d+)?)\s?%", lambda m: _num(re.match(r"[\d,.]+", m.group(1))) + " por ciento", t)
    t = re.sub(r"\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b|\b\d+(?:\.\d+)?\b", _num, t)
    t = re.sub(r"\b(\w*)uno\u2063 (\w+)", _apocope, t).replace("\u2063", "")
    t = t.replace("«", "").replace("»", "").replace("“", "").replace("”", "")
    return re.sub(r"\s+", " ", t).strip()


if __name__ == "__main__":
    print(normalizar("El art. 17 de la CPEUM y el CPF, art. 336: de 1 a 5 años; multa de $1,250.50 o 30%. SCJN, CDMX, 2026."))
