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


V2_SCHEMA_PATH = ROOT / 'specs/001-add-lambda-deployment/contracts/verification-report-v2.schema.json'


def v2_schema():
    return json.loads(V2_SCHEMA_PATH.read_text())


def test_legacy_v1_schema_is_byte_unchanged():
    # rest-migration.md: report v1 keeps describing the legacy HTTP API evidence.
    import hashlib
    digest = hashlib.sha256((ROOT / 'specs/001-add-lambda-deployment/contracts/verification-report.schema.json').read_bytes()).hexdigest()
    assert digest == 'd93c1285e380fee4d1325c5a17a38c70920800780b08b26f2ff9f594852736dc'


def test_v2_schema_is_valid_and_pins_rest_profile():
    schema = v2_schema()
    Draft202012Validator.check_schema(schema)
    assert schema['properties']['schema_version']['const'] == 2
    assert schema['properties']['profile']['const'] == 'rest'
    assert 'profile' in schema['required']


def test_v2_gateway_is_named_stage_rest_v1_with_29_second_integration():
    gateway = v2_schema()['$defs']['gateway']
    assert gateway['properties']['stage_name'].get('const') is None
    assert gateway['properties']['stage_name']['not'] == {'const': '$default'}
    assert gateway['properties']['integration_type']['const'] == 'AWS_PROXY'
    assert gateway['properties']['payload_format_version']['const'] == '1.0'
    assert gateway['properties']['integration_timeout_ms']['const'] == 29000
    assert 'payload_format_version' in gateway['required']


def test_v2_report_accepts_rest_profile_and_rejects_legacy_shape():
    v = verifier()
    report = v.new_report('local', profile='rest')
    Draft202012Validator(v2_schema(), format_checker=FormatChecker()).validate(report)
    assert report['schema_version'] == 2 and report['profile'] == 'rest'
    assert len(report['stages']) == 16
    with pytest.raises(Exception):
        Draft202012Validator(v2_schema(), format_checker=FormatChecker()).validate(v.new_report('local'))


def test_profiles_cannot_cross_as_evidence():
    v = verifier()
    rest = v.new_report('local', profile='rest')
    http = v.new_report('local')
    v.require_profile(rest, 'rest')
    v.require_profile(http, 'http')
    with pytest.raises(v.ConfigurationError):
        v.require_profile(rest, 'http')
    with pytest.raises(v.ConfigurationError):
        v.require_profile(http, 'rest')


def test_validate_selects_schema_by_report_version():
    v = verifier()
    v.validate(v.new_report('local'))
    v.validate(v.new_report('local', profile='rest'))
    bad = v.new_report('local', profile='rest')
    bad['profile'] = 'http'
    with pytest.raises(Exception):
        v.validate(bad)
