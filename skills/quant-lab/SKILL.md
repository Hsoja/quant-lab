---
name: quant-lab
description: >
  Reglas y flujo de verificación para cualquier análisis que combine código y
  un LLM sobre documentos oficiales (10-K, 10-Q, un informe regulatorio,
  cualquier reporte estructurado): cada cifra con una cita literal verificada
  contra el documento guardado, nunca inventada por el modelo. Úsala siempre
  que se construya o se use una herramienta que lea reportes oficiales y
  resuma cambios, calcule métricas derivadas (EBITDA, FCF, CAGR, u otras), o
  genere un reporte con citas — incluso si el usuario no menciona "Quant Lab"
  por nombre. También aplica a cualquier pipeline extract → verify → llm →
  report sobre documentos oficiales de otro dominio que necesite el mismo
  nivel de verificabilidad (legal, salud, cumplimiento).
---

# Quant Lab: análisis verificable con citas

Extraído del proyecto Quant Lab (monitor de reportes financieros con citas verificables). El
problema que resuelve: cuando un LLM resume o explica las cifras de un documento, puede inventar
un número o una fuente sin que se note. Este flujo elimina esa duda separando quién hace qué: el
código calcula, el LLM redacta, y un verificador independiente confirma cada cita contra el
documento guardado antes de que llegue a cualquier reporte.

## Reglas no negociables

1. **Cada cifra lleva fuente**: documento, sección y fecha. Sin fuente → **"no verificado"**.
   Nunca se rellena con un supuesto, un promedio ni un cero.
2. **Los números los calcula el código** (datos estructurados: XBRL, una API oficial, una tabla),
   nunca el LLM. El LLM explica y resume; no inventa cifras.
3. **Cada afirmación lleva una cita estructurada** `{doc_id, sección, frase_exacta, hash}`. Un
   verificador independiente confirma que `frase_exacta` existe literal en el documento guardado
   (identificado por su hash). Si no existe, la afirmación se descarta por completo — valor y
   cita, los dos, no solo la cita.
4. **Nunca un veredicto binario de acción** (p. ej. "compra"/"vende" en finanzas): se muestra la
   tesis o el hallazgo, el riesgo, y qué lo invalidaría.
5. **Siempre el argumento en contra** o las señales de alerta del método que corresponda al
   dominio.
6. **El riesgo y las limitaciones se muestran primero**, antes que las cifras.
7. **Sin probabilidades** salvo que se validen con backtesting (o el equivalente del dominio)
   fuera de muestra, y sin fuga de datos: la variable que se quiere predecir nunca entra como
   insumo.
8. **Pie fijo** de descargo correspondiente al dominio (p. ej. "Análisis informativo, no
   asesoría financiera").

## El flujo de verificación (el orden importa)

1. **Ingesta** — Descargar y guardar el documento tal cual, con su hash (sha256). El hash es la
   identidad del documento para todo lo que sigue; cualquier verificación posterior vuelve a
   abrir el archivo guardado por ese hash, nunca confía en una copia en memoria.

2. **Extracción** — Localizar cada cifra en una fuente estructurada y, por separado, localizar su
   `frase_exacta` dentro del MISMO documento guardado — nunca inventada ni copiada de un resumen.
   - Un valor **derivado** (calculado a partir de otros, p. ej. EBITDA = utilidad operativa +
     depreciación y amortización) no tiene cita propia a propósito: se apoya en sus componentes,
     que sí están citados por separado. No cuenta como "no verificado" solo por no tener su
     propia frase — solo si ni siquiera se pudo calcular. Mantener esta distinción explícita en
     el modelo de datos evita que un valor bien fundamentado se vea, por accidente, igual de poco
     confiable que uno que de verdad no se pudo confirmar.
   - Si no hay una fuente sólida para una cifra, se devuelve "no verificado" con la razón —
     nunca se aproxima, nunca se promedia con otra cosa.
   - Si una cifra puede salir de más de un campo/tag según la fuente (cada emisor etiqueta un
     poco distinto), prueba varios candidatos conocidos **en un orden documentado** y usa el
     primero que exista. Nunca un campo inventado sobre la marcha para que "cuadre" el número.

3. **Verificador — antes del resumen con el LLM, a propósito** — Reabre el documento guardado por
   su hash, recomputa la misma representación (texto plano, estructura) que usó la extracción, y
   confirma que cada `frase_exacta` exista ahí, literal. Si no existe, o el hash no coincide, la
   afirmación se descarta por completo. Construir este paso antes del LLM importa por dos
   razones: no depende de que el LLM exista para funcionar, y sirve igual de bien para validar lo
   que el LLM escriba en el paso siguiente — un solo filtro, dos usos.

4. **Resumen con LLM** — El modelo redacta a partir de un JSON de hechos **ya verificados**,
   nunca a partir del documento crudo. Esto no es una precaución extra: elimina la superficie de
   inyección de instrucciones de raíz — si el documento nunca llega al modelo, nada escondido en
   él puede influirlo. Además, cada línea que el modelo escriba debe señalar la clave del hecho
   en el que se apoya (p. ej. `[[ebitda]]`); cualquier línea sin esa marca, o que señale una
   clave que no exista en el JSON que se le dio, se descarta de forma determinista después —
   nunca se confía en que el modelo siguió la instrucción del prompt, se comprueba.

5. **Reporte** — Riesgo y limitaciones primero, luego las cifras con su cita (o "no
   verificado"), luego los cálculos derivados, luego el resumen narrativo. Nunca una
   recomendación de acción.

## Cómo adaptar esto a un análisis nuevo

- Cambia la fuente (otro tipo de reporte, otro regulador, otro formato de documento) y el formato
  de `frase_exacta` (texto plano, HTML, PDF) — el flujo de 5 pasos no cambia.
- Antes de escribir código, documenta por escrito cómo se calcula cada métrica derivada (como se
  hizo para EBITDA/CAPEX/variación de capital de trabajo en el `SPEC.md` de Quant Lab). Decidir
  esto por adelantado evita que el LLM —o la persona que programa con prisa— "decida" la fórmula
  sobre la marcha, de forma distinta cada vez.
- Si el dominio no es financiero, cambia las reglas 4-8 por el método de ese dominio (su propio
  "argumento en contra", su propio pie de descargo) pero conserva las reglas 1-3 y el flujo de
  verificación tal cual: son las que de verdad evitan que el LLM invente algo.

## Referencia

Implementación completa de ejemplo (genérica, sin datos de ninguna empresa en particular):
proyecto Quant Lab, módulos `extract/`, `verify/`, `llm/` y `report/`. El `SPEC.md` del proyecto
documenta además cómo se decidieron las fórmulas de EBITDA, impuestos, CAPEX y variación de
capital de trabajo — un ejemplo de cómo fijar por escrito una decisión de cálculo antes de
programarla.
