"""Smoke test: verify the module can be imported and has expected structure."""

import ogentic_converter


def test_import_ogentic_converter() -> None:
    """Test that ogentic_converter module can be imported."""
    assert ogentic_converter is not None
    assert hasattr(ogentic_converter, "__version__")
    assert isinstance(ogentic_converter.__version__, str)
