# Deploy TradingView MCP on AWS Lambda

This guide deploys the existing **HTTP API v2** profile: an ARM64 container behind a
protected gateway, using a stable `live` alias. The planned REST/usage-plan profile
requires a separate [migration](../specs/001-add-lambda-deployment/contracts/rest-migration.md).
Authentication and billing belong to the separate
[auth/subscription project](../../mcp-auth-subscriptions/README.md).

## 1. Prerequisites

- Python 3.11, uv 0.13.1, AWS CLI v2, and native Linux ARM64 Docker execution.
- A clean, committed checkout with the pinned baseline revision available.
- A same-account/region HTTP API with its execute-api endpoint enabled, auto-deploy
  `$default` stage, and REQUEST authorizer using `Authorization`, caching disabled,
  and valid invocation permissions. Reserve `/mcp`, `/mcp/`, and `/health`.
- Scoped deployment permissions and an externally issued eligible client token for
  live verification. The runtime creates neither the API nor authentication resources.

Run commands from the repository root; replace example region/names as needed.

```sh
uv sync --python 3.11 --dev --group deployment --locked
uv run --locked --group deployment cfn-lint infra/lambda/ecr.yaml infra/lambda/runtime.yaml
export AWS_REGION=ca-central-1
export REPOSITORY_NAME=tradingview-mcp-lambda
export RUNTIME_STACK=tradingview-mcp-lambda-test
export EVIDENCE_DIR=/tmp/tradingview-lambda-evidence
mkdir -p "$EVIDENCE_DIR"
```

## 2. Build, verify, and publish

For a local build:

```sh
(
set -eu
SOURCE_COMMIT=$(git rev-parse HEAD)
LOCK_SHA256=$(shasum -a 256 uv.lock | cut -d' ' -f1)
test -z "$(git status --porcelain)"
docker buildx build --platform linux/arm64 --provenance=false --sbom=false --load \
  -f Dockerfile.lambda --build-arg "SOURCE_COMMIT=$SOURCE_COMMIT" \
  --build-arg SOURCE_DIRTY=false --build-arg "LOCK_SHA256=$LOCK_SHA256" \
  -t tradingview-mcp-lambda:test .
BASELINE_REF=$(uv run --locked python -c "import json; print(json.load(open('tests/integration/support/baseline.json'))['baseline_ref'])")
BASELINE_CONTEXT=$(mktemp -d)
trap 'rm -rf "$BASELINE_CONTEXT"' EXIT HUP INT TERM
git archive "$BASELINE_REF" | tar -x -C "$BASELINE_CONTEXT"
docker build --platform linux/arm64 --label "org.opencontainers.image.revision=$BASELINE_REF" \
  -t tradingview-mcp-baseline:test "$BASELINE_CONTEXT"
rm -rf "$BASELINE_CONTEXT"
uv run --locked --group deployment python scripts/verify_lambda.py local \
  --baseline-image tradingview-mcp-baseline:test --lambda-image tradingview-mcp-lambda:test \
  --report "$EVIDENCE_DIR/local.json"
)
```

Local verification normally exits **2** because cloud stages remain `not_run`;
all required local stages must pass. Emulated timing is not native acceptance.

Bootstrap the retained ECR repository once:

```sh
aws cloudformation deploy --region "$AWS_REGION" --stack-name tradingview-mcp-lambda-ecr \
  --template-file infra/lambda/ecr.yaml --parameter-overrides "RepositoryName=$REPOSITORY_NAME"
```

Run [Publish Lambda image](../.github/workflows/publish-lambda-image.yml) on `main`.
Configure the protected `lambda-publication` environment with `AWS_REGION`,
`ECR_REPOSITORY`, and `AWS_ROLE_TO_ASSUME`. The OIDC role must trust the exact
repository/environment and have repository-scoped ECR publication permissions;
[IAM details](../specs/001-add-lambda-deployment/contracts/deployment.md#optional-publishing-workflow).
The workflow builds/tests/pushes the same image and does not deploy Lambda.

Download that run's `local.json` and `publication.json` into `$EVIDENCE_DIR`;
use its published `image_uri`, `source_commit`, and `dependency_lock_sha256` below.
Deploy by immutable digest (`repository@sha256:...`), never a tag.

## 3. Configure and deploy

Create a private mode-0600 parameter file outside the checkout/build/evidence:

```sh
umask 077
export PRIVATE_PARAMETERS=$(mktemp /tmp/tradingview-mcp-params.XXXXXX)
```

Populate it with an editor; replace placeholders with the release and gateway values:

```json
[
  {"ParameterKey":"ImageUri","ParameterValue":"PUBLISHED_DIGEST_URI"},
  {"ParameterKey":"DeploymentRevision","ParameterValue":"UNIQUE_REVISION"},
  {"ParameterKey":"SourceCommit","ParameterValue":"PUBLISHED_SOURCE_COMMIT"},
  {"ParameterKey":"LockSha256","ParameterValue":"PUBLISHED_LOCK_SHA256"},
  {"ParameterKey":"ApiId","ParameterValue":"HTTP_API_ID"},
  {"ParameterKey":"AuthorizerId","ParameterValue":"REQUEST_AUTHORIZER_ID"},
  {"ParameterKey":"RollbackVersion","ParameterValue":""}
]
```

Optional provider credentials are `MarketauxApiToken`, `ProxyUsernamePrefix`, and
`ProxyPassword`; add them only to the private file. All nine provider settings and
defaults are in the [configuration matrix](../specs/001-add-lambda-deployment/data-model.md#existing-application-environment-mapping).
Values become native Lambda environment variables; no `.env` file or startup fetch.
Omitted update parameters retain their values; explicit empty strings clear them.
Preserve unchanged settings and adapter keys. Never log credentials or put them in
commands/build arguments; `NoEcho` does not hide Lambda configuration reads.

Defaults: 1024 MiB memory, 512 MiB temporary storage, concurrency 5, 14-day logs,
25-second Lambda timeout. Stack names match `[A-Za-z][A-Za-z0-9-]{0,47}`.

```sh
(
set -eu
trap 'rm -f "$PRIVATE_PARAMETERS"' EXIT HUP INT TERM
uv run --locked --group deployment python scripts/verify_lambda.py preflight \
  --region "$AWS_REGION" --stack "$RUNTIME_STACK" --parameters-file "$PRIVATE_PARAMETERS"
aws cloudformation deploy --region "$AWS_REGION" --stack-name "$RUNTIME_STACK" \
  --template-file infra/lambda/runtime.yaml --capabilities CAPABILITY_IAM \
  --parameter-overrides "file://$PRIVATE_PARAMETERS"
aws cloudformation describe-stacks --region "$AWS_REGION" --stack-name "$RUNTIME_STACK" \
  --query 'Stacks[0].Outputs'
)
```

Preflight rejects incompatible APIs, conflicting routes, invalid images/settings,
and insufficient concurrency. Connect the MCP client to `McpEndpoint` with its
protected Authorization credential. Transport is finite JSON POST; public `/health`
also requires authorization. Browser/Origin requests and streaming are unsupported.

## 4. Verify

Set `IMAGE_URI` from `publication.json`; securely load `TRADINGVIEW_MCP_TOKEN` into
the local environment. Provide read access to runtime logs and gateway JSON logs
containing `requestId`, `status`, `integrationStatus`, and `integrationRequestId`.
Do not log headers, tokens, claims, or bodies.

```sh
uv run --locked --group deployment python scripts/verify_lambda.py live \
  --region "$AWS_REGION" --stack "$RUNTIME_STACK" --expected-image-uri "$IMAGE_URI" \
  --report "$EVIDENCE_DIR/live.json"
```

Acceptance requires complete MCP interactions, concurrent clients, pre-invocation
authorization denials, and two fresh environments correlated to successful requests.
Health alone is insufficient. Record actual deploy/update/rollback/cleanup evidence
using the [lifecycle contract](../specs/001-add-lambda-deployment/contracts/deployment.md#verification-cli-scriptsverify_lambdapy)
and [report schema](../specs/001-add-lambda-deployment/contracts/verification-report.schema.json).
Collect matching runtime evidence before cleanup; unperformed checks stay `not_run`.
After completing the lifecycle steps below, combine the evidence:

```sh
uv run --locked --group deployment python scripts/verify_lambda.py combine \
  --local-report "$EVIDENCE_DIR/local.json" --live-report "$EVIDENCE_DIR/live.json" \
  --lifecycle-evidence "$EVIDENCE_DIR/lifecycle.json" --report "$EVIDENCE_DIR/final.json"
```

Exit codes: **0** full success; **1** failed acceptance; **2** incomplete;
**3** invalid configuration/evidence. Only `combine` establishes full deployment success.

## 5. Update, rollback, and cleanup

- **Update:** record the active version/digest; deploy a tested digest and fresh
  `DeploymentRevision`, explicitly clearing `RollbackVersion`; preflight and verify.
- **Configuration/credential change:** keep the image, use a fresh revision, preserve
  other settings, clear rollback, and verify. Recreate the private input file each time.
- **Rollback:** set `RollbackVersion` to a retained version of this function, preserve
  other parameters/revision, and deploy through CloudFormation. Verify `ActiveVersion`
  and digest. Old environment credentials may need replacement in a forward update.
- **Cleanup:** after collecting evidence, delete only the named disposable runtime:

```sh
aws cloudformation delete-stack --region "$AWS_REGION" --stack-name "$RUNTIME_STACK"
aws cloudformation wait stack-delete-complete --region "$AWS_REGION" --stack-name "$RUNTIME_STACK"
```

Verify its attachments are removed while the supplied API/authorizer/Cognito and
unrelated routes remain. ECR/rollback images are retained; purging them is separate.
For 401/403 check credentials; for 500 check the authorizer; for 502/504 check
integration/alias permissions, timeouts, and buffered payload size.

## AWS-native MCP logging and tracing

Application monitoring adds no dependency. CloudWatch receives stdlib JSON startup/request/tool failure logs with durations, safe stack locations, opaque correlation IDs and available AWS trace identifiers; no arguments/results, authorization/cookies or raw exception/provider values. Successful polling emits no routine application logs. Search by service=tradingview-mcp and the response's x-correlation-id within a bounded incident window. Legacy raw prints and SDK/Uvicorn logging are suppressed only in Lambda.

Set TracingMode=Active to enable AWS-native Lambda X-Ray (default PassThrough), ObservabilityEnvironment=development|test|production and finite LogRetentionDays (legacy default 14; choose 3 in development). The template grants conditional native trace-write permissions and scoped log writes. No collector, tracing SDK, app sampler, exporter, custom segment or extra monitoring service is used.

Native X-Ray provides supported service/invocation-level tracing, not custom tool/provider spans. Use sanitized CloudWatch failure timings for application detail and native Lambda error/duration/throttling metrics. AWS controls Lambda sampling; spec 002 owns the future REST-stage 1% rule. The legacy HTTP API has no REST-stage X-Ray integration. Real ingestion, native graph/header linkage, sampling and ARM64 execution remain T058 acceptance; no monitoring deployment is implied. See the [contract](../specs/001-add-lambda-deployment/contracts/observability.md).
