"""Opt-in publication retains the tested single-image identity."""
from pathlib import Path
import yaml

ROOT=Path(__file__).resolve().parents[2]


def test_manual_native_arm_publication_with_scoped_identity():
    text=(ROOT/'.github/workflows/publish-lambda-image.yml').read_text()
    t=yaml.safe_load(text)
    triggers=t.get('on',t.get(True))
    assert set(triggers)=={'workflow_dispatch'}
    job=t['jobs']['publish']
    assert job['runs-on']=='ubuntu-24.04-arm'
    assert job['permissions']=={'contents':'read','id-token':'write'}
    assert job['environment']=='lambda-publication'
    assert 'AWS_ROLE_TO_ASSUME' in text and 'ECR_REPOSITORY' in text
    assert 'AWS_ACCESS_KEY_ID' not in text and 'cloudformation deploy' not in text
    build=text.index('docker buildx build')
    gate=text.index('scripts/verify_lambda.py local')
    push=text.index('docker push')
    assert build<gate<push
    assert '--provenance=false' in text and '--sbom=false' in text and '--load' in text
    assert 'verify_publication' in text
    assert 'fetch-depth: 0' in text
