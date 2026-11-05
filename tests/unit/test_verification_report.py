"""Report contract validation, independent of optional AWS tooling."""
import copy
import importlib.util
import json
from pathlib import Path
import pytest
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / 'specs/001-add-lambda-deployment/contracts/verification-report.schema.json').read_text())


def verifier():
    spec = importlib.util.spec_from_file_location('verify_lambda', ROOT / 'scripts/verify_lambda.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_schema_contract():
    Draft202012Validator.check_schema(SCHEMA)


def test_empty_report_is_incomplete_and_schema_valid():
    v = verifier()
    report = v.new_report('local')
    Draft202012Validator(SCHEMA, format_checker=FormatChecker()).validate(report)
    assert len(report['stages']) == 16
    assert v.exit_code(report) == 2
    assert report['authorization_evidence'] is None


@pytest.mark.parametrize('mutation', ['duplicate', 'missing', 'false_success', 'bad_gateway', 'bad_status'])
def test_malformed_reports_rejected(mutation):
    report = verifier().new_report('local')
    if mutation == 'duplicate': report['stages'][-1] = copy.deepcopy(report['stages'][0])
    if mutation == 'missing': report['stages'].pop()
    if mutation == 'false_success': report['full_deployment_success'] = True
    if mutation == 'bad_gateway': report['target']['gateway'] = {'route_ids': ['one']}
    if mutation == 'bad_status': report['stages'][0]['status'] = 'ok'
    assert list(Draft202012Validator(SCHEMA).iter_errors(report))
