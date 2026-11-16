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

## Operación única

Ver `docs/operacion_unica.md`. Al iniciar, revisar en `git log` si hay commits de sesiones ajenas a las tres autorizadas; si los hay, no revertirlos: reportarlos al responsable.

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
5. **Calendario.** Cada pieza aprobada (directa o delegada) entra al calendario `data/calendario_lanzamiento.json` en cuanto se aprueba, en su fecha y hora (imagen 09:00, Reel 19:00), con pieza, versión, archivo, SHA-256, asset_id, release y fecha de aprobación; no se espera a cerrar el lote. Un día puede tener una sola pieza mientras la otra se produce. Correr `pruebas/test_publicador.py`. Publicación autorizada hasta `PUBLICAR_HASTA` = 2027-02-20 (orden definitiva del 3-11-2026).
6. **Siguiente lote.** Cuando el lote activo esté completo y en el calendario, crear el siguiente lote: 7 Reels y 7 imágenes, una semana después, con temas que no repitan los de las últimas 3 semanas, preferentemente de alcance federal o nacional y con un artículo de respuesta literal. Seguir la misma estructura y pasar `pruebas/test_lote_piloto.py`.
7. **Aviso al responsable.** Una vez por lote aprobado, enviarle un resumen breve en español: piezas con su fecha, qué dicen, fundamento, versión, y el recordatorio de que puede vetar en 72 h respondiendo «veto <pieza>». Si no hay nada que aprobar ni ningún problema, no escribir.
8. **Reels en Instagram.** Seguir `docs/meta_publicacion.md`: como máximo 2 cargas no públicas al día, y si aparece el código 368 detenerse. Desde el 2-11-2026 el responsable autorizó publicar en Instagram los Reels cortos (`IG_REELS="corto"`, `IG_REEL_MAX_S="45.5"` desde el 3-11 en `data/lanzamiento.json`); los más largos siguen solo en Facebook. Revisar en `registro/publicacion.jsonl` que los Reels cortos queden publicados en IG y, si aparece el código 368, poner `IG_REELS` en `"0"` y avisar.
9. **YouTube.** Revisar en `registro/publicacion.jsonl` el campo `youtube` de cada Reel: `PROGRAMADO` es lo esperado; `SIMULADO` significa que faltan los secretos de OAuth (avisar una vez al responsable con `docs/plataformas.md`); `ERROR` con «sin confirmación» exige revisar el canal antes de reintentar (no duplicar videos).
10. **TikTok.** Revisar `registro/tiktok.jsonl`: `EN_BANDEJA` es lo esperado; `SIMULADO` = falta la conexión (`docs/plataformas.md`); `ERROR` con «sin confirmación» = revisar la bandeja antes de reintentar; «la clave de renovación venció» = repetir `tiktok-conectar`.

## Inventario de 90 días (instrucción del responsable del 3-11-2026)
- **Meta:** 90 Reels + 90 imágenes, del 23-11-2026 al 20-02-2027 (imagen 09:00, Reel 19:00, CDMX). Siempre 90 días preparados por adelantado.
- **Lotes de dos semanas (28 piezas, desde el 3-11):** el lote activo puede arrastrar solicitudes pendientes del anterior (`arrastre`). En cuanto el lote activo tenga todas sus solicitudes redactadas, preparar y activar el siguiente (lote 6: 28-12 al 10-01; lote 7: 11-01 al 24-01; lote 8: 25-01 al 07-02; lote 9: 08-02 al 20-02). Cada ciclo redacta y produce hasta 2 piezas por formato. El siguiente tema ya debe estar preparado: mantener siempre al menos un lote propuesto en `data/lote_<n>_propuesta.json` (temas variados: laboral, constitucional, consumidor, civil y familiar, penal, derechos humanos, cotidiano; sin repetir las 3 semanas previas; días consecutivos no parecidos).
- **Reels nuevos de 30 a 42 s** (salen también en Instagram). Identidad gráfica, plantillas y voz aprobadas: no se cambian.
- **Calendario ≠ publicación:** las piezas se agregan al calendario al aprobarse, pero solo se programan o publican las fechas ≤ `PUBLICAR_HASTA` (data/lanzamiento.json). Ampliarlo requiere autorización expresa del responsable.
- **Cuotas:** 3 ciclos diarios; si aparece «tope propio diario» o la guardia de minutos, no se reintenta: continúa el ciclo siguiente.
- **Etapa 2 (21-02 al 21-05-2027):** al haber publicaciones, registrar métricas (alcance, reproducciones, retención, interacciones, seguidores, por tema, duración, horario y red) y preparar propuestas; no se modifican piezas de la etapa 1.

## Costos y límites

- **GitHub Actions:** tope propio de 1,850 minutos al mes para producción (autorizado 3-11 hasta 2,000, cuota gratuita comprobada; 150 reservados a publicación) (`registro/actions_mes.json`).
- **Gemini:** cuota gratuita. Si aparece «tope propio diario», esperar al siguiente día del Pacífico.

## Reels en Instagram (decisión del responsable, 2-11-2026: opción B)

- En Instagram se publican los Reels aprobados que duran **45 s o menos** (`IG_REELS=corto`, `IG_REEL_MAX_S=45` en `data/lanzamiento.json`). Los más largos salen solo en Facebook.
- Desde el lote 5 todos los Reels se producen de 45 s o menos: el redactor pide de 30 a 42 s, el esquema limita la narración a 620 caracteres y la auditoría técnica exige de 20 a 45 s.
- Los Reels ya aprobados no se modifican.

## Adelanto del lanzamiento (decisión del responsable, 3-11-2026)

- **Fecha objetivo provisional: lunes 16-11-2026**, solo si hay 45 Reels + 45 imágenes aprobados y las integraciones funcionan. La fecha original (23-11) sigue vigente mientras el responsable no autorice expresamente el inicio.
- **Candado:** `PUBLICAR_DESDE="2026-11-23"` en `data/lanzamiento.json`. Los días 16 al 22-11 pueden entrar al calendario, pero no se programan ni publican. **Solo el responsable lo cambia**, después de que Claude le confirme qué plataformas están listas y le pida la autorización concreta.
- **6-11-2026: autorización del responsable** («Autorizo iniciar el 16 de noviembre en Facebook, Instagram y YouTube»): `ADELANTO_AUTORIZADO=2026-11-16`. El publicador usa esa fecha automáticamente solo cuando hay 45 días consecutivos completos desde el 16-11 (`publicador.desde_efectivo`); TikTok sigue con el 23-11. Al activarse, Claude comprueba en Meta y YouTube lo programado del 16 al 22-11 y avisa al responsable.
- **Prioridad de producción:** completar 25 Reels y 22 imágenes; primero las piezas en REVISION_HUMANA, después las RETENIDAS que se puedan corregir sin rebajar la exactitud jurídica (si la causa es del tema, sustituir el tema). Las fechas de las solicitudes son solo espacios.
- **Lugar en el calendario de cada pieza nueva aprobada:** el primer espacio libre de su formato desde el 16-11 (imagen 09:00, Reel 19:00), sin el mismo tema en el mismo formato en 7 días y sin la misma pregunta en imagen y Reel el mismo día. No mover nada de lo ya programado en Facebook (23-11 en adelante dentro de 28 días). La meta es la reserva de 45 días consecutivos desde el 16-11 (`registro/avance.md`).
- **Activación del lote 6:** en cuanto el lote 5 tenga todas sus solicitudes redactadas.
- **Minutos:** la guardia detiene los ciclos en 1,850 (cuota gratuita de 2,000 comprobada; presupuesto de Actions 0 USD con «Usage blocked»). Si el consumo diario supera 70 min con más de 10 días por delante, quitar el ciclo de las 15:17 hasta que la reserva esté completa o el mes cambie.

## Monetización: versión larga de TikTok y video semanal de YouTube (decisión del responsable, 16-11-2026)

Registro de la decisión: `data/lanzamiento.json` → `monetizacion_decisiones`. Las dos cosas empiezan solas por fecha
(`TIKTOK_LARGO_DESDE` = 2026-12-01, `YOUTUBE_SEMANAL_DESDE` = 2026-12-03); antes de esas fechas sus pasos terminan sin hacer nada.
No cambian `PUBLICAR_DESDE`, `ADELANTO_AUTORIZADO`, `PUBLICAR_HASTA` ni ninguna otra autorización de publicación, no tocan los
Reels aprobados ni sus aprobaciones, y cada pieza derivada tiene su propia versión (SHA-256), respaldo y aprobación.

### 1. Versión larga solo para TikTok (65 a 75 s)

- **Por qué.** El programa de Recompensas de TikTok exige videos de más de 1 minuto. Facebook, Instagram y YouTube siguen con el Reel de 30 a 45 s.
- **Quién la produce.** Paso «Versión larga solo para TikTok» de `ciclo.yml` (después del ciclo; `continue-on-error`, nunca detiene el ciclo) → `python sistema/tiktok_largo.py producir`. Hasta 2 por ciclo (`TIKTOK_LARGO_POR_CICLO`), las de los Reels **más próximos a publicarse** primero, con al menos 4 días de anticipación (para que quepan las 72 h de veto). Los Reels que ya duran más de 60 s no necesitan versión larga.
- **Cómo se redacta.** `redactor.ampliar_tiktok`: a partir del guion del Reel aprobado, misma pregunta (título, gancho, respuesta corta y análisis jurídico congelados), la misma escena de cita con la **misma cita literal**, solo los **mismos artículos** ya cotejados (texto oficial completo descargado de nuevo) y **un** agregado: un ejemplo práctico que aplica una regla del análisis (afirmación «interpretacion» con la cita literal de esa regla) o una condición/excepción que esté expresamente en el texto oficial (afirmación «hecho_normativo» con su cita literal). Controles que no se relajan: esquema (rango propio 930–1040 caracteres ≈ 61–74 s; `esquema.MIN/MAX_NARRACION_TIKTOK`), `controles_ampliacion` (misma cita, mismos artículos, al menos una afirmación nueva anclada), `razonamiento.revisar` (sustento, condiciones, coherencia visible, vaguedades, jurisprudencia…), auditor independiente, y después `verificador` y el dictamen de siempre. Auditoría técnica con su rango propio: más de 60 s y hasta 75 s (`auditoria.DURACION_TIKTOK`); en la variante el control de TikTok es obligatorio.
- **Dónde queda.** `piezas/<ID>-TT/` (guion, salida), respaldo en el release `piezas-AAAA-MM` y registro en `estado/tiktok_largo.json` (estados: `PENDIENTE` → reintento, `REVISION_HUMANA`, `APROBADA`, `RECHAZADA`, `RETENIDA`, `DESCARTADA` tras 2 descartes del tema; ese día va el Reel normal). El ciclo **no** encola las piezas `-TT` (`ciclo.es_derivada`).
- **Aprobación.** Igual que un Reel: revisión editorial cuadro por cuadro contra el texto oficial y `python sistema/decidir.py aprobar <ID>-TT <versión> --por "Claude (revisión editorial delegada)" --delegada`. `decidir.py listar` muestra también las variantes pendientes. Veto del responsable: `decidir.py rechazar <ID>-TT <versión> --nota "veto del responsable"` (se admite aunque ya esté aprobada).
- **Calendario.** Al aprobarse entra sola como `dia["reel"]["tiktok"]` = {pieza, version, archivo, sha256, asset_id, release, aprobada, aprobacion, de_version, duracion_s}; `de_version` es la versión del Reel de la que deriva. Si el Reel cambia de versión o la variante se veta, sale del calendario (`python sistema/tiktok_largo.py calendario` lo sincroniza). Ningún otro campo cambia.
- **Envío.** `tiktok.py` (cada noche) manda la versión larga solo si: el Reel del día sigue aprobado y fuera de veto, la variante deriva de esa misma versión, está aprobada en su versión exacta, terminó su veto y el archivo descargado tiene su huella. Si no, manda el Reel normal y deja el motivo en `variante_omitida`. Nunca manda las dos el mismo día: si una ya está en la bandeja (o quedó sin confirmación), esa es la del día. El texto del recordatorio es el mismo del Reel.

### 2. Video largo semanal de YouTube (8 a 10 min)

- **Por qué.** Ruta de 4,000 h de visualización del Programa de Socios (los Shorts no suman horas).
- **Jueves 01:23 CDMX** (`youtube-semanal.yml`, trabajo «armar», con la guardia de minutos): `python sistema/youtube_semanal.py armar` reúne los Reels **aprobados en su versión exacta y ya publicados** (fecha anterior a hoy, dentro del tramo autorizado, veto vencido antes de su hora) de los últimos 7 días y los agrupa por rama del derecho (la del artículo que cita cada Reel; Constitución arts. 13 a 23 = justicia penal). Toma la rama con más Reels de la semana; si no llega a 8 min, completa con Reels publicados antes de la misma rama (primero los que no han salido en otro video semanal) y, para justicia penal y Constitución, con la otra (ambas son derecho constitucional). Si ninguna rama alcanza, queda `INSUFICIENTE` y esa semana no hay video.
- **Video.** 1920x1080: intro y cierre con el logotipo, los colores y la firma sonora de la marca (`marca/`), cada Reel centrado sobre el fondo de marca con la pregunta («PREGUNTA n DE m») a la izquierda y la fuente oficial (ley y artículo) a la derecha, aviso «Información general, no asesoría legal» en pantalla, fundidos de 0.3 s y audio normalizado en dos pasadas (−14 LUFS). Cada Reel se descarga del respaldo y se comprueba su aprobación y su huella antes de usarlo.
- **Título y descripción.** «N preguntas sobre <tema>: lo que dice la ley en México»; descripción con capítulos (uno por Reel, el primero en 0:00), las fuentes oficiales de cada segmento (ley, artículo y URL oficial) y el aviso. Todo queda en `semanal/<ID>/manifiesto.json` (ID = `Y<domingo AAAAMMDD>-SEM`).
- **Auditoría técnica.** Duración de 8 a 10 min, 1920x1080, H.264 yuv420p, 30 cps, AAC 48 kHz estéreo, integridad, −14 LUFS ±1.5, pico ≤ −1 dBTP, sin silencios > 2 s ni negros > 1 s, capítulos (≥ 3, el primero en 0:00, ≥ 10 s cada uno, escritos en la descripción), fuentes de cada segmento, aviso, título ≤ 100 y descripción ≤ 4,900 caracteres. Resultado en `semanal/<ID>/salida/auditoria.json`; si algo falla queda `RETENIDO`.
- **Aprobación.** Delegada con 72 h de veto: revisar el video (descargar por su huella del release), el título, los capítulos y las fuentes, y `python sistema/decidir.py aprobar Y<AAAAMMDD>-SEM <versión> --por "Claude (revisión editorial delegada)" --delegada`. **Para que salga el domingo a las 12:00 hay que aprobarlo a más tardar el jueves a las 11:00 CDMX** (el veto debe terminar antes de subirlo).
- **Programación.** Domingo 11:07 CDMX (trabajo «programar»): si está aprobado y el veto terminó, `youtube.py` lo sube como video normal (no Short), privado con `publishAt` = domingo 12:00 CDMX. Si el veto terminó después, la ejecución del lunes 11:07 lo programa para las 12:00 de ese día (`tarde: true`). Idempotente con el libro de operaciones (marca `…-yt`): nunca se sube dos veces; una carga sin confirmación no se reintenta sola. Respeta el paro de emergencia y `PUBLICAR_HASTA`. Sin las condiciones de YouTube, solo simula.
- **Primer video:** armado el jueves 3-12-2026, programado para el domingo 6-12-2026 a las 12:00.

### Qué revisa la operación diaria (además de la rutina)

1. `python sistema/decidir.py listar`: aprobar o corregir las piezas `-TT` y el video semanal en `REVISION_HUMANA` (el semanal, el mismo jueves por la mañana).
2. `estado/tiktok_largo.json`: piezas `PENDIENTE` con `intentos` ≥ 1 o `DESCARTADA`/`RETENIDA` (motivo en `motivo` y `estado/descartes/<ID>-TT.json`); si la causa es del sistema, corregirla con prueba de regresión.
3. `registro/tiktok.jsonl`: `variante` = «larga» es lo esperado cuando la variante está aprobada; `variante_omitida` explica por qué salió el Reel normal.
4. `estado/youtube_semanal.json` y `registro/youtube_semanal.jsonl`: `INSUFICIENTE` (no hay video esa semana; avisar al responsable si se repite), `ERROR` (repetir con `youtube-semanal.yml`, `accion=armar`, después de corregir), `RETENIDO` (fallas técnicas), `PROGRAMADO` (lo esperado el domingo), `VENCIDO`.
5. Minutos: el armado semanal usa del orden de 15 a 25 min de Actions por semana y la versión larga unos minutos por pieza dentro del ciclo; todo pasa por la guardia de 1,850 min.
