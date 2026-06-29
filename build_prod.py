"""Build the packaged Web console launcher with PyInstaller.

Thin wrapper around ``BrainAlphaOps.spec`` so the hidden-import list, data
files, and binary options live in a single source of truth. Passes
``--clean --noconfirm`` to match the previous behavior.
"""
import os
import subprocess
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))

cmd = [sys.executable, "-m", "PyInstaller", "BrainAlphaOps.spec", "--clean", "--noconfirm"]
print("Running:", " ".join(cmd))
raise SystemExit(subprocess.call(cmd))
