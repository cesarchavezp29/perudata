"""
perudata — Peru's official INEI microdata, one import away.

    from perudata import enaho, endes, epen, eea, panel, validate

    df = enaho.load(2024, "34")        # ENAHO sumaria: income, spending, poverty
    validate.poverty(years=[2024])     # reproduces INEI's official 27.6%

Five surveys, one consistent API (download / load / catalog), every file
verified on download by opening it, and a validation gate that reproduces the
official poverty series to 0.0pp before you build anything on top.

Data lands in ./peru_raw by default — override per call with out= or globally
with the PERUDATA_DIR environment variable.
"""
from . import dictionary, eea, enaho, endes, epen, harmonize, panel, validate  # noqa: F401
from ._core import (  # noqa: F401
    CorruptMember,
    NotPublished,
    PerudataError,
    ServerRefused,
)
from .dataset import dataset  # noqa: F401

__version__ = "0.1.2"
__all__ = ["dataset", "dictionary", "enaho", "endes", "epen", "eea", "panel", "validate",
           "harmonize",
           "PerudataError", "NotPublished", "ServerRefused", "CorruptMember"]
