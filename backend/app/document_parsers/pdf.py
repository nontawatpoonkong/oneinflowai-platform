"""Text-based PDF extraction without OCR."""

from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.document_parsers.base import DocumentParser
from app.document_parsers.exceptions import (
    CorruptedDocumentError,
    EncryptedPdfError,
    ExtractionLimitExceededError,
    PageLimitExceededError,
)

_PAGE_SEPARATOR = "\n\n"


class PdfDocumentParser(DocumentParser):
    mime_types = frozenset({"application/pdf"})

    def __init__(
        self,
        *,
        maximum_pages: int | None = None,
        character_ceiling: int | None = None,
    ) -> None:
        # Both limits stop work early: the page count is checked before any
        # text is extracted, and extraction stops as soon as the raw text
        # passes the ceiling instead of after every page has been read.
        self.maximum_pages = maximum_pages
        self.character_ceiling = character_ceiling

    def extract(self, data: bytes) -> str:
        try:
            reader = PdfReader(BytesIO(data), strict=True)
            if reader.is_encrypted:
                raise EncryptedPdfError("Encrypted PDFs are not supported")
            pages = reader.pages
            if self.maximum_pages is not None and len(pages) > self.maximum_pages:
                raise PageLimitExceededError("PDF has too many pages")
            texts: list[str] = []
            characters = 0
            for page in pages:
                text = page.extract_text() or ""
                characters += len(text) + len(_PAGE_SEPARATOR)
                if (
                    self.character_ceiling is not None
                    and characters > self.character_ceiling
                ):
                    raise ExtractionLimitExceededError("Extracted text is too long")
                texts.append(text)
            return _PAGE_SEPARATOR.join(texts)
        except (
            EncryptedPdfError,
            PageLimitExceededError,
            ExtractionLimitExceededError,
        ):
            raise
        except (PdfReadError, ValueError, TypeError, OSError):
            raise CorruptedDocumentError("PDF cannot be parsed") from None
