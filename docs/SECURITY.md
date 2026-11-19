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

## Actualización — gráfica/noticias en vivo y chat de preguntas (SPEC.md 9.6-9.8)

Dos adiciones que se consideraron y se descartaron por abrir superficie nueva de verdad, y dos que
se hicieron con un cambio acotado y explícito:

- **Descartado: chat en vivo con un LLM.** Necesitaría un servidor con la llave de la API guardada
  en secreto, y cualquier visitante anónimo podría agotar la cuota o generar costo sin control. En
  vez de eso, las respuestas del chat (sección 9.6) se generan por código, en el build, a partir de
  las mismas cifras ya verificadas — la página nunca llama a un LLM ni a ningún servidor propio.
- **Descartado: calcular cualquier ticker en vivo.** Mismo problema: requeriría un backend público
  sin autenticación. La página sigue limitada a las empresas precalculadas.
- **Hecho: `frame-src https://s.tradingview.com`** (sección 9.7). Es el único cambio real a la CSP
  en esta fase. Los widgets se embeben como `<iframe sandbox="allow-scripts allow-same-origin
  allow-popups">` — nunca `allow-forms` ni `allow-top-navigation` — y nunca con el script de
  TradingView (que habría exigido abrir `script-src` también). El símbolo se valida con una
  expresión regular (`/^[A-Z]+:[A-Z.]{1,10}$/`) antes de armar la URL del iframe, aunque hoy
  siempre venga de datos propios y conocidos (defensa en profundidad). El contenido de esos
  widgets es de TradingView: no se verifica ni se cita, y la página lo dice.
- **Hecho: se quitó la sección "Por qué puedes confiar..."** (sección 9.8), sin cambio de
  seguridad — solo contenido.

Revisar y ampliar esta tabla en cada fase que añada una superficie nueva.

## Diseño v2 (Capa B Monte Carlo + diario)

- **Hecho: sin superficie nueva de red.** La simulación corre 100 % en el navegador con datos ya
  embebidos; no hay `fetch`, formularios, `localStorage` ni cookies (comprobado por pruebas). La CSP
  sigue igual (script por hash SHA-256, sin `'unsafe-inline'` en scripts).
- **Hecho: entradas del usuario acotadas** (precio, μ, σ, días, simulaciones, capital, semilla) antes
  de simular; todo se pinta con `createElement`/`createElementNS` + `textContent`, nunca `innerHTML`.
- **Hecho: descarga del diario** con `Blob` + `download` (archivo local, sin red).
- **Hecho: ticker validado** con expresión regular antes de armar la URL de historial en
  `ingest/price.py`. Bandit B311 (`random`) es simulación estadística, no criptografía (`# nosec`).
