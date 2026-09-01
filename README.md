# ogentic-converter

Synthetic-replica conversion primitive for the privacy-aware AI pipeline.

## Overview

`ogentic-converter` is a Python library that implements the conversion step in the privacy-aware AI pipeline. It transforms source data into synthetic replicas that preserve statistical properties while removing sensitive information.

**Key properties:**
- **Privacy-preserving by default**: Conversion never persists source content or replicas beyond the call boundary unless explicitly opted in
- **Deterministic**: Same input + same seed + same policy = same replica
- **Type-safe**: Full Python 3.11+ type hints with strict mypy validation
- **Async-ready**: Built for modern Python async patterns

## Installation

```bash
pip install ogentic-converter
```

For development:

```bash
pip install -e ".[dev]"
```

## Quick Start

```python
import ogentic_converter

# Conversion API to be documented here
```

## Development

### Prerequisites

- Python 3.11 or later
- pip and venv (or uv)

### Setup

```bash
# Clone the repo
git clone https://github.com/OgenticAI/ogentic-converter.git
cd ogentic-converter

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install in development mode with dev dependencies
pip install -e ".[dev]"
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=ogentic_converter

# Run specific test file
pytest tests/test_smoke.py -v
```

### Linting and Type Checking

```bash
# Lint with ruff
ruff check src/ tests/

# Type check with mypy
mypy src/ogentic_converter/
```

### Code Quality

All code must pass:
- **ruff**: Python linting and formatting
- **mypy**: Strict static type checking
- **pytest**: Unit and integration tests

## Architecture

For architectural details and system design, see [`docs/architecture.md`](docs/architecture.md).

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for contribution guidelines, PR process, and code standards.

## Security

To report security vulnerabilities, see [`SECURITY.md`](SECURITY.md).

## License

Licensed under the Apache License 2.0. See [`LICENSE`](LICENSE) for details.

## Code of Conduct

This project adheres to the Contributor Covenant. See [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).
