# Changelog

All notable changes to this project are documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning: [semver](https://semver.org/).

---

## [Unreleased]

---

## [v0.9.5] - 2026-06-09

### Changed

- Bumped all actions to Node.js 24 compatible versions (`actions/checkout@v6`, `aws-actions/configure-aws-credentials@v6`, `docker/build-push-action@v7`, `docker/setup-buildx-action@v4`, `release-drafter/release-drafter@v6`)

---

## [v0.9.4] - prior to documentation pass

### Added

- `docker-deploy.yml` — new reusable workflow: writes image tag to SSM Parameter Store and restarts a systemd service on the target EC2 instance via SSM Send-Command

---

## [v0.9.3] - prior to documentation pass

### Changed

- Bumped `security-actions/scan` pin to `v0.3.0`, which replaced the Trivy GitHub Action with a direct Trivy binary install for improved ARM64 compatibility

---

## [v0.9.2] - prior to documentation pass

### Changed

- Removed `security-events: write` and `actions: read` permissions from `docker-release.yml` — SARIF upload to the GitHub Security tab is deferred until code scanning is enabled per-repo; uploading SARIF to repos without code scanning enabled causes workflow failures

---

## [v0.9.1] - prior to documentation pass

### Fixed

- Added `actions: read` permission to `docker-release.yml` — required by `codeql-action/upload-sarif` to fetch workflow-run metadata internally

---

## [v0.9.0] - prior to documentation pass

### Added

- Wired supply-chain controls via `sbe-devops/security-actions` composite actions at `v0.1.0`
- `trivy_scan` input: opt-in Trivy vulnerability scan via `security-actions/scan`
- `sbom` input: opt-in CycloneDX SBOM generation via `security-actions/sbom`
- `sign` input: opt-in Cosign keyless image signing via `security-actions/sign`
- SBOM attestation step via `security-actions/attest` (runs when `push` and `sbom` are both true)

---

## [v0.8.2] - prior to documentation pass

### Fixed

- Overrode the container entrypoint (`--entrypoint ''`) during runtime version extraction — images using a custom `ENTRYPOINT run` script would otherwise fail the extraction `docker run`

---

## [v0.8.1] - prior to documentation pass

### Fixed

- Upgraded `codeql-action` from v3 to v4
- Guarded SARIF upload step on file existence to prevent failures when Trivy produces no output

---

## [v0.8.0] - prior to documentation pass

### Fixed

- Corrected `trivy-action` pin from `0.30.0` to `v0.36.0` (v0.30.0 returned a 404 on ARM runners)

---

## [v0.7.0] - prior to documentation pass

### Fixed

- Replaced `grep -oP` (PCRE, not available on ARM64) with `grep -oE` for version string extraction; added `|| true` guard for `pipefail` safety

### Added

- `trivy_scan` and `trivy_severity` inputs for opt-in inline Trivy scanning (pre-`security-actions` implementation; superseded in v0.9.0)

---

## [v0.6.1] - prior to documentation pass

### Added

- `version_extract_pattern` input — configurable `grep -oE` regex for extracting non-standard version strings (e.g., Java version output)

---

## [v0.6.0] - prior to documentation pass

### Added

- `version_extract_command` input — runs a command inside the built image and prefixes the extracted runtime semver to the push tag (e.g., `3.11.15-v26.5.0`)

---

## [v0.5.1] - prior to documentation pass

### Fixed

- Replaced `describe-images` verify step with `batch-get-image` in `docker-promote.yml` — supports nested ECR repo paths (e.g., `csi-foo/bar`)

---

## [v0.5.0] - prior to documentation pass

### Fixed

- Fixed ECR repo name extraction to correctly handle nested ECR repository paths (e.g., `csi-amazonlinux/amazonlinux`)

---

## [v0.4.x] - prior to documentation pass

### Fixed

- Corrected container-structure-test download URL — `v2.4.0` returns 404; pinned to `v1.22.1`

### Added

- `docker-promote.yml` — re-tags a versioned immutable image as `latest` in ECR using `ecr batch-get-image` + `put-image`
- `run_tests` and `test_config` inputs — opt-in container structure tests before push; installs `container-structure-test` at build time
- Initial build, test, and push flow with separate build-for-testing and push-to-ECR steps

---

## [v0.1.0] - prior to documentation pass

### Added

- Initial `docker-release.yml` — ARM-native (`linux/arm64`) Docker build and push to ECR via OIDC
