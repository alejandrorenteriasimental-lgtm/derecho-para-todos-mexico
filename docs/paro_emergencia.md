# Paro de emergencia de las publicaciones

Cualquiera de estas acciones detiene **todas** las publicaciones automáticas. Lo ya programado en Facebook queda como está.

1. **La más rápida (sin código).** En GitHub, abre el repositorio y entra a **Settings → Secrets and variables → Actions → Variables**. Crea o edita `PAUSA_PUBLICACION` con el valor `1`. La siguiente ejecución ya no envía nada.
2. **Automática.** Si el sistema detecta un archivo distinto al aprobado, una pieza sin aprobación vigente o un error de Meta no transitorio, crea él mismo el archivo `estado/pausa_publicacion.json` con el motivo y se detiene.
3. **Desactivar el lanzamiento.** Cambia `PUBLICAR` a `0`. El sistema vuelve a modo de simulación.

Las publicaciones que Facebook ya tiene programadas se cancelan desde Meta Business Suite → Planificador. Claude puede indicarte cuáles son con el registro `estado/operaciones.jsonl`.

**Para reanudar:** revisa el motivo en `registro/publicacion.jsonl`, corrige la causa, borra `estado/pausa_publicacion.json` y quita `PAUSA_PUBLICACION`.
