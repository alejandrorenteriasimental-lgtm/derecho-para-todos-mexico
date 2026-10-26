# Tarea «guionista» — de solicitud a guion verificable

Esta es la instrucción completa para la tarea programada que convierte solicitudes en guiones. Está pensada para
ejecutarse como **tarea programada de Claude** sobre el repositorio del proyecto (no usa APIs de pago: consume la
suscripción existente). El ciclo de GitHub Actions **no confía** en lo que escriba esta tarea: todo guion pasa por
`esquema.py` (estructura) y `verificador.py` (cotejo contra el documento oficial) antes de producirse.

## Entrada
Archivos `estado/solicitudes/*.json` con `estado = PENDIENTE_GUION` (los genera `sistema/planificador.py --escribir`).

## Pasos por solicitud
1. Investigar el tema **solo en fuentes oficiales**: Constitución y leyes en `diputados.gob.mx/LeyesBiblio`,
   jurisprudencia en `sjf2.scjn.gob.mx`, DOF en `dof.gob.mx`. Confirmar vigencia (leyenda «Última reforma publicada DOF»).
2. Para cada afirmación jurídica, registrar una fuente con: `url` (PDF oficial), `documento` (título exacto del
   ordenamiento), `articulo`, `texto_literal` (copiado **del PDF oficial**, no de espejos privados), `jurisdiccion`.
3. Marcar `tipo: "interpretacion"` en toda afirmación que no sea reproducción directa de la norma; si existe duda
   material (criterios divididos, falta de jurisprudencia obligatoria), escribirla en `nota`. Una interpretación con
   duda queda retenida automáticamente.
4. Escribir `piezas/<ID>/guion.json`:
   - Reel: esquema de `piezas/T073/guion.json` (gancho → desarrollo → cierre con aviso «no es asesoría legal»;
     300–1,600 caracteres de narración; tipos de escena: gancho, titular, cita, lista, excepcion, cierre).
   - Imagen: esquema de `piezas/I001/guion.json` (plantilla, titular ≤ 70 caracteres, bajada ≤ 160, máximo tres
     puntos, `copy` con aviso, `alt`, fuentes y afirmaciones).
5. Si la solicitud es `relacion: "complemento"`, reutilizar las fuentes del Reel pero con otro ángulo y otra
   plantilla. Prohibido copiar el guion del Reel.
6. Ejecutar `python3 sistema/esquema.py` (vía `validar`) y corregir hasta que no haya errores.
7. Prohibido: inventar artículos, tesis, registros digitales, expedientes o cifras; nombrar personas reales en temas
   penales sin resolución firme; frases de asesoría («en tu caso», «te garantizo»).
8. Cambiar la solicitud a `estado = GUION_LISTO` y abrir un pull request (no fusionar a la rama principal sin que pasen las pruebas).

## Salida esperada del ciclo
El ciclo verifica las fuentes en vivo: si el literal no está en el artículo citado del documento oficial, la pieza
queda RETENIDA y se registra el motivo exacto en `piezas/<ID>/salida/verificacion.json`.
