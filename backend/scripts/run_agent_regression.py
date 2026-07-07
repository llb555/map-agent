"""Run the focused Agent regression and failure-drill suite."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    targets = [
        "app/tests/regression",
        "app/tests/unit/test_stream_event_contract.py",
        "app/tests/integration/test_api.py::test_chat_session_detail_supports_legacy_route_payload",
    ]
    return subprocess.call([sys.executable, "-m", "pytest", *targets], cwd=BACKEND_ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
