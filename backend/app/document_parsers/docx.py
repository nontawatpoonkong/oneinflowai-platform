"""DOCX plain-text extraction without layout reconstruction."""

from io import BytesIO
from zipfile import BadZipFile

from docx import Document
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.document_parsers.base import DocumentParser
from app.document_parsers.exceptions import CorruptedDocumentError


class DocxDocumentParser(DocumentParser):
    mime_types = frozenset(
        {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        }
    )

    def extract(self, data: bytes) -> str:
        try:
            document = Document(BytesIO(data))
            blocks: list[str] = []
            for child in document.element.body.iterchildren():
                if isinstance(child, CT_P):
                    blocks.append(Paragraph(child, document).text)
                elif isinstance(child, CT_Tbl):
                    table = Table(child, document)
                    blocks.extend(
                        "\t".join(cell.text for cell in row.cells)
                        for row in table.rows
                    )
            return "\n".join(blocks)
        except (BadZipFile, KeyError, ValueError, TypeError, OSError):
            raise CorruptedDocumentError("DOCX cannot be parsed") from None
