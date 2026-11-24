"""Ucap entry point.  python main.py [--screenshot out.png]"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _reexec_in_venv() -> None:
    """Started with a Python outside the project venv? Re-run with the venv so dependencies are found."""
    if getattr(sys, "frozen", False):
        return
    venv = HERE / ".venv"
    py = venv / "Scripts" / ("pythonw.exe" if Path(sys.executable).name.lower() == "pythonw.exe" else "python.exe")
    if py.exists() and Path(sys.prefix).resolve() != venv.resolve():
        sys.exit(subprocess.call([str(py), str(HERE / "main.py"), *sys.argv[1:]]))


def main() -> int:
    _reexec_in_venv()
    parser = argparse.ArgumentParser(prog="ucap")
    parser.add_argument("--screenshot", metavar="FILE.png", help="draw ~120 frames, save the window as PNG, exit")
    args = parser.parse_args()

    sys.path.insert(0, str(HERE))
    from ucap.app import UcapApp, single_instance

    if args.screenshot:
        out = os.path.abspath(args.screenshot)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        return UcapApp(screenshot=out).run()
    if not single_instance():
        return 0
    return UcapApp().run()


if __name__ == "__main__":
    sys.exit(main())
