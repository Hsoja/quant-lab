# Seguridad — Quant Lab (STRIDE, antes de codificar)

| # | Categoría STRIDE | Amenaza | Mitigación |
|---|---|---|---|
| 1 | **Tampering** (manipulación) | El documento del reporte (10-K) es texto no confiable: podría contener instrucciones que intenten manipular al LLM para que invente cifras, ignore las reglas de cita o cambie su propio comportamiento. | El texto del documento y del usuario van en su propio rol, nunca concatenados al prompt del sistema. El LLM nunca calcula cifras (eso lo hace `calc/`); solo resume. El verificador (`verify/`) rechaza cualquier cita que no exista literalmente en el documento guardado, venga o no del LLM. |
| 2 | **Information Disclosure** (fuga de información) | Llaves de API, el contacto de `EDGAR_CONTACT`, o datos personales/de portafolio terminan en el repo, en commits, en README o en tests. | Llaves y contacto solo en `.env` (gitignorado, permisos 0600); `.env.example` sin valores reales. Ningún código, doc o test menciona portafolios, tickers propios ni datos personales — solo "empresa de ejemplo". Escaneo de secretos antes de cada PR (skill `auditoria-seguridad`). |
| 3 | **Denial of Service / abuso de la fuente externa** | El ingestor excede el límite de tasa de SEC EDGAR (riesgo de bloqueo de IP) o descarga documentos sin límite de tamaño/tiempo, agotando memoria, disco o la cuota del LLM. | `ingest/` usa 1 solicitud/segundo con backoff en 429/5xx, timeout en cada solicitud y tope de tamaño de archivo. Toda llamada al LLM tiene tope de tokens de entrada y de salida. |

## Actualización — Fase 5 (llm/)

La mitigación de Tampering de arriba se volvió más fuerte de lo planeado: `llm/summarizer.py`
**nunca envía el texto crudo del documento al modelo**. Solo recibe el JSON de hechos que
`extract/` calculó y `verify/` ya confirmó contra el documento guardado (ver SPEC.md sección 5 y
el docstring de `llm/summarizer.py`). Una instrucción escondida en el 10-K no tiene ninguna vía
para llegar al modelo porque el modelo nunca lee el 10-K.

Además, cada línea de la respuesta del LLM se descarta si no cita una clave real del JSON que se
le dio (`enforce_citations`): no se confía en que el modelo siguió la regla del prompt, se
comprueba después, de forma determinista — el mismo espíritu del verificador de citas, aplicado
a la salida del LLM.

## Actualización — "Pruébalo con una acción" (SPEC.md sección 9)

Nueva fuente externa (`ingest/price.py`, Yahoo Finance no oficial) y una nueva superficie en la
página web. Ninguna de las dos cambia el modelo de amenazas de fondo:

- **El fetch de precio ocurre en el build (`scripts/precompute_examples.py`), nunca en el
  navegador.** La página sigue sin hacer ninguna llamada de red: los datos de las empresas de
  ejemplo viajan embebidos en un atributo HTML (`data-json`), no en un `<script>` con el JSON
  dentro (evita depender de cómo cada navegador aplica la CSP a ese tipo de bloque) y se leen con
  `JSON.parse` + `textContent`/`createElement` — nunca con `innerHTML`.
- **Mismas reglas de acceso que `ingest/edgar.py`:** solo `https://`, límite de tasa, reintento
  con backoff, tope de tamaño de respuesta. Si la fuente de precio falla, el precio (y todo lo
  que depende de él) sale "no verificado" — nunca un valor de respaldo.
- **Hallazgo real durante esta fase:** la CSP original (`script-src 'self'`) bloqueaba el propio
  `<script>` inline de la página, porque `'self'` no permite scripts inline, solo scripts con
  `src=`. El navegador lo bloqueaba en silencio y todo el contenido `.reveal` se quedaba invisible
  para siempre. Corregido permitiendo el script por el **hash SHA-256 de su contenido exacto**
  (`script-src 'self' 'sha256-...'`), calculado en Python a partir del mismo texto que se inserta
  en la página — nunca con `'unsafe-inline'`. Un nonce no habría servido: la página es estática, así
  que el nonce sería siempre el mismo, visible en el propio HTML, sin ningún valor real. Además, el
  contenido ahora es visible **por defecto** y solo se "pre-esconde" si el script confirma que
  arrancó (clase `.js-ready`), para que un futuro fallo del script, por cualquier motivo, no vuelva
  a dejar la página en blanco.

Revisar y ampliar esta tabla en cada fase que añada una superficie nueva.
