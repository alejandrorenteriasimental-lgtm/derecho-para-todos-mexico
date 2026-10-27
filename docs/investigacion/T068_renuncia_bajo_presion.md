# Investigación: «¿Qué pasa si te obligan a firmar tu renuncia?» (T068)

Esta investigación se hizo después del rechazo humano de R20261028-T068 (26-10-2026, versión c607942b03d912b6). Sirve como base para la versión corregida. No es asesoría jurídica.

## Fuentes consultadas

**Ley Federal del Trabajo (LFT).** Texto oficial de la Cámara de Diputados (https://www.diputados.gob.mx/LeyesBiblio/pdf/LFT.pdf), extraído en GitHub Actions el 27-10-2026 (corrida 40433681587). La última reforma que indica el documento es del DOF 14-05-2026. El texto literal de cada artículo está en `registro/textos/LFT_*.json`.

**Jurisprudencia.** Datos tomados de dos fuentes secundarias que coinciden entre sí: elconta.mx y una reproducción en PDF de cerlatam.com. **No pude abrir el Semanario Judicial (sjf2.scjn.gob.mx) desde este entorno**, así que el registro digital debe confirmarse ahí antes de citarlo en una pieza.

## A. Lo que la ley dice expresamente (hecho normativo)

| # | Afirmación | Fuente | Fragmento literal |
|---|---|---|---|
| 1 | Es nula la renuncia a salarios devengados, indemnizaciones y demás prestaciones derivadas de los servicios prestados, cualquiera que sea la forma o el nombre del documento. | LFT art. 33, párr. 1 | «Es nula la renuncia que los trabajadores hagan de los salarios devengados, de las indemnizaciones y demás prestaciones que deriven de los servicios prestados, cualquiera que sea la forma o denominación que se le dé.» |
| 2 | Un convenio o liquidación debe hacerse por escrito y ratificarse ante el Centro de Conciliación o el Tribunal. Si se firmó sin intervención de las autoridades, puede reclamarse ante el Tribunal la nulidad de lo que contenga renuncia de derechos. | LFT art. 33, párr. 2 y 3 | «…será susceptible de ser reclamada la nulidad ante el Tribunal, solamente de aquello que contenga renuncia de los derechos de los trabajadores…» |
| 3 | Las disposiciones de la LFT son de orden público. No producen efecto las estipulaciones que impliquen renuncia de los derechos que enumera la ley. | LFT art. 5 | «Las disposiciones de esta Ley son de orden público por lo que no producirá efecto legal…» |
| 4 | El patrón que despide debe dar aviso escrito con la conducta y la fecha. La falta de aviso, por sí sola, presume que la separación no fue justificada, salvo prueba en contrario. | LFT art. 47, últimos párrafos | «La falta de aviso al trabajador personalmente o por conducto del Tribunal, por sí sola presumirá la separación no justificada, salvo prueba en contrario…» |
| 5 | El trabajador puede pedir que se le reinstale o que se le indemnice con tres meses de salario. Se pide ante la Autoridad Conciliadora y, si no hay arreglo, ante el Tribunal. | LFT art. 48 | «El trabajador podrá solicitar ante la Autoridad Conciliadora, o ante el Tribunal si no existe arreglo conciliatorio, que se le reinstale en el trabajo que desempeñaba, o que se le indemnice con el importe de tres meses de salario…» |
| 6 | En ciertos casos el patrón puede negarse a reinstalar si paga las indemnizaciones del art. 50: antigüedad menor de un año, trabajadores de confianza, trabajo del hogar, eventuales, entre otros. | LFT art. 49 | «La persona empleadora quedará eximida de la obligación de reinstalar…» |
| 7 | **Plazo:** dos meses, contados desde el día siguiente a la separación. Se suspende con la solicitud de conciliación. | LFT art. 518 | «Prescriben en dos meses las acciones de los trabajadores que sean separados del trabajo. La prescripción corre a partir del día siguiente a la fecha de la separación.» |
| 8 | La solicitud de conciliación interrumpe la prescripción, hasta que el Centro expide la constancia de no conciliación. | LFT art. 521, fr. III | «Por la presentación de la solicitud de conciliación a que se refiere el artículo 684-B de esta Ley…» |
| 9 | **Vía:** la conciliación empieza con una solicitud ante el Centro Federal de Conciliación y Registro Laboral o el Centro de Conciliación local. El Centro da asesoría jurídica gratuita sobre derechos y plazos. | LFT art. 684-E, fr. I y III | «…ante el Centro Federal de Conciliación y Registro Laboral o al Centro de Conciliación local que corresponda…»; «Deberán proporcionar asesoría jurídica de manera gratuita sobre sus derechos y los plazos de prescripción…» |
| 10 | Separarse por decisión propia es una acción distinta, con un plazo de un mes desde que se conoce la causa. | LFT art. 517, fr. II | «Las acciones de los trabajadores para separarse del trabajo.» |

## B. Lo que requiere interpretación o depende de pruebas (no presentarlo como regla general)

1. **La ley no dice expresamente que una renuncia obtenida por coacción equivalga a un despido.** Esa consecuencia viene de criterios judiciales y depende de que se pruebe la presión. Si se prueba, la separación puede tratarse como no voluntaria y reclamarse con las acciones por despido (arts. 48 y 518).
2. **Criterio judicial: NO CITAR.** Existe una jurisprudencia de un tribunal colegiado sobre cómo se valoran las pruebas cuando
   el trabajador alega que lo obligaron a renunciar, pero **no se ha verificado en el Semanario Judicial de la Federación**
   (instrucción del responsable, 26-10-2026). Mientras no se verifique ahí, la pieza no menciona tesis, jurisprudencia ni
   registros, y no afirma cómo se reparte la carga de la prueba. Sus datos quedan en `registro/tesis/` para la verificación.
3. **«Firmar o no»:** la ley no ordena firmar ni prohíbe negarse. Cualquier consejo sobre qué hacer en el momento sería asesoría personalizada y se debe evitar.
4. **Para la pieza:** lo seguro es explicar la regla general y sus condiciones (efecto, vía, autoridad y plazo, con su artículo), sin prometer un resultado ni dar consejo personal.

## C. Qué dejó ver el error

- La pieza rechazada usó solo el art. 33, que trata la renuncia a **prestaciones**, no la renuncia **al empleo**.
- No dijo qué hacer, ante quién ni en qué plazo.
- Aludió a un «recurso legal específico» sin nombrarlo.
- Lo corregido en el sistema: `razonamiento.revisar_cobertura`, `vaguedades`, `consecuencias_sin_sustento`, la investigación complementaria en `redactor.generar` y los subtítulos medidos en `render`.
