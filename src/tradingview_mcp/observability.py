"""Lambda CloudWatch diagnostics using stdlib only; X-Ray segments are AWS-managed."""
from __future__ import annotations

import contextvars
import functools
import json
import logging
import os
import re
import secrets
import sys
import time
import traceback

_CONTEXT = contextvars.ContextVar('mcp_diagnostics', default=None)
_OPAQUE = re.compile(r'[A-Za-z0-9_-]{1,64}')
_SAFE = re.compile(r'[A-Za-z0-9_.-]{1,96}')
_FIELDS = {'operation','tool','outcome','duration_ms','status_code','correlation_id','request_id','trace_id','trace_parent_id','frames'}


def parent_context(value):
    """Read existing AWS tracking identifiers; do not generate spans or authorize users."""
    if not isinstance(value, str) or len(value) > 512:
        return None
    parts = {}
    for field in value.split(';'):
        key, _, item = field.strip().partition('=')
        if key in ('Root','Parent','Sampled'):
            if key in parts:
                return None
            parts[key] = item
    root, parent, sampled = (parts.get(k, '') for k in ('Root','Parent','Sampled'))
    if not re.fullmatch(r'1-[0-9a-f]{8}-[0-9a-f]{24}', root) or not re.fullmatch(r'[0-9a-f]{16}', parent) or sampled not in ('0','1'):
        return None
    if not int(root[2:].replace('-', ''), 16) or not int(parent, 16):
        return None
    return {'trace_id': root, 'trace_parent_id': parent, 'sampled': sampled == '1'}


class Telemetry:
    def __init__(self, *, environment='development', release='unknown', stream=None):
        self.stream = stream or getattr(sys.stdout, 'diagnostic_stream', sys.stdout)
        self.environment = environment if environment in ('development','test','production') else 'unknown'
        self.release = release if isinstance(release, str) and _SAFE.fullmatch(release) else 'unknown'

    def emit(self, level, **fields):
        try:
            record = {'timestamp': round(time.time(), 3), 'level': level, 'service': 'tradingview-mcp',
                      'environment': self.environment, 'release': self.release}
            for key, value in {**(_CONTEXT.get() or {}), **fields}.items():
                if key in _FIELDS and isinstance(value, (str, int, float, list)):
                    record[key] = value
            line = json.dumps(record, separators=(',', ':'), allow_nan=False)
            if len(line.encode()) <= 4095:
                self.stream.write(line + '\n')
        except Exception:
            pass

    def failure(self, operation, error=None, **fields):
        frames = []
        if error is not None:
            for frame in traceback.extract_tb(error.__traceback__)[-8:]:
                filename = os.path.basename(frame.filename)
                frames.append({'file': filename if _SAFE.fullmatch(filename) else 'module', 'line': frame.lineno,
                               'function': frame.name if _SAFE.fullmatch(frame.name) else 'function'})
        self.emit('ERROR', operation=operation, outcome='unexpected_error', frames=frames, **fields)

    def wrap_tools(self, manager):
        for tool in manager.list_tools():
            if getattr(tool.fn, '_mcp_observed', False):
                continue
            original, name = tool.fn, tool.name
            @functools.wraps(original)
            async def observed(*args, __fn=original, __name=name, **kwargs):
                started = time.perf_counter()
                try:
                    result = await __fn(*args, **kwargs)
                    if isinstance(result, dict) and bool(result.get('error') or result.get('isError')):
                        self.emit('WARNING', operation='mcp.tool', tool=__name, outcome='tool_error', duration_ms=round((time.perf_counter()-started)*1000, 3))
                    return result
                except Exception as error:
                    self.failure('mcp.tool', error, tool=__name, duration_ms=round((time.perf_counter()-started)*1000, 3))
                    raise
            observed._mcp_observed = True
            tool.fn = observed


class ObservedApp:
    def __init__(self, app, telemetry):
        self.app, self.telemetry = app, telemetry

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        def header(name):
            values = [v.decode('latin-1') for k,v in scope.get('headers', []) if k.lower() == name]
            return values[0] if len(values) == 1 else ''
        correlation = header(b'x-correlation-id')
        if not _OPAQUE.fullmatch(correlation):
            correlation = secrets.token_hex(16)
        diagnostic = {'correlation_id': correlation}
        request_id = header(b'x-amzn-requestid')
        if _OPAQUE.fullmatch(request_id):
            diagnostic['request_id'] = request_id
        parent = parent_context(header(b'x-amzn-trace-id'))
        if parent and parent['sampled']:
            diagnostic.update(trace_id=parent['trace_id'], trace_parent_id=parent['trace_parent_id'])
        # LWA is long-running: do not read a stale process-wide invocation trace variable.
        token = _CONTEXT.set(diagnostic)
        route = scope.get('path')
        operation = 'mcp.request' if route in ('/mcp','/mcp/') else 'health' if route == '/health' else 'other'
        started, status, sent, complete = time.perf_counter(), 500, False, False
        async def observed_send(message):
            nonlocal status, sent, complete
            if message['type'] == 'http.response.start':
                sent, status = True, message['status']
                headers = [(k,v) for k,v in message.get('headers',[]) if k.lower()!=b'x-correlation-id']
                message = {**message,'headers':headers+[(b'x-correlation-id',correlation.encode())]}
            elif message['type'] == 'http.response.body' and not message.get('more_body',False):
                complete = True
            await send(message)
        try:
            try:
                await self.app(scope,receive,observed_send)
                if status >= 500:
                    self.telemetry.emit('ERROR',operation=operation,outcome='server_error',status_code=status,duration_ms=round((time.perf_counter()-started)*1000,3))
            except Exception as error:
                self.telemetry.failure(operation,error,status_code=500,duration_ms=round((time.perf_counter()-started)*1000,3))
                if not sent:
                    await observed_send({'type':'http.response.start','status':500,'headers':[(b'content-type',b'application/json')]})
                if not complete:
                    await observed_send({'type':'http.response.body','body':b'{"error":"internal server error"}' if status==500 else b''})
        finally:
            _CONTEXT.reset(token)


class SafeConsole:
    """Discard raw legacy output; emit one value-free notice per stream."""
    encoding = 'utf-8'
    errors = 'strict'
    def __init__(self,telemetry):
        self.telemetry=telemetry
        self.diagnostic_stream=telemetry.stream
        self.warned=False
    def write(self,value):
        if value.strip() and not self.warned:
            self.warned=True
            self.telemetry.emit('WARNING',operation='telemetry',outcome='unstructured_output_suppressed')
        return len(value)
    def flush(self): pass
    def isatty(self): return False


def configure(env):
    logging.disable(logging.CRITICAL)
    telemetry=Telemetry(environment=env['TRADINGVIEW_MCP_ENVIRONMENT'],release=env.get('TRADINGVIEW_MCP_DEPLOYMENT_REVISION','unknown'))
    sys.stdout=SafeConsole(telemetry)
    sys.stderr=SafeConsole(telemetry)
    telemetry.emit('INFO',operation='startup',outcome='initialized')
    return telemetry
