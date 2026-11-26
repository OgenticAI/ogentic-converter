"""Domain exceptions.

Messages never contain source text, entity text or synthetic values, so they are
safe to log or print to stderr.
"""


class ConversionError(ValueError):
    """The input cannot be converted safely (bad offsets, exhausted corpus, ...)."""
