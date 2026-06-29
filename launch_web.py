"""Editor-friendly local web console launcher."""

from __future__ import annotations

import sys

from brain_alpha_ops.secure_credentials import install_log_redaction
from brain_alpha_ops.web import main


if __name__ == "__main__":
    install_log_redaction()
    raise SystemExit(main(sys.argv[1:]))
