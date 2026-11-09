"""Native AWS monitoring: stdlib diagnostics, real tools/context, no tracing SDK/exporter."""
import asyncio
import io
import json
import os
import subprocess
import sys
from types import SimpleNamespace

import httpx
import pytest
from starlette.testclient import TestClient
from tradingview_mcp.observability import Telemetry, ObservedApp, parent_context, _CONTEXT
SECRET='DO_NOT_LOG_TOKEN_OR_CUSTOMER_DETAILS'
PARENT='Root=1-6a000000-123456789012345678901234;Parent=1234567890abcdef;Sampled='


async def success(scope,receive,send):
    await send({'type':'http.response.start','status':200,'headers':[]})
    await send({'type':'http.response.body','body':b'ok'})


def test_existing_aws_context_is_correlated_without_custom_segments_or_sensitive_input():
    stream=io.StringIO();telemetry=Telemetry(stream=stream)
    async def application(scope,receive,send):
        telemetry.emit('INFO',operation='mcp.request',outcome='fixture')
        await success(scope,receive,send)
    response=TestClient(ObservedApp(application,telemetry)).post('/mcp?token='+SECRET,
        headers={'Authorization':SECRET,'Cookie':SECRET,'x-amzn-trace-id':PARENT+'1','x-correlation-id':'safe_correlation','x-amzn-requestid':'safe_request'},content=SECRET)
    assert response.text=='ok' and response.headers['x-correlation-id']=='safe_correlation'
    record=json.loads(stream.getvalue())
    assert record['trace_id']=='1-6a000000-123456789012345678901234'
    assert record['trace_parent_id']=='1234567890abcdef' and record['request_id']=='safe_request'
    assert 'span_id' not in record and SECRET not in stream.getvalue()


@pytest.mark.parametrize('header',['bad','Root='+SECRET,PARENT+'1;Parent=1234567890abcdef',PARENT.replace(';Parent','=junk;Parent')+'1'])
def test_malformed_aws_context_is_ignored(header):
    assert parent_context(header) is None


def test_error_records_are_safe_and_useful_without_any_trace_header():
    stream=io.StringIO()
    async def failing(scope,receive,send): raise RuntimeError(SECRET)
    response=TestClient(ObservedApp(failing,Telemetry(stream=stream))).post('/mcp',headers={'x-correlation-id':'bad '+SECRET})
    assert response.status_code==500 and SECRET not in response.text
    record=json.loads(stream.getvalue())
    assert record['outcome']=='unexpected_error' and record['frames'][-1]['function']=='failing'
    assert record['correlation_id']==response.headers['x-correlation-id']
    assert 'trace_id' not in record and SECRET not in stream.getvalue()
    assert len(stream.getvalue().encode())<=4096


@pytest.mark.asyncio
async def test_concurrent_requests_keep_context_through_threaded_tools():
    stream=io.StringIO();telemetry=Telemetry(stream=stream)
    async def tool(**kwargs):
        await asyncio.sleep(0)
        return await asyncio.to_thread(lambda:dict(_CONTEXT.get()))
    item=SimpleNamespace(name='approved_tool',fn=tool)
    telemetry.wrap_tools(SimpleNamespace(list_tools=lambda:[item]))
    async def application(scope,receive,send):
        result=await item.fn(secret=SECRET)
        await send({'type':'http.response.start','status':200,'headers':[]})
        await send({'type':'http.response.body','body':json.dumps(result).encode()})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=ObservedApp(application,telemetry)),base_url='http://test') as client:
        a,b=await asyncio.gather(*(client.post('/mcp',headers={'x-correlation-id':value}) for value in ['request_a','request_b']))
    assert a.json()['correlation_id']=='request_a' and b.json()['correlation_id']=='request_b'
    assert _CONTEXT.get() is None and stream.getvalue()==''


def test_tool_error_envelopes_and_exceptions_preserve_behavior_without_raw_output():
    stream=io.StringIO();telemetry=Telemetry(stream=stream);result={'error':SECRET}
    async def tool(): return result
    item=SimpleNamespace(name='approved_tool',fn=tool);manager=SimpleNamespace(list_tools=lambda:[item])
    telemetry.wrap_tools(manager);first=item.fn;telemetry.wrap_tools(manager)
    assert first is item.fn and asyncio.run(item.fn()) is result
    assert json.loads(stream.getvalue())['outcome']=='tool_error'
    assert SECRET not in stream.getvalue()
    async def failing(): raise ValueError(SECRET)
    item=SimpleNamespace(name='failed_tool',fn=failing);telemetry.wrap_tools(SimpleNamespace(list_tools=lambda:[item]))
    with pytest.raises(ValueError,match=SECRET):asyncio.run(item.fn())
    assert SECRET not in stream.getvalue()


def test_no_success_polling_volume_and_no_invented_trace_ids():
    stream=io.StringIO();telemetry=Telemetry(stream=stream)
    client=TestClient(ObservedApp(success,telemetry))
    assert client.get('/health').status_code==200 and client.post('/mcp').status_code==200
    assert stream.getvalue()==''
    assert parent_context(PARENT+'0')['sampled'] is False
    assert not hasattr(telemetry,'tracer') and not hasattr(telemetry,'provider')


def test_console_output_and_sdk_logging_cannot_leak_secrets_in_lambda():
    code='''
import logging,sys
from tradingview_mcp.observability import configure
telemetry=configure({'TRADINGVIEW_MCP_ENVIRONMENT':'test'})
print('DO_NOT_LOG_TOKEN_OR_CUSTOMER_DETAILS')
print('DO_NOT_LOG_TOKEN_OR_CUSTOMER_DETAILS',file=sys.stderr)
logging.error('DO_NOT_LOG_TOKEN_OR_CUSTOMER_DETAILS')
telemetry.emit('ERROR',operation='test',outcome='controlled_failure')
'''
    result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=10)
    assert result.returncode==0 and not result.stderr
    records=[json.loads(line) for line in result.stdout.splitlines()]
    assert records[0]['outcome']=='initialized' and records[-1]['outcome']=='controlled_failure'
    assert SECRET not in result.stdout


def test_logging_failures_do_not_break_requests():
    class Broken:
        def write(self,_):raise RuntimeError(SECRET)
    Telemetry(stream=Broken()).emit('ERROR',operation='test',outcome='test')


def test_invalid_startup_has_safe_json_and_no_optional_monitoring_dependencies():
    result=subprocess.run([sys.executable,'-m','tradingview_mcp.lambda_server'],env=dict(os.environ,TRADINGVIEW_MCP_PUBLIC_HOST=SECRET),capture_output=True,text=True,timeout=10)
    assert result.returncode==1 and json.loads(result.stdout)['outcome']=='invalid_configuration'
    assert SECRET not in result.stdout+result.stderr
    import tomllib
    from pathlib import Path
    metadata=tomllib.loads((Path(__file__).parents[2]/'pyproject.toml').read_text())
    assert 'observability' not in metadata['project'].get('optional-dependencies',{})
    assert not any('opentelemetry' in item for item in metadata['project']['dependencies'])
