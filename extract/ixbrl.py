"""Convierte el HTML con iXBRL en línea de un 10-K en texto plano, registrando
en el mismo paso en qué posición de ese texto plano cae cada hecho
(`ix:nonFraction` / `ix:nonNumeric`) con sus atributos XBRL.

Por qué así: la "frase_exacta" de cada cita (ver SPEC.md sección 5) tiene que
ser una porción CONTIGUA y LITERAL de un texto reproducible a partir del
documento guardado. Si tomáramos el HTML crudo, la etiqueta de una cifra
("Utilidad operativa") y su valor casi siempre están en celdas de tabla
distintas, separadas por markup — no forman una frase contigua en el HTML
crudo. Por eso definimos "el documento" para efectos de cita como el texto
plano que resulta de este parser, aplicado siempre de la misma forma
(determinista) tanto al extraer como al verificar. verify/ vuelve a correr
este mismo parser sobre el HTML guardado y confirma que la frase exista ahí.

Limitación conocida (documentada, no oculta): no se interpreta CSS
(`display:none`), así que texto oculto del documento (p. ej. bloques de
metadatos de Document and Entity Information) puede colarse en el texto
plano. Tampoco se resuelven hechos anidados (un ix:nonFraction dentro de
otro). Para los estados financieros estándar de un 10-K esto no es un
problema; queda anotado para una fase futura.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser

_SKIP_TAGS = {"script", "style"}
_FACT_TAGS = {"ix:nonfraction", "ix:nonnumeric"}
_BOUNDARY_TAGS = {
    "td", "tr", "th", "p", "div", "br", "li", "table",
    "h1", "h2", "h3", "h4", "h5", "h6",
}
_WS_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class IxFact:
    tag: str  # "ix:nonfraction" | "ix:nonnumeric"
    name: str  # ej. "us-gaap:OperatingIncomeLoss" (prefijo tal cual lo declaró el documento)
    context_ref: str
    sign: str | None
    scale: int
    decimals: str | None
    text_start: int  # offset en el texto plano devuelto por parse_ixbrl
    text_end: int
    raw_text: str  # texto literal entre esos offsets (número tal como se imprime)

    @property
    def local_name(self) -> str:
        return self.name.split(":")[-1]


class _IxbrlToText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._length = 0
        self._skip_depth = 0
        self._open_facts: list[dict] = []
        self._raw_facts: list[dict] = []

    def _append(self, text: str) -> None:
        if not text:
            return
        collapsed = _WS_RE.sub(" ", text)
        if not collapsed:
            return
        if self._parts and self._parts[-1][-1:] not in (" ", "") and collapsed[0] != " ":
            collapsed = " " + collapsed
        self._parts.append(collapsed)
        self._length += len(collapsed)

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if tag in _BOUNDARY_TAGS:
            self._append(" ")
        if tag in _FACT_TAGS and self._skip_depth == 0:
            attrs_d = dict(attrs)
            self._open_facts.append(
                {
                    "tag": tag,
                    "name": attrs_d.get("name", ""),
                    "context_ref": attrs_d.get("contextref", ""),
                    "sign": attrs_d.get("sign"),
                    "scale": int(attrs_d["scale"]) if attrs_d.get("scale") else 0,
                    "decimals": attrs_d.get("decimals"),
                    "start": self._length,
                }
            )

    def handle_startendtag(self, tag: str, attrs) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if tag in _FACT_TAGS and self._open_facts and self._open_facts[-1]["tag"] == tag:
            opened = self._open_facts.pop()
            opened["end"] = self._length
            self._raw_facts.append(opened)
        if tag in _BOUNDARY_TAGS:
            self._append(" ")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._append(data)

    def finalize(self) -> tuple[str, list[IxFact]]:
        text = "".join(self._parts)
        facts = [
            IxFact(
                tag=f["tag"],
                name=f["name"],
                context_ref=f["context_ref"],
                sign=f["sign"],
                scale=f["scale"],
                decimals=f["decimals"],
                text_start=f["start"],
                text_end=f["end"],
                raw_text=text[f["start"] : f["end"]],
            )
            for f in self._raw_facts
        ]
        return text, facts


def parse_ixbrl(html_text: str) -> tuple[str, list[IxFact]]:
    """Devuelve (texto_plano, hechos) a partir del HTML con iXBRL en línea."""
    parser = _IxbrlToText()
    parser.feed(html_text)
    parser.close()
    return parser.finalize()


def to_number(raw_text: str, sign: str | None, scale: int) -> float | None:
    """Convierte el texto literal de un hecho iXBRL a número.

    Devuelve None si el texto no se puede interpretar (no se inventa un
    valor; quien llama debe tratarlo como "no verificado").
    """
    cleaned = raw_text.strip()
    if cleaned in ("", "-", "—", "–"):
        return 0.0
    cleaned = cleaned.replace(",", "")
    negative_paren = cleaned.startswith("(") and cleaned.endswith(")")
    if negative_paren:
        cleaned = cleaned[1:-1]
    try:
        value = float(cleaned)
    except ValueError:
        return None
    if negative_paren:
        value = -value
    if scale:
        value *= 10**scale
    if sign == "-":
        value = -value
    return value
