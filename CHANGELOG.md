# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-07-19

### Added

- GitHub Actions CI (pytest, ruff, skill gate) on Python 3.10–3.12
- Dependabot for pip / Actions / skill installer npm
- Issue templates, `CODE_OF_CONDUCT.md`, this `CHANGELOG.md`
- Deeper convert + API smoke tests
- `scripts/sync-agent-skills.py` to regenerate agent skill copies from one canonical skill

### Changed

- Vendor only `.agents` + `.cursor` skill copies in-repo (other agents via installer)
- Bump package metadata and README discoverability (badges, clearer status)

### Security

- Prepublish gate remains required before push/publish of skill changes
- Docs keep preferring trusted-clone / version-pinned npm skill installs

## [0.2.0] - 2026-07-19

### Added

- Installable `src/image2svg` package with CLI (`image2svg`) and server entry point
- OSS docs: LICENSE, CONTRIBUTING, SECURITY, multilingual usage, libraries map
- Portable `open-source-repo` Agent Skill + Python/npm installers
- `scripts/prepublish-check.py` gate for skill integrity

### Changed

- Moved convert / background / analyze / web into package layout
- Cloudflare worker under `deployments/cloudflare/`
- Root `convert.py` / `server.py` / `background_removal.py` become compatibility shims
