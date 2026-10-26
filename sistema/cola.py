"""Cola de trabajo persistente basada en archivos (versionados en el repositorio).
Estados: PENDIENTE → (verificación jurídica) → PRODUCIDO → APROBADO | RETENIDO | REVISION_HUMANA
         APROBADO → SIMULADO (modo simulación; nunca cuenta como programado ni publicado)
         APROBADO → PUBLICANDO → PROGRAMADO | PUBLICADO → MEDIDO ; FALLIDO tras agotar reintentos.
PROGRAMADO y PUBLICADO solo se alcanzan con confirmación del estado remoto en Meta (ver publicar.py).
Garantías: un trabajo por pieza; transiciones registradas; reintentos acotados con espera exponencial;
bloqueo (lease) contra dos ejecuciones simultáneas; la publicación es idempotente (ver publicar.py)."""
import json, os, time
from datetime import datetime, timezone, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
COLA = RAIZ / "estado" / "cola.json"
BITACORA = RAIZ / "estado" / "bitacora.jsonl"
LOCK = RAIZ / "estado" / "lock.json"
MAX_INTENTOS = 3
TRANSICIONES = {
    "PENDIENTE": {"PRODUCIDO", "RETENIDO", "REVISION_HUMANA", "FALLIDO"},   # la verificación jurídica ocurre antes de producir
    "PRODUCIDO": {"APROBADO", "RETENIDO"},
    "RETENIDO": {"PENDIENTE"},            # vuelve a verificarse si el motivo era transitorio o si el guion cambió
    "REVISION_HUMANA": {"APROBADO", "RETENIDO", "PENDIENTE"},
    "APROBADO": {"SIMULADO", "PUBLICANDO", "FALLIDO"},
    "SIMULADO": {"APROBADO", "PENDIENTE"},   # tras la autorización de lanzamiento puede re-entrar a publicación real
    "PUBLICANDO": {"PROGRAMADO", "PUBLICADO", "FALLIDO"},
    "PROGRAMADO": {"PUBLICADO", "FALLIDO"},
    "PUBLICADO": {"MEDIDO"},
    "MEDIDO": set(), "FALLIDO": {"PENDIENTE"},
}
ESTADOS_REALES = {"PUBLICANDO", "PROGRAMADO", "PUBLICADO", "MEDIDO"}   # solo alcanzables en modo real


def ahora():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def cargar():
    return json.loads(COLA.read_text()) if COLA.exists() else {"trabajos": {}}


def guardar(c):
    COLA.parent.mkdir(exist_ok=True)
    tmp = COLA.with_suffix(".tmp"); tmp.write_text(json.dumps(c, ensure_ascii=False, indent=2)); os.replace(tmp, COLA)  # escritura atómica


def log(evento):
    BITACORA.parent.mkdir(exist_ok=True)
    with open(BITACORA, "a") as f: f.write(json.dumps({"ts": ahora(), **evento}, ensure_ascii=False) + "\n")


def adquirir_lock(dueño, minutos=50):
    if LOCK.exists():
        l = json.loads(LOCK.read_text())
        if datetime.fromisoformat(l["expira"]) > datetime.now(timezone.utc) and l["dueño"] != dueño:
            return False
    LOCK.parent.mkdir(exist_ok=True)
    LOCK.write_text(json.dumps({"dueño": dueño, "expira": (datetime.now(timezone.utc) + timedelta(minutes=minutos)).isoformat()}))
    return True


def liberar_lock(dueño):
    if LOCK.exists() and json.loads(LOCK.read_text())["dueño"] == dueño: LOCK.unlink()


def encolar(c, pieza_id, prioridad=0, formato="reel", huella=None):
    if pieza_id in c["trabajos"]:
        return False  # nunca duplica trabajos
    c["trabajos"][pieza_id] = {"id": pieza_id, "formato": formato, "huella": huella, "estado": "PENDIENTE", "prioridad": prioridad,
                               "intentos": 0, "creado": ahora(), "historial": [], "error": None, "publicaciones": {},
                               "proximo_intento": None, "retencion": None}
    log({"pieza": pieza_id, "evento": "encolado"}); return True


def mover(c, pieza_id, nuevo, motivo="", modo=None):
    t = c["trabajos"][pieza_id]
    if nuevo in ESTADOS_REALES and modo != "real":
        raise ValueError(f"{nuevo} solo es alcanzable con una operación real confirmada (modo={modo})")
    if nuevo not in TRANSICIONES[t["estado"]]:
        raise ValueError(f"Transición inválida {t['estado']} → {nuevo} en {pieza_id}")
    t["historial"].append({"de": t["estado"], "a": nuevo, "ts": ahora(), "motivo": motivo}); t["estado"] = nuevo
    log({"pieza": pieza_id, "evento": "transicion", "a": nuevo, "motivo": motivo})


def fallo(c, pieza_id, error):
    t = c["trabajos"][pieza_id]; t["intentos"] += 1; t["error"] = str(error)[:500]
    espera = 15 * 2 ** (t["intentos"] - 1)  # 15, 30, 60 min
    t["proximo_intento"] = (datetime.now(timezone.utc) + timedelta(minutes=espera)).isoformat()
    log({"pieza": pieza_id, "evento": "fallo", "intento": t["intentos"], "error": t["error"]})
    if t["intentos"] >= MAX_INTENTOS:
        mover(c, pieza_id, "FALLIDO", "intentos agotados"); return "alerta"
    return "reintento"


def siguientes(c, estado, n=1, formato=None):
    hoy = datetime.now(timezone.utc)
    lista = [t for t in c["trabajos"].values() if t["estado"] == estado and (formato is None or t.get("formato", "reel") == formato) and
             (not t["proximo_intento"] or datetime.fromisoformat(t["proximo_intento"]) <= hoy)]
    return sorted(lista, key=lambda t: (-t["prioridad"], t["creado"]))[:n]
