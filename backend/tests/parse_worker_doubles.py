"""Stand-ins for the isolated parser child, imported by spawned test workers.

They replace `app.document_parsers.isolation._child_main` and keep its
signature. The heartbeat double treats `mime_type` as a file path so the test
can observe from outside whether the child process is still running.
"""

import os
import time
from pathlib import Path


def heartbeat_forever(sender, mime_type, data, limits) -> None:
    marker = Path(mime_type)
    beats = 0
    while True:
        beats += 1
        marker.write_text(str(beats))
        time.sleep(0.05)


def exit_abruptly(sender, mime_type, data, limits) -> None:
    os._exit(3)
