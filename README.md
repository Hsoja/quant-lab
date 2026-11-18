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

MVP en construcción. Fase actual: `ingest/` (descarga y hash del documento) ya funciona contra
EDGAR real. Las demás fases (`extract/`, `calc/`, `verify/`, `llm/`, `report/`) son esqueleto.

## Instalar

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # y pon tu propio contacto en EDGAR_CONTACT
```

## Correr las pruebas

```bash
pytest
```

Por defecto no se llama a EDGAR real (las pruebas de red están marcadas y se saltan). Para
confirmar el acceso real:

```bash
RUN_NETWORK_TESTS=1 pytest -m network
```
