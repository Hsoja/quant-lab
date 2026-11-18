# Quant Lab

Monitor de reportes financieros oficiales con **citas verificables**. Lee un reporte (por ahora,
un 10-K de SEC EDGAR), extrae cifras estructuradas, las calcula por código y cita cada afirmación
contra el documento original guardado. Un verificador automático comprueba que cada cita exista
literalmente en el documento; si no existe, se descarta y se marca **"no verificado"**.

**No es asesoría financiera.** Es una herramienta de investigación: muestra tesis, riesgo y qué la
invalidaría — nunca una señal de compra o venta. Pensada para que cualquier persona la use con
cualquier empresa no financiera que reporte ante la SEC (bancos quedan fuera: EBITDA y EV/EBITDA
no les aplican con sentido).

Las reglas y decisiones completas viven en [`SPEC.md`](SPEC.md). La amenaza de seguridad de cada
pieza vive en [`docs/SECURITY.md`](docs/SECURITY.md).

## Estado

MVP completo (fases 0-6) y validado en vivo contra un 10-K real: `ingest/`, `extract/`, `calc/`,
`verify/`, `llm/` y `report/` funcionan de punta a punta. Ejemplo generado con datos públicos:
[`examples/reporte_ejemplo.md`](examples/reporte_ejemplo.md) y
[`examples/reporte_ejemplo.html`](examples/reporte_ejemplo.html).

## Instalar

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # y pon tu propio contacto en EDGAR_CONTACT
```

## Usar

```bash
python cli.py SPGI --out-dir salida
```

Descarga el 10-K más reciente del ticker, lo guarda con su hash, extrae y verifica las cifras, y
escribe `salida/reporte.md` y `salida/reporte.html` (página estática, sin backend ni formularios:
ver "La página web" abajo). `ANTHROPIC_API_KEY` en `.env` es opcional; solo hace falta para el
resumen de cambios de `llm/summarizer.py` (fase 5), que **nunca** recibe el texto del documento,
solo el JSON de cifras ya verificadas (ver `docs/SECURITY.md`).

## La página web

`report/html_report.py` genera un único archivo HTML autocontenido (blanco y azul claro) a partir
de los mismos datos que el reporte en Markdown. Es estático a propósito: sin backend, sin
formularios, sin `localStorage`, sin scripts ni fuentes externas. Todo texto dinámico pasa por
`html.escape` antes de insertarse y trae una Content-Security-Policy estricta (`default-src
'none'`). Las animaciones respetan `prefers-reduced-motion`.

## Correr las pruebas

```bash
pytest
```

Por defecto no se llama a EDGAR real (las pruebas de red están marcadas y se saltan). Para
confirmar el acceso real:

```bash
RUN_NETWORK_TESTS=1 pytest -m network
```
