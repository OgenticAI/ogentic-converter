# Security Policy

## Reporting Security Vulnerabilities

If you discover a security vulnerability in ogentic-converter, please report it responsibly **without disclosing it publicly**.

### Reporting Process

1. **Email us directly** at [security@ogentic.ai](mailto:security@ogentic.ai) with:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Any suggested remediation

2. **Include:**
   - Your contact information
   - Affected version(s)
   - Date discovered

3. **Do not:**
   - Open a public GitHub issue
   - Post on public forums
   - Disclose details before we've had time to respond

### Response Timeline

We aim to:
- Acknowledge receipt within **24 hours**
- Provide an initial assessment within **72 hours**
- Publish a fix within **7-14 days** for critical issues
- Coordinate timing with your responsible disclosure expectations

## Security Best Practices for Users

### Using ogentic-converter

- **Keep dependencies updated**: Regularly run `pip install --upgrade ogentic-converter`
- **Review release notes**: Check for security advisories in each release
- **Report issues responsibly**: Follow this policy if you discover vulnerabilities
- **Use environment variables** for secrets, never hardcode credentials
- **Validate input**: Treat untrusted data with care

### Privacy and Data Handling

ogentic-converter is designed with privacy as a first principle:
- **Ephemeral by default**: Conversion outputs are not persisted unless explicitly requested
- **No telemetry**: We do not collect usage data or send data to external services
- **User control**: Callers control all persistence and data lifecycle decisions

## Security Advisories

We publish security advisories through:
- GitHub Security Advisories (linked in releases)
- `CHANGELOG.md` (marked with `[SECURITY]`)
- Release notes on PyPI

## Dependencies and Scanning

- We regularly audit dependencies for vulnerabilities
- We use SBOM (Software Bill of Materials) for transparency
- Vulnerability reports can be filed via GitHub's advisory database

## Compliance

ogentic-converter aims to support:
- OWASP secure coding practices
- NIST guidelines for data privacy
- General security hygiene (no hardcoded secrets, input validation, etc.)

## Questions?

For security-related questions (not vulnerability reports), open an issue on GitHub or email [security@ogentic.ai](mailto:security@ogentic.ai).

Thank you for helping keep ogentic-converter secure.
