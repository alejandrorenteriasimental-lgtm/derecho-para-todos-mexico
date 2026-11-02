# Operación autónoma diaria — Aquí Dice la Ley

Esta guía la ejecuta Claude en una tarea programada diaria (sesión nueva cada vez). La pidió el responsable, César Alejandro Rentería Simental, el 29-10-2026: «quiero que sea lo más autónomo posible, que todo se vaya publicando sin mi intervención en la medida de lo posible». Eligió el modelo «Yo reviso; tú puedes vetar».

## Reglas que no cambian

- **Gasto.** 0 MXN. No se activa facturación ni se contrata nada.
- **Credenciales.** No se piden ni se escriben tokens o claves; viven en los secretos de GitHub.
- **Controles jurídicos.** No se relajan. No se cita jurisprudencia que no se haya verificado oficialmente.
- **Otros proyectos.** No se toca Cronista Imposible ni ningún otro proyecto.
- **Piezas aprobadas.** No se modifica una pieza ya aprobada. Si la pieza cambia, la aprobación deja de valer.
- **Aprobación desde el lote 4: delegada.**
  - Claude revisa y corrige cada pieza, y la aprueba con `python sistema/decidir.py aprobar <pieza> <versión> --por "Claude (revisión editorial delegada)" --delegada`.
  - La pieza solo se publica 72 horas después. El publicador lo hace cumplir.
  - Si el responsable la veta en ese plazo, se registra con `decidir.py rechazar … --nota "veto del responsable"` y no se publica.
- **Lotes 1 a 3.** Conservan la aprobación directa del responsable.
- **Paro de emergencia.** Ver `docs/paro_emergencia.md`. Si existe `estado/pausa_publicacion.json`, no se reanuda sin revisar la causa.

## Rutina diaria

1. **Estado.** Hacer `git pull` en el repositorio `alejandrorenteriasimental-lgtm/derecho-para-todos-mexico` (con `gh`; despacho de flujos por REST: `gh api -X POST repos/{repo}/actions/workflows/<archivo>/dispatches -f ref=main`). Leer después:
   - `registro/publicacion.jsonl` (última ejecución): modo, pausa, errores;
   - `registro/metricas_generacion.jsonl` y `estado/bitacora.jsonl` (último día);
   - `estado/cola.json` (piezas en REVISION_HUMANA, RETENIDO o PENDIENTE).
2. **Publicación.**
   - Revisar que cada pieza del calendario que entró en la ventana de 28 días esté PROGRAMADO en Facebook. La comprobación de solo lectura es `meta-prueba.yml` con `modo=lectura`, que lista las programadas.
   - Si el publicador se pausó, diagnosticar la causa, corregir solo causas del sistema, avisar al responsable y no reanudar si la causa no está clara.
3. **Producción del lote activo** (`data/lote_piloto.json`).
   - Para cada descarte, identificar la causa. Si es del sistema, corregirla con prueba de regresión y reabrir la solicitud. Si es del tema, después de 2 descartes sustituir la pregunta por otra con respuesta literal en un artículo federal verificado (`textos.yml` para traer el texto oficial).
   - Despachar `ciclo.yml` cuando haga falta. El sistema redacta una pieza por formato por ciclo.
4. **Revisión editorial de cada pieza en REVISION_HUMANA.** Descargar el archivo del respaldo `piezas-2026-10` por su huella.
   - Contra el texto oficial (`registro/textos/`): sin generalizaciones, con condiciones y excepciones, cita literal.
   - Coherencia entre lo visible y lo narrado. Revisar todos los campos visibles: `titulo`, `items`, `etiqueta`, `encabezado`, `detalle`, `fuente_corta`, `ojo`, `bajada`, `mito`, `realidad`, `fuente_visible`.
   - Cuadro por cuadro en los Reels; la imagen completa en las imágenes.
   - Texto de la publicación (`copy`) claro, sin relleno.
   - Si algo falla: editar el guion, registrarlo en `ediciones`, pasar `razonamiento.revisar` e `imagen.revision_previa`, mover la pieza a PENDIENTE y volver a producir.
   - Si todo está bien: aprobar con `--delegada`.
5. **Calendario.** Cuando las 14 piezas de un lote estén aprobadas, agregar la semana a `data/calendario_lanzamiento.json` con pieza, versión, archivo, SHA-256, asset_id, release y fecha de aprobación. El formato está en las entradas existentes. Correr `pruebas/test_publicador.py`.
6. **Siguiente lote.** Cuando el lote activo esté completo y en el calendario, crear el siguiente lote: 7 Reels y 7 imágenes, una semana después, con temas que no repitan los de las últimas 3 semanas, preferentemente de alcance federal o nacional y con un artículo de respuesta literal. Seguir la misma estructura y pasar `pruebas/test_lote_piloto.py`.
7. **Aviso al responsable.** Una vez por lote aprobado, enviarle un resumen breve en español: piezas con su fecha, qué dicen, fundamento, versión, y el recordatorio de que puede vetar en 72 h respondiendo «veto <pieza>». Si no hay nada que aprobar ni ningún problema, no escribir.
8. **Reels en Instagram.** Seguir `docs/meta_publicacion.md`: como máximo 2 cargas no públicas al día, y si aparece el código 368 detenerse. Desde el 2-11-2026 el responsable autorizó publicar en Instagram los Reels de hasta 45 s (`IG_REELS="corto"`, `IG_REEL_MAX_S="45"` en `data/lanzamiento.json`); los más largos siguen solo en Facebook. Revisar en `registro/publicacion.jsonl` que los Reels cortos queden publicados en IG y, si aparece el código 368, poner `IG_REELS` en `"0"` y avisar.
9. **YouTube.** Revisar en `registro/publicacion.jsonl` el campo `youtube` de cada Reel: `PROGRAMADO` es lo esperado; `SIMULADO` significa que faltan los secretos de OAuth (avisar una vez al responsable con `docs/plataformas.md`); `ERROR` con «sin confirmación» exige revisar el canal antes de reintentar (no duplicar videos).

## Costos y límites

- **GitHub Actions:** tope propio de 1,700 minutos al mes (`registro/actions_mes.json`).
- **Gemini:** cuota gratuita. Si aparece «tope propio diario», esperar al siguiente día del Pacífico.
