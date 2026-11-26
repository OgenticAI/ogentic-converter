"""ogentic-converter: Synthetic-replica conversion primitive for the privacy-aware AI pipeline."""

__version__ = "0.1.0"

from .core import convert, load_shield_entities, restore  # noqa: E402
from .errors import ConversionError  # noqa: E402
from .models import ConversionResult, MappingEntry, Policy, ReversalMapping, ShieldEntity  # noqa: E402

__all__ = [
    "ConversionError",
    "ConversionResult",
    "MappingEntry",
    "Policy",
    "ReversalMapping",
    "ShieldEntity",
    "__version__",
    "convert",
    "load_shield_entities",
    "restore",
]
