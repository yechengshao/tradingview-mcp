"""Native image acceptance. Publishing requires prerequisites; defaults report skips."""
import json
import os
from pathlib import Path
import subprocess
import time
import uuid
import pytest

ROOT=Path(__file__).resolve().parents[2]


def docker(*args):
    return subprocess.run(['docker',*args],text=True,capture_output=True,timeout=60)


@pytest.fixture(scope='module')
def image():
    image=os.environ.get('LAMBDA_TEST_IMAGE')
    info=docker('info','--format','{{.Architecture}}')
    reason=None
    if info.returncode:reason='Docker daemon unavailable'
    elif info.stdout.strip() not in ('aarch64','arm64'):reason='Native ARM64 Docker host required'
    elif not image:reason='LAMBDA_TEST_IMAGE is required'
    if reason:
        if os.environ.get('REQUIRE_LAMBDA_CONTAINER_TESTS')=='1':pytest.fail(reason)
        pytest.skip(reason)
    inspect=docker('image','inspect',image)
    assert inspect.returncode==0
    metadata=json.loads(inspect.stdout)[0]
    assert metadata['Architecture']=='arm64'
    assert metadata['Config']['User'] not in ('','root','0')
    yield image


def test_image_readonly_storage_files_and_credential_exclusion(image):
    code='''import os,pathlib,json
assert pathlib.Path('/opt/extensions/lambda-adapter').is_file()
import tradingview_mcp,importlib.util
assert importlib.util.find_spec('boto3') is None
assert importlib.util.find_spec('cfnlint') is None
root=pathlib.Path(tradingview_mcp.__file__).parent
assert list((root/'coinlist').glob('*.txt'))
assert not list(pathlib.Path('/app').rglob('.env*'))
assert not pathlib.Path('/app/tests').exists()
assert not pathlib.Path('/app/.aws').exists()
assert not pathlib.Path('/app/.codex').exists()
pathlib.Path('/tmp/write-test').write_text('ok')
try: pathlib.Path('/app/no-write').write_text('no')
except OSError: pass
else: raise AssertionError('root filesystem writable')
assert os.environ['PROXY_PASSWORD']==' x"\\\\$`$(nope) '
'''
    r=docker('run','--rm','--read-only','--tmpfs','/tmp:rw,nosuid,size=128m',
        '-e','PROXY_PASSWORD= x"\\$`$(nope) ','--entrypoint','/app/.venv/bin/python',image,'-c',code)
    assert r.returncode==0,r.stderr


def test_image_finite_mcp_health_and_method_boundary(image):
    import httpx
    name='mcp-test-'+uuid.uuid4().hex[:12]
    try:
        r=docker('run','-d','--name',name,'--read-only','--tmpfs','/tmp:rw,nosuid,size=128m',
            '-p','127.0.0.1::8000','-e','TRADINGVIEW_MCP_PUBLIC_HOST=abc123.execute-api.ca-central-1.amazonaws.com',image)
        assert r.returncode==0,r.stderr
        mapping=docker('port',name,'8000/tcp').stdout.strip()
        url='http://'+mapping
        headers={'host':'localhost:8000','accept':'application/json, text/event-stream'}
        for _ in range(100):
            try:
                h=httpx.get(url+'/health',headers=headers,timeout=1)
                if h.status_code==200:break
            except httpx.HTTPError:pass
            time.sleep(.1)
        else:pytest.fail('image never ready')
        assert h.json()=={'status':'ok'}
        for _ in range(10):
            assert httpx.get(url+'/health',headers=headers,timeout=5).status_code==200
        assert httpx.get(url+'/mcp',headers=headers).status_code==405
        for path in ['/mcp','/mcp/']:
            r=httpx.post(url+path,headers=headers,json={'jsonrpc':'2.0','id':1,'method':'tools/call',
                'params':{'name':'futures_watchlist','arguments':{}}},timeout=35)
            assert r.status_code==200 and r.headers['content-type'].startswith('application/json')
            assert not r.json()['result'].get('isError',False)
    finally:
        docker('rm','-f',name)


def test_installed_image_controlled_provider_parity_and_health_independence(image):
    """Inject test-only code through argv; handlers/data come from the built image."""
    import asyncio
    from contextlib import contextmanager
    import sys
    sys.path.insert(0,str(Path(__file__).parent/'support'))
    from provider_fixture import baseline,http_probe
    import httpx
    for failed in [False,True]:
        name='provider-test-'+uuid.uuid4().hex[:12]
        code='''from tradingview_mcp import server
from tradingview_mcp.core.errors import ScreenerServiceError,ErrorCode
from tradingview_mcp.lambda_server import create_app
import uvicorn
calls=0
def provider(*a,**kw):
 global calls
 calls+=1
 if kw.get('limit')==1:
  import time
  time.sleep(.3)
 if FAILED: raise ScreenerServiceError(ErrorCode.NO_DATA,'controlled provider unavailable',retryable=False)
 return [{'symbol':'FIXTURE','changePercent':1.25,'indicators':{'close':100}}]
server.fetch_trending_analysis=provider
app=create_app()
original=app.app
async def guarded(scope,receive,send):
 before=calls
 await original(scope,receive,send)
 if scope['type']=='http' and scope['path']=='/health': assert calls==before
app.app=guarded
uvicorn.run(app,host='0.0.0.0',port=8000,log_level='critical',access_log=False)
'''.replace('FAILED',str(failed))
        try:
            r=docker('run','-d','--name',name,'--read-only','--tmpfs','/tmp:rw,nosuid,size=128m',
                '-p','127.0.0.1::8000','-e','TRADINGVIEW_MCP_PUBLIC_HOST=abc123.execute-api.ca-central-1.amazonaws.com',
                '--entrypoint','/app/.venv/bin/python',image,'-c',code)
            assert r.returncode==0,r.stderr
            url='http://'+docker('port',name,'8000/tcp').stdout.strip()
            for _ in range(100):
                try:
                    if httpx.get(url+'/health',headers={'host':'localhost:8000'},timeout=1).status_code==200:break
                except httpx.HTTPError:pass
                time.sleep(.1)
            else:pytest.fail('controlled image never ready')
            actual=asyncio.run(http_probe(url))
            assert actual['tools']==baseline()['catalog']['tools']
            expected=baseline()['failure_results'] if failed else baseline()['catalog']['results']
            assert actual['results']==expected
            for _ in range(10):
                assert httpx.get(url+'/health',headers={'host':'localhost:8000'},timeout=5).json()=={'status':'ok'}
            assert httpx.post(url+'/mcp/',headers={'host':'evil.example'},json={}).status_code==421
            assert httpx.post(url+'/mcp/',headers={'host':'localhost:8000','origin':'null'},json={}).status_code==403
            headers={'host':'localhost:8000','accept':'application/json, text/event-stream'}
            oversized=httpx.post(url+'/mcp',headers=headers,json={'padding':'x'*(4*1024*1024)},timeout=10)
            assert oversized.status_code==413
            with pytest.raises(httpx.TimeoutException):
                httpx.post(url+'/mcp',headers=headers,json={'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'top_gainers','arguments':{'limit':1}}},timeout=.05)
            assert httpx.get(url+'/health',headers=headers,timeout=5).json()=={'status':'ok'}
        finally:docker('rm','-f',name)
