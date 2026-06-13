"""Fixtures y helpers compartidos por los tests."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
FAMILY_PL = EXAMPLES / "family.pl"


def _prolog_available() -> bool:
    """True si pyswip importa y `swipl` está en el PATH.

    Los tests de integración del tracer se saltean si falta cualquiera de los
    dos, para que la suite corra (parcialmente) sin SWI-Prolog instalado.
    """
    if shutil.which("swipl") is None:
        return False
    try:
        import pyswip  # noqa: F401
    except Exception:
        return False
    return True


# Marca reutilizable: salta el test si no hay un entorno Prolog usable.
requires_prolog = pytest.mark.skipif(
    not _prolog_available(),
    reason="requiere SWI-Prolog (swipl en el PATH) y pyswip",
)


@pytest.fixture
def family_pl() -> Path:
    """Ruta al programa de ejemplo `examples/family.pl`."""
    assert FAMILY_PL.exists(), f"falta el ejemplo: {FAMILY_PL}"
    return FAMILY_PL
