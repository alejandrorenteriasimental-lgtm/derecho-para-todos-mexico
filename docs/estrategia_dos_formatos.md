# Estrategia editorial de dos formatos diarios (v0.2)

**Meta inicial:** 1 Reel + 1 imagen fija al día → 14 publicaciones semanales, ≈ 60 al mes.
**Hipótesis, no certeza:** publicar más no garantiza más alcance. El volumen se mantiene solo si los indicadores
de calidad (abajo) no caen; si caen, se reduce la imagen a 4–5 por semana antes que bajar la calidad del Reel.

## Papel de cada formato
| | Reel (video vertical 1080×1920) | Imagen fija (1080×1350, 4:5) |
|---|---|---|
| Función | Atraer público nuevo (distribución a no seguidores) | Reforzar, ser guardada y compartida |
| Estructura | Historia: gancho → regla → excepciones → cierre | Una idea central: titular + explicación breve + cita/fuente |
| Temas | Casos, derechos cotidianos con conflicto, mitos con giro | Conceptos, diferencias, «tres claves», mito/realidad, datos |
| Métrica principal | Retención media y % que llega al final | Compartidos + guardados por cada 1,000 vistas |
| Hora inicial (CDMX) | 19:00 | 09:00 |

## Relación entre formatos (sin duplicar)
- Martes, jueves y sábado la imagen **complementa** el Reel del día anterior: misma investigación y fuentes ya
  verificadas, pero otro ángulo y otra plantilla (p. ej., Reel «¿cárcel por deudas?» → imagen «Deuda civil vs. fraude»).
- Lunes, miércoles, viernes y domingo la imagen es **independiente** (conceptos y mitos).
- El planificador impide repetir tema en 60 días y repetir categoría en días consecutivos del mismo formato.

## Plantillas de imagen (provisionales; el sistema definitivo se diseña en la Fase 4 junto con el del Reel)
`concepto` (titular + bajada + cita oficial + «ojo») · `tres_claves` · `mito_realidad` · `diferencia` · `dato`.
Rotación semanal: lun concepto · mar tres claves · mié mito/realidad · jue diferencia · vie dato · sáb concepto · dom tres claves.

## Horarios: experimento, no supuesto
Referencia externa (no específica de México ni de divulgación jurídica): Sprout Social, con ≈2,000 millones de
interacciones de 307,000 perfiles (nov-2025 a feb-2026), ubica la mejor franja de Facebook de martes a miércoles
entre mediodía y 20:00 hora local, y el domingo como el día más débil. Se usa solo como punto de partida.

Diseño (8 semanas, después de las primeras 2 semanas de calibración):
1. Reel: alternar 13:00 y 19:00 por día, con asignación aleatoria balanceada (cada horario 4 veces por semana y día de la semana).
2. Imagen: alternar 09:00 y 20:30 con la misma regla.
3. Métrica de decisión por formato: vistas a 72 h por cada 1,000 seguidores (normaliza el crecimiento de la página) y
   compartidos + guardados por cada 1,000 vistas.
4. Regla: se adopta un horario solo si supera al otro en ≥ 15 % en la mediana y la diferencia se mantiene en las dos
   mitades del experimento. Si no, se conserva el horario base. Se registra en `registro/experimentos.jsonl`.

## Indicadores (se leen con la API de Insights una vez conectada la Página)
Vistas (`post_media_view`; las métricas *impressions* fueron retiradas por Meta en 2025), alcance único
(`post_total_media_view_unique`), tiempo medio y curva de retención del Reel, reacciones, comentarios, compartidos,
guardados, visitas al perfil y nuevos seguidores por pieza.
**Pendiente de verificar al conectar:** la disponibilidad de «guardados» de publicaciones de Página de Facebook vía
API no está confirmada en la documentación revisada; en Instagram sí existe la métrica `saved`. Si no está disponible
en Facebook se usará el panel de Meta Business Suite (exportación manual semanal) o el dato de Instagram.

## Costos de la línea de imagen
Variable por imagen: **0 MXN** (Pillow, tipografías OFL y tesseract, todo local). Cómputo: ≈ 5–10 s por imagen
incluida la auditoría OCR. 30 imágenes al mes ≈ 5 min de runner, dentro de los 2,000 min gratuitos del plan Free de
GitHub para repositorios privados (el Reel consume la mayor parte: ver informe de costos v0.2).
