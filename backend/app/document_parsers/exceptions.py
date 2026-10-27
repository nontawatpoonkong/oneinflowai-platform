"""Typed, provider-neutral document extraction failures."""


class DocumentExtractionError(Exception):
    """Base safe extraction failure."""


class UnsupportedDocumentParserError(DocumentExtractionError):
    """No parser supports the trusted document MIME type."""


class CorruptedDocumentError(DocumentExtractionError):
    """The document container cannot be parsed safely."""


class EncryptedPdfError(DocumentExtractionError):
    """The PDF requires a password."""


class NoExtractableTextError(DocumentExtractionError):
    """The document contains no usable text."""


class ExtractionLimitExceededError(DocumentExtractionError):
    """Extracted output exceeds the configured character limit."""


class PageLimitExceededError(DocumentExtractionError):
    """The PDF declares more pages than the configured maximum."""


class ArchiveExpansionLimitError(DocumentExtractionError):
    """The DOCX archive declares more inflated content than allowed."""


class ParseTimeoutError(DocumentExtractionError):
    """Parsing ran past its deadline and the parser process was stopped."""


class ParserWorkerFailedError(DocumentExtractionError):
    """The isolated parser process exited without a usable result."""
