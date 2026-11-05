"""Original local and HTTP launch behavior remains compatible without AWS."""
import asyncio
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
import pytest
sys.path.insert(0,str(Path(__file__).parent/'support'))
from provider_fixture import ROOT, baseline, baseline_source, stdio_probe, http_server, http_probe


def test_original_launch_files_are_unchanged():
    data=baseline()
    for path in ['Dockerfile','docker-compose.yml','src/tradingview_mcp/server.py']:
        assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==data['file_sha256'][path]


def test_original_stdio_and_http_still_match_frozen_catalog():
    assert asyncio.run(stdio_probe())==baseline()['catalog']
    with http_server(mode='original') as url:
        assert asyncio.run(http_probe(url))==baseline()['catalog']


def test_original_image_behavior():
    image=os.environ.get('BASELINE_TEST_IMAGE')
    if not image:
        if os.environ.get('REQUIRE_BASELINE_CONTAINER_TESTS')=='1':pytest.fail('BASELINE_TEST_IMAGE required')
        pytest.skip('BASELINE_TEST_IMAGE not supplied')
    import json,httpx
    r=subprocess.run(['docker','image','inspect',image],capture_output=True,text=True)
    assert r.returncode==0
    meta=json.loads(r.stdout)[0]
    assert meta['Config']['Labels']['org.opencontainers.image.revision']==baseline()['baseline_ref']
    name='baseline-test-'+uuid.uuid4().hex[:12]
    try:
        r=subprocess.run(['docker','run','-d','--name',name,'-p','127.0.0.1::8000',image],capture_output=True,text=True)
        assert r.returncode==0
        port=subprocess.check_output(['docker','port',name,'8000/tcp'],text=True).strip()
        url='http://'+port
        for _ in range(150):
            try:
                r=httpx.get(url+'/health',headers={'host':'localhost:8000'},timeout=1)
                if r.status_code==200:break
            except httpx.HTTPError:pass
            time.sleep(.1)
        else:pytest.fail('original image not ready')
        assert r.json()=={'status':'ok'}
        result=asyncio.run(http_probe(url,deterministic=True))
        assert result['tools']==baseline()['catalog']['tools']
        assert result['results']['futures_watchlist']==baseline()['catalog']['results']['futures_watchlist']
    finally:
        subprocess.run(['docker','rm','-f',name],capture_output=True)
