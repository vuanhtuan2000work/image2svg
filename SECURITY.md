# Security Policy

## Supported versions

Security fixes are applied on the latest `master` branch.

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security-sensitive reports.

Instead, contact the repository maintainers privately (GitHub Security Advisories preferred) and include:

- Description of the issue
- Steps to reproduce
- Potential impact
- Any suggested fix

## Local service notes

The FastAPI UI binds to `127.0.0.1` by default. If you expose it on a network interface:

- Treat uploaded files as untrusted input
- Do not enable download-on-demand ML/background models on shared hosts without review
- Prefer reverse-proxy auth in front of any public deployment
