"""Movement traces: one JSON record per controller input or walk, from the lab
app's log and Command File Runner results. Format: docs/TRACES.md."""

from .extract import extract, read_jsonl, write_jsonl  # noqa: F401
from .summary import summarize  # noqa: F401
