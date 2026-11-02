# Operación única — quién puede modificar el repositorio (3-11-2026)

Decisión pedida por el responsable el 2-11-2026 («unificar la operación… evitar cambios contradictorios»).

## Quién escribe en `main`
1. **Flujos de GitHub Actions** (usuario `dpt-bot`): `ciclo`, `publicacion`, `tiktok`, `meta-prueba`, `textos`, `revision`. Solo escriben `estado/`, `registro/` y los guiones producidos.
2. **La tarea programada «Aquí Dice la Ley · Operación autónoma diaria»** (05:41 CDMX): única operación editorial y técnica rutinaria (revisión, aprobación delegada, calendario, lotes, correcciones con prueba).
3. **Una sola conversación de trabajo con el responsable**: la que él esté usando en ese momento. Todo cambio de reglas, código o autorización sale de ahí y queda en un commit con su sesión.

Cualquier otra sesión de Claude trabaja en **solo lectura**: puede consultar y reportar, no hacer commits.

## Reglas para quien escribe
- `git pull` antes de empezar y antes de cada commit; nunca forzar (`--force`).
- Las pruebas (`python -m pytest -q pruebas -m "not vivo"`) pasan antes de subir; si una dependencia nueva aparece, va en `requirements.txt` en el mismo commit.
- No se tocan piezas aprobadas ni `estado/aprobaciones.jsonl` salvo con `sistema/decidir.py`.
- Las decisiones del responsable se registran en `data/lanzamiento.json` (autorización) o en el documento correspondiente, con fecha y su texto.

## Tareas programadas relacionadas (cuenta del responsable)
| Tarea | Función | Escribe en el repo |
|---|---|---|
| Aquí Dice la Ley · Operación autónoma diaria | operación diaria | sí (operador 2) |
| Aquí Dice la Ley · Recordatorio TikTok (19:47) | aviso al celular | no |
| PDF de seguimiento 3-11 (sesión …Tqt1fi…, una vez) | informe en PDF | no (solo lectura); el responsable dijo el 2-11 que no quiere más informes: queda a su decisión desactivarla |

Las tareas de Cronista Imposible son de otro proyecto y no se tocan.
