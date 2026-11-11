"""REST-v1 event transport checks for the Lambda entrypoint (spec 001 T051).

The API Gateway REST-v1 event fixtures in fixtures/rest_v1 are hand-written from the
documented proxy event format; none is produced by this repository's code.

Limitation: the pinned Lambda Web Adapter binary (1.1.0, from the Dockerfile.lambda
digest) could not be extracted in this environment, so the event-to-HTTP step below is
a test model of the adapter's documented mapping, not the packaged adapter. Packaged
Runtime API checks stay open under T051 until they run against the built image.
"""
import base64
import json
from pathlib import Path
import sys
from urllib.parse import urlencode

import pytest

sys.path.insert(0, str(Path(__file__).parent / 'support'))
from provider_fixture import http_server  # noqa: E402

FIXTURES = Path(__file__).parent / 'fixtures' / 'rest_v1'
MCP_HEADERS = {'Accept': 'application/json, text/event-stream', 'Content-Type': 'application/json'}


class ProfileError(ValueError):
    """Raised for events outside the REST-v1 profile this service supports."""


def load(name):
    return json.loads((FIXTURES / name).read_text())


def to_http(event):
    """Model of the adapter mapping: REST-v1 proxy event to one HTTP request."""
    if event.get('version') == '2.0' or 'rawPath' in event or 'httpMethod' not in event:
        raise ProfileError('not a REST-v1 proxy event')
    headers = []
    for name, values in event.get('multiValueHeaders', {}).items():
        headers.extend((name, v) for v in values)
    query = event.get('multiValueQueryStringParameters') or {}
    pairs = [(k, v) for k, values in query.items() for v in values]
    path = event['path'] + ('?' + urlencode(pairs) if pairs else '')
    body = event.get('body') or ''
    raw = base64.b64decode(body) if event.get('isBase64Encoded') else body.encode()
    return event['httpMethod'], path, headers, raw


@pytest.fixture(scope='module')
def url():
    with http_server(mode='lambda') as base:
        yield base


def host_header(event):
    return next(v for k, v in event['multiValueHeaders'].items() if k.lower() == 'host')[0]


def send_event(base, event):
    import httpx
    method, path, headers, body = to_http(event)
    host = host_header(event)
    other = [(k, v) for k, v in headers if k.lower() not in ('host', 'content-length')]
    with httpx.Client(timeout=35, headers={'host': host}) as client:
        return client.request(method, base + path, headers=other, content=body)


def test_post_initialize_round_trips_as_json(url):
    response = send_event(url, load('post_mcp_initialize.json'))
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('application/json')
    assert json.loads(response.text)['result']['serverInfo']['name']


def test_tools_list_is_served_statelessly(url):
    response = send_event(url, load('post_mcp_tools_list.json'))
    assert response.status_code == 200
    assert 'mcp-session-id' not in {k.lower() for k in response.headers}
    assert response.headers['content-type'].startswith('application/json')


def test_base64_body_is_decoded(url):
    response = send_event(url, load('post_mcp_base64.json'))
    assert response.status_code == 200
    assert json.loads(response.text)['result']['serverInfo']['name']


def test_repeated_headers_and_query_are_forwarded_without_error(url):
    event = load('post_mcp_repeated.json')
    method, path, headers, _ = to_http(event)
    assert path == '/mcp?trace=a&trace=b&mode=x'
    assert [v for k, v in headers if k == 'X-Forwarded-For'] == ['203.0.113.10']
    assert send_event(url, event).status_code == 200


def test_trailing_slash_is_normalized_without_redirect(url):
    response = send_event(url, load('post_mcp_trailing_slash.json'))
    assert response.status_code == 200
    assert not response.is_redirect


def test_health_is_exact_and_upstream_free(url):
    response = send_event(url, load('get_health.json'))
    assert response.status_code == 200
    assert json.loads(response.text) == {'status': 'ok'}


def test_get_on_mcp_is_rejected_with_allow_post(url):
    response = send_event(url, load('get_mcp.json'))
    assert response.status_code == 405
    assert response.headers['allow'] == 'POST'


def test_unexpected_host_is_rejected_before_mcp(url):
    assert send_event(url, load('wrong_host.json')).status_code == 421


def test_browser_origin_is_rejected(url):
    assert send_event(url, load('origin_present.json')).status_code == 403


def test_stage_prefix_in_event_path_is_not_routed(url):
    # REST-v1 event.path excludes the stage; the fixture carries the stage only in
    # requestContext. A stage-prefixed path is not routed, and base-path stripping stays
    # unimplemented until representative events prove it is needed.
    response = send_event(url, load('post_mcp_stage_in_path.json'))
    assert response.status_code == 404


def test_http_api_payload_is_outside_this_profile():
    with pytest.raises(ProfileError):
        to_http(load('http_api_v2_payload.json'))


def test_responses_are_never_event_streams(url):
    response = send_event(url, load('post_mcp_initialize.json'))
    assert 'text/event-stream' not in response.headers['content-type']
