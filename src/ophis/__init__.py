"""Ophis - a control centre for the Razer Blade 14 (2022)."""

import subprocess
from pathlib import Path

__version__ = "0.2.0"


def build_id() -> str:
    """Short commit of the checkout, so a stale window is obvious in About."""
    try:
        return subprocess.check_output(
            ["git", "-C", str(Path(__file__).resolve().parent.parent.parent),
             "rev-parse", "--short", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=1,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return ""
