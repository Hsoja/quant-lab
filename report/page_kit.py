"""Compartido entre los generadores de página HTML estática y autocontenida
(report/html_report.py hoy; los demos nuevos de calc/ en los próximos
milestones): embebe fuentes como `data:` URI y calcula el hash SHA-256 que la
CSP usa para permitir el único `<script>` inline por su contenido exacto
(ver docs/SECURITY.md) — así ninguna de esas páginas carga nada de un host
externo de fuentes o scripts.
"""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path


def font_css(fonts_dir: Path, font_faces: tuple[tuple[str, str, str, str], ...]) -> str:
    rules = []
    for family, style, weight, filename in font_faces:
        data = base64.b64encode((fonts_dir / filename).read_bytes()).decode("ascii")
        rules.append(
            f'@font-face {{ font-family: "{family}"; font-style: {style}; font-weight: {weight}; '
            f"font-display: swap; src: url(data:font/woff2;base64,{data}) format(\"woff2\"); }}"
        )
    return "\n".join(rules)


def sha256_b64(text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return base64.b64encode(digest).decode("ascii")
