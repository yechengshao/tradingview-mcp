"""Frozen pre-feature workflow identity, not candidate-derived expectations."""
import hashlib
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).parent/'support'))
from provider_fixture import ROOT,baseline


def test_existing_publishing_and_unit_workflows_preserved():
    for path in ['.github/workflows/publish-image.yml','.github/workflows/test.yml']:
        assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==baseline()['file_sha256'][path]
    assert (ROOT/'.github/workflows/publish-image.yml').read_text()==baseline()['publishing']['workflow']
