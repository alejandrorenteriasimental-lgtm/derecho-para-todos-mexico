# Derecho para Todos México — sistema de producción v0.2

Producción autónoma, gratuita y auditada de **1 Reel + 1 imagen fija al día** sobre Derecho mexicano.
Corre en GitHub Actions; no requiere una conversación abierta. **Nada se publica** sin `PUBLICAR=1`,
`LANZAMIENTO_AUTORIZADO=SI` y los secretos de Meta. Presupuesto externo autorizado: **0 MXN** (`TOPE_MXN_MES`).

## Flujo
```
catálogo (data/catalogo.csv) → planificador → solicitudes → [tarea guionista] → piezas/<id>/guion.json
  → esquema.py (estructura) → verificador.py (cotejo contra el PDF oficial: dominio, identidad, vigencia, artículo, literal)
  → producción: Reel (narración → música → render → mezcla) | imagen (plantilla programática)
  → auditoría técnica (ffprobe/ffmpeg | contraste WCAG, márgenes, OCR) + dictamen jurídico (verificación + reglas editoriales)
  → APROBADO → publicar.py (libro de operaciones idempotente) → SIMULADO | PUBLICANDO → PROGRAMADO/PUBLICADO → MEDIDO
```

## Estados
`PENDIENTE → PRODUCIDO → APROBADO | RETENIDO | REVISION_HUMANA → SIMULADO` (modo simulación)
`APROBADO → PUBLICANDO → PROGRAMADO → PUBLICADO → MEDIDO` (solo modo real, con confirmación del estado remoto).
La cola rechaza por código cualquier paso a PUBLICANDO/PROGRAMADO/PUBLICADO que no provenga de una operación real.

## Ejecutar
```bash
pip install -r requirements.txt && bash sistema/descargar_modelos.sh
python -m pytest -q pruebas -m "not vivo"     # 98 pruebas sin red
python -m pytest -q pruebas -m vivo           # contra los PDF oficiales (requiere red: GitHub Actions)
python sistema/producir.py piezas/T073        # Reel
python sistema/imagen.py piezas/I001          # imagen fija
python sistema/ciclo.py                       # un ciclo completo (simulación por defecto)
python sistema/planificador.py                # plan editorial de 7 días (con --escribir crea solicitudes)
python sistema/comparar_voces.py 2            # banco de voces (requiere requirements-dev.txt y modelos de medición)
```

## Archivos clave
| Archivo | Función |
|---|---|
| `sistema/verificador.py` | Descarga y coteja la fuente oficial; evidencia con sha256, fecha de reforma, huella del artículo |
| `sistema/publicar.py` | Reels y fotos de Página; libro `estado/operaciones.jsonl`; recuperación ante caídas y respuestas ambiguas |
| `sistema/cola.py` | Cola persistente con transiciones validadas, bloqueo y reintentos |
| `sistema/ciclo.py` | Orquestación diaria (verifica antes de producir; publica en la misma ejecución) |
| `sistema/narracion.py`, `voces.py`, `normalizar.py`, `config_voz.json` | Voz: normalización para lectura, síntesis por oración, masterización |
| `sistema/imagen.py` | Línea de imagen fija: plantillas, auditoría de legibilidad y OCR, copy y metadatos |
| `sistema/presupuesto.py` | Guardia de gasto (tope 0 MXN) |
| `sistema/planificador.py`, `docs/tarea_guionista.md` | Generación de solicitudes y especificación de la tarea guionista |

## Límites conocidos (v0.2)
- La verificación en vivo contra diputados.gob.mx no puede ejecutarse en el entorno de trabajo (red bloqueada);
  se ejecuta en GitHub Actions (`pruebas/test_vivo.py`). Hasta que esa prueba pase, ninguna pieza es apta.
- El verificador comprueba texto y vigencia; no interpreta el alcance jurídico. Las interpretaciones de riesgo medio
  o alto van a revisión humana; las que declaran duda material se retienen.
- La jurisprudencia (registro digital en el Semanario Judicial) aún no se verifica automáticamente.
- La redacción automática de guiones requiere activar la tarea programada «guionista» (autorización pendiente).
- Las plantillas de imagen son provisionales; el sistema de diseño definitivo es parte de la Fase 4.
