from extract.facts import Citation, CitedValue
from extract.ixbrl import parse_ixbrl
from ingest.edgar import sha256_hex
from verify.verifier import verify_citation, verify_cited_value

DOC = b"<html><body><table><tr><td>Operating income</td><td>1,000</td></tr></table></body></html>"
DOC_HASH = sha256_hex(DOC)


def test_verify_citation_accepts_literal_phrase_present_in_document():
    text, _facts = parse_ixbrl(DOC.decode("utf-8"))
    citation = Citation(doc_id="D", seccion="S", frase_exacta=text.strip(), hash=DOC_HASH)
    result = verify_citation(citation, DOC)
    assert result.ok


def test_verify_citation_rejects_fabricated_phrase():
    """Caso central del verificador: una cita inventada DEBE ser rechazada."""
    citation = Citation(
        doc_id="D",
        seccion="S",
        frase_exacta="Esta frase nunca aparece en el documento guardado",
        hash=DOC_HASH,
    )
    result = verify_citation(citation, DOC)
    assert not result.ok
    assert "literal" in result.reason.lower()


def test_verify_citation_rejects_hash_mismatch():
    citation = Citation(doc_id="D", seccion="S", frase_exacta="Operating income", hash="hash-que-no-es")
    result = verify_citation(citation, DOC)
    assert not result.ok
    assert "hash" in result.reason.lower()


def test_verify_citation_rejects_empty_frase():
    citation = Citation(doc_id="D", seccion="S", frase_exacta="   ", hash=DOC_HASH)
    result = verify_citation(citation, DOC)
    assert not result.ok


def test_verify_cited_value_discards_value_and_citation_on_fabricated_citation():
    fabricated = CitedValue(
        concept="x",
        label="X",
        value=999.0,
        citation=Citation(
            doc_id="D", seccion="S", frase_exacta="algo inventado que no está ahí", hash=DOC_HASH
        ),
    )
    result = verify_cited_value(fabricated, DOC)
    assert result.value is None
    assert result.citation is None
    assert "rechazada" in result.nota.lower()


def test_verify_cited_value_keeps_value_when_citation_is_valid():
    text, _facts = parse_ixbrl(DOC.decode("utf-8"))
    valid = CitedValue(
        concept="x",
        label="X",
        value=1000.0,
        citation=Citation(doc_id="D", seccion="S", frase_exacta=text.strip(), hash=DOC_HASH),
    )
    result = verify_cited_value(valid, DOC)
    assert result.value == 1000.0
    assert result.citation is not None


def test_verify_cited_value_passes_through_values_already_sin_cita():
    sin_cita = CitedValue(concept="x", label="X", value=None, citation=None, nota="no verificado")
    result = verify_cited_value(sin_cita, DOC)
    assert result is sin_cita
