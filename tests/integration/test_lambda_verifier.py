"""Independent read-only snapshots exercise gateway and release validation."""
import copy
import importlib.util
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[2]


def verifier():
    spec=importlib.util.spec_from_file_location('v',ROOT/'scripts/verify_lambda.py')
    v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v);return v


def gateway():
    alias='arn:aws:lambda:ca-central-1:123456789012:function:test:live'
    api='abc123'
    routes=[{'RouteId':str(i),'RouteKey':key,'AuthorizationType':'CUSTOM','AuthorizerId':'auth','Target':'integrations/integration'} for i,key in enumerate(['ANY /mcp','ANY /mcp/','GET /health'])]
    statements=[{'Effect':'Allow','Action':'lambda:InvokeFunction','Resource':alias,
        'Principal':{'Service':'apigateway.amazonaws.com'},'Condition':{'StringEquals':{'AWS:SourceAccount':'123456789012'},'ArnLike':{'AWS:SourceArn':f'arn:aws:execute-api:ca-central-1:123456789012:{api}/$default/{path}'}}} for path in ['*/mcp','*/mcp/','GET/health']]
    return {'api':{'ApiId':api,'ProtocolType':'HTTP','ApiEndpoint':f'https://{api}.execute-api.ca-central-1.amazonaws.com'},
        'stage':{'StageName':'$default','AutoDeploy':True},
        'authorizer':{'AuthorizerId':'auth','AuthorizerType':'REQUEST','IdentitySource':['$request.header.Authorization'],'AuthorizerResultTtlInSeconds':0},
        'routes':routes,'integration':{'IntegrationId':'integration','IntegrationType':'AWS_PROXY','IntegrationMethod':'POST','IntegrationUri':alias,'PayloadFormatVersion':'2.0','TimeoutInMillis':30000},
        'alias_policy':{'Statement':statements},'other_policies':[],'function_urls':[]},alias


def test_exact_supplied_gateway_profile_accepted():
    s,alias=gateway()
    assert verifier().assess_gateway(s,alias,'123456789012','ca-central-1')['route_ids']==['0','1','2']


@pytest.mark.parametrize('case',['public_route','wrong_stage','disabled_endpoint','wrong_alias','wrong_payload','unscoped_permission','function_url','extra_policy','bypass_route','cache'])
def test_gateway_bypass_and_unsupported_profiles_rejected(case):
    s,alias=gateway()
    if case=='public_route':s['routes'][0]['AuthorizationType']='NONE'
    elif case=='wrong_stage':s['stage']['AutoDeploy']=False
    elif case=='disabled_endpoint':s['api']['DisableExecuteApiEndpoint']=True
    elif case=='wrong_alias':s['integration']['IntegrationUri']=alias.replace(':live',':1')
    elif case=='wrong_payload':s['integration']['PayloadFormatVersion']='1.0'
    elif case=='unscoped_permission':s['alias_policy']['Statement'][0]['Condition']['ArnLike']['AWS:SourceArn']='*'
    elif case=='function_url':s['function_urls']=['url']
    elif case=='extra_policy':s['other_policies']=[{'Effect':'Allow','Principal':'*'}]
    elif case=='bypass_route':s['routes'].append({'RouteId':'other','RouteKey':'GET /mcp','Target':'integrations/integration','AuthorizationType':'NONE'})
    elif case=='cache':s['authorizer']['AuthorizerResultTtlInSeconds']=300
    with pytest.raises(ValueError):verifier().assess_gateway(s,alias,'123456789012','ca-central-1')


def test_manifest_config_identity_and_index_rejection():
    v=verifier();manifest={'schemaVersion':2,'config':{'digest':'sha256:'+'a'*64},'layers':[]}
    assert v.verify_publication(manifest,'sha256:'+'a'*64,{'architecture':'arm64','os':'linux'})
    with pytest.raises(ValueError):v.verify_publication({'manifests':[]},'sha256:'+'a'*64,{})
    with pytest.raises(ValueError):v.verify_publication(manifest,'sha256:'+'b'*64,{'architecture':'arm64','os':'linux'})


def test_status_code_alone_or_authorizer_500_never_proves_denial():
    v=verifier()
    assert not v.denial_proven({'status_code':403,'gateway_request_id':'request'},403,'request')
    assert not v.denial_proven({'status_code':500,'gateway_request_id':'request','integration_status':'-','platform_request_id':'-'},500,'request')
    assert v.denial_proven({'status_code':403,'gateway_request_id':'request','integration_status':'-','platform_request_id':'-'},403,'request')


def test_live_control_plane_has_no_mutating_sdk_calls():
    # Audit the explicit client method surface, not network-dependent behavior.
    import ast
    tree=ast.parse((ROOT/'scripts/verify_lambda.py').read_text())
    forbidden=('create_','update_','delete_','put_','publish_','add_permission','remove_permission','invoke')
    calls=[n.func.attr for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)]
    assert not any(call.startswith(forbidden) for call in calls)


@pytest.mark.parametrize('explicit_clear',[False,True])
@pytest.mark.parametrize('tracing',[False,True])
def test_preflight_preserves_omitted_and_clears_explicit_credential(tmp_path,monkeypatch,explicit_clear,tracing):
    """All clients are read-only fakes; values are synthetic and never printed."""
    import json
    from types import SimpleNamespace
    from tradingview_mcp import lambda_server
    v=verifier();snapshot,alias=gateway()
    source='c'*40;lock='d'*64;uri='123456789012.dkr.ecr.ca-central-1.amazonaws.com/repo@sha256:'+'a'*64
    previous={'ImageUri':uri,'DeploymentRevision':'old','SourceCommit':source,'LockSha256':lock,'ApiId':'abc123','AuthorizerId':'auth','RollbackVersion':''}
    class CF:
        def describe_stacks(self,**kw):return {'Stacks':[{'Parameters':[{'ParameterKey':k,'ParameterValue':x} for k,x in previous.items()],
            'Outputs':[{'OutputKey':'FunctionArn','OutputValue':alias.removesuffix(':live')}]+[{'OutputKey':k,'OutputValue':str(i)} for i,k in enumerate(['McpRouteId','McpSlashRouteId','HealthRouteId'])]}]}
    class Lambda:
        def can_paginate(self,method):return False
        def list_versions_by_function(self,**kw):return {'Versions':[{'Description':'Revision old','Version':'1'}]}
        def get_function_configuration(self,**kw):return {'Environment':{'Variables':{'PROXY_PASSWORD':'synthetic-keep'}}}
        def get_policy(self,**kw):return {'Policy':json.dumps({'Statement':[{'Effect':'Allow','Principal':{'Service':'apigateway.amazonaws.com'},'Action':'lambda:InvokeFunction','Condition':{'ArnLike':{'AWS:SourceArn':'arn:aws:execute-api:ca-central-1:123456789012:abc123/authorizers/auth'}}}]})}
        def get_account_settings(self):return {'AccountLimit':{'UnreservedConcurrentExecutions':200}}
        def get_function_concurrency(self,**kw):return {'ReservedConcurrentExecutions':5}
    class API:
        def get_api(self,**kw):return snapshot['api']
        def get_stage(self,**kw):return snapshot['stage']
        def get_authorizer(self,**kw):return snapshot['authorizer']|{'AuthorizerUri':'arn:aws:apigateway:ca-central-1:lambda:path/2015-03-31/functions/arn:aws:lambda:ca-central-1:123456789012:function:auth/invocations'}
        def can_paginate(self,method):return False
        def get_routes(self,**kw):return {'Items':snapshot['routes']}
    clients={'cloudformation':CF(),'lambda':Lambda(),'apigatewayv2':API(),'sts':SimpleNamespace(get_caller_identity=lambda:{'Account':'123456789012'})}
    monkeypatch.setattr(v,'aws_session',lambda region:SimpleNamespace(client=lambda service:clients[service]))
    monkeypatch.setattr(v,'registry_identity',lambda *a:('sha256:'+'a'*64,{'org.opencontainers.image.revision':source,'tradingview.lock-sha256':lock}))
    observed=[];original=lambda_server.validate_environment
    def capture(env):observed.append(env.copy());return original(env)
    monkeypatch.setattr(lambda_server,'validate_environment',capture)
    entries=[{'ParameterKey':'DeploymentRevision','ParameterValue':'new'}]
    if explicit_clear:entries.append({'ParameterKey':'ProxyPassword','ParameterValue':''})
    if tracing:entries.extend([{'ParameterKey':'TracingMode','ParameterValue':'Active'},{'ParameterKey':'ObservabilityEnvironment','ParameterValue':'production'}])
    path=tmp_path/'private.json';path.write_text(json.dumps(entries));path.chmod(0o600)
    assert v.preflight(SimpleNamespace(region='ca-central-1',stack='test',parameters_file=str(path)))==0
    assert observed[0]['PROXY_PASSWORD']==('' if explicit_clear else 'synthetic-keep')
    assert observed[0]['TRADINGVIEW_MCP_ENVIRONMENT']==('production' if tracing else 'development')


@pytest.mark.parametrize('wrong_version',[False,True])
def test_cloudwatch_gateway_to_startup_join_uses_real_report_records(wrong_version):
    import json
    from datetime import datetime,timezone
    from types import SimpleNamespace
    v=verifier();r=v.new_report('live');r['started_at']='2026-11-02T00:00:00+00:00';r['completed_at']='2026-11-02T00:01:00+00:00'
    uri='123456789012.dkr.ecr.ca-central-1.amazonaws.com/repo@sha256:'+'a'*64
    r['release']['resolved_image_uri']=uri
    t=r['target'];t.update(function_arn='arn:aws:lambda:ca-central-1:123456789012:function:test',function_version='1')
    base=int(datetime(2026,11,2,tzinfo=timezone.utc).timestamp()*1000)+1000
    keys=['initialization','discovery','tool_execution']
    gateway=[{'message':json.dumps({'requestId':'g'+str(i),'status':'200','integrationStatus':'200','integrationRequestId':'p'+str(i)}),'timestamp':base+i} for i in range(3)]
    platform=[{'message':f'REPORT RequestId: p{i}\tDuration: 5 ms'+ ('\tInit Duration: 100 ms' if i<2 else ''),
        'timestamp':base+i,'logStreamName':f'2026/11/02/[{"999" if wrong_version else "1"}]stream{i}'} for i in range(3)]
    class Logs:
        def filter_log_events(self,**kw):
            assert 'startTime' in kw and 'endTime' in kw
            return {'events':gateway if kw['logGroupName']=='gateway' else platform}
    session=SimpleNamespace(client=lambda service:Logs())
    observation={'snapshot':{'stage':{'AccessLogSettings':{'DestinationArn':'arn:aws:logs:ca-central-1:123456789012:log-group:gateway'}}},'log_group_name':'runtime','resolved_image_uri':uri}
    g,(correlations,cold)=v.observed_correlations(session,t,observation,r)
    requests=[q|{'stage':keys[i]} for i,q in enumerate(correlations)]
    side={'run_id':r['run_id'],'resolved_image_uri':uri,'gateway_correlations':correlations,
        'interactions':[{'interaction_id':'i','completed_success':True,'requests':requests}]}
    r['cold_start_evidence']=cold
    assert len(v.qualified_cold_starts(r,side))==(0 if wrong_version else 2)


def test_sanitized_snapshot_retains_policy_without_freeform_metadata():
    snapshot,alias=gateway()
    snapshot['authorizer']['Name']='arbitrary-untrusted-description'
    clean=verifier().sanitized_gateway_snapshot(snapshot)
    assert 'arbitrary-untrusted-description' not in str(clean)
    assert verifier().assess_gateway(clean,alias,'123456789012','ca-central-1')


@pytest.mark.parametrize('foreign_function',[False,True])
def test_resolve_target_reads_real_shapes_and_keeps_provider_values_private(foreign_function):
    from types import SimpleNamespace
    import json
    v=verifier();snapshot,alias=gateway()
    function=alias.removesuffix(':live')
    if foreign_function:function=function.replace('123456789012','999999999999')
    uri='123456789012.dkr.ecr.ca-central-1.amazonaws.com/repo@sha256:'+'a'*64
    class Missing(Exception):
        response={'Error':{'Code':'ResourceNotFoundException'}}
    class CF:
        def describe_stacks(self,**kw):
            out={'FunctionArn':function,'ApiId':'abc123','AuthorizerId':'auth','IntegrationId':'integration','LogGroupName':'runtime'}
            return {'Stacks':[{'StackId':'arn:aws:cloudformation:ca-central-1:123456789012:stack/test/uuid','Outputs':[{'OutputKey':k,'OutputValue':x} for k,x in out.items()]}]}
    class Lambda:
        def get_alias(self,**kw):return {'AliasArn':alias,'FunctionVersion':'1'}
        def get_function(self,**kw):
            return {'Code':{'ResolvedImageUri':uri},'Configuration':{'Architectures':['arm64'],'Timeout':25,'Environment':{'Variables':{
                'TRADINGVIEW_MCP_PUBLIC_HOST':'abc123.execute-api.ca-central-1.amazonaws.com',
                'TRADINGVIEW_MCP_SOURCE_COMMIT':'c'*40,'TRADINGVIEW_MCP_LOCK_SHA256':'d'*64,
                'TRADINGVIEW_MCP_DEPLOYMENT_REVISION':'revision','PROXY_PASSWORD':'synthetic-private-provider-value',
                'MARKETAUX_DAILY_BUDGET':'90','PROXY_ENABLED':'true','PROXY_HOST':'p.webshare.io',
                'PROXY_PORT':'80','PROXY_SESSION_MIN':'1','PROXY_SESSION_MAX':'250'}}}}
        def can_paginate(self,method):return True
        def get_paginator(self,method):
            key='Aliases' if method=='list_aliases' else 'Versions'
            value=[{'Name':'live'}] if key=='Aliases' else [{'Version':'1'}]
            return SimpleNamespace(paginate=lambda **kw:[{key:value}])
        def get_policy(self,**kw):
            if kw.get('Qualifier')=='live':return {'Policy':json.dumps(snapshot['alias_policy'])}
            raise Missing()
        def get_function_url_config(self,**kw):raise Missing()
    class API:
        def can_paginate(self,method):return False
        def get_integrations(self,**kw):return {'Items':[snapshot['integration']]}
        def get_integration(self,**kw):return snapshot['integration']
        def get_api(self,**kw):return snapshot['api']
        def get_stage(self,**kw):return snapshot['stage']
        def get_authorizer(self,**kw):return snapshot['authorizer']
        def get_routes(self,**kw):return {'Items':snapshot['routes']}
    clients={'cloudformation':CF(),'lambda':Lambda(),'apigatewayv2':API()}
    session=SimpleNamespace(region_name='ca-central-1',client=lambda service:clients[service])
    if foreign_function:
        with pytest.raises(ValueError):v.resolve_target(session,'test',uri)
    else:
        target,observation=v.resolve_target(session,'test',uri)
        assert target['gateway']['api_id']=='abc123'
        assert observation['_provider_values'][-1]=='synthetic-private-provider-value'
        assert 'synthetic-private-provider-value' not in json.dumps(observation['safe_configuration'])


def test_local_cli_profile_flag_selects_report_version(tmp_path, monkeypatch):
    v = verifier()
    # Stub the slow child test runs; this checks profile wiring, not test outcomes.
    monkeypatch.setattr(v, 'run_tests', lambda *a, **k: ('not_run', [], 0))
    rest = tmp_path / 'rest.json'
    assert v.main(['local', '--report', str(rest), '--profile', 'rest']) in (0, 2)
    import json
    report = json.loads(rest.read_text())
    assert report['schema_version'] == 2 and report['profile'] == 'rest'
    http = tmp_path / 'http.json'
    v.main(['local', '--report', str(http)])
    report = json.loads(http.read_text())
    assert report['schema_version'] == 1 and 'profile' not in report


def test_local_cli_rejects_unknown_profile(tmp_path):
    v = verifier()
    with pytest.raises(SystemExit) as exc:
        v.main(['local', '--report', str(tmp_path / 'x.json'), '--profile', 'websocket'])
    assert exc.value.code == 3
