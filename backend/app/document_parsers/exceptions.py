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
    """Normalized output exceeds the configured character limit."""
