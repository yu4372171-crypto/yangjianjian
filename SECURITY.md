# Security Policy

## Supported versions

Security fixes are applied to the latest public release and the current `main` branch.

## Reporting a vulnerability

Please report vulnerabilities privately to the repository maintainers. Do not open a public issue containing:

- customer videos, project databases or personal information;
- account passwords, access tokens, refresh tokens or API keys;
- update signing private keys;
- logs that contain local paths, user names or service credentials;
- a working exploit against a deployed instance.

Include the affected version, a minimal reproduction that uses synthetic data, and the security impact. Maintainers should acknowledge a report within seven days.

## Credential handling

- Public source must never contain fixed production passwords or API keys.
- Local administrator credentials must be supplied through environment variables.
  `scripts/hash-password.py` creates a PBKDF2-SHA256 value for
  `YJJ_ADMIN_PASSWORD_HASH`; plaintext development passwords are supported only
  for local debugging.
- Third-party API secrets should be encrypted with Windows DPAPI for the current user.
- Update signing private keys and release credentials must remain in a controlled release environment.
- Diagnostics and support bundles must redact local paths, tokens, cookies and authorization headers.

## Local model and FFmpeg downloads

Download definitions should use HTTPS allowlists, file-size limits and SHA-256 checks. Never execute an unverified model, media file or updater package.
