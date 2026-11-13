"""Packaged-adapter checks through the Lambda Runtime Interface Emulator (spec 001 T051).

Requires Docker, a native ARM64 host, LAMBDA_TEST_IMAGE and RIE_BINARY (an arm64
aws-lambda-rie executable). Missing prerequisites skip locally and fail when
REQUIRE_LAMBDA_CONTAINER_TESTS=1 (CI).
"""
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

import pytest

FIXTURES = Path(__file__).parent / 'fixtures' / 'rest_v1'
INVOKE = '/2015-03-31/functions/function/invocations'
PUBLIC_HOST = 'example123.execute-api.ca-central-1.amazonaws.com'


def docker(*args):
    return subprocess.run(['docker', *args], text=True, capture_output=True, timeout=120)


@pytest.fixture(scope='module')
def emulator():
    image = os.environ.get('LAMBDA_TEST_IMAGE')
    binary = os.environ.get('RIE_BINARY')
    reason = None
    if docker('info', '--format', '{{.Architecture}}').returncode:
        reason = 'Docker daemon unavailable'
    elif not image:
        reason = 'LAMBDA_TEST_IMAGE is required'
    elif not binary or not Path(binary).is_file():
        reason = 'RIE_BINARY (arm64 aws-lambda-rie) is required'
    if reason:
        if os.environ.get('REQUIRE_LAMBDA_CONTAINER_TESTS') == '1':
            pytest.fail(reason)
        pytest.skip(reason)
    name = 'rie-test-' + uuid.uuid4().hex[:12]
    run = docker('run', '-d', '--name', name, '-p', '127.0.0.1::8080',
                 '-v', f'{Path(binary).resolve()}:/aws-lambda-rie:ro',
                 '--entrypoint', '/aws-lambda-rie',
                 '--read-only', '--tmpfs', '/tmp:rw,nosuid,size=128m',
                 '-e', f'TRADINGVIEW_MCP_PUBLIC_HOST={PUBLIC_HOST}',
                 image, '/app/.venv/bin/python', '-m', 'tradingview_mcp.lambda_server')
    assert run.returncode == 0, run.stderr
    try:
        import httpx
        url = 'http://' + docker('port', name, '8080/tcp').stdout.strip() + INVOKE
        ready = False
        for _ in range(150):
            try:
                if httpx.post(url, json=load('get_health.json'), timeout=5).status_code == 200:
                    ready = True
                    break
            except httpx.HTTPError:
                pass
            time.sleep(.2)
        if not ready:
            logs = docker('logs', name)
            pytest.fail('emulator never answered: ' + (logs.stdout + logs.stderr)[-2000:])
        yield url
    finally:
        docker('rm', '-f', name)


def load(name):
    return json.loads((FIXTURES / name).read_text())


def invoke(url, fixture):
    import httpx
    return httpx.post(url, json=load(fixture), timeout=35).json()


def test_initialize_is_converted_to_a_rest_v1_success_response(emulator):
    response = invoke(emulator, 'post_mcp_initialize.json')
    assert response['statusCode'] == 200
    assert json.loads(response['body'])['result']['serverInfo']['name']


def test_health_is_exact_through_the_adapter(emulator):
    response = invoke(emulator, 'get_health.json')
    assert response['statusCode'] == 200
    assert json.loads(response['body']) == {'status': 'ok'}


def test_get_on_mcp_is_405_with_allow_post(emulator):
    response = invoke(emulator, 'get_mcp.json')
    assert response['statusCode'] == 405
    # REST-v1 responses may carry headers in either map; compare names case-insensitively.
    allow = [v for k, v in response.get('headers', {}).items() if k.lower() == 'allow']
    allow += [v for k, values in response.get('multiValueHeaders', {}).items() if k.lower() == 'allow' for v in values]
    assert allow and all(v == 'POST' for v in allow), response


def test_unexpected_host_is_421(emulator):
    assert invoke(emulator, 'wrong_host.json')['statusCode'] == 421


def test_browser_origin_is_403(emulator):
    assert invoke(emulator, 'origin_present.json')['statusCode'] == 403


def test_stage_prefixed_path_is_not_routed(emulator):
    assert invoke(emulator, 'post_mcp_stage_in_path.json')['statusCode'] == 404
