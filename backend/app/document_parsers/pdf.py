"""Text-based PDF extraction without OCR."""

from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.document_parsers.base import DocumentParser
from app.document_parsers.exceptions import CorruptedDocumentError, EncryptedPdfError


class PdfDocumentParser(DocumentParser):
    mime_types = frozenset({"application/pdf"})

    def extract(self, data: bytes) -> str:
        try:
            reader = PdfReader(BytesIO(data), strict=True)
            if reader.is_encrypted:
                raise EncryptedPdfError("Encrypted PDFs are not supported")
            return "\n\n".join((page.extract_text() or "") for page in reader.pages)
        except EncryptedPdfError:
            raise
        except (PdfReadError, ValueError, TypeError, OSError):
            raise CorruptedDocumentError("PDF cannot be parsed") from None
