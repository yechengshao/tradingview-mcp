"""Test-only process fixture. Never installed in the production image."""
from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tarfile
import tempfile
import time

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = Path(__file__).with_name('baseline.json')


def baseline():
    data = json.loads(MANIFEST.read_text())
    ref = data['baseline_ref']
    subprocess.run(['git', 'cat-file', '-e', f'{ref}^{{commit}}'], cwd=ROOT, check=True, capture_output=True)
    lock = subprocess.check_output(['git', 'show', f'{ref}:uv.lock'], cwd=ROOT)
    if hashlib.sha256(lock).hexdigest() != data['capture']['dependency_lock_sha256']:
        raise ValueError('baseline provenance mismatch')
    for name,expected in data.get('file_sha256',{}).items():
        content=subprocess.check_output(['git','show',f'{ref}:{name}'],cwd=ROOT)
        if hashlib.sha256(content).hexdigest()!=expected:raise ValueError('baseline source identity mismatch')
    return data


@contextmanager
def baseline_source():
    data = baseline()
    with tempfile.TemporaryDirectory(prefix='mcp-baseline-') as tmp:
        archive = subprocess.check_output(['git', 'archive', data['baseline_ref']], cwd=ROOT)
        import io
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(tmp, filter='data')
        yield Path(tmp)


def clean_env(source):
    # No inherited AWS/provider/client credentials in deterministic children.
    return {'PATH': os.environ['PATH'], 'PYTHONPATH': str(source / 'src'),
            'HOME': tempfile.gettempdir(), 'PYTHONUNBUFFERED': '1',
            'TRADINGVIEW_MCP_PUBLIC_HOST': 'example123.execute-api.ca-central-1.amazonaws.com'}


@contextmanager
def http_server(source=ROOT, mode='lambda', provider='success', drift=False):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    args = [sys.executable, str(Path(__file__).resolve()), 'serve', '--source', str(source),
            '--mode', mode, '--provider', provider, '--port', str(port)]
    if drift:args.append('--drift')
    with tempfile.TemporaryFile() as log:
        proc = subprocess.Popen(args, env=clean_env(source), cwd=source, stdout=log, stderr=log)
        try:
            import httpx
            url = f'http://127.0.0.1:{port}'
            for _ in range(150):
                if proc.poll() is not None:
                    log.seek(0)
                    raise RuntimeError('fixture startup failed: ' + log.read().decode()[-3000:])
                try:
                    if httpx.get(url + '/health', headers={'host':'localhost:8000'}, timeout=.2).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(.05)
            else:
                raise TimeoutError('fixture readiness unavailable')
            yield url
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


async def collect(session, deterministic=False):
    await session.initialize()
    tools, resources = [], []
    cursor = None
    while True:
        page = await session.list_tools(cursor=cursor)
        tools.extend(t.model_dump(mode='json', exclude_none=True) for t in page.tools)
        cursor = page.nextCursor
        if not cursor:
            break
    cursor = None
    while True:
        page = await session.list_resources(cursor=cursor)
        resources.extend(r.model_dump(mode='json', exclude_none=True) for r in page.resources)
        cursor = page.nextCursor
        if not cursor:
            break
    results = {}
    calls=[('futures_watchlist', {})] if deterministic else [('futures_watchlist', {}), ('top_gainers', {'limit': 2}), ('coin_analysis', {}), ('missing_tool', {})]
    for name, args in calls:
        reply = await session.call_tool(name, args)
        results[name] = reply.model_dump(mode='json', exclude_none=True)
    return {'tools': sorted(tools, key=lambda t:t['name']),
            'resources': sorted(resources, key=lambda r:r['uri']), 'results': results}


async def http_probe(url, deterministic=False):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    import httpx
    async with httpx.AsyncClient(headers={'host':'localhost:8000'}, timeout=35) as client:
        async with streamable_http_client(url + '/mcp', http_client=client) as (read, write, _):
            async with ClientSession(read, write) as session:
                return await collect(session, deterministic)


async def stdio_probe(source=ROOT, provider='success', drift=False):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    params = StdioServerParameters(command=sys.executable,
        args=[str(Path(__file__).resolve()), 'serve', '--source', str(source),
              '--mode', 'stdio', '--provider', provider]+(['--drift'] if drift else []), env=clean_env(source), cwd=source)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            return await collect(session)


def serve(args):
    sys.path.insert(0, str(Path(args.source) / 'src'))
    from tradingview_mcp import server
    def provider(*a, **kw):
        if args.provider == 'failure':
            from tradingview_mcp.core.errors import ScreenerServiceError, ErrorCode
            raise ScreenerServiceError(ErrorCode.NO_DATA, 'controlled provider unavailable', retryable=False)
        return [{'symbol': 'FIXTURE', 'changePercent': 1.25, 'indicators': {'close': 100}}]
    server.fetch_trending_analysis = provider
    if args.drift:server.mcp._tool_manager.list_tools()[0].description='controlled registration drift'
    if args.mode == 'stdio':
        server.mcp.run(transport='stdio')
    else:
        import uvicorn
        if args.mode == 'lambda':
            from tradingview_mcp.lambda_server import create_app
            app = create_app()
        else:
            app = server.mcp.streamable_http_app()
        uvicorn.run(app, host='127.0.0.1', port=args.port, log_level='critical', access_log=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['serve', 'capture'])
    parser.add_argument('--source', default=str(ROOT))
    parser.add_argument('--mode', choices=['lambda', 'original', 'stdio'], default='lambda')
    parser.add_argument('--provider', choices=['success', 'failure'], default='success')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--drift', action='store_true')
    args = parser.parse_args()
    if args.action == 'serve':
        serve(args)
    else:
        data = baseline()
        with baseline_source() as source:
            data['catalog'] = asyncio.run(stdio_probe(source))
            data['failure_results'] = asyncio.run(stdio_probe(source, 'failure'))['results']
            files = ['Dockerfile', 'docker-compose.yml', 'src/tradingview_mcp/server.py',
                     '.github/workflows/publish-image.yml', '.github/workflows/test.yml']
            data['file_sha256'] = {f:hashlib.sha256((source / f).read_bytes()).hexdigest() for f in files}
            data['launch'] = {'stdio':['tradingview-mcp'],
                'docker':['tradingview-mcp','streamable-http','--host','0.0.0.0','--port','8000'],
                'port':8000,'health':{'status':'ok'}}
            data['publishing'] = {'destination':'ghcr.io/${{ github.repository }}',
                'architectures':['linux/amd64','linux/arm64'],
                'workflow':(source / '.github/workflows/publish-image.yml').read_text()}
        import importlib.metadata
        data['capture']['packages'] = {k:importlib.metadata.version(k) for k in ['mcp','starlette','httpx','uvicorn','pandas']}
        MANIFEST.write_text(json.dumps(data, indent=2, sort_keys=True)+'\n')
