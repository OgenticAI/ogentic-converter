# Contributing to ogentic-converter

Thank you for your interest in contributing! This document outlines the process for contributing code, documentation, and other improvements.

## Code of Conduct

This project adheres to the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to uphold this code.

## Development Setup

### Prerequisites

- Python 3.11 or later
- Git
- pip or uv

### Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/ogentic-converter.git
   cd ogentic-converter
   ```
3. **Create a virtual environment**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```
4. **Install with development dependencies**:
   ```bash
   pip install -e ".[dev]"
   ```

## Branch Naming and Commits

- **Branch names**: Use Linear ticket IDs in branch names: `david/oge-XXXX-description`
- **Commit messages**: Reference Linear issues: `feat(OGE-XXXX): description`
- **Commits**: Make focused, logical commits; use conventional commit prefixes:
  - `feat`: New feature
  - `fix`: Bug fix
  - `refactor`: Code refactoring without behavior change
  - `docs`: Documentation only
  - `test`: Test additions or changes
  - `chore`: Build, dependencies, or tooling

## Pull Request Process

1. **Create a branch** from `main` using Linear ticket ID
2. **Make your changes** following the code standards below
3. **Write or update tests** for new functionality
4. **Run quality checks** (see below)
5. **Push to your fork** and create a Pull Request
6. **Describe your changes** in the PR with reference to the Linear issue
7. **Respond to code review** feedback
8. **Squash and merge** once approved (one commit per feature)

## Code Standards

### Typing

- **All code must be fully type-hinted** using Python 3.11+ syntax
- Use `from typing import` for runtime generics (avoid `typing.List`, prefer `list`, etc. where possible)
- Complex types should be validated with mypy --strict

### Style

- **Line length**: 120 characters (enforced by ruff)
- **Formatter**: ruff format (run: `ruff format src/ tests/`)
- **Linter**: ruff check (run: `ruff check src/ tests/`)
- **Type checker**: mypy with strict mode (run: `mypy src/ogentic_converter/`)

### Testing

- **Coverage**: Aim for 80%+ coverage on new code
- **Async code**: Use `pytest-asyncio` with `asyncio_mode = "auto"`
- **Acceptance tests**: Include at least one failure path per feature (per CLAUDE.md)

Example test:

```python
import pytest
from ogentic_converter import some_function


def test_some_function_success() -> None:
    """Test the happy path."""
    result = some_function(input_data)
    assert result is not None


@pytest.mark.asyncio
async def test_some_function_async() -> None:
    """Test async behavior."""
    result = await some_async_function(input_data)
    assert result == expected


def test_some_function_error_handling() -> None:
    """Test error handling (failure path)."""
    with pytest.raises(ValueError):
        some_function(bad_input)
```

### Documentation

- **Docstrings**: All public functions and classes must have docstrings
- **Format**: Google-style docstrings
- **Examples**: Include usage examples for public APIs

Example:

```python
def process_data(source: str, seed: int) -> str:
    """
    Convert source data to a synthetic replica.

    Privacy-preserving by default: the replica is ephemeral unless
    explicitly persisted by the caller.

    Args:
        source: The source data to convert.
        seed: Random seed for deterministic output.

    Returns:
        The synthetic replica as a string.

    Raises:
        ValueError: If source is empty or seed is negative.
    """
```

## Running Checks Locally

Before pushing, run all quality checks:

```bash
# Lint
ruff check src/ tests/

# Format (if needed)
ruff format src/ tests/

# Type check
mypy src/ogentic_converter/

# Tests
pytest tests/ -v --cov=ogentic_converter
```

Or use a single command:

```bash
make check  # If Makefile exists
```

## CI/CD

All commits to `main` and all pull requests run:
- **ruff lint and format check**
- **mypy strict type checking**
- **pytest with coverage**

Your PR must pass all checks before merging.

## Privacy and Security

- **Never commit secrets**: API keys, credentials, or PII belong in `.env` files (which are gitignored)
- **Log responsibly**: Follow CLAUDE.md §5 — no raw payment payloads, PII, or full request bodies
- **Report security issues**: See [SECURITY.md](SECURITY.md)

## Questions?

- Check the [README](README.md) for setup and quick start
- See [docs/architecture.md](docs/architecture.md) for system design
- Open a GitHub issue to discuss larger changes before starting work

Thank you for contributing!
