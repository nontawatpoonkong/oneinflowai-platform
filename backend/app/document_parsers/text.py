"""UTF-8 text and Markdown parsers."""

from app.document_parsers.base import DocumentParser
from app.document_parsers.exceptions import CorruptedDocumentError


class TextDocumentParser(DocumentParser):
    mime_types = frozenset({"text/plain"})

    def extract(self, data: bytes) -> str:
        try:
            return data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise CorruptedDocumentError("Text is not valid UTF-8") from None


class MarkdownDocumentParser(TextDocumentParser):
    """Retain Markdown syntax while normalizing it as readable plain text."""

    mime_types = frozenset({"text/markdown", "text/x-markdown"})
