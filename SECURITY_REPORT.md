# Reporte de seguridad — Quant Lab

Última auditoría: **2026-11-18**, antes de la primera publicación del repo (privado). Corresponde
a la skill `auditoria-seguridad`. Las amenazas STRIDE por fase viven en
[`docs/SECURITY.md`](docs/SECURITY.md); este documento es el resultado de correr los escáneres y
revisar el diff.

## Veredicto

🟢 **Aprobado.** Sin hallazgos altos ni medios abiertos. Un hallazgo medio se encontró y se
corrigió en la misma sesión (ver tabla).

## 1. Resultados por herramienta

| Herramienta | Resultado | Detalle |
| --- | --- | --- |
| `pytest` | ✅ Correcto | 50 pruebas pasan, 1 se salta (red real, opt-in con `RUN_NETWORK_TESTS=1`). |
| `bandit` (`--severity-level medium`) | ✅ Correcto | 1 hallazgo medio encontrado y corregido (ver QL-1). 125 hallazgos bajos (`B101`, uso de `assert`) son todos en `tests/`: no aplica, es el patrón normal de pytest. |
| `pip-audit` | ✅ Correcto | 0 vulnerabilidades conocidas tras actualizar `requirements.txt` (ver QL-2, QL-3, QL-4). |
| `semgrep` (`p/python`) | ✅ Correcto | 151 reglas, 0 hallazgos en los 15 archivos de código. |
| `gitleaks` (todo el historial) | ✅ Correcto | 4 commits escaneados, 0 secretos encontrados. |
| Revisión manual del diff | ✅ Correcto | Ver sección 3. |
| Escaneo de datos personales | ✅ Correcto | Búsqueda de nombre, apellidos, usuario de GitHub, banco, ciudad y correos en todo el repo (código, docs, ejemplos): sin resultados. |
| DAST / cabeceras de despliegue | ⚪ No aplica | No hay servidor desplegado: el reporte web es un archivo HTML estático, sin backend. |

## 2. Hallazgos

| ID | Severidad | Archivo | Corrección | Estado |
| --- | --- | --- | --- | --- |
| QL-1 | Media (CWE-22, bandit B310) | `ingest/edgar.py` | `_get()` descargaba cualquier esquema de URL (`urllib.request.urlopen` sigue `file://`, `ftp://`, etc. si se le da la oportunidad). Se agregó una validación explícita: solo `https://`, antes de abrir la conexión. Prueba nueva: `test_get_rejects_non_https_scheme`. | Corregido |
| QL-2 | Media (CVE-2025-71176) | `requirements.txt` (`pytest` 8.3.5) | DoS/escalada local por el patrón de nombre de `/tmp/pytest-of-{user}` en UNIX. Solo afecta el entorno de desarrollo (pytest nunca corre en producción). Corregido subiendo el mínimo a `pytest>=9.0.3`. Requirió recrear el entorno virtual con Python 3.13 (pytest 9 no soporta 3.8). | Corregido |
| QL-3 | Media (CVE-2026-28684) | `requirements.txt` (`python-dotenv` 1.0.1) | `set_key()`/`unset_key()` pueden seguir symlinks al reescribir `.env`. El proyecto solo usa `load_dotenv()` (lectura), nunca esas funciones, así que no era explotable aquí — se corrigió de todos modos subiendo el mínimo a `python-dotenv>=1.2.2`. | Corregido |
| QL-4 | Media (CVE-2026-63374, CVE-2026-64847) | `requirements.txt` (`anyio` 4.5.2, dependencia transitiva de `anthropic`) | Validación de certificado en dominios IDN y bloqueo de un pool de procesos por `stderr` sin drenar. El proyecto no usa dominios internacionalizados ni pools de procesos propios; se fijó `anyio>=4.14.2` como mínimo directo para no depender de cuándo `anthropic` suba su propio piso. | Corregido |
| QL-5 | Informativa | Entorno de desarrollo | El `.venv` original usaba Python 3.8.10 (fin de soporte), que bloqueaba las versiones parchadas de QL-2/3/4 (no existen builds para 3.8). Se recreó `.venv` con Python 3.13 (disponible vía Homebrew, sin tocar el `pyenv` global del sistema, que sigue en 3.8.10 para otros proyectos). | Aceptado (acción: usar Python ≥3.9 para este proyecto en adelante) |

## 3. Revisión manual del diff (ver también `docs/SECURITY.md`)

- **Rutas de red:** solo `www.sec.gov` y `data.sec.gov`, ambas documentadas en `SPEC.md` sección 3. Ningún otro dominio.
- **Credenciales/tokens fijos:** ninguno (`EDGAR_CONTACT` y `ANTHROPIC_API_KEY` solo por variable de entorno, `.env.example` sin valores reales).
- **`eval`/`exec`/`pickle`/`shell=True`/`yaml.load`:** ninguno en el código (la única coincidencia es un literal de texto dentro de una prueba que confirma que esos patrones *no* aparecen en el HTML generado).
- **Dependencias nuevas:** `pytest`, `python-dotenv`, `anthropic`, `anyio` — nombres exactos (sin typosquatting), paquetes de PyPI ampliamente usados y mantenidos, licencias permisivas (MIT, BSD-3-Clause, Apache-2.0).
- **CI:** no existe todavía (no se ha publicado el repo). Queda pendiente para cuando se configure.
- **Logs:** `cli.py` solo imprime rutas de archivos locales; sin datos personales ni secretos.
- **Binarios o archivos generados sin origen:** ninguno. `examples/reporte_ejemplo.{md,html}` se generan por código (`report/report.py`, `report/html_report.py`) a partir de datos públicos de una empresa de ejemplo.
- **`.gitignore`:** agrega `salida/`, `data/raw/`, `.venv/`, `.env` — todo revisado, sin exclusiones sospechosas.

## 4. Riesgos residuales y lo que no se verificó

- El resumen con LLM (`llm/summarizer.py`, fase 5) no se probó contra la API real de Anthropic en esta sesión (sin `ANTHROPIC_API_KEY` disponible en el entorno). Se validó con un cliente simulado que respeta el mismo contrato (`client.messages.create`, bloques `TextBlock`). **No verificado** contra la API real.
- No hay CI configurado todavía: los escáneres se corrieron manualmente en esta sesión, no en cada cambio futuro.
- El acceso real a SEC EDGAR (ingest/) sí se validó en vivo varias veces en sesiones anteriores (ver `SPEC.md` sección 3 e historial).

## 5. Historial

- 2026-11-18 — v1. Primera auditoría, antes de publicar el repo. Veredicto 🟢 Aprobado.
