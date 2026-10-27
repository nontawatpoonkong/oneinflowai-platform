"""Run document extraction in a child process that can be stopped.

A thread running pypdf cannot be interrupted: cancelling the awaiting task
leaves the parse consuming CPU and memory until it ends on its own. Each
isolated extraction therefore runs in its own spawned process. The parent
waits up to the deadline for a result and kills the child otherwise, so a
hostile PDF costs at most `timeout_seconds` of one CPU. On Linux the child
also caps its own address space and CPU time; Windows has no equivalent in
the standard library, so only the wall-clock deadline applies there.

The child receives the bytes and limits as arguments and never reads
settings, the database, or storage. It reports failures by exception class
name only, so no document content or parser message crosses back.
"""

import multiprocessing
from dataclasses import asdict, dataclass
from multiprocessing.connection import Connection

from app.document_parsers import exceptions as parser_exceptions
from app.document_parsers.base import ExtractionOutput
from app.document_parsers.docx import DocxDocumentParser
from app.document_parsers.exceptions import (
    DocumentExtractionError,
    ParserWorkerFailedError,
    ParseTimeoutError,
)
from app.document_parsers.pdf import PdfDocumentParser
from app.document_parsers.registry import DocumentParserRegistry
from app.document_parsers.text import MarkdownDocumentParser, TextDocumentParser

# Spawn on every platform: forking a threaded server process is unsafe.
_CONTEXT = multiprocessing.get_context("spawn")
# How long a child that already sent its result may take to exit.
_EXIT_GRACE_SECONDS = 2.0
# Raw text may shrink during normalization (whitespace, line endings), so the
# early stop allows some headroom; the exact limit is applied afterwards.
_RAW_CHARACTER_HEADROOM = 2


@dataclass(frozen=True, slots=True)
class ParseLimits:
    maximum_characters: int
    maximum_pages: int
    timeout_seconds: float
    memory_limit_bytes: int


def extract_in_subprocess(
    *, mime_type: str, data: bytes, limits: ParseLimits
) -> ExtractionOutput:
    """Blocking; call through `asyncio.to_thread`."""
    receiver, sender = _CONTEXT.Pipe(duplex=False)
    process = _CONTEXT.Process(
        target=_child_main,
        args=(sender, mime_type, data, limits),
        daemon=True,
    )
    try:
        process.start()
        # Drop the parent's copy so a child that dies reads as EOF.
        sender.close()
        if not receiver.poll(limits.timeout_seconds):
            raise ParseTimeoutError("Document parsing exceeded the time limit")
        try:
            kind, payload = receiver.recv()
        except (EOFError, OSError):
            raise ParserWorkerFailedError("Parser process exited early") from None
    finally:
        receiver.close()
        _stop(process)
    if kind == "ok":
        return ExtractionOutput(**payload)
    raise _error_class(payload)("Document extraction failed")


def _stop(process) -> None:
    if process.pid is None:
        return
    process.join(_EXIT_GRACE_SECONDS if process.is_alive() else 0)
    if process.is_alive():
        process.kill()
        process.join()
    process.close()


def _error_class(name: object) -> type[DocumentExtractionError]:
    candidate = getattr(parser_exceptions, str(name), None)
    if isinstance(candidate, type) and issubclass(candidate, DocumentExtractionError):
        return candidate
    return ParserWorkerFailedError


def _apply_resource_limits(limits: ParseLimits) -> None:
    try:
        import resource
    except ImportError:  # Windows: only the parent's deadline applies.
        return
    memory = limits.memory_limit_bytes
    resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
    cpu_seconds = int(limits.timeout_seconds) + 1
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))


def _child_main(
    sender: Connection, mime_type: str, data: bytes, limits: ParseLimits
) -> None:
    try:
        _apply_resource_limits(limits)
        registry = DocumentParserRegistry(
            (
                PdfDocumentParser(
                    maximum_pages=limits.maximum_pages,
                    character_ceiling=limits.maximum_characters
                    * _RAW_CHARACTER_HEADROOM,
                ),
                DocxDocumentParser(),
                MarkdownDocumentParser(),
                TextDocumentParser(),
            )
        )
        output = registry.extract(
            mime_type=mime_type,
            data=data,
            maximum_characters=limits.maximum_characters,
        )
        outcome: tuple[str, object] = ("ok", asdict(output))
    except DocumentExtractionError as exc:
        outcome = ("error", type(exc).__name__)
    except Exception:  # noqa: BLE001 - MemoryError, parser bugs: report only
        outcome = ("error", ParserWorkerFailedError.__name__)
    try:
        sender.send(outcome)
    finally:
        sender.close()
