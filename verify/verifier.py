"""Fase 4: verificador automático de citas — se construye ANTES del resumen
con LLM a propósito (SPEC.md sección 6): cualquier afirmación, venga del LLM
o de extract/, pasa por este mismo filtro. Vuelve a abrir el documento
guardado por su hash y confirma que `frase_exacta` existe ahí, literal, con
el MISMO parser que usó extract/ (extract.ixbrl.parse_ixbrl), para que "el
documento" signifique lo mismo de los dos lados.

Si una cita no pasa, la afirmación se descarta por completo (valor y cita),
nunca se "arregla" ni se adivina: queda "no verificado".
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from extract.facts import Citation, CitedValue
from extract.ixbrl import parse_ixbrl
from ingest.edgar import sha256_hex


@dataclass(frozen=True)
class VerificationResult:
    ok: bool
    reason: str


def verify_citation(citation: Citation, document_bytes: bytes) -> VerificationResult:
    """Confirma que `citation.frase_exacta` existe, literal, en el documento."""
    actual_hash = sha256_hex(document_bytes)
    if actual_hash != citation.hash:
        return VerificationResult(
            ok=False,
            reason=(
                f"El hash del documento ({actual_hash}) no coincide con el de la cita "
                f"({citation.hash}): no se confía en este archivo para verificarla."
            ),
        )
    if not citation.frase_exacta or not citation.frase_exacta.strip():
        return VerificationResult(ok=False, reason="La cita no tiene frase_exacta.")
    full_text, _facts = parse_ixbrl(document_bytes.decode("utf-8", errors="replace"))
    if citation.frase_exacta not in full_text:
        return VerificationResult(
            ok=False, reason="La frase_exacta no existe, literal, en el documento guardado."
        )
    return VerificationResult(ok=True, reason="La frase existe literal en el documento citado.")


def verify_cited_value(cited_value: CitedValue, document_bytes: bytes) -> CitedValue:
    """Re-verifica un `CitedValue`; si la cita no pasa, lo descarta por completo.

    Si `cited_value` ya llegó sin cita (por ejemplo, un concepto no reportado
    o derivado), se devuelve tal cual: no hay nada que re-verificar.
    """
    if cited_value.citation is None:
        return cited_value
    result = verify_citation(cited_value.citation, document_bytes)
    if result.ok:
        return cited_value
    return dataclasses.replace(
        cited_value,
        value=None,
        citation=None,
        nota=f"Cita rechazada por el verificador: {result.reason}",
    )


def verify_all(facts: dict[str, object], document_bytes: bytes) -> dict[str, object]:
    """Aplica `verify_cited_value` a todos los `CitedValue` de un dict de
    resultados de extract/ (incluida la serie `revenue_series`)."""
    verified: dict[str, object] = {}
    for key, value in facts.items():
        if isinstance(value, CitedValue):
            verified[key] = verify_cited_value(value, document_bytes)
        elif isinstance(value, list):
            verified[key] = [
                verify_cited_value(v, document_bytes) if isinstance(v, CitedValue) else v
                for v in value
            ]
        else:
            verified[key] = value
    return verified
