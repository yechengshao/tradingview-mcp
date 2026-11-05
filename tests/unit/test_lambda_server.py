"""Lambda-only config/security wrapper contracts without shared MCP mutation."""
import json
import os
import subprocess
import sys
import pytest
from starlette.testclient import TestClient

PUBLIC = 'abc123.execute-api.ca-central-1.amazonaws.com'


def module():
    from tradingview_mcp import lambda_server
    return lambda_server


def test_import_does_not_import_server():
    result = subprocess.run([sys.executable,'-c',
        "import sys; import tradingview_mcp.lambda_server; assert 'tradingview_mcp.server' not in sys.modules"], capture_output=True)
    assert result.returncode == 0, result.stderr.decode()


def test_defaults_empty_optional_and_literal_credentials():
    m=module()
    env=m.validate_environment({'TRADINGVIEW_MCP_PUBLIC_HOST':PUBLIC})
    assert len(set(m.APPLICATION_DEFAULTS) & env.keys()) == 9
    assert env['MARKETAUX_API_TOKEN'] == env['PROXY_PASSWORD'] == ''
    assert env['PROXY_PORT']=='80' and env['PROXY_ENABLED']=='true'
    literal=' x"\\$`$(nope) '
    env=m.validate_environment({'TRADINGVIEW_MCP_PUBLIC_HOST':PUBLIC,'PROXY_PASSWORD':literal})
    assert env['PROXY_PASSWORD']==literal


@pytest.mark.parametrize('key,value', [('PROXY_PORT','0'),('PROXY_PORT','65536'),
    ('PROXY_SESSION_MIN','251'),('PROXY_ENABLED','yes'),('MARKETAUX_DAILY_BUDGET','-1'),
    ('PROXY_HOST',''),('PROXY_HOST','https://invalid'),('PROXY_PASSWORD','a\x00b'),
    ('PROXY_PASSWORD','SENSITIVE'*600),('TRADINGVIEW_MCP_PUBLIC_HOST','attacker.example')])
def test_invalid_config_redacts_values(key,value):
    with pytest.raises(ValueError) as exc:
        module().validate_environment({'TRADINGVIEW_MCP_PUBLIC_HOST':PUBLIC,key:value})
    assert 'SENSITIVE' not in str(exc.value)
    assert 'a\x00b' not in str(exc.value)


def test_environment_size_includes_extra_configured_keys():
    with pytest.raises(ValueError):
        module().validate_environment({'TRADINGVIEW_MCP_PUBLIC_HOST':PUBLIC,'EXTRA':'x'*4096})


async def dummy(scope, receive, send):
    if scope['type']=='lifespan':
        while True:
            msg=await receive()
            await send({'type':msg['type']+'.complete'})
            if msg['type']=='lifespan.shutdown': return
    else:
        body=json.dumps({'path':scope['path']}).encode()
        await send({'type':'http.response.start','status':200,'headers':[(b'content-type',b'application/json')]})
        await send({'type':'http.response.body','body':body})


@pytest.mark.parametrize('host', ['127.0.0.1:8000','localhost:8000',PUBLIC,PUBLIC+':443'])
def test_exact_hosts_and_slash_without_auth(host):
    app=module().LambdaBoundary(dummy,PUBLIC)
    with TestClient(app, base_url='http://'+host) as client:
        r=client.post('/mcp/',json={})
        assert r.status_code==200 and r.json()['path']=='/mcp'
        assert client.get('/health').status_code==200
        for method in ['GET','DELETE','OPTIONS','PUT','PATCH']:
            r=client.request(method,'/mcp')
            assert r.status_code==405 and r.headers['allow']=='POST'


@pytest.mark.parametrize('headers', [{'host':'evil.example'}, {'host':PUBLIC+'.evil'},
    {'origin':'null'}, {'origin':'https://'+PUBLIC}, {'host':PUBLIC+',evil'},
    {'host':PUBLIC,'origin':''}])
def test_rejected_authority_and_origin(headers):
    with TestClient(module().LambdaBoundary(dummy,PUBLIC),base_url='http://localhost:8000') as client:
        assert client.get('/health',headers=headers).status_code in (400,403,421)


def test_forwarded_host_does_not_override_actual_authority():
    with TestClient(module().LambdaBoundary(dummy,PUBLIC),base_url='http://evil.example') as client:
        assert client.get('/health',headers={'x-forwarded-host':PUBLIC}).status_code==421
