import json
import pytest
from starlette.testclient import TestClient
from tradingview_mcp.lambda_secrets import MarketauxToken, parameter_name_from

NAME = '/mcp/test/service/marketaux-api-token'
SECRET = 'sentinel-marketaux-value'


class FakeSsm:
    def __init__(self, values):
        self.values = list(values)
        self.calls = []

    def get_parameter(self, **kwargs):
        self.calls.append(kwargs)
        item = self.values.pop(0)
        if isinstance(item, Exception):
            raise item
        return {'Parameter': {'Value': item}}


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_parameter_name_must_match_the_exact_convention():
    assert parameter_name_from({'MARKETAUX_API_TOKEN_PARAMETER': NAME}) == NAME
    assert parameter_name_from({}) == ''
    for bad in ['/mcp/staging/service/marketaux-api-token', '/mcp/test/service/other', 'marketaux-api-token']:
        with pytest.raises(ValueError):
            parameter_name_from({'MARKETAUX_API_TOKEN_PARAMETER': bad})


def test_reads_exact_secure_string_with_decryption_and_caches_until_ttl():
    ssm, clock = FakeSsm([SECRET, 'rotated']), Clock()
    token = MarketauxToken(NAME, client=ssm, ttl_seconds=300, clock=clock)
    assert token.value() == SECRET
    assert token.value() == SECRET
    assert ssm.calls == [{'Name': NAME, 'WithDecryption': True}]
    clock.now += 301
    assert token.value() == 'rotated'
    assert len(ssm.calls) == 2


def test_failed_refresh_keeps_last_good_value_and_emits_no_secret():
    emitted = []
    ssm = FakeSsm([SECRET, RuntimeError('AccessDenied for ' + SECRET)])
    clock = Clock()
    token = MarketauxToken(NAME, client=ssm, ttl_seconds=300, clock=clock,
                           emit=lambda level, **fields: emitted.append((level, fields)))
    assert token.value() == SECRET
    clock.now += 301
    assert token.value() == SECRET
    assert emitted == [('WARNING', {'operation': 'marketaux.token', 'outcome': 'refresh_failed', 'error_class': 'RuntimeError'})]
    assert SECRET not in json.dumps(emitted, default=str)


def test_missing_or_invalid_value_yields_empty_token_without_crashing():
    for bad in ['', 'x' * 513, 'bad\x00value']:
        token = MarketauxToken(NAME, client=FakeSsm([bad]), clock=Clock())
        assert token.value() == ''


def test_boundary_runs_refresh_only_for_http_requests():
    from tradingview_mcp.lambda_server import LambdaBoundary
    calls = []

    async def app(scope, receive, send):
        if scope['type'] == 'lifespan':
            while True:
                message = await receive()
                await send({'type': message['type'] + '.complete'})
                if message['type'] == 'lifespan.shutdown':
                    return
        await send({'type': 'http.response.start', 'status': 200, 'headers': []})
        await send({'type': 'http.response.body', 'body': b'{}'})

    with TestClient(LambdaBoundary(app, before_http=lambda: calls.append(1))) as client:
        assert client.get('/health').status_code == 200
    assert calls == [1]
