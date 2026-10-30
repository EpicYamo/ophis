"""Ophis - a control centre for the Razer Blade 14 (2022)."""

import subprocess
import sys
from pathlib import Path

__version__ = "0.3.2"


def build_id() -> str:
    """Short commit of the checkout, so a stale window is obvious in About."""
    if getattr(sys, "frozen", False):
        return ""
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
