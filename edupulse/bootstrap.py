"""Ensure the repo root is on sys.path so `import edupulse` works when scripts
are run as files (python hardware/capture/foo.py) without an editable install.

Prefer:  pip install -e .
"""
from __future__ import annotations

import sys
from pathlib import Path

_DONE = False


def ensure_package_importable() -> Path:
    """Add the directory that contains the `edupulse` package to sys.path once.

    Returns that directory (repo root when layout is standard).
    """
    global _DONE
    # Already importable?
    try:
        import edupulse  # noqa: F401

        root = Path(edupulse.__file__).resolve().parent.parent
        _DONE = True
        return root
    except ImportError:
        pass

    here = Path(__file__).resolve()
    # edupulse/bootstrap.py -> package dir -> repo root
    candidates = [
        here.parent.parent,  # repo root
        Path.cwd(),
        *list(Path.cwd().parents)[:4],
    ]
    for root in candidates:
        if (root / "edupulse" / "__init__.py").is_file():
            s = str(root)
            if s not in sys.path:
                sys.path.insert(0, s)
            _DONE = True
            return root

    raise ImportError(
        "Cannot locate edupulse package. Run from the EduPulse repo root "
        "or: pip install -e ."
    )
