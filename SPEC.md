# SPEC — Quant Lab MVP

Monitor de reportes financieros oficiales con citas verificables. Lee un reporte, extrae cifras
estructuradas, las calcula por código y cita cada afirmación contra el documento guardado.
Este documento manda sobre el código: toda decisión de cálculo vive aquí, no en el LLM.

**No es asesoría financiera.** Es una herramienta de investigación: muestra tesis, riesgo y qué la
invalidaría, nunca una señal de compra o venta.

Este proyecto es genérico y reusable: funciona para cualquier empresa no financiera que reporte
ante la SEC. Los ejemplos de este documento usan una **empresa de ejemplo** elegida solo porque
tiene un 10-K simple de leer (márgenes altos, poco CAPEX). El código no asume ninguna empresa fija.

## 1. Alcance del MVP

- Una empresa de ejemplo, un tipo de reporte (10-K anual), citas verificadas.
- Descargar y guardar el documento original con su hash.
- Extraer por código: EBITDA (derivado), impuestos, CAPEX y variación de capital de trabajo — cada
  cifra con su cita.
- Calcular FCF y CAGR de ingresos.
- Resumen de cambios contra el reporte anterior, con citas.
- Verificador automático (construido **antes** del resumen con LLM) y reporte final en Markdown.

Fuera del MVP (fases futuras): SEDAR+, FRED, Banco de Canadá, DCF, backtester, panel macro, diario
de decisiones, interfaz web.

## 2. Reglas no negociables

1. Cada cifra lleva fuente: documento, sección y fecha. Sin fuente → **"no verificado"**.
2. Los números los calcula el código (datos estructurados), nunca el LLM. El LLM solo explica.
3. Cada afirmación del LLM sale con una cita estructurada `{doc_id, sección, frase_exacta, hash}`.
   El verificador busca la frase literal en el documento guardado; si no está, se descarta.
4. Nunca "compra" ni "vende". Se muestra tesis, riesgo y qué la invalidaría.
5. Siempre el argumento en contra y las señales de alerta del método.
6. El riesgo se muestra primero.
7. Sin probabilidades salvo backtesting fuera de muestra validado, y sin fuga de datos.
8. Pie en todo reporte: «Análisis informativo, no asesoría financiera.»
9. El MVP evita bancos: EBITDA y EV/EBITDA no les aplican con sentido.

## 3. Fuente y formato del documento

- **Fuente:** SEC EDGAR, 10-K anual.
- **Formato:** el HTML del 10-K con **iXBRL en línea** (inline XBRL: tags `ix:nonFraction` /
  `ix:nonNumeric` incrustados en el texto real del documento), no el XBRL "puro" separado.
  Así cada cifra apunta a su lugar exacto en el documento y la **frase exacta de la cita sale
  literalmente de ese HTML**, nunca de una API de resumen.
- La API `data.sec.gov/api/xbrl/companyconcept` se usa solo como **ayuda interna** para saber qué
  tag XBRL (`us-gaap:...`) y qué periodo buscar dentro del HTML — nunca como fuente de la cita.
- **SEDAR+:** no verificado hasta probar que existe un acceso programático real. No se promete.

### Acceso a EDGAR (confirmado 2026-11-17)

- Mapeo ticker → CIK: `https://www.sec.gov/files/company_tickers.json`.
- Lista de filings: `https://data.sec.gov/submissions/CIK{cik10}.json` (campo `filings.recent`,
  filtrar `form == "10-K"`).
- Documento: `https://www.sec.gov/Archives/edgar/data/{cik}/{accession_sin_guiones}/{primaryDocument}`.
- **Obligatorio:** header `User-Agent` con un contacto identificable (`EDGAR_CONTACT` en `.env`,
  nunca hardcodeado ni con datos personales de quien lo use). SEC no verifica el correo, pero exige
  el formato.
- **Límite de tasa:** SEC pide no pasar de ~10 solicitudes/segundo. El ingestor usa **1 solicitud
  por segundo** (conservador) y reintenta con backoff si responde 429 o 5xx.
- Probado en vivo el 17 nov 2026 con la empresa de ejemplo: CIK, lista de 10-K y descarga del
  documento HTML con iXBRL funcionaron; hash SHA-256 calculado sobre 4,097,675 bytes.

## 4. Decisiones de cálculo (fijas para el MVP)

### 4.1 EBITDA — derivado, no una etiqueta XBRL

El EBITDA **no existe como tag XBRL estándar**. Se calcula por código:

```
EBITDA (derivado) = Utilidad operativa (us-gaap:OperatingIncomeLoss)
                   + Depreciación y amortización (us-gaap:DepreciationDepletionAndAmortization,
                     o el tag equivalente que la empresa reporte en su estado de flujo de efectivo)
```

- Cada componente se cita por separado (su propia frase exacta en el documento).
- El resultado de la suma se marca explícitamente **"(derivado)"** en el reporte: no es una frase
  del documento, es un cálculo nuestro sobre dos cifras citadas.
- **No se usa** el "EBITDA ajustado" (non-GAAP) que la empresa narra en su discusión y análisis:
  esa cifra excluye partidas a discreción de la empresa y no es comparable ni verificable con la
  misma vara entre reportes.

### 4.2 Impuestos

Se usa el **gasto por impuestos del estado de resultados** (`us-gaap:IncomeTaxExpenseBenefit`),
base devengado (no caja). Es la cifra consistente con un FCF simplificado que parte de EBITDA
(utilidad operativa), que también es base devengado.

- El **impuesto pagado en efectivo** (`us-gaap:IncomeTaxesPaidNet`, revelado en notas de flujo de
  efectivo) se muestra aparte, **solo como referencia**, con su propia cita. No entra en la
  fórmula del FCF del MVP. Se documenta la diferencia en el reporte cuando sea grande.

### 4.3 CAPEX

Se usa **pagos/adiciones por compra de propiedad, planta y equipo**. No todas las empresas etiquetan
este concepto igual, así que se prueban estos tags en orden y se usa el primero que el filing
reporte (confirmado en vivo con la empresa de ejemplo, que no usa el primero):

1. `us-gaap:PaymentsToAcquirePropertyPlantAndEquipment` (estado de flujo de efectivo — forma más común)
2. `us-gaap:PropertyPlantAndEquipmentAdditions` (nota de adiciones a propiedad, planta y equipo — la
   empresa de ejemplo usa esta)

- No incluye intangibles capitalizados (ej. software interno) ni adquisiciones de negocios: quedan
  fuera del alcance del MVP. Esto es una **simplificación documentada**, no un "no verificado" —
  la cifra que se usa sí tiene cita completa, solo que el alcance de "inversión" es más angosto que
  el CAPEX total económico de la empresa.
- Si ningún candidato aparece en el filing, CAPEX sale como "no verificado" (nunca se inventa un
  tercer tag sobre la marcha fuera de esta lista documentada).

### 4.4 Variación de capital de trabajo (ΔWK)

No hay un tag único universal. Regla de decisión, en este orden:

1. Si el estado de flujo de efectivo reporta una **línea agregada** (ej. "cambios netos en activos
   y pasivos operativos"), se usa esa cifra con su cita directa.
2. Si no existe una línea agregada, se **suman** las líneas individuales de capital de trabajo del
   estado de flujo de efectivo (cuentas por cobrar, cuentas por pagar, ingresos diferidos, inventario,
   etc.), cada una citada por separado, y el total se marca **"(derivado)"**.
3. Si ni (1) ni (2) se pueden extraer con una cita completa, la variación de capital de trabajo
   sale como **"no verificado"** — nunca se inventa ni se aproxima con otra cifra.

### 4.5 FCF (Flujo de Caja Libre, versión simplificada del MVP)

```
FCF = EBITDA (derivado) − Impuestos (gasto, devengado) − CAPEX − ΔWK
```

Es la fórmula de las siglas de análisis financiero (FCFF simplificado, sin ajuste de intereses).
No es un FCFF/FCFE completo. Se documenta como aproximación en el reporte final.

### 4.6 CAGR de ingresos

```
CAGR = (Ingreso_final / Ingreso_inicial) ^ (1 / años) − 1
```

Usa `us-gaap:Revenues` o `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax` (el que la
empresa reporte) del 10-K actual y de uno anterior. El MVP compara **2 reportes**; más años de
historia quedan para una fase posterior.

## 5. Formato de la cita estructurada

```json
{
  "doc_id": "CIK0000064040-ACCESSION",
  "seccion": "Estado consolidado de resultados",
  "frase_exacta": "texto literal copiado del HTML iXBRL",
  "hash": "sha256 del documento HTML guardado"
}
```

- `frase_exacta` se extrae del HTML con iXBRL en línea descargado y guardado localmente — nunca de
  un resumen, nunca de la API de `companyconcept`.
- El verificador (`verify/`) vuelve a abrir el documento guardado por su `hash` y confirma que
  `frase_exacta` existe ahí, literal. Si no existe, la afirmación se descarta y se marca
  **"no verificado"**.

## 6. Orden de fases (MVP)

0. SPEC.md + esqueleto del repo con pruebas (hoy).
1. `ingest/` — descarga y hash del documento.
2. `extract/` — EBITDA, impuestos, CAPEX, ΔWK, cada uno con cita.
3. `calc/` — FCF y CAGR.
4. `verify/` — verificador de citas, **antes** del resumen con LLM (orden invertido a propósito:
   el verificador no depende del LLM y así cualquier cita, venga de donde venga, pasa por el mismo
   filtro).
5. `llm/` — resumen de cambios con citas estructuradas. El texto del documento y del usuario se
   pasan en su propio rol, nunca concatenados al prompt del sistema (riesgo de inyección: el 10-K
   es un documento no confiable).
6. `report/` — Markdown final: riesgo arriba, cifras con fuente, pie de no asesoría.
7. Auditoría de seguridad, skill reusable, publicación del repo.

## 7. Seguridad (resumen; detalle en `docs/SECURITY.md`)

- Llaves y `EDGAR_CONTACT` solo en `.env` (gitignored, permisos 0600); `.env.example` sin valores
  reales.
- Nada personal en el repo: ni portafolios, ni correos, ni montos de nadie. Solo datos públicos de
  la empresa de ejemplo.
- Sin `eval`, `exec` ni `subprocess(shell=True)`.
- Tope de tokens y de salida en cualquier llamada al LLM.

## 9. Pruébalo con una acción (experimental)

Apartado interactivo adicional en la página web, pedido explícitamente como "una prueba, no te
bases en esto". Deja elegir entre unas pocas empresas de ejemplo **ya precalculadas** y muestra,
además de las cifras citadas de siempre, una lectura mecánica de "barata / cara / neutral".

### 9.1 Por qué no es en vivo

Dejar escribir cualquier ticker y calcularlo al momento necesitaría un servidor corriendo en
algún lugar — exactamente la superficie de ataque nueva que este proyecto evita a propósito (ver
`docs/SECURITY.md`). En vez de eso: un script (`scripts/precompute_examples.py`) corre el pipeline
completo para una lista corta de empresas y guarda el resultado en `examples/companies.json`. La
página solo lee ese JSON ya embebido (atributo `data-json`, nunca un `<script>` con el JSON
dentro, para no depender de cómo cada navegador trata la CSP ahí) — cero llamadas de red desde el
navegador, cero cambio a la superficie de seguridad de la página.

### 9.2 Precio de la acción — fuente NO oficial

SEC EDGAR no trae precios de mercado. Se usa el endpoint de gráficas de Yahoo Finance
(`ingest/price.py`): funciona, pero **no es una API pública documentada ni soportada**, puede
cambiar o dejar de funcionar sin aviso. Se probó primero Stooq (gratis, sin llave) pero ahora exige
un reto de JavaScript que un script no puede resolver — descartada. Si la fuente de precio falla,
el precio y todo lo que depende de él (P/E, FCF yield, veredicto) salen **"no verificado"**; nunca
se inventa ni se usa un precio de respaldo.

La cita del precio reutiliza exactamente el mismo formato `{doc_id, sección, frase_exacta, hash}`
que una cita del 10-K, y el mismo verificador (`verify_citation`): `frase_exacta` es la porción
literal de la respuesta cruda de Yahoo (ej. `"regularMarketPrice":452.35`), `hash` es el sha256 de
esa respuesta completa.

### 9.3 EPS y las dos razones calculadas

- **EPS (derivado):** utilidad neta (`us-gaap:NetIncomeLoss`) ÷ acciones diluidas
  (`us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding`, con
  `WeightedAverageNumberOfSharesOutstandingBasic` como candidato de respaldo).
- **P/E** = precio ÷ EPS. Solo se calcula si EPS > 0.
- **FCF yield** = FCF ÷ capitalización de mercado (precio × acciones diluidas). Depende del FCF
  (sección 4.5), que a su vez depende de ΔWK — por eso sale "no verificado" en varias de las
  empresas de ejemplo, honestamente, en vez de aproximarlo.

### 9.4 Veredicto — simplificación documentada, no el manual completo

Dos umbrales fijos, sin comparación sectorial, sin las 7 señales de alerta, sin PEG, sin considerar
el crecimiento:

| Señal | Barata | Cara |
| --- | --- | --- |
| P/E | ≤ 20 | ≥ 30 |
| FCF yield | ≥ 5 % | < 2 % |

Si ambas señales coinciden → ese veredicto. Si no coinciden → "neutral". Si no hay ninguna señal
calculable → "no verificado". El reporte web muestra esta limitación explícitamente junto al
veredicto; nunca se presenta como la metodología completa del manual de inversión, y nunca se
convierte en "compra" o "vende" (regla 4, igual que todo lo demás en este proyecto).

### 9.5 Empresas de ejemplo (probadas en vivo, 2026-11-18)

SPGI, COST, AAPL, UBER. Mezcla a propósito: COST y SPGI salen con todas las cifras citadas; AAPL y
UBER muestran ΔWK (y por lo tanto FCF y FCF yield) como "no verificado" — bueno para demostrar que
el sistema no inventa cuando falta una fuente.

### 9.6 Chat de preguntas — nunca en vivo

Pedido explícito: un bot al que preguntarle "qué opina" de una empresa, con tesis y bases. Se
descartó un chat en vivo (necesitaría un servidor con la llave de la API, que cualquier visitante
podría agotar — la misma superficie de ataque que el proyecto evita desde el principio). En su
lugar, `scripts/precompute_examples.py` arma 3 preguntas y respuestas por empresa de ejemplo
(`build_qa`), **generadas por código a partir de las mismas cifras ya verificadas** (nunca una
llamada a un LLM, nunca un número que no esté ya citado arriba en la misma página): crecimiento de
ingresos, lectura simple de valoración, y un riesgo específico (si la utilidad neta supera por
mucho al EBITDA, se señala como posible ganancia no recurrente — la misma "trampa" que el manual de
inversión advierte para un ratio visto de un solo vistazo). La página solo muestra estas respuestas
ya escritas; no hay ningún campo de texto libre ni ninguna llamada de red al hacer una pregunta.
Regla 4 sigue aplicando: ninguna respuesta dice "compra" ni "vende".

### 9.7 Gráfica y noticias en vivo (TradingView, iframe)

Mismo patrón que TradePro: widgets de TradingView como `<iframe>` con `sandbox` (nunca el script
de TradingView, para no tocar `script-src`). La CSP agrega `frame-src https://www.tradingview-widget.com` (host corregido en v1.8: el patrón
anterior, `s.tradingview.com` con `?symbol=`, no cargaba los widgets; ver sección 12)
— el único cambio real a la superficie de seguridad de esta fase. El símbolo (ej. `NYSE:SPGI`) se
valida con una expresión regular antes de armar la URL del iframe, y la bolsa de cada empresa de
ejemplo se documenta a mano en `scripts/precompute_examples.py` (`_EXCHANGE_BY_TICKER`) — no se
autodetecta. El contenido de esos widgets es de TradingView, no de este proyecto: no se verifica
ni se cita, y la página lo dice explícitamente.

### 9.8 Sección de confianza retirada

A pedido explícito, se quitó la sección "Por qué puedes confiar en esta página" y sus 3 tarjetas.
El enlace al código fuente se movió al pie de página, sin la sección alrededor.

## 10. Historial

- 2026-11-17 — v1. Creado para el bloque de arranque. Empresa de ejemplo y fuente elegidas,
  acceso a EDGAR probado en vivo, decisiones de cálculo de EBITDA/impuestos/CAPEX/ΔWK fijadas,
  fases 4 y 5 invertidas (verificador antes del resumen LLM).
- 2026-11-17 — v1.1. Fases 2–4 construidas y validadas en vivo contra el 10-K real de la empresa
  de ejemplo: `extract/` (EBITDA derivado, impuestos, CAPEX, ingresos, ΔWK, todos citados contra
  el HTML con iXBRL), `calc/` (FCF, CAGR de ingresos) y `verify/` (verificador, antes del LLM).
  Corrección a la sección 4.3: CAPEX prueba dos tags candidatos en orden porque el tag original
  no estaba etiquetado en el filing real; el segundo sí. Resultado honesto del MVP: todas las
  cifras salen citadas salvo ΔWK, que este filing no reporta como línea agregada — queda
  "no verificado" a propósito, sin sumar líneas sueltas (regla 4.4 paso 3).
- 2026-11-18 — v1.2. Fases 5-6 construidas: `llm/` (resumen de cambios; el modelo nunca recibe el
  documento crudo, solo el JSON de hechos ya verificados) y `report/` (Markdown final). Se agregó
  `cli.py` (pipeline completo de punta a punta) y, fuera del alcance original del MVP, una
  **página web estática** adicional (`report/html_report.py`): blanco y
  azul claro, sin backend ni formularios, con CSP estricta y todo texto escapado. Se corrigió un
  bug real: `CitedValue.no_verificado` marcaba EBITDA como "no verificado" aunque sus dos
  componentes estuvieran citados, porque un valor derivado nunca tiene cita propia a propósito.
- 2026-11-18 — v1.3. Rediseño de la página web (ver README "La página web") y bug real corregido:
  la propia CSP de la página (`script-src 'self'` sin permitir el `<script>` inline) bloqueaba el
  script que revela el contenido — todo se quedaba invisible. Arreglado con un hash SHA-256 del
  script exacto en vez de `'unsafe-inline'`, y además el contenido pasa a ser visible por defecto
  (solo se "pre-esconde" si el script confirma que arrancó), para que un futuro fallo del script,
  por cualquier motivo, nunca vuelva a dejar la página en blanco.
- 2026-11-18 — v1.4. Sección 9: apartado interactivo "Pruébalo con una acción" (experimental),
  con precio de Yahoo Finance (no oficial), EPS/P/E/FCF yield derivados y un veredicto simple
  barata/cara/neutral — todo precalculado (`scripts/precompute_examples.py`), nunca en vivo desde
  el navegador. Repo publicado como público en GitHub (decisión explícita, fuera del alcance
  original "privado por ahora" de la sección 7): `github.com/Hsoja/quant-lab`, página en
  `hsoja.github.io/quant-lab`.
- 2026-11-18 — v1.5. Rediseño estilo tablero (tarjetas grandes, gráfica de ingresos en SVG propio),
  gráfica y noticias en vivo de TradingView por iframe (sección 9.7), chat de preguntas ya
  preparadas con tesis y riesgo por empresa (sección 9.6, nunca en vivo, nunca compra/vende), y se
  retiró la sección "Por qué puedes confiar en esta página" (sección 9.8).
- 2026-11-18 — v1.6. Paleta de colores cambiada de blanco/azul claro a oscura con brillos
  degradados índigo/morado, a pedido explícito (se compartieron imágenes de referencia de
  tableros). Cambio puramente visual (CSS): mismas reglas de seguridad, mismo contenido, mismo
  orden de secciones.
- 2026-11-18 — v1.7. Sección 11: diseño v2 de la página en dos capas separadas. **Capa A**
  (hechos verificados: riesgo primero, cifras con cita, cálculos) y **Capa B** (simulación Monte
  Carlo GBM en el navegador, etiquetada SIMULADO · SIN VALIDAR, sin citas) con una frontera visible
  entre ambas, más un **diario de decisiones** (copiar/descargar Markdown; no guarda nada). μ y σ
  salen de cierres diarios históricos (`calc/montecarlo.py`, `scripts/precompute_examples.py`,
  fuente no oficial); si no hay historial, la página pide supuestos manuales marcados "no
  verificado". Las probabilidades no están validadas con backtest y la página lo dice.
- 2026-11-18 — v1.8. Sección 12: diseño v3 (fondo animado, tipografías propias, widgets de
  TradingView que sí cargan y asistente flotante). Mismo contenido y mismas reglas; ver abajo.

## 12. Diseño v3 (2026-11-18)

Pedido explícito: más dinámica, más diseño de fondo (referencias: tablero oscuro con tarjetas
degradadas), conectada a TradingView, un bot como el de Operativa y tipografías con carácter
(referencias: TradePro y Operativa.ia). Solo cambia la presentación; las reglas 1-5 y la
separación Capa A / Capa B no se tocan.

- **Diseño.** `report/assets/style.css`. Fondo con cuadrícula, tres orbes que derivan, una
  constelación de partículas en `<canvas>` (decorativa, se detiene con la pestaña oculta) y brillo
  que sigue al puntero en las tarjetas. Tarjetas KPI con tinte degradado y franja de estado,
  borde de frontera animado, gráfica de ingresos que se dibuja al entrar, reloj UTC y menú que
  marca la sección activa. Todo respeta `prefers-reduced-motion`.
- **Tipografías.** Manrope (texto), Instrument Serif cursiva (acentos) e IBM Plex Mono (cifras),
  todas OFL, en `report/assets/fonts/` y **embebidas como `data:` URI** al generar la página
  (`font-src data:`): sigue siendo un solo archivo y no se carga nada de un host de fuentes.
- **TradingView.** Los widgets viejos no cargaban: usaban `s.tradingview.com` con `?symbol=`. Ahora
  se usa el mismo patrón verificado de TradePro: iframe con `sandbox` a
  `https://www.tradingview-widget.com/embed-widget/<widget>/?locale=...#<config JSON>`; la
  configuración viaja en el hash, que el navegador no envía al servidor. Cinta de precios global,
  gráfica interactiva y rangos de precio por empresa, y noticias. El feed de noticias solo responde
  con `locale=en`; con `es` TradingView muestra un error. Siguen marcados "externo · no verificado".
- **Asistente "Quant".** Botón flotante y panel lateral (estilo Operativa) con orbe de puntos,
  escritura progresiva y preguntas sugeridas. **No es un chat en vivo**: no hay red, modelo ni
  llave. Empareja la pregunta con respuestas redactadas al generar la página (`_bot_kb` en
  `report/html_report.py`, a partir de las mismas cifras verificadas, más las respuestas por
  empresa de la sección 9.6). Sin respuesta preparada, dice que no la tiene (`no verificado`).
- **Resumen de verificación en el encabezado** (citadas / derivadas / sin verificar): se cuenta
  en código a partir de las cifras reales, nunca un porcentaje inventado.
- **CSP.** Cambios: `frame-src` pasa a `https://www.tradingview-widget.com`, se agrega
  `font-src data:` y se quitó `frame-ancestors`, que los navegadores ignoran dentro de un
  `<meta>` (GitHub Pages no permite cabeceras propias, así que esa protección no es posible aquí).
- **Publicación.** La página en vivo se sirve desde la rama `gh-pages` (`index.html`). Hay que
  copiarle `examples/reporte_ejemplo.html` después de regenerarlo.
