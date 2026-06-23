# container-workflows

Reusable GitHub Actions workflows for SBE container image lifecycle: build / scan / SBOM / sign / attest / promote / deploy. Consumed by every CSI gold image release and every client container build that follows SBE Docker standards. All workflows run on ARM64 (`ubuntu-24.04-arm`) by default, consistent with the Graviton-first policy in `standards/docker.md`.

---

## Workflows

### `docker-release.yml` — Build, scan, test, push, sign

The primary release workflow. Builds a `linux/arm64` image, optionally runs supply-chain controls (Trivy scan, SBOM, Cosign keyless signing, SBOM attestation), optionally runs container structure tests, and pushes to ECR. All supply-chain steps are opt-in via boolean inputs (`trivy_scan`, `sbom`, `sign`).

**Supply-chain controls (opt-in today, required in Phase 2):**

| Step | Input flag | What it does |
|---|---|---|
| Trivy vulnerability scan | `trivy_scan: true` | Scans the locally built image; fails if findings at or above `trivy_severity` | 
| SBOM generation | `sbom: true` | Generates a CycloneDX SBOM via `security-actions/sbom` |
| Cosign keyless signing | `sign: true` | Signs the pushed image digest with Cosign OIDC via `security-actions/sign` |
| SBOM attestation | `sbom: true` (also requires `push: true`) | Attaches the SBOM as a Cosign attestation via `security-actions/attest` |

Per ADR-0003 and ADR-0011, these controls are currently opt-in. They will be enforced as required (`trivy_scan: true`, `sbom: true`, `sign: true`) on all CSI prod releases in Phase 2 of the SOC2 supply-chain controls implementation.

**Runtime version tagging:**

When `version_extract_command` is set, the workflow runs the command inside the built image and extracts a version string. The final pushed tag becomes `<runtime_version>-<image_tag>` (e.g., `3.11.15-v26.5.0`). The entrypoint is overridden during extraction so it works with images that use a custom `ENTRYPOINT`.

**When to use:**

Use `docker-release.yml` as the release trigger in any image repo. Trigger it on `gh release create` (a GitHub release event). Set `push: false` on PRs for build verification without pushing.

---

### `docker-promote.yml` — Promote versioned tag to `latest`

Re-tags an existing immutable image in ECR as `latest` using `ecr batch-get-image` + `put-image`. This is the only mechanism that moves `latest`. `latest` is never auto-updated on release — promotion is an explicit, separate step.

**When to use:**

After validating a release (structure tests passed, smoke-tested in a lower environment), trigger this workflow to advance the `latest` pointer. Per `standards/docker.md`, downstream images that `FROM csi-*/latest` receive the update on their next build.

---

### `docker-deploy.yml` — Deploy image tag to EC2 via SSM

Writes the image tag to an SSM Parameter Store path and restarts the systemd service on the target EC2 instance via SSM Send-Command. Finds the instance by EC2 tag key/value.

**When to use:**

Use for EC2-hosted services that use the `tf-aws-ec2-docker` deployment pattern. The instance must have SSM Agent running and the IAM role must allow `ssm:SendCommand`. After the command is sent the workflow does not wait for completion — verify service health via CloudWatch Logs or instance health checks.

---

### `release-drafter.yml` — Release notes automation

Automatically drafts release notes from merged pull request titles, grouped by PR label. Triggers on push to `main` and on PR open/sync. See `.github/release-drafter.yml` for label-to-category mapping. Do not call this workflow directly — it runs on its own triggers.

---

## Usage

Pin to a release tag in every caller. Never use `@main`.

### Build and push a container image

```yaml
name: Release

on:
  release:
    types: [published]

jobs:
  build:
    permissions:
      id-token: write
      contents: read
    uses: sbe-devops/container-workflows/.github/workflows/docker-release.yml@v0.9.8
    with:
      ecr_repository_url: "123456789012.dkr.ecr.us-east-1.amazonaws.com/my-app"
      role_arn: "arn:aws:iam::123456789012:role/github-actions-ecr-push"
      image_tag: ${{ github.event.release.tag_name }}
      run_tests: true
      trivy_scan: true
      sbom: true
      sign: true
```

### Build with cross-account base image (client repos using SBE CSI)

Client repos that build `FROM` a CSI base image hosted in the SBE account use `base_image_role_arn` to authenticate to the SBE registry before the build. The primary `role_arn` still handles push to the client's own ECR.

```yaml
jobs:
  build:
    permissions:
      id-token: write
      contents: read
    uses: sbe-devops/container-workflows/.github/workflows/docker-release.yml@v0.9.8
    with:
      ecr_repository_url: "111122223333.dkr.ecr.us-east-1.amazonaws.com/my-client-app"
      role_arn: "arn:aws:iam::111122223333:role/my-app-ecr-push"
      base_image_role_arn: "arn:aws:iam::112401921630:role/sbe-csi-reader"
      image_tag: ${{ github.event.release.tag_name }}
      trivy_scan: true
      sbom: true
```

The `sbe-csi-reader` role ARN is stored as a GitHub Actions variable `SBE_CSI_READER_ROLE_ARN` in each consumer org. The role is managed in `sbe-devops/infra` and trusts each registered consumer org via OIDC sub claim.

### Build with a private library checked out from source

When a dependency isn't published to a package index and must be installed from a private repo, use `extra_repo` to check it out into the build context before the Docker build. The checked-out directory is available to `COPY` in the Dockerfile.

```yaml
jobs:
  setup:
    runs-on: ubuntu-24.04-arm
    permissions:
      contents: read
    outputs:
      extra_repo_token: ${{ steps.token.outputs.token }}
    steps:
      - name: Generate my-lib token
        id: token
        uses: actions/create-github-app-token@v3
        with:
          client-id: ${{ vars.MY_GH_APP_CLIENT_ID }}
          private-key: ${{ secrets.MY_GH_APP_PRIVATE_KEY }}

  build:
    needs: setup
    permissions:
      id-token: write
      contents: read
    uses: sbe-devops/container-workflows/.github/workflows/docker-release.yml@v0.9.8
    with:
      ecr_repository_url: "111122223333.dkr.ecr.us-east-1.amazonaws.com/my-app"
      role_arn: "arn:aws:iam::111122223333:role/my-app-ecr-push"
      base_image_role_arn: "arn:aws:iam::112401921630:role/sbe-csi-reader"
      image_tag: ${{ github.event.release.tag_name }}
      trivy_scan: true
      extra_repo: my-org/my-lib
      extra_repo_ref: v0.1.0
      extra_repo_path: my-lib
      extra_repo_token: ${{ needs.setup.outputs.extra_repo_token }}
```

In the Dockerfile, copy the checked-out directory before installing dependencies:

```dockerfile
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
COPY requirements.txt /tmp/requirements.txt
COPY my-lib /tmp/my-lib
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt
```

In `requirements.txt`, reference the local path:

```
my-lib @ file:///tmp/my-lib
```

### Promote versioned tag to `latest`

```yaml
name: Promote

on:
  workflow_dispatch:
    inputs:
      image_tag:
        description: Tag to promote to latest
        required: true

jobs:
  promote:
    permissions:
      id-token: write
      contents: read
    uses: sbe-devops/container-workflows/.github/workflows/docker-promote.yml@v0.9.8
    with:
      ecr_repository_url: "123456789012.dkr.ecr.us-east-1.amazonaws.com/my-app"
      role_arn: "arn:aws:iam::123456789012:role/github-actions-ecr-push"
      image_tag: ${{ inputs.image_tag }}
```

### Deploy image to EC2 via SSM

```yaml
name: Deploy

on:
  workflow_dispatch:
    inputs:
      image_tag:
        description: Image tag to deploy
        required: true

jobs:
  deploy:
    permissions:
      id-token: write
      contents: read
    uses: sbe-devops/container-workflows/.github/workflows/docker-deploy.yml@v0.9.8
    with:
      role_arn: "arn:aws:iam::123456789012:role/github-actions-deploy"
      ssm_image_tag_param: "/my-project/my-service/image-tag"
      image_tag: ${{ inputs.image_tag }}
      ec2_instance_tag_key: "Project"
      ec2_instance_tag_value: "my-project"
      service_name: "my-service"
```

---

## Inputs

### `docker-release.yml`

| Input | Type | Required | Default | Description |
|---|---|:---:|---|---|
| `ecr_repository_url` | string | yes | — | Full ECR repository URL (e.g. `123456789012.dkr.ecr.us-east-1.amazonaws.com/my-image`) |
| `role_arn` | string | yes | — | IAM role ARN to assume for ECR authentication (OIDC) |
| `image_tag` | string | yes | — | Release tag (e.g. `v26.5.0`). Combined with runtime version when `version_extract_command` is set |
| `push` | boolean | no | `true` | Push image to ECR after build. Set `false` for PR build verification |
| `run_tests` | boolean | no | `false` | Run container structure tests before push |
| `test_config` | string | no | `tests/structure-test.yaml` | Path to container-structure-test config file |
| `version_extract_command` | string | no | `""` | Command to run inside the built image to extract the runtime version (e.g. `python3 --version`). When set, the pushed tag becomes `<version>-<image_tag>` |
| `version_extract_pattern` | string | no | `[0-9]+\.[0-9]+\.[0-9]+` | Regex passed to `grep -oE` to extract the version string from `version_extract_command` output |
| `trivy_scan` | boolean | no | `false` | Run Trivy vulnerability scan after build. Fails on findings at or above `trivy_severity` |
| `trivy_severity` | string | no | `HIGH,CRITICAL` | Comma-separated severity levels that fail the build |
| `sbom` | boolean | no | `false` | Generate a CycloneDX SBOM and attach it as a Cosign attestation after push |
| `sign` | boolean | no | `false` | Keyless sign the image with Cosign after push |
| `dockerfile` | string | no | `Dockerfile` | Path to the Dockerfile |
| `build_context` | string | no | `.` | Docker build context path |
| `build_args` | string | no | `""` | Build arguments, one per line (`KEY=VALUE`) |
| `aws_region` | string | no | `us-east-1` | AWS region for ECR |
| `base_image_role_arn` | string | no | `""` | Optional IAM role ARN in a second account to assume before build for cross-account base image pulls. When set, Docker is logged into that ECR registry before the primary registry auth — enabling `FROM` references to images in a different account (e.g. `sbe-csi-reader` for client repos pulling from the SBE shared registry). |
| `extra_repo` | string | no | `""` | Optional additional repo to check out into the build context before the Docker build (`owner/repo` format). Use when a dependency must be installed from source (e.g. a private library not on PyPI). See `extra_repo_ref`, `extra_repo_path`, and `extra_repo_token`. |
| `extra_repo_ref` | string | no | `""` | Ref (tag, branch, or SHA) to check out for `extra_repo`. Defaults to the repo's default branch when not set. |
| `extra_repo_path` | string | no | `"extra-repo"` | Path within the workspace to check out `extra_repo` into. Defaults to `extra-repo`. This directory is included in the Docker build context, so `COPY extra_repo_path /dest` works in the Dockerfile. |
| `extra_repo_token` | string | no | `""` | Installation token for authenticating the `extra_repo` checkout. GitHub App tokens must be generated in the caller before invoking this workflow (use `actions/create-github-app-token@v3`) and passed here via `needs.<setup-job>.outputs.token`. Not required for public repos. |

### `docker-promote.yml`

| Input | Type | Required | Default | Description |
|---|---|:---:|---|---|
| `ecr_repository_url` | string | yes | — | Full ECR repository URL |
| `role_arn` | string | yes | — | IAM role ARN to assume for ECR operations (OIDC) |
| `image_tag` | string | yes | — | Version tag to promote to `latest` (e.g. `v1.1.0`) |
| `aws_region` | string | no | `us-east-1` | AWS region for ECR |

### `docker-deploy.yml`

| Input | Type | Required | Default | Description |
|---|---|:---:|---|---|
| `role_arn` | string | yes | — | IAM role ARN to assume for deployment (OIDC) |
| `aws_region` | string | no | `us-east-1` | AWS region |
| `ssm_image_tag_param` | string | yes | — | SSM Parameter Store path to write the image tag (e.g. `/my-project/my-service/image-tag`) |
| `image_tag` | string | yes | — | Image tag to deploy (e.g. `v0.3.1`) |
| `ec2_instance_tag_key` | string | yes | — | EC2 tag key used to find the target instance (e.g. `Project`) |
| `ec2_instance_tag_value` | string | yes | — | EC2 tag value used to find the target instance (e.g. `my-project`) |
| `service_name` | string | yes | — | systemd service name to restart on the EC2 instance |

---

## Outputs

### `docker-release.yml`

| Output | Description |
|---|---|
| `image_tag` | The final image tag pushed to ECR. If `version_extract_command` was set, this is `<runtime_version>-<image_tag>` (e.g. `3.11.15-v26.5.0`). Otherwise it is the raw `image_tag` input. |

---

## Required permissions

The caller must grant all permissions that the reusable workflow's jobs declare. Reusable workflows cannot claim permissions the caller did not grant.

| Workflow | Required permissions | Notes |
|---|---|---|
| `docker-release.yml` | `id-token: write`, `contents: read` | `id-token` required for OIDC AWS credentials; also required for Cosign keyless signing when `sign: true` |
| `docker-promote.yml` | `id-token: write`, `contents: read` | `id-token` required for OIDC AWS credentials |
| `docker-deploy.yml` | `id-token: write`, `contents: read` | `id-token` required for OIDC AWS credentials and SSM commands |

No `security-events: write` is required. SARIF upload to the GitHub Security tab is deferred until code scanning is enabled per-repo (see Limitations).

---

## Compliance posture

| SOC2 Control | Criterion | How this repo addresses it |
|---|---|---|
| CC7.1 | System monitoring — detection of security events | Trivy scan (`trivy_scan: true`) detects CVEs at or above `trivy_severity` and fails the build, preventing vulnerable images from reaching ECR |
| CC7.2 | System performance monitoring and evidence retention | CycloneDX SBOM (`sbom: true`) provides a point-in-time inventory of all packages and dependencies in every released image, attached as a Cosign attestation |
| CC8.1 | Change management — tamper-evident release controls | Cosign keyless signing (`sign: true`) cryptographically binds the image digest to the OIDC identity of the GitHub Actions workflow run; SBOM attestation ties the SBOM to the same digest |
| CC6.7 | Logical and physical access controls — data at rest | ECR encryption at rest is inherited from the ECR repository configuration (managed by `tf-aws-ecr`); this workflow does not configure or override it |

Per ADR-0003, `trivy_scan`, `sbom`, and `sign` will be enforced as required on all CSI production releases in Phase 2.

---

## Versioning

This repo follows [semver](https://semver.org/): `vMAJOR.MINOR.PATCH`. Increment MAJOR on breaking input, output, or permission changes; MINOR on backward-compatible additions; PATCH on bug fixes. The repo remains at `v0.x.x` until proven stable across multiple consumers.

```yaml
uses: sbe-devops/container-workflows/.github/workflows/docker-release.yml@v0.9.8
```

Always pin to a tag — never `@main`. Releases at [sbe-devops/container-workflows/releases](https://github.com/sbe-devops/container-workflows/releases). Cutting procedure and the **fail-forward** rule (never re-release a tag) are documented in [SBE GitHub Actions standards](https://github.com/sbe-devops/standards/blob/main/github-actions.md#versioning).

**Cutting a release** — use `gh release create`, which creates both the tag and the GitHub Release in one step:

```bash
gh release create vX.Y.Z --title "vX.Y.Z" --notes "..."
```

---

## Limitations

- `docker-deploy.yml` sends the SSM command but does not wait for completion. Verify service health via CloudWatch Logs or instance health checks after the workflow finishes.
- SARIF upload to the GitHub Security tab is deferred until code scanning is enabled per-repo. The `security-events: write` permission and Trivy SARIF upload step were removed in v0.9.2 to avoid failing SARIF uploads on repos without code scanning enabled.
- Structure tests (`run_tests: true`) install `container-structure-test` from GitHub Releases at build time. If the release binary URL changes, pin `CST_VERSION` in the workflow. Current pinned version: `v1.22.1`.

---

## References

- [SBE GitHub Actions standards](https://github.com/sbe-devops/standards/blob/main/github-actions.md)
- [SBE Docker standards](https://github.com/sbe-devops/standards/blob/main/docker.md)
- [sbe-devops/security-actions](https://github.com/sbe-devops/security-actions) — composite actions for scan, SBOM, sign, attest
- [ADR-0003 — SOC2 baseline](https://github.com/sbe-devops/decisions/blob/main/0003-soc2-baseline.md)
- [Reusable workflows (GitHub docs)](https://docs.github.com/en/actions/sharing-automations/reusing-workflows)
- [Cosign keyless signing](https://docs.sigstore.dev/signing/overview/)
- [CycloneDX SBOM specification](https://cyclonedx.org/specification/overview/)
- [Trivy vulnerability scanner](https://aquasecurity.github.io/trivy/)
- [Container Structure Tests](https://github.com/GoogleContainerTools/container-structure-test)
