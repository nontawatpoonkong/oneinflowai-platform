"""Parser selection and normalized extraction output."""

from app.document_parsers.base import DocumentParser, ExtractionOutput
from app.document_parsers.docx import DocxDocumentParser
from app.document_parsers.exceptions import UnsupportedDocumentParserError
from app.document_parsers.normalization import normalize_text
from app.document_parsers.pdf import PdfDocumentParser
from app.document_parsers.text import MarkdownDocumentParser, TextDocumentParser


class DocumentParserRegistry:
    def __init__(self, parsers: tuple[DocumentParser, ...] | None = None) -> None:
        self.parsers = parsers or (
            PdfDocumentParser(),
            DocxDocumentParser(),
            MarkdownDocumentParser(),
            TextDocumentParser(),
        )

    def extract(
        self, *, mime_type: str, data: bytes, maximum_characters: int
    ) -> ExtractionOutput:
        parser = next(
            (candidate for candidate in self.parsers if candidate.supports(mime_type)),
            None,
        )
        if parser is None:
            raise UnsupportedDocumentParserError("Unsupported document type")
        text = normalize_text(
            parser.extract(data), maximum_characters=maximum_characters
        )
        return ExtractionOutput(
            text=text,
            character_count=len(text),
            word_count=len(text.split()),
            method=parser.__class__.__name__,
        )
