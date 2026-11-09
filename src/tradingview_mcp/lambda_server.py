"""Isolated stateless Lambda HTTP entrypoint. Authorization belongs to API Gateway."""
from __future__ import annotations

import os
import re
from collections.abc import Mapping

APPLICATION_DEFAULTS = {
    'MARKETAUX_API_TOKEN':'', 'MARKETAUX_DAILY_BUDGET':'90',
    'PROXY_HOST':'p.webshare.io', 'PROXY_PORT':'80', 'PROXY_USERNAME_PREFIX':'',
    'PROXY_PASSWORD':'', 'PROXY_SESSION_MIN':'1', 'PROXY_SESSION_MAX':'250',
    'PROXY_ENABLED':'true',
}
CONFIGURED_KEYS = set(APPLICATION_DEFAULTS) | {
    'TRADINGVIEW_MCP_PUBLIC_HOST','TRADINGVIEW_MCP_DEPLOYMENT_REVISION',
    'TRADINGVIEW_MCP_SOURCE_COMMIT','TRADINGVIEW_MCP_LOCK_SHA256',
    'AWS_LWA_PORT','AWS_LWA_READINESS_CHECK_PATH','AWS_LWA_READINESS_CHECK_HEALTHY_STATUS',
    'AWS_LWA_INVOKE_MODE','PYTHONDONTWRITEBYTECODE','PYTHONUNBUFFERED','HOME','TMPDIR','UV_CACHE_DIR',
}
OBSERVABILITY_DEFAULTS = {
    'TRADINGVIEW_MCP_ENVIRONMENT': 'development',
}
CONFIGURED_KEYS.update(OBSERVABILITY_DEFAULTS)
PUBLIC_HOST = re.compile(r'[a-z0-9]+\.execute-api\.[a-z]{2}(?:-[a-z0-9]+)+-\d\.amazonaws\.com')


def validate_environment(source: Mapping[str,str]) -> dict[str,str]:
    """Validate literal configured strings, with value-free failure messages.

    Include all non-reserved environment entries in sizing. Lambda supplies reserved
    platform variables itself; these do not consume the configured 4-KB allowance.
    """
    env = APPLICATION_DEFAULTS | OBSERVABILITY_DEFAULTS | dict(source)
    public = env.get('TRADINGVIEW_MCP_PUBLIC_HOST','')
    if not PUBLIC_HOST.fullmatch(public):
        raise ValueError('Invalid TRADINGVIEW_MCP_PUBLIC_HOST authority')
    if any(not isinstance(v,str) or '\x00' in v for v in env.values()):
        raise ValueError('Environment values must be literal NUL-free strings')
    def integer(key, low, high=None):
        value=env[key]
        if not re.fullmatch(r'\d+',value) or int(value)<low or (high is not None and int(value)>high):
            raise ValueError('Invalid range for '+key)
        return int(value)
    integer('MARKETAUX_DAILY_BUDGET',0)
    integer('PROXY_PORT',1,65535)
    if integer('PROXY_SESSION_MIN',1)>integer('PROXY_SESSION_MAX',1):
        raise ValueError('Invalid proxy session bounds')
    if env['PROXY_ENABLED'] not in ('true','false'):
        raise ValueError('PROXY_ENABLED requires a literal boolean')
    if not re.fullmatch(r'(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?',env['PROXY_HOST']):
        raise ValueError('Invalid PROXY_HOST hostname')
    if env['TRADINGVIEW_MCP_ENVIRONMENT'] not in ('development','test','production'):
        raise ValueError('Invalid observability environment')
    reserved={'AWS_REGION','AWS_DEFAULT_REGION','AWS_EXECUTION_ENV','AWS_LAMBDA_FUNCTION_NAME',
        'AWS_LAMBDA_FUNCTION_MEMORY_SIZE','AWS_LAMBDA_FUNCTION_VERSION','AWS_LAMBDA_INITIALIZATION_TYPE',
        'AWS_LAMBDA_LOG_GROUP_NAME','AWS_LAMBDA_LOG_STREAM_NAME','AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY',
        'AWS_SESSION_TOKEN','AWS_LAMBDA_RUNTIME_API','_HANDLER','_X_AMZN_TRACE_ID','LAMBDA_TASK_ROOT','LAMBDA_RUNTIME_DIR'}
    if sum(len(k.encode())+len(v.encode()) for k,v in env.items() if k not in reserved)>4096:
        raise ValueError('Configured environment exceeds Lambda 4-KB limit')
    return env


class LambdaBoundary:
    """Exact authority/origin/method policy; passes SDK lifespan through unchanged."""
    def __init__(self, app, public_host):
        self.app=app
        self.hosts={public_host,public_host+':443','localhost','localhost:8000',
                    '127.0.0.1','127.0.0.1:8000','[::1]','[::1]:8000'}

    async def __call__(self,scope,receive,send):
        if scope['type']!='http':
            return await self.app(scope,receive,send)
        headers=scope.get('headers',[])
        hosts=[v.decode('latin-1') for k,v in headers if k.lower()==b'host']
        status=None
        allow=[]
        if len(hosts)!=1 or hosts[0] not in self.hosts:
            status=421
        elif any(k.lower()==b'origin' for k,_ in headers):
            status=403
        elif scope['path'] in ('/mcp','/mcp/'):
            if scope['method']!='POST':
                status=405
                allow=[(b'allow',b'POST')]
            else:
                scope=dict(scope,path='/mcp',raw_path=b'/mcp')
        if status:
            await send({'type':'http.response.start','status':status,
                        'headers':[(b'content-type',b'application/json')]+allow})
            return await send({'type':'http.response.body','body':b'{"error":"request rejected"}'})
        return await self.app(scope,receive,send)


def create_app():
    # Docker/platform defaults are not part of Lambda's configured 4-KB map.
    env=validate_environment({k:v for k,v in os.environ.items() if k in CONFIGURED_KEYS})
    for key in APPLICATION_DEFAULTS:
        os.environ[key]=env[key]
    from tradingview_mcp.observability import configure, ObservedApp
    telemetry = configure(env)
    # Import only after environment validation. No cloud/store/provider startup call.
    from tradingview_mcp.server import mcp
    from mcp.server.transport_security import TransportSecuritySettings
    if mcp._session_manager is not None:
        raise RuntimeError('Lambda application must be created once per process')
    boundary_hosts=LambdaBoundary(None,env['TRADINGVIEW_MCP_PUBLIC_HOST']).hosts
    mcp.settings.stateless_http=True
    mcp.settings.json_response=True
    mcp.settings.transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,allowed_hosts=sorted(boundary_hosts),allowed_origins=[])
    telemetry.wrap_tools(mcp._tool_manager)
    return ObservedApp(LambdaBoundary(mcp.streamable_http_app(),env['TRADINGVIEW_MCP_PUBLIC_HOST']), telemetry)


def main():
    import uvicorn
    try:
        app=create_app()
    except ValueError:
        # Environment may contain credentials. Never echo values or exception context.
        from tradingview_mcp.observability import Telemetry
        Telemetry().emit('ERROR', operation='startup', outcome='invalid_configuration')
        raise SystemExit(1) from None
    except Exception as error:
        from tradingview_mcp.observability import Telemetry
        Telemetry().failure('startup', error)
        raise SystemExit(1) from None
    try:
        uvicorn.run(app,host='0.0.0.0',port=8000,workers=1,proxy_headers=False,
                    access_log=False,log_level='warning')
    except (Exception, SystemExit) as error:
        app.telemetry.failure('startup', error)
        raise SystemExit(1) from None


if __name__=='__main__':
    main()
