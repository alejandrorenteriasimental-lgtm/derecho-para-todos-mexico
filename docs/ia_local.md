# IA local en GitHub Actions — experimento retirado (25–26 de octubre de 2026)

**Estado:** retirada del ciclo diario el 26-10-2026 (commit 871d2d1). El código se conserva (`sistema/ia_local.sh`,
`modelos.servidor_local`, sección `respaldo_local` de `config_ia.json`) y solo se activa con `IA_LOCAL=1`.

## Qué se probó
- llama.cpp (MIT) desde GitHub Releases + modelos GGUF abiertos descargados de Hugging Face.
- Primero Qwen2.5-7B (redacción) + Phi-3.5-mini (auditoría) con dos servidores; después Qwen2.5-3B Q4_K_M
  (Apache-2.0) y Phi-3.5-mini Q4_K_M (MIT), un modelo a la vez.

## Resultados (evidencia en el repositorio)
| Ejecución | Resultado |
|---|---|
| 40263291647 | Falla: la versión «latest» de llama.cpp ya no publicaba binarios (se corrigió buscando en 15 versiones). |
| 40265332401, 40265994959 | Código 143: memoria insuficiente. Los runners de repositorios privados tienen 2 núcleos y 7 GB de RAM. |
| 40267027982 | Funcionó técnicamente: 1.8 tokens/s de generación, 13 tokens/s de lectura; una llamada del redactor tardó 549 s. 55 min de ciclo; 4 temas descartados (esquema inválido, citas no copiadas) y 1 HTTP 400. El auditor nunca llegó a ejecutarse. |

## Por qué se retiró
- Calidad insuficiente: el modelo de 3B no copia citas literales ni respeta el esquema.
- Costo en minutos: ≈55 min por ciclo → ≈1,650–1,900 min/mes, casi todo el límite gratuito de 2,000.
- Ningún contenido incorrecto pasó (los controles funcionaron), pero tampoco se produjo nada.

## Cuándo reconsiderarla
Solo si cambian los runners (más RAM/CPU sin costo) o aparece un modelo pequeño que copie citas con fidelidad;
habría que medirlo de nuevo con `IA_LOCAL=1` en una ejecución manual, nunca en el cron diario.
