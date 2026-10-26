"""Guardia de presupuesto. Todo componente que pudiera generar un cargo externo debe pedir autorización aquí ANTES
de ejecutarse. Con el tope autorizado de 0 MXN (valor predeterminado) cualquier gasto mayor a cero se rechaza.
Hoy ningún componente del sistema genera cargos: la guardia existe para que un cambio futuro no pueda gastar sin
autorización explícita (variable TOPE_MXN_MES, que solo modifica la persona responsable)."""
import json, os
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
GASTOS = RAIZ / "registro" / "gastos.jsonl"


class PresupuestoExcedido(Exception):
    pass


def tope(env=os.environ):
    try:
        return max(0.0, float(env.get("TOPE_MXN_MES") or 0))
    except ValueError:
        return 0.0   # un valor ilegible nunca amplía el presupuesto


def gastado_mes(archivo=None):
    archivo = Path(archivo or GASTOS)
    if not archivo.exists(): return 0.0
    mes = datetime.now(timezone.utc).strftime("%Y-%m")
    return sum(json.loads(l)["mxn"] for l in archivo.read_text().splitlines() if l.strip() and json.loads(l)["fecha"].startswith(mes))


def autorizar(mxn, concepto, env=os.environ, archivo=None):
    if mxn < 0: raise ValueError("monto negativo")
    if mxn == 0: return True
    t, g = tope(env), gastado_mes(archivo)
    if g + mxn > t:
        raise PresupuestoExcedido(f"{concepto}: {mxn:.2f} MXN rebasa el tope autorizado ({t:.2f} MXN/mes; gastado {g:.2f})")
    archivo = Path(archivo or GASTOS); archivo.parent.mkdir(parents=True, exist_ok=True)
    with open(archivo, "a") as f:
        f.write(json.dumps({"fecha": datetime.now(timezone.utc).isoformat(timespec="seconds"), "mxn": mxn, "concepto": concepto}, ensure_ascii=False) + "\n")
    return True
