# ogentic-converter

Synthetic-replica conversion for the privacy-aware AI pipeline.

[`ogentic-shield`](https://github.com/OgenticAI/ogentic-shield) finds the sensitive
entities in a text. `ogentic-converter` replaces each identifier with a **realistic
synthetic value of the same kind**, so the downstream model reads natural text
instead of opaque tokens. Afterwards, `restore` puts the real values back into the
model's reply.

```
Dear R. Castellanos, your SSN 412-71-3359 is on file.     <- original (stays with you)
Dear Y. Southwell, your SSN 928-43-3243 is on file.       <- replica (goes to the model)
```

It is the alternative to [`ogentic-redact`](https://github.com/OgenticAI/ogentic-redact),
which swaps identifiers for reversible tokens like `[Person_1a2b3c4d]`. Tokens are
exact, but a prompt full of `[Ssn_…]` labels reads as suspicious, and small local
models often refuse it. A replica reads like an ordinary document.

**v0.1 is Template mode only:** bundled on-device corpora and format rules, with no
LLM and no network access.

## Install

```bash
pip install ogentic-converter
```

Python 3.11+. The only runtime dependency is Pydantic v2.

## Quickstart (Python)

```python
from ogentic_converter import convert, load_shield_entities, restore

text = "Dear R. Castellanos, your SSN 412-71-3359 is on file. Reply to jane.doe@acme-legal.com."

# The `entities` list from `ogentic-shield analyze --output json`.
# Offsets are Unicode code points (Python str indices).
entities = load_shield_entities([
    {"text": "R. Castellanos", "category": "PERSON", "category_group": "PII", "confidence": 0.85, "start": 5, "end": 19},
    {"text": "412-71-3359", "category": "SSN", "category_group": "PII", "confidence": 1.0, "start": 30, "end": 41},
    {"text": "jane.doe@acme-legal.com", "category": "EMAIL_ADDRESS", "category_group": "PII", "confidence": 1.0,
     "start": 63, "end": 86},
])

result = convert(text, entities, policy="legal", seed=42)
print(result.replica)
# Dear Y. Southwell, your SSN 928-43-3243 is on file. Reply to imani.sheringham@example.com.

# ...send result.replica to a model. Suppose it answers:
reply = "Y. Southwell should confirm SSN 928-43-3243 by writing to imani.sheringham@example.com."
print(restore(reply, result.mapping))
# R. Castellanos should confirm SSN 412-71-3359 by writing to jane.doe@acme-legal.com.
```

`convert` returns a `ConversionResult`:

| field | meaning |
|---|---|
| `replica` | the text with every converted identifier replaced |
| `mapping` | `ReversalMapping`: synthetic -> original entries. **Sensitive**: it holds the originals. Excluded from `repr()`. |
| `converted_count` | number of replaced occurrences |
| `unconverted_categories` | identifier categories left unchanged because v0.1 has no generator for them |
| `policy`, `corpus_version` | what produced the replica |

## Quickstart (CLI)

```bash
printf '%s' "Dear R. Castellanos, your SSN 412-71-3359 is on file. Reply to jane.doe@acme-legal.com." > note.txt
ogentic-shield analyze -f note.txt --output json > entities.json

ogentic-converter convert --entities entities.json --policy legal --seed 42 --mapping mapping.json < note.txt > replica.txt
cat replica.txt
# Dear Y. Southwell, your SSN 928-43-3243 is on file. Reply to imani.sheringham@example.com.

echo "Y. Southwell should confirm SSN 928-43-3243 by writing to imani.sheringham@example.com." \
  | ogentic-converter restore --mapping mapping.json
# R. Castellanos should confirm SSN 412-71-3359 by writing to jane.doe@acme-legal.com.
```

- `convert` reads the text on stdin and writes only the replica to stdout, byte for byte
  (no newline added). The mapping goes to the `--mapping` file, created with mode `0600`.
  An existing file is never overwritten.
- `restore` reads the model's reply on stdin and writes the restored text to stdout.
- Errors and warnings go to stderr with a non-zero exit code, and never quote the input.
  If any categories are left unconverted, `convert` prints a warning naming them.

### JSON mode (for embedding in another process)

A parent process that holds the mapping in memory, and never writes the originals to
disk, can use `--json` on either subcommand. Each call takes one JSON object on stdin
and returns one JSON object on stdout. No file is written.

```bash
ogentic-converter convert --json   # stdin:  {"text": str,
                                    #          "entities": <Shield analyze JSON object, or a bare entity list>,
                                    #          "policy": "legal"|"clinical"|"financial"|"generic",  (default "generic")
                                    #          "seed": int|null}                                     (default null = random)
                                    # stdout: {"replica": str, "mapping": <ReversalMapping>,
                                    #          "converted_count": int, "unconverted_categories": [str]}

ogentic-converter restore --json   # stdin:  {"text": str, "mapping": <ReversalMapping, as returned by convert>}
                                    # stdout: {"text": str}
```

> **Warning: `--json` stdout carries the original values.** The `mapping` object
> contains every original identifier. The output is meant for a parent process that
> keeps it in memory. Never redirect it to a file, a log or a terminal you record. This
> is why `--json` is opt-in, and why the file mode with its `0600` mapping file is the
> default.

- Unknown request fields are rejected.
- `--json` cannot be combined with the file-mode flags (`--entities`, `--mapping`,
  `--policy` and `--seed` on `convert`; `--mapping` on `restore`). Combining them is a
  usage error with exit code 2, so the mapping has exactly one channel.
- Entities may omit `text` and work from offsets alone. When `text` is present, it must
  match the text at those offsets.
- On any failure, stdout is empty, the exit code is non-zero, and stderr gives a
  sanitised message that never quotes the input.

## What gets replaced

| Shield category | Synthetic value |
|---|---|
| `PERSON`, `PATIENT_NAME`, `PROVIDER_NAME`, `EXECUTIVE_NAME` | Names from the bundled corpus, in the same shape: `R. Castellanos` -> `Y. Southwell`; a lone surname stays a lone surname. Honorifics, suffixes and case are kept (`Dr. … , MD`, `MARIA CASTELLANOS`). `Mr.`/`Mrs.`/`Ms.` select a matching given-name list. |
| `EMAIL_ADDRESS` | A synthetic local part at an RFC 2606 reserved domain (`example.com`, `example.org`, `example.net`) |
| `PHONE_NUMBER` | NANP numbers become `AAA-555-01XX`, the range reserved for fiction, with the original punctuation. Other numbers keep their country code and get random digits. |
| `SSN`, `US_SSN` | Area number 900-999 (never issued as an SSN) with group 01-49 (outside every ITIN range), in the original format |
| `DATE_OF_BIRTH` | The same date format, shifted by one offset per call (30-365 days, either direction), so gaps between dates are preserved |
| `CASE_NUMBER` | Digits replaced; letters and punctuation kept (`24-cv-01234` -> `15-cv-78208`) |
| `BATES_NUMBER`, `INSURANCE_ID` | Every letter and digit replaced; length, case and punctuation kept |
| `LOCATION` | Street addresses, towns and ZIP codes replaced; US states kept |
| `INSTITUTION_NAME`, `LAW_FIRM_NAME` | The distinctive part replaced, type words kept (`Harrowgate General Hospital` -> `Fairhaven General Hospital`, `Pellham & Corrigan LLP` -> `Hartwell & Sandoval LLP`) |

Labels that Shield includes in a span, such as `SSN `, `DOB: ` or `Patient`, are kept as they are.

**Not replaced (classification signals):** `PRIVILEGE_MARKER`, `COURT_FILING`,
`COUNSEL_COMMUNICATION`, `WORK_PRODUCT`, `LITIGATION_MARKER`, `DISTRIBUTION_RESTRICTION`,
`MNPI_MARKER`, `INSIDER_MARKER`, `MA_ACTIVITY`, `PSYCHOTHERAPY_NOTE_MARKER`, `SESSION_MARKER`,
`MINOR_CLIENT_MARKER`, `CLINICAL_RISK_FLAG`, `TRAUMA_INDICATOR`. These describe the document;
they identify nobody.

**Not supported in v0.1 (left unchanged, reported in `unconverted_categories`):** every
other category, for example `CREDIT_CARD`, `IBAN_CODE`, `IP_ADDRESS`, `DEAL_VALUE`,
`DIAGNOSIS`, `MEDICATION` and `US_PASSPORT`. The converter never invents a replacement
for a kind it does not understand. If `unconverted_categories` is not empty, the replica
still contains those values: redact them with `ogentic-redact`, or do not send the text.

The policy (`legal`, `clinical`, `financial`, `generic`) sets the default organisation
style when a name carries no type word (`LLP`, `Medical Center`, `Capital`, `Group`).
The policy is also mixed into the seed, so each policy produces a different replica.

## Guarantees

- **Consistent within a call.** The same original value gets the same synthetic value
  everywhere in the text, including repeats that Shield did not flag. A surname seen in a
  flagged name is also replaced where it appears alone (`Ms. Castellanos`).
- **Collision-free.** Distinct originals get distinct synthetic values. No synthetic
  value appears as a word anywhere in the input text (case-insensitive).
- **Deterministic.** The same text, entities, policy and seed always give the same replica
  and mapping, whatever the entity order, Python version or `PYTHONHASHSEED`. Draws use
  HMAC-SHA256, not `random` or `hash()`. With `seed=None`, every call draws a fresh random seed.
- **No leakage of converted values.** `convert` raises instead of returning a replica in
  which a converted original still appears.
- **Overlapping spans** from Shield are merged into their union, so no flagged character
  is left outside a replacement. A union of different kinds has every letter and digit scrambled.
- **Strict offsets.** Offsets must be Unicode code points. If an entity carries Shield's
  `text` field and it does not match the text at those offsets (for example UTF-16 or byte
  offsets), `convert` raises `ConversionError`.
- **Restore** is one pass, longest synthetic first, whole words only. Values the model
  left out are simply absent, and unrelated text is untouched.
- **Ephemeral.** Nothing is persisted. The mapping exists only in the returned object,
  or in the file you name on the CLI.

## Seeds and the mapping are secrets

- **The mapping** contains every original value. Store it apart from the replica, and
  never send it to the model.
- **The seed** acts as a key. Anyone who has the seed and the replica can test guesses:
  the date offset, for instance, is a function of the seed alone. Pass a seed when you
  need reproducibility (tests, audits); otherwise leave it `None`. Reusing one seed
  across documents also makes the same person map to the same synthetic name in all of
  them, which links those documents.

## Limits of v0.1

- Conversion is only as complete as Shield's detection. An identifier Shield missed
  (and that is not a repeat of one it found) stays in the replica.
- Given names that appear alone, without a flagged full name, are not propagated.
  Surnames are, which can over-replace an ordinary capitalised word that is also a
  flagged surname (`May`, `Rose`).
- Gender is inferred only from an honorific in the same span.
- The local part of a synthetic email is not tied to the synthetic name of the same person.
- Non-NANP phone numbers get random digits, which may form a real number.

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

ruff check src/ tests/
mypy --strict src/ogentic_converter/
pytest --cov=ogentic_converter
```

Releases: push a `vX.Y.Z` tag that matches `__version__` in
`src/ogentic_converter/__init__.py`. `.github/workflows/release.yml` builds the sdist
and the universal wheel (`py3-none-any`, with no per-platform matrix), checks that the
version matches the tag, and publishes to PyPI through trusted publishing (OIDC).

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for contribution guidelines, PR process, and code standards.

## Security

To report security vulnerabilities, see [`SECURITY.md`](SECURITY.md).

## License

Licensed under the Apache License 2.0. See [`LICENSE`](LICENSE) for details.

## Code of Conduct

This project adheres to the Contributor Covenant. See [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).
