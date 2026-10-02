# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [0.1.0] - Unreleased

First public release. Template mode only: bundled corpora and format rules, with no LLM
and no network access.

### Added

- `convert(text, entities, policy="generic", seed=None) -> ConversionResult`: replaces
  every identifier entity from `ogentic-shield` with a realistic, format-preserving
  synthetic value. Covers names, emails (RFC 2606 domains), NANP phones (555-01XX),
  SSNs (area 900-999, group 01-49), dates of birth (one date shift per call), case
  numbers, Bates numbers, insurance IDs, locations, institutions and law firms.
- `restore(text, mapping) -> str`: maps synthetic values in a model reply back to the
  originals (one pass, longest first, whole words).
- `load_shield_entities(...)`: parses `ogentic-shield analyze --output json`, or a bare
  entity list, with sanitised errors.
- Pydantic v2 models: `ShieldEntity`, `ConversionResult`, `ReversalMapping`,
  `MappingEntry`, and the `Policy` enum (`legal`, `clinical`, `financial`, `generic`).
- Within-call consistency, collision-free assignment, HMAC-SHA256 determinism, a
  no-leak check, union merging of overlapping spans, and strict code-point offset
  validation.
- Classification signals (privilege markers and similar) are passed through untouched.
  Unsupported categories are left unchanged and reported in `unconverted_categories`.
- Versioned synthetic corpus (`corpus_v1.json`) shipped as package data.
- `ogentic-converter convert` / `restore` CLI. The replica goes to stdout byte for
  byte. The mapping goes to an owner-only (`0600`) file that is never overwritten.
- `--json` mode on `convert` and `restore`: one JSON request on stdin and one JSON result
  on stdout, mapping included, with no file written. It is for parent processes that
  keep the mapping in memory. Opt-in; mixing it with file-mode flags is a usage error.
- Release workflow: sdist and universal wheel, a tag/version check, and PyPI trusted
  publishing.
