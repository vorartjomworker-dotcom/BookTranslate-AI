from app.services.document_parser import NormalizedBlock, NormalizedChapter, NormalizedDocument
from app.services.epub_export import reconstruct_epub
from app.services.epub_structured_parser import parse_epub


def test_translated_epub_round_trip_preserves_links_and_math(tmp_path) -> None:
    mathml = '<math xmlns="http://www.w3.org/1998/Math/MathML"><mi>x</mi><mo>=</mo><mn>1</mn></math>'
    source = NormalizedDocument(
        title="Translated Book",
        chapters=[
            NormalizedChapter(
                title="Translated Chapter",
                blocks=[
                    NormalizedBlock(
                        position=0,
                        block_type="paragraph",
                        source_text="Translated latency paragraph.",
                        metadata_json={
                            "hyperlinks": [{"href": "#spec", "text": "specification"}],
                            "mathml": [mathml],
                        },
                    )
                ],
            )
        ],
    )
    output = tmp_path / "translated.epub"
    reconstruct_epub(source, output, language="ru")
    assert output.exists() and output.stat().st_size > 0

    parsed = parse_epub(output)
    paragraph = next(block for block in parsed.chapters[0].blocks if block.block_type == "paragraph")
    assert "Translated latency paragraph." in (paragraph.source_text or "")
    assert paragraph.metadata_json["hyperlinks"][0]["href"] == "#spec"
    assert paragraph.metadata_json["mathml"]
