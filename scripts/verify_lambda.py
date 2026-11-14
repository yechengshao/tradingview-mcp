#!/usr/bin/env python3
"""Read-only Lambda verification. Missing evidence never implies acceptance."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / 'specs/001-add-lambda-deployment/contracts/verification-report.schema.json'
STAGES = ('artifact_startup', 'health', 'client_initialization', 'tool_discovery',
          'tool_execution', 'authorization', 'invalid_tool_input', 'upstream_failure',
          'cold_start', 'concurrent_clients', 'docker_compatibility',
          'local_transport_compatibility', 'existing_unit_suite', 'release_identity',
          'release_lifecycle', 'documentation_walkthrough')


class ConfigurationError(ValueError):
    """A diagnostic written to exclude credential values."""


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


PROFILES = {'http': 1, 'rest': 2}
SCHEMA_V2_PATH = ROOT / 'specs/001-add-lambda-deployment/contracts/verification-report-v2.schema.json'


def new_report(mode, expected_image_uri=None, profile='http'):
    if profile not in PROFILES:
        raise ConfigurationError('Unsupported verification profile')
    report = {'schema_version':PROFILES[profile], 'mode':mode, 'run_id':str(uuid.uuid4()),
        'started_at':now(), 'completed_at':now(),
        'release':{'source_commit':git('rev-parse','HEAD'),
            'source_dirty':bool(git('status','--porcelain')), 'dependency_lock_sha256':digest(ROOT/'uv.lock'),
            'image_config_digest':None, 'expected_image_uri':expected_image_uri,
            'resolved_image_uri':None, 'architecture':'arm64'},
        'target':dict.fromkeys(('account_id','region','stack_id','function_arn','function_version','alias','endpoint','gateway')) | {'kind':'local' if mode=='local' else 'aws_lambda'},
        'additional_targets':[], 'stages':[{'name':name,'status':'not_run',
            'reason':'Required evidence not collected','duration_ms':0,'evidence':[]} for name in STAGES],
        'counts':dict.fromkeys(('attempted_interactions','passed_interactions','concurrent_clients','passed_health_checks','evidenced_fresh_starts'),0),
        'cold_start_evidence':[], 'live_market_probe':{'status':'not_run','reason':'Optional market probe not attempted','evidence':[]},
        'full_deployment_success':False,'authorization_evidence':None}
    if profile == 'rest':
        report['profile'] = 'rest'
    return report


def require_profile(report, profile):
    """Reject evidence produced under the other gateway profile (rest-migration.md)."""
    actual = 'rest' if report.get('schema_version') == PROFILES['rest'] else 'http'
    if profile not in PROFILES or actual != profile:
        raise ConfigurationError('Report profile %s cannot be used as %s evidence' % (actual, profile))


def stage(report, name, status, reason, evidence=None, duration_ms=0):
    record = next(s for s in report['stages'] if s['name']==name)
    record.update(status=status,reason=reason,evidence=evidence or [],duration_ms=duration_ms)


def evidence(path, description):
    return {'description':description,'ref':str(Path(path).resolve()),'sha256':digest(path)}


def write_json(path, obj):
    p=Path(path)
    p.parent.mkdir(parents=True,exist_ok=True)
    # Owner-only evidence can contain infrastructure identifiers; never credentials.
    fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    os.fchmod(fd,0o600)
    with os.fdopen(fd,'w') as f:
        json.dump(obj,f,indent=2)
        f.write('\n')


def validate(report):
    from jsonschema import Draft202012Validator, FormatChecker
    version = report.get('schema_version')
    if version == PROFILES['rest']:
        schema = json.loads(SCHEMA_V2_PATH.read_text())
    elif version == PROFILES['http']:
        schema = json.loads(SCHEMA_PATH.read_text())
    else:
        raise ConfigurationError('Unsupported report schema_version')
    Draft202012Validator(schema,format_checker=FormatChecker()).validate(report)
    if instant(report['completed_at']) < instant(report['started_at']):
        raise ConfigurationError('invalid report observation window')
    if report['counts']['passed_interactions'] > report['counts']['attempted_interactions']:
        raise ConfigurationError('passed interactions exceed attempts')


def exit_code(report):
    if any(s['status']=='fail' for s in report['stages']):
        return 1
    return 0 if report['full_deployment_success'] else 2


def sanitize(message, secrets=()):
    text=str(message)
    for value in secrets:
        if value: text=text.replace(value,'[REDACTED]')
    return re.sub(r'(?i)(Bearer\s+)[^\s,;]+',r'\1[REDACTED]',text)


def read_evidence(item):
    p=Path(item['ref'])
    if not p.is_file() or not item.get('sha256') or digest(p)!=item['sha256']:
        raise ConfigurationError('Missing or changed evidence artifact')
    return json.loads(p.read_text())


def instant(value):
    dt=datetime.fromisoformat(value.replace('Z','+00:00'))
    if dt.tzinfo is None: raise ConfigurationError('Evidence time requires timezone')
    return dt


def completed_interactions(report,sidecar):
    if sidecar.get('run_id')!=report['run_id'] or sidecar.get('resolved_image_uri')!=report['release']['resolved_image_uri']:
        return []
    targets={(t['function_arn'],t['function_version']) for t in [report['target']]+report['additional_targets']}
    fields=('gateway_request_id','platform_request_id','function_arn','function_version','log_stream','observed_at')
    correlations={tuple(c.get(f) for f in fields) for c in sidecar.get('gateway_correlations',[])
        if c.get('status_code')==200 and c.get('integration_status')=='200'
        and all(isinstance(c.get(f),str) and c[f] and c[f]!='-' for f in fields)}
    start,end=instant(report['started_at']),instant(report['completed_at'])
    valid=[];seen=set()
    for interaction in sidecar.get('interactions',[]):
        identity=interaction.get('interaction_id');requests=interaction.get('requests',[])
        if not interaction.get('completed_success') or not identity or identity in seen:continue
        seen.add(identity)
        if {q.get('stage') for q in requests}!={'initialization','discovery','tool_execution'}:continue
        try:
            if all(start<=instant(q['observed_at'])<=end and
                (q['function_arn'],q['function_version']) in targets and
                tuple(q.get(f) for f in fields) in correlations for q in requests):valid.append(interaction)
        except (KeyError,ValueError,TypeError):continue
    return valid


def qualified_cold_starts(report,sidecar):
    fields=('function_arn','function_version','log_stream','platform_request_id')
    valid_requests={tuple(q[f] for f in fields) for i in completed_interactions(report,sidecar) for q in i['requests']}
    start,end=instant(report['started_at']),instant(report['completed_at'])
    qualified={}
    for cold in report['cold_start_evidence']:
        key=tuple(cold[f] for f in fields)
        if cold['resolved_image_uri']!=report['release']['resolved_image_uri']:continue
        if not start<=instant(cold['observed_at'])<=end or key not in valid_requests:continue
        qualified[key[:3]]=cold
    return list(qualified.values())


def validate_lifecycle(report,lifecycle):
    from jsonschema import Draft202012Validator, FormatChecker
    schema=json.loads(SCHEMA_PATH.read_text())
    if list(Draft202012Validator({'$ref':'#/$defs/lifecycleEvidence','$defs':schema['$defs']},format_checker=FormatChecker()).iter_errors(lifecycle)):
        raise ConfigurationError('Invalid lifecycle evidence')
    uri=report['release']['expected_image_uri']
    if not (lifecycle['starting_image_uri']==lifecycle['rollback_image_uri']==uri) or lifecycle['updated_image_uri']==uri:
        raise ConfigurationError('Lifecycle release mismatch')
    targets={t['stack_id'] for t in [report['target']]+report['additional_targets']}
    if not set(lifecycle['target_stack_ids'])<=targets:raise ConfigurationError('Lifecycle target mismatch')
    for step in lifecycle['steps'].values():
        if step['status']=='pass' and not step['evidence']:raise ConfigurationError('Lifecycle pass lacks evidence')
        for item in step['evidence']:read_evidence(item)
    # Configuration-only acceptance is additional to distinct-image acceptance.
    env=[]
    for item in lifecycle['steps']['update']['evidence']:
        data=read_evidence(item)
        if data.get('kind')=='environment_update_rollback':env.append(data)
    if all(s['status']=='pass' for s in lifecycle['steps'].values()):
        if not any(e.get('status')=='pass' and e.get('same_image_uri')==uri and
            e.get('starting_revision')==e.get('rollback_revision') and
            e.get('starting_revision') and e.get('updated_revision')!=e.get('starting_revision') for e in env):
            raise ConfigurationError('Missing environment-only update/rollback evidence')
    return all(s['status']=='pass' for s in lifecycle['steps'].values())


def lifecycle_example(image_uri,updated_uri,stack_id):
    return {'schema_version':1,'reviewer':'unperformed example','completed_at':now(),
        'starting_image_uri':image_uri,'updated_image_uri':updated_uri,'rollback_image_uri':image_uri,
        'target_stack_ids':[stack_id],
        'steps':{name:{'status':'not_run','reason':'Procedure only; not observed','evidence':[]} for name in
            ('clean_checkout_deploy','update','rollback','cleanup','documentation_review')}}


def maximum_overlap(interactions):
    events=[]
    for item in interactions:
        try:
            start,end=instant(item['started_at']),instant(item['completed_at'])
            if start<end:
                events.extend([(start,1),(end,-1)])
        except (KeyError,ValueError):continue
    current=maximum=0
    for _,delta in sorted(events):
        current+=delta;maximum=max(maximum,current)
    return maximum


def combine_reports(local,live,lifecycle):
    validate(local);validate(live)
    if local['mode']!='local' or live['mode']!='live':raise ConfigurationError('Expected local and live inputs')
    keys=('source_commit','source_dirty','dependency_lock_sha256','architecture')
    if any(local['release'][k]!=live['release'][k] for k in keys):raise ConfigurationError('Release provenance mismatch')
    for key in ('image_config_digest','expected_image_uri'):
        if local['release'][key] is not None and live['release'][key] is not None and local['release'][key]!=live['release'][key]:
            raise ConfigurationError('Image identity mismatch')
    if next(s for s in live['stages'] if s['name']=='authorization')['status']=='pass':
        revalidate_authorization(live)
    result=copy.deepcopy(live);result['mode']='combine';result['full_deployment_success']=False
    # Retain the live run window/ID: cold-start sidecars are bound to it.
    local_names={'upstream_failure','docker_compatibility','local_transport_compatibility','existing_unit_suite'}
    for name in STAGES:
        a=next(s for s in local['stages'] if s['name']==name)
        b=next(s for s in live['stages'] if s['name']==name)
        chosen=a if name in local_names else b
        if name in ('artifact_startup','health','invalid_tool_input'):
            status='fail' if 'fail' in (a['status'],b['status']) else ('pass' if a['status']==b['status']=='pass' else 'not_run')
            chosen={'name':name,'status':status,'reason':'Local artifact and live evidence both required',
                    'duration_ms':a['duration_ms']+b['duration_ms'],'evidence':a['evidence']+b['evidence']}
        result['stages'][STAGES.index(name)]=copy.deepcopy(chosen)
    if not local['release']['image_config_digest'] or not live['release']['image_config_digest']:
        stage(result,'release_identity','not_run','Local or deployed image configuration identity unavailable')
    if result['release']['expected_image_uri'] and result['release']['resolved_image_uri']:
        if result['release']['expected_image_uri']!=result['release']['resolved_image_uri']:
            stage(result,'release_identity','fail','Expected and resolved image differ')
    else:
        stage(result,'release_identity','not_run','Published expected/resolved release identity unavailable')
    sidecars=[]
    for s in live['stages']:
        for item in s['evidence']:
            data=read_evidence(item)
            if data.get('kind')=='completed_interactions':sidecars.append(data)
    qualified=qualified_cold_starts(live,sidecars[0]) if len(sidecars)==1 else []
    complete=completed_interactions(live,sidecars[0]) if len(sidecars)==1 else []
    if len({i.get('interaction_id') for i in complete})!=live['counts']['passed_interactions'] or not complete:
        stage(result,'tool_execution','not_run','Completed-interaction evidence does not cover reported successes')
    if live['counts']['concurrent_clients']>=5 and maximum_overlap(complete)<5:
        stage(result,'concurrent_clients','not_run','Five overlapping successful interactions not evidenced')
    result['cold_start_evidence']=qualified
    result['counts']['evidenced_fresh_starts']=len(qualified)
    if len(qualified)<2:stage(result,'cold_start','not_run','Insufficient correlated successful-interaction startup evidence')
    if lifecycle is not None:
        passed=validate_lifecycle(result,lifecycle)
        lifecycle_refs=[item for step in lifecycle['steps'].values() for item in step['evidence']]
        stage(result,'release_lifecycle','pass' if passed else ('fail' if any(s['status']=='fail' for s in lifecycle['steps'].values()) else 'not_run'),'Recorded operator lifecycle evidence',lifecycle_refs)
        doc=lifecycle['steps']['documentation_review']
        stage(result,'documentation_walkthrough',doc['status'],doc['reason'],doc['evidence'])
    for s in result['stages']:
        for item in s['evidence']:read_evidence(item)
    c=result['counts']
    thresholds=c['attempted_interactions']==c['passed_interactions'] and c['passed_interactions']>=20 and c['concurrent_clients']>=5 and c['passed_health_checks']>=10 and c['evidenced_fresh_starts']>=2
    result['full_deployment_success']=all(s['status']=='pass' for s in result['stages']) and thresholds
    validate(result)
    return result
def run_tests(report, selectors, directory, label, env=None):
    """Execute required checks, retaining only sanitized count/identity evidence."""
    import time
    import xml.etree.ElementTree as ET
    started=time.monotonic()
    with __import__('tempfile').TemporaryDirectory(prefix='lambda-tests-') as temp:
        junit=Path(temp)/'results.xml'
        result=subprocess.run([sys.executable,'-m','pytest','-q',*selectors,'--junitxml',str(junit)],
            cwd=ROOT,env=env,capture_output=True,text=True,timeout=300)
        tests=[]
        if junit.exists():
            for test in ET.parse(junit).iter('testcase'):
                tests.append({'name':test.attrib.get('classname','')+'.'+test.attrib['name'],
                    'status':'fail' if test.find('failure') is not None or test.find('error') is not None else ('not_run' if test.find('skipped') is not None else 'pass')})
        status='fail' if result.returncode or not tests or any(t['status']=='fail' for t in tests) else ('not_run' if any(t['status']=='not_run' for t in tests) else 'pass')
        path=directory/(label+'.json')
        write_json(path,{'run_id':report['run_id'],'release':report['release'],
            'selection':selectors,'returncode':result.returncode,'tests':tests})
        return status,[evidence(path,label+' required checks')],(time.monotonic()-started)*1000


def local_mode(args):
    report=new_report('local',args.expected_image_uri)
    directory=Path(args.report).resolve().parent/(report['run_id']+'-evidence')
    # Source checks cannot establish anything about an untested image.
    status,refs,ms=run_tests(report,['tests/unit','tests/integration/test_release_workflow_contract.py'],directory,'unit-and-workflow')
    stage(report,'existing_unit_suite',status,'Hermetic unit suite and frozen original workflow contract',refs,ms)
    status,refs,ms=run_tests(report,['tests/integration/test_original_transports.py::test_original_launch_files_are_unchanged','tests/integration/test_original_transports.py::test_original_stdio_and_http_still_match_frozen_catalog'],directory,'original-launch')
    stage(report,'local_transport_compatibility',status,'Original separate-process launch/catalog checks',refs,ms)
    try:
        info=subprocess.run(['docker','info','--format','{{.Architecture}}'],capture_output=True,text=True,timeout=15)
        native=info.returncode==0 and info.stdout.strip() in ('arm64','aarch64')
    except (OSError,subprocess.TimeoutExpired):native=False
    if native and args.lambda_image:
        inspected=subprocess.run(['docker','image','inspect',args.lambda_image],capture_output=True,text=True,check=True)
        meta=json.loads(inspected.stdout)[0]
        labels=meta['Config'].get('Labels') or {}
        if meta['Architecture']!='arm64':raise ConfigurationError('Candidate image must be ARM64')
        if labels.get('org.opencontainers.image.revision')!=report['release']['source_commit'] or labels.get('tradingview.lock-sha256')!=report['release']['dependency_lock_sha256']:
            raise ConfigurationError('Local image source/lock provenance mismatch')
        if labels.get('tradingview.source-dirty')!=str(report['release']['source_dirty']).lower():raise ConfigurationError('Local image dirty-source identity mismatch')
        report['release']['image_config_digest']=meta['Id']
        env=dict(os.environ,LAMBDA_TEST_IMAGE=args.lambda_image,REQUIRE_LAMBDA_CONTAINER_TESTS='1')
        status,refs,ms=run_tests(report,['tests/integration/test_lambda_container.py'],directory,'candidate-image',env)
        for name in ['artifact_startup','health','client_initialization','tool_discovery','tool_execution','invalid_tool_input','upstream_failure']:
            stage(report,name,status,'Native no-source-mount candidate image checks',refs,ms)
    else:
        for name in ['artifact_startup','health','client_initialization','tool_discovery','tool_execution','invalid_tool_input','upstream_failure']:
            stage(report,name,'not_run','Native ARM64 Docker daemon and candidate image required')
    if native and args.baseline_image:
        env=dict(os.environ,BASELINE_TEST_IMAGE=args.baseline_image,REQUIRE_BASELINE_CONTAINER_TESTS='1')
        status,refs,ms=run_tests(report,['tests/integration/test_original_transports.py::test_original_image_behavior'],directory,'baseline-image',env)
        stage(report,'docker_compatibility',status,'Pinned-source original image check',refs,ms)
    else:stage(report,'docker_compatibility','not_run','Native Docker and pinned baseline image required')
    report['completed_at']=now()
    return report
def verify_publication(manifest, config_digest, config):
    if 'manifests' in manifest or manifest.get('schemaVersion')!=2 or manifest.get('config',{}).get('digest')!=config_digest:
        raise ConfigurationError('Published manifest must be the tested single-image configuration')
    if config.get('architecture')!='arm64' or config.get('os')!='linux':
        raise ConfigurationError('Image must be linux/arm64')
    return True


def assess_gateway(snapshot,alias_arn,account,region):
    api=snapshot['api'];api_id=api['ApiId'];auth=snapshot['authorizer'];integration=snapshot['integration']
    base=f'https://{api_id}.execute-api.{region}.amazonaws.com'
    if api.get('ProtocolType')!='HTTP' or api.get('DisableExecuteApiEndpoint',False) or api['ApiEndpoint']!=base:
        raise ConfigurationError('Unsupported supplied HTTP API profile')
    if snapshot['stage'].get('StageName')!='$default' or not snapshot['stage'].get('AutoDeploy'):
        raise ConfigurationError('Supplied auto-deploy default stage required')
    identities=auth.get('IdentitySource',[])
    if auth.get('AuthorizerType')!='REQUEST' or '$request.header.Authorization' not in identities:
        raise ConfigurationError('Supplied Authorization-header REQUEST authorizer required')
    if auth.get('AuthorizerResultTtlInSeconds',300)>0 and '$context.routeKey' not in identities:
        raise ConfigurationError('Authorizer cache must be disabled or scoped by route key')
    expected={'IntegrationType':'AWS_PROXY','IntegrationMethod':'POST','IntegrationUri':alias_arn,'PayloadFormatVersion':'2.0','TimeoutInMillis':30000}
    if any(integration.get(k)!=v for k,v in expected.items()):raise ConfigurationError('Gateway integration mismatch')
    required={'ANY /mcp','ANY /mcp/','GET /health'}
    routes=[r for r in snapshot['routes'] if r.get('Target')=='integrations/'+integration['IntegrationId']]
    if len(routes)!=3 or {r['RouteKey'] for r in routes}!=required:
        raise ConfigurationError('Unexpected routes invoking feature integration')
    if any(r.get('AuthorizationType')!='CUSTOM' or r.get('AuthorizerId')!=auth['AuthorizerId'] for r in routes):
        raise ConfigurationError('Feature routes require supplied CUSTOM authorization')
    for route in snapshot['routes']:
        if route not in routes and route['RouteKey'].split(' ',1)[-1] in ('/mcp','/mcp/','/health'):
            raise ConfigurationError('Conflicting method-specific route')
    prefix=f'arn:aws:execute-api:{region}:{account}:{api_id}/$default/'
    allowed={prefix+'*/mcp',prefix+'*/mcp/',prefix+'GET/health'}
    statements=snapshot['alias_policy'].get('Statement',[])
    observed=[]
    for p in statements:
        c=p.get('Condition',{})
        source=c.get('ArnLike',{}).get('AWS:SourceArn')
        if p.get('Effect')!='Allow' or p.get('Action')!='lambda:InvokeFunction' or p.get('Resource')!=alias_arn or p.get('Principal')!={'Service':'apigateway.amazonaws.com'} or c.get('StringEquals',{}).get('AWS:SourceAccount')!=account or source not in allowed:
            raise ConfigurationError('Unexpected alias invocation permission')
        observed.append(source)
    if len(observed)!=3 or set(observed)!=allowed or snapshot['other_policies'] or snapshot['function_urls']:
        raise ConfigurationError('Missing scoped permissions or alternate invocation path')
    for other in snapshot.get('other_integrations',[]):
        if alias_arn.rsplit(':',1)[0] in other.get('IntegrationUri',''):
            raise ConfigurationError('Alternate integration references this function')
    return {'api_id':api_id,'stage_name':'$default','authorizer_id':auth['AuthorizerId'],
        'integration_id':integration['IntegrationId'],'route_ids':[r['RouteId'] for r in routes],
        'payload_format_version':'2.0'}


def sanitized_gateway_snapshot(snapshot):
    fields={'api':('ApiId','ProtocolType','ApiEndpoint','DisableExecuteApiEndpoint'),
        'stage':('StageName','AutoDeploy'),
        'authorizer':('AuthorizerId','AuthorizerType','IdentitySource','AuthorizerResultTtlInSeconds'),
        'integration':('IntegrationId','IntegrationType','IntegrationMethod','IntegrationUri','PayloadFormatVersion','TimeoutInMillis')}
    result={k:{field:snapshot[k][field] for field in names if field in snapshot[k]} for k,names in fields.items()}
    route_fields=('RouteId','RouteKey','AuthorizationType','AuthorizerId','Target')
    result['routes']=[{k:r[k] for k in route_fields if k in r} for r in snapshot['routes']]
    result.update({k:snapshot[k] for k in ('alias_policy','other_policies','function_urls')})
    result['other_integrations']=[{k:i[k] for k in ('IntegrationId','IntegrationUri') if k in i} for i in snapshot.get('other_integrations',[])]
    return result


def denial_proven(event,status,request_id):
    return status in (401,403) and event.get('gateway_request_id')==request_id and event.get('status_code')==status and event.get('integration_status')=='-' and event.get('platform_request_id')=='-'


def aws_session(region):
    try:import boto3
    except ImportError:raise ConfigurationError('Install optional deployment tooling for AWS reads') from None
    return boto3.Session(region_name=region)


def pages(client,method,key,**kwargs):
    if client.can_paginate(method):
        for page in client.get_paginator(method).paginate(**kwargs):
            yield from page.get(key,[])
        return
    token=None
    while True:
        args=dict(kwargs)
        if token:args['NextToken']=token
        data=getattr(client,method)(**args)
        yield from data.get(key,[])
        token=data.get('NextToken')
        if not token:break


def optional_read(client,method,**kwargs):
    try:return getattr(client,method)(**kwargs)
    except Exception as exc:
        code=getattr(exc,'response',{}).get('Error',{}).get('Code')
        if code in ('ResourceNotFoundException','PolicyNotFoundException'):return None
        raise


def function_exposure(lam,function):
    aliases=list(pages(lam,'list_aliases','Aliases',FunctionName=function))
    versions=lam.get_paginator('list_versions_by_function').paginate(FunctionName=function)
    qualifiers=[None]+[a['Name'] for a in aliases]
    # Version policies, including retained versions, must not expose another path.
    qualifiers += [v['Version'] for page in versions for v in page.get('Versions',[]) if v['Version']!='$LATEST']
    policies=[];urls=[]
    for qualifier in qualifiers:
        args={'FunctionName':function}
        if qualifier:args['Qualifier']=qualifier
        policy=optional_read(lam,'get_policy',**args)
        if policy and qualifier!='live':policies.extend(json.loads(policy['Policy']).get('Statement',[]))
        if qualifier is None or any(a['Name']==qualifier for a in aliases):
            url=optional_read(lam,'get_function_url_config',**args)
            if url:urls.append({'qualifier':qualifier})
    return policies,urls


def resolve_target(session,stack,expected_uri):
    cf=session.client('cloudformation');lam=session.client('lambda');api=session.client('apigatewayv2')
    stacks=cf.describe_stacks(StackName=stack)['Stacks']
    if len(stacks)!=1:raise ConfigurationError('Expected one runtime stack')
    obj=stacks[0];outputs={x['OutputKey']:x['OutputValue'] for x in obj.get('Outputs',[])}
    function=outputs['FunctionArn'];alias=lam.get_alias(FunctionName=function,Name='live')
    version=alias['FunctionVersion'];config=lam.get_function(FunctionName=function,Qualifier=version)
    if config['Code'].get('ResolvedImageUri')!=expected_uri:raise ConfigurationError('Active resolved image differs from expected release')
    account=function.split(':')[4];region=function.split(':')[3]
    if region!=session.region_name or obj['StackId'].split(':')[3:5]!=[region,account]:raise ConfigurationError('Function stack/account/region mismatch')
    if not expected_uri.startswith(f'{account}.dkr.ecr.{region}.amazonaws.com/'):
        raise ConfigurationError('Function image must share its account and region')
    api_id=outputs['ApiId'];auth_id=outputs['AuthorizerId'];integration_id=outputs['IntegrationId']
    policies,urls=function_exposure(lam,function)
    integrations=list(pages(api,'get_integrations','Items',ApiId=api_id))
    snapshot={'api':api.get_api(ApiId=api_id),'stage':api.get_stage(ApiId=api_id,StageName='$default'),
        'authorizer':api.get_authorizer(ApiId=api_id,AuthorizerId=auth_id),
        'routes':list(pages(api,'get_routes','Items',ApiId=api_id)),
        'integration':api.get_integration(ApiId=api_id,IntegrationId=integration_id),
        'alias_policy':json.loads(lam.get_policy(FunctionName=function,Qualifier='live')['Policy']),
        'other_policies':policies,'function_urls':urls,
        'other_integrations':[i for i in integrations if i['IntegrationId']!=integration_id]}
    gateway=assess_gateway(snapshot,alias['AliasArn'],account,region)
    env=config['Configuration'].get('Environment',{}).get('Variables',{})
    # Keep resolved provider values solely in memory for validation; never evidence.
    from tradingview_mcp.lambda_server import validate_environment,APPLICATION_DEFAULTS
    validate_environment(env)
    if env['TRADINGVIEW_MCP_PUBLIC_HOST']!=f'{api_id}.execute-api.{region}.amazonaws.com':raise ConfigurationError('Public authority configuration mismatch')
    safe_keys=set(APPLICATION_DEFAULTS)-{'MARKETAUX_API_TOKEN','PROXY_USERNAME_PREFIX','PROXY_PASSWORD'}
    safe={k:env[k] for k in sorted(safe_keys)}
    safe['deployment_revision']=env['TRADINGVIEW_MCP_DEPLOYMENT_REVISION']
    if config['Configuration']['Architectures']!=['arm64'] or config['Configuration']['Timeout']>25:
        raise ConfigurationError('Active architecture/timeout mismatch')
    target={'kind':'aws_lambda','account_id':account,'region':region,'stack_id':obj['StackId'],
        'function_arn':function,'function_version':version,'alias':'live',
        'endpoint':snapshot['api']['ApiEndpoint']+'/mcp','gateway':gateway}
    return target,{'snapshot':snapshot,'safe_configuration':safe,
        'source_commit':env['TRADINGVIEW_MCP_SOURCE_COMMIT'],'lock_sha256':env['TRADINGVIEW_MCP_LOCK_SHA256'],
        'log_group_name':outputs['LogGroupName'],'resolved_image_uri':config['Code']['ResolvedImageUri'],
        '_provider_values':tuple(env.get(k,'') for k in ('MARKETAUX_API_TOKEN','PROXY_USERNAME_PREFIX','PROXY_PASSWORD'))}


def registry_identity(session,uri):
    import httpx
    match=re.fullmatch(r'([0-9]{12})\.dkr\.ecr\.([a-z0-9-]+)\.amazonaws\.com/([a-z0-9._/-]+)@(sha256:[a-f0-9]{64})',uri)
    if not match or match[2]!=session.region_name:raise ConfigurationError('Same-region immutable ECR digest required')
    ecr=session.client('ecr')
    if session.client('sts').get_caller_identity()['Account']!=match[1]:raise ConfigurationError('Same-account ECR image required')
    images=ecr.batch_get_image(repositoryName=match[3],imageIds=[{'imageDigest':match[4]}]).get('images',[])
    if len(images)!=1:raise ConfigurationError('Immutable ECR image unavailable')
    manifest=json.loads(images[0]['imageManifest'])
    if 'manifests' in manifest:raise ConfigurationError('Lambda requires single-platform image')
    config_digest=manifest['config']['digest']
    auth=ecr.get_authorization_token(registryIds=[match[1]])['authorizationData'][0]
    registry=f'{match[1]}.dkr.ecr.{match[2]}.amazonaws.com'
    if auth['proxyEndpoint']!='https://'+registry:raise ConfigurationError('Unexpected ECR registry endpoint')
    # Registry credential remains in memory, never in logs/evidence/arguments.
    response=httpx.get(f'https://{registry}/v2/{match[3]}/blobs/{config_digest}',
        headers={'Authorization':'Basic '+auth['authorizationToken']},follow_redirects=True,timeout=30)
    response.raise_for_status();blob=response.content
    if 'sha256:'+hashlib.sha256(blob).hexdigest()!=config_digest:raise ConfigurationError('Registry configuration digest mismatch')
    config=json.loads(blob);verify_publication(manifest,config_digest,config)
    labels=config.get('config',{}).get('Labels',{})
    return config_digest,{k:labels.get(k) for k in ['org.opencontainers.image.revision','tradingview.lock-sha256','tradingview.source-dirty']}
def log_events(logs,group,started,completed):
    args={'logGroupName':group,'startTime':int(instant(started).timestamp()*1000),
        'endTime':int(instant(completed).timestamp()*1000)+1}
    token=None
    while True:
        if token:args['nextToken']=token
        page=logs.filter_log_events(**args)
        yield from page.get('events',[])
        following=page.get('nextToken')
        if not following or following==token:break
        token=following


def observed_correlations(session,target,observation,report):
    """Allowlist gateway/platform identifiers from owner-enabled CloudWatch logs."""
    logs=session.client('logs')
    destination=observation['snapshot']['stage'].get('AccessLogSettings',{}).get('DestinationArn','')
    if ':log-group:' not in destination:return [],[]
    group=destination.split(':log-group:',1)[1].removesuffix(':*')
    gateways=[]
    for event in log_events(logs,group,report['started_at'],report['completed_at']):
        try:
            obj=json.loads(event['message'])
            # Format documented in the operator guide. Missing fields are not evidence.
            if not all(k in obj for k in ('requestId','status','integrationStatus','integrationRequestId')):continue
            gateways.append({'gateway_request_id':str(obj['requestId']),'status_code':int(obj['status']),
                'integration_status':str(obj['integrationStatus']),'platform_request_id':str(obj['integrationRequestId']),
                'observed_at':datetime.fromtimestamp(event['timestamp']/1000,timezone.utc).isoformat()})
        except (ValueError,KeyError,TypeError):continue
    platforms={};cold=[]
    for event in log_events(logs,observation['log_group_name'],report['started_at'],report['completed_at']):
        message=event['message'];request=None;duration=None
        try:
            obj=json.loads(message)
            if obj.get('type')=='platform.report':
                request=obj['record']['requestId'];duration=obj['record']['metrics'].get('initDurationMs')
        except (ValueError,KeyError,TypeError):pass
        if not request:
            match=re.search(r'REPORT RequestId:\s*(\S+)',message)
            if match:
                request=match[1]
                init=re.search(r'Init Duration:\s*([\d.]+)\s*ms',message)
                if init:duration=float(init[1])
        if not request or f'[{target["function_version"]}]' not in event['logStreamName']:continue
        record={'function_arn':target['function_arn'],'function_version':target['function_version'],
            'log_stream':event['logStreamName'],'platform_request_id':request,
            'observed_at':datetime.fromtimestamp(event['timestamp']/1000,timezone.utc).isoformat()}
        platforms[request]=record
        if duration is not None:cold.append(record|{'resolved_image_uri':observation['resolved_image_uri'],'init_duration_ms':duration})
    correlations=[]
    for gateway in gateways:
        platform=platforms.get(gateway['platform_request_id'])
        if platform:correlations.append(platform|gateway)
    return gateways, (correlations,cold)


def live_interaction(endpoint,token,index):
    import httpx,time
    from mcp.types import CallToolResult
    headers={'Authorization':token if token.lower().startswith('bearer ') else 'Bearer '+token,
        'Accept':'application/json, text/event-stream'}
    requests=[];started=now()
    with httpx.Client(timeout=httpx.Timeout(35,connect=10),headers=headers,follow_redirects=False) as client:
        def rpc(method,params,kind=None,notification=False):
            body={'jsonrpc':'2.0','method':method,'params':params}
            if not notification:body['id']=len(requests)+1
            response=client.post(endpoint,json=body)
            if notification:
                if response.status_code!=202:raise ConfigurationError('Notification was not finitely accepted')
                return None
            if response.status_code!=200 or not response.headers.get('content-type','').startswith('application/json'):
                raise ConfigurationError('MCP request did not return finite successful JSON')
            data=response.json()
            if data.get('error') or 'result' not in data:raise ConfigurationError('MCP response failed')
            if kind:requests.append({'stage':kind,'gateway_request_id':response.headers.get('apigw-requestid') or response.headers.get('x-amzn-requestid'),'observed_at':now()})
            return data['result']
        rpc('initialize',{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'lambda-verifier','version':'1'}},'initialization')
        rpc('notifications/initialized',{},notification=True)
        catalog=[];cursor=None
        while True:
            page=rpc('tools/list',{'cursor':cursor} if cursor else {},'discovery')
            catalog.extend(page['tools']);cursor=page.get('nextCursor')
            if not cursor:break
        expected=json.loads((ROOT/'tests/integration/support/baseline.json').read_text())['catalog']
        from mcp.types import Tool
        normalized=sorted([Tool.model_validate(t).model_dump(mode='json',exclude_none=True) for t in catalog],key=lambda t:t['name'])
        if normalized!=expected['tools']:raise ConfigurationError('Live tool catalog differs from frozen baseline')
        result=rpc('tools/call',{'name':'futures_watchlist','arguments':{}},'tool_execution')
        if CallToolResult.model_validate(result).model_dump(mode='json',exclude_none=True)!=expected['results']['futures_watchlist']:
            raise ConfigurationError('Deterministic tool result differs from frozen baseline')
    return {'interaction_id':str(index),'completed_success':True,'started_at':started,'completed_at':now(),'requests':requests}


def live_mode(args):
    import concurrent.futures
    import time
    import httpx
    report=new_report('live',args.expected_image_uri)
    directory=Path(args.report).resolve().parent/(report['run_id']+'-evidence')
    session=aws_session(args.region)
    targets=[];observations=[]
    try:
        for name in [args.stack]+args.additional_stack:
            target,observation=resolve_target(session,name,args.expected_image_uri)
            targets.append(target);observations.append(observation)
        if len({t['gateway']['api_id'] for t in targets})!=len(targets):raise ConfigurationError('Additional targets require distinct supplied APIs')
        if any(o['safe_configuration']!=observations[0]['safe_configuration'] or o['_provider_values']!=observations[0]['_provider_values'] for o in observations[1:]):raise ConfigurationError('Additional target settings/revision mismatch')
        config_digest,labels=registry_identity(session,args.expected_image_uri)
        if labels['tradingview.source-dirty'] not in ('true','false'):raise ConfigurationError('Image dirty-source label unavailable')
        if any(o['source_commit']!=labels['org.opencontainers.image.revision'] or o['lock_sha256']!=labels['tradingview.lock-sha256'] for o in observations):
            raise ConfigurationError('Deployed source/lock metadata differs from image labels')
        if labels['org.opencontainers.image.revision']!=report['release']['source_commit'] or labels['tradingview.lock-sha256']!=report['release']['dependency_lock_sha256']:
            raise ConfigurationError('Verifier checkout does not match tested release')
        report['target']=targets[0];report['additional_targets']=targets[1:]
        report['release'].update(image_config_digest=config_digest,resolved_image_uri=args.expected_image_uri,
            source_dirty=labels['tradingview.source-dirty']=='true')
        path=directory/'configuration.json'
        safe=[{'target':t,'application':o['safe_configuration'],'gateway':sanitized_gateway_snapshot(o['snapshot'])} for t,o in zip(targets,observations)]
        write_json(path,{'run_id':report['run_id'],'release':report['release'],'observations':safe})
        config_refs=[evidence(path,'Independent deployed target, gateway, permission and registry observations')]
        stage(report,'release_identity','pass','Resolved immutable release and protected target observed',config_refs)
        stage(report,'artifact_startup','pass','Published active image/configuration resolved',config_refs)
    except ValueError:
        stage(report,'release_identity','fail','Deployment configuration or release identity mismatch')
        report['completed_at']=now();return report
    token=os.environ.get('TRADINGVIEW_MCP_TOKEN','')
    interactions=[];denied=[];attempted=0;failures=0
    if token:
        # First exercise each target, then a true simultaneous five-client burst.
        jobs=[targets[i%len(targets)] for i in range(15)]
        for i,t in enumerate(jobs):
            attempted+=1
            try:interactions.append(live_interaction(t['endpoint'],token,i))
            except (httpx.HTTPError,ValueError,KeyError):failures+=1
        barrier=__import__('threading').Barrier(5)
        def burst(i):
            barrier.wait(timeout=10)
            return live_interaction(targets[i%len(targets)]['endpoint'],token,15+i)
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            futures=[pool.submit(burst,i) for i in range(5)]
            for f in futures:
                attempted+=1
                try:interactions.append(f.result())
                except (httpx.HTTPError,ValueError,KeyError):failures+=1
        counts=report['counts'];counts.update(attempted_interactions=attempted,passed_interactions=len(interactions))
        counts['concurrent_clients']=5 if all(any(x['interaction_id']==str(15+i) for x in interactions) for i in range(5)) else 0
        path=directory/'protocol.json'
        write_json(path,{'run_id':report['run_id'],'release':report['release'],'attempted':attempted,'completed':len(interactions),'failed':failures,'concurrent_clients':counts['concurrent_clients']})
        refs=[evidence(path,'Complete initialization/discovery/tool interactions')]
        for name in ['client_initialization','tool_discovery','tool_execution','concurrent_clients']:
            stage(report,name,'pass' if failures==0 else 'fail','Twenty interactions and five simultaneous clients required',refs)
        headers={'Authorization':token if token.lower().startswith('bearer ') else 'Bearer '+token,'Accept':'application/json, text/event-stream'}
        health=[]
        for i in range(10):
            start=time.monotonic()
            try:
                response=httpx.get(targets[0]['endpoint'].removesuffix('/mcp')+'/health',headers=headers,timeout=5)
                health.append(response.status_code==200 and response.json()=={'status':'ok'} and time.monotonic()-start<=5)
            except (httpx.HTTPError,ValueError):health.append(False)
        counts['passed_health_checks']=sum(health)
        path=directory/'health.json';write_json(path,{'results':health})
        stage(report,'health','pass' if all(health) else 'fail','Ten warm health responses within five seconds each',[evidence(path,'Timed exact health responses')])
        invalid=[]
        for name in ['missing_tool','coin_analysis']:
            try:
                response=httpx.post(targets[0]['endpoint'],headers=headers,timeout=httpx.Timeout(35,connect=10),json={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':name,'arguments':{}}})
                data=response.json()
                invalid.append(response.status_code==200 and bool(data.get('error') or data.get('result',{}).get('isError')))
            except (httpx.HTTPError,ValueError):invalid.append(False)
        path=directory/'invalid-input.json';write_json(path,{'rejected':invalid})
        stage(report,'invalid_tool_input','pass' if all(invalid) else 'fail','Unknown tool and missing required arguments',[evidence(path,'Invalid-input observations')])
    # Missing/invalid checks cover every owned route, including external health.
    for target_index,t in enumerate(targets):
        for credential_case in ['missing','invalid']:
            for path,method in [('/mcp','POST'),('/mcp/','POST'),('/health','GET')]:
                for operation in (['tools/list','tools/call'] if method=='POST' else [None]):
                    headers={} if credential_case=='missing' else {'Authorization':'Bearer intentionally-invalid-verifier-credential'}
                    headers['Accept']='application/json, text/event-stream'
                    body=None if method=='GET' else {'jsonrpc':'2.0','id':1,'method':operation,'params':{} if operation=='tools/list' else {'name':'futures_watchlist','arguments':{}}}
                    try:
                        response=httpx.request(method,t['endpoint'].removesuffix('/mcp')+path,headers=headers,json=body,timeout=httpx.Timeout(35,connect=10))
                        denied.append({'target_index':target_index,'credential_case':credential_case,'path':path,'method':method,'operation':operation,
                            'gateway_request_id':response.headers.get('apigw-requestid') or response.headers.get('x-amzn-requestid'),
                            'status_code':response.status_code})
                    except httpx.HTTPError:
                        denied.append({'target_index':target_index,'credential_case':credential_case,'path':path,'method':method,'operation':operation,'gateway_request_id':None,'status_code':0})
    if any(d['status_code'] not in (401,403) for d in denied):
        stage(report,'authorization','fail','A required unauthorized request was not rejected by the gateway')
    # CloudWatch delivery is asynchronous. Bounded reads; no configuration mutation.
    gateways=[];correlations=[];cold=[]
    for attempt in range(args.log_attempts):
        report['completed_at']=now()
        gateways=[];correlations=[];cold=[]
        try:
            for t,o in zip(targets,observations):
                g,p=observed_correlations(session,t,o,report)
                gateways.extend(g)
                if p:correlations.extend(p[0]);cold.extend(p[1])
        except Exception:
            # Missing log permission/delivery is explicitly incomplete, never denial proof.
            gateways=[];correlations=[];cold=[]
        if len(correlations)>=sum(len(i['requests']) for i in interactions) and len(gateways)>=len(denied):break
        if attempt+1<args.log_attempts:time.sleep(5)
    by_id={c['gateway_request_id']:c for c in correlations}
    completed=[]
    for interaction in interactions:
        if all(q['gateway_request_id'] in by_id for q in interaction['requests']):
            copied=copy.deepcopy(interaction)
            copied['requests']=[by_id[q['gateway_request_id']]|{'stage':q['stage']} for q in copied['requests']]
            completed.append(copied)
    sidecar={'kind':'completed_interactions','run_id':report['run_id'],'resolved_image_uri':args.expected_image_uri,
        'interactions':completed,'gateway_correlations':correlations}
    path=directory/'completed-interactions.json';write_json(path,sidecar)
    side_ref=evidence(path,'Completed successful interactions and authoritative request correlations')
    # Store sidecar once; combine requires exactly one authoritative sidecar.
    next(s for s in report['stages'] if s['name']=='tool_execution')['evidence'].append(side_ref)
    report['cold_start_evidence']=cold
    qualified=qualified_cold_starts(report,sidecar)
    report['cold_start_evidence']=qualified;report['counts']['evidenced_fresh_starts']=len(qualified)
    stage(report,'cold_start','pass' if len(qualified)>=2 else 'not_run','Two distinct startups correlated to complete interactions required',[side_ref] if len(qualified)>=2 else [])
    # Keep sidecar reference only once even if cold_start passes.
    if len(qualified)>=2:
        path=directory/'qualified-cold.json';write_json(path,{'qualified':qualified})
        next(s for s in report['stages'] if s['name']=='cold_start')['evidence']=[evidence(path,'Qualified fresh execution environments')]
    auth_stage=next(s for s in report['stages'] if s['name']=='authorization')
    proofs=[]
    for d in denied:
        matched=next((g for g in gateways if denial_proven(g,d['status_code'],d['gateway_request_id'])),None)
        if matched:proofs.append(d|matched|{'service_invoked':False})
    if len(proofs)==len(denied) and proofs and auth_stage['status']!='fail':
        path=directory/'gateway-denials.json';write_json(path,{'run_id':report['run_id'],'denials':proofs})
        ref=evidence(path,'Gateway denial with absent integration before backend invocation')
        report['authorization_evidence']={'denied_requests':[{k:d[k] for k in ('credential_case','gateway_request_id','status_code','service_invoked')}|{'evidence':[ref]} for d in proofs if d['target_index']==0],
            'public_bypass_absent':True,'configuration_evidence':config_refs}
        stage(report,'authorization','pass','Every target/route denial correlated before backend invocation',config_refs+[ref])
    report['completed_at']=now()
    return report
def revalidate_authorization(report):
    auth=report['authorization_evidence']
    if not auth:raise ConfigurationError('Missing authorization evidence')
    records=[read_evidence(e) for e in auth['configuration_evidence']]
    if len(records)!=1:raise ConfigurationError('One scoped configuration observation required')
    record=records[0]
    if record.get('run_id')!=report['run_id'] or record.get('release')!=report['release']:
        raise ConfigurationError('Authorization observation provenance mismatch')
    targets=[report['target']]+report['additional_targets']
    observations=record.get('observations',[])
    if [o.get('target') for o in observations]!=targets:
        raise ConfigurationError('Authorization target coverage mismatch')
    for target,observation in zip(targets,observations):
        observed=assess_gateway(observation['gateway'],target['function_arn']+':live',target['account_id'],target['region'])
        if observed!=target['gateway']:raise ConfigurationError('Gateway identity mismatch')
        expected=f"https://{observed['api_id']}.execute-api.{target['region']}.amazonaws.com/mcp"
        if target['endpoint']!=expected:raise ConfigurationError('Gateway endpoint mismatch')
    denial_records=[]
    refs={e['ref']:e for d in auth['denied_requests'] for e in d['evidence']}
    for item in refs.values():
        data=read_evidence(item)
        if data.get('run_id')!=report['run_id']:raise ConfigurationError('Denial run mismatch')
        denial_records.extend(data.get('denials',[]))
    expected={(case,path,operation) for case in ('missing','invalid') for path in ('/mcp','/mcp/','/health') for operation in ([None] if path=='/health' else ['tools/list','tools/call'])}
    for index in range(len(targets)):
        valid=[d for d in denial_records if d.get('target_index')==index and denial_proven(d,d.get('status_code'),d.get('gateway_request_id'))]
        actual={(d.get('credential_case'),d.get('path'),d.get('operation')) for d in valid}
        if actual!=expected:raise ConfigurationError('Missing per-target route/operation denial proof')
    for denial in auth['denied_requests']:
        if not any(d.get('target_index')==0 and all(d.get(k)==denial[k] for k in ('credential_case','gateway_request_id','status_code','service_invoked')) for d in denial_records):
            raise ConfigurationError('Authorization result differs from denial evidence')


def preflight(args):
    """Read-only deployment preflight; no provider values leave this function."""
    from tradingview_mcp.lambda_server import validate_environment
    path=Path(args.parameters_file).resolve()
    if path.is_relative_to(ROOT) or path.stat().st_mode & 0o077:
        raise ConfigurationError('Private parameters require owner-only file outside checkout')
    entries=json.loads(path.read_text())
    if not isinstance(entries,list) or any(not isinstance(e,dict) or 'ParameterKey' not in e for e in entries):
        raise ConfigurationError('Expected CloudFormation parameter-object array')
    session=aws_session(args.region);cf=session.client('cloudformation');api=session.client('apigatewayv2');lam=session.client('lambda')
    template=json.loads((ROOT/'infra/lambda/runtime.yaml').read_text())
    definitions=template['Parameters'];parameters={k:str(v['Default']) for k,v in definitions.items() if 'Default' in v}
    previous={};owned=set();old_revision=None
    try:
        prior=cf.describe_stacks(StackName=args.stack)['Stacks'][0]
        previous={p['ParameterKey']:p.get('ParameterValue','') for p in prior['Parameters']}
        old_revision=previous.get('DeploymentRevision')
        outputs={x['OutputKey']:x['OutputValue'] for x in prior.get('Outputs',[])}
        owned={outputs.get(k) for k in ('McpRouteId','McpSlashRouteId','HealthRouteId')}
        config=lam.get_function_configuration(FunctionName=outputs['FunctionArn'])
        variables=config.get('Environment',{}).get('Variables',{})
        for key,envkey in [('MarketauxApiToken','MARKETAUX_API_TOKEN'),('ProxyUsernamePrefix','PROXY_USERNAME_PREFIX'),('ProxyPassword','PROXY_PASSWORD')]:
            previous[key]=variables.get(envkey,'')
        parameters.update(previous)
    except Exception as exc:
        code=getattr(exc,'response',{}).get('Error',{}).get('Code')
        if code!='ValidationError' or 'does not exist' not in str(exc):raise
    seen=set()
    for entry in entries:
        key=entry['ParameterKey']
        if key not in definitions or key in seen:raise ConfigurationError('Unknown or duplicated parameter')
        seen.add(key)
        if entry.get('UsePreviousValue'):
            if key not in previous:raise ConfigurationError('Previous parameter unavailable')
            continue
        if not isinstance(entry.get('ParameterValue'),str):raise ConfigurationError('Parameter values must be literal strings')
        parameters[key]=entry['ParameterValue']
    for key,rule in definitions.items():
        value=parameters.get(key)
        if value is None:raise ConfigurationError('Required deployment parameter omitted: '+key)
        if 'AllowedPattern' in rule and not re.fullmatch(rule['AllowedPattern'],value):raise ConfigurationError('Invalid parameter format: '+key)
        if rule.get('Type')=='Number':
            if not re.fullmatch(r'\d+',value):raise ConfigurationError('Integer parameter required: '+key)
            number=int(value)
            if number<rule.get('MinValue',0) or number>rule.get('MaxValue',float('inf')):raise ConfigurationError('Parameter out of range: '+key)
        if 'AllowedValues' in rule and value not in [str(v) for v in rule['AllowedValues']]:raise ConfigurationError('Unsupported parameter value: '+key)
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9-]{0,47}',args.stack):raise ConfigurationError('Runtime stack name must be letter-led, at most 48 characters')
    if previous:
        if parameters['RollbackVersion']:
            if parameters['DeploymentRevision']!=old_revision:raise ConfigurationError('Rollback must preserve deployment revision')
            lam.get_function(FunctionName=args.stack,Qualifier=parameters['RollbackVersion'])
        elif parameters['DeploymentRevision']==old_revision:
            raise ConfigurationError('Forward code/environment publication requires a fresh deployment revision')
        elif any(v.get('Description')=='Revision '+parameters['DeploymentRevision'] for v in pages(lam,'list_versions_by_function','Versions',FunctionName=args.stack)):
            raise ConfigurationError('Deployment revision was already published')
    elif parameters['RollbackVersion']:raise ConfigurationError('Initial deployment cannot select rollback version')
    env={}
    def render(value):
        if isinstance(value,str):return value
        if 'Ref' in value:return parameters[value['Ref']]
        result=value['Fn::Sub']
        for key,v in parameters.items():result=result.replace('${'+key+'}',v)
        return result.replace('${AWS::Region}',args.region)
    for k,v in template['Resources']['Function']['Properties']['Environment']['Variables'].items():env[k]=render(v)
    validate_environment(env)
    api_id=parameters['ApiId'];authorizer_id=parameters['AuthorizerId']
    a=api.get_api(ApiId=api_id);st=api.get_stage(ApiId=api_id,StageName='$default');auth=api.get_authorizer(ApiId=api_id,AuthorizerId=authorizer_id)
    if a['ProtocolType']!='HTTP' or a.get('DisableExecuteApiEndpoint') or a['ApiEndpoint']!=f'https://{api_id}.execute-api.{args.region}.amazonaws.com' or not st.get('AutoDeploy'):
        raise ConfigurationError('Unsupported supplied API/stage profile')
    if auth['AuthorizerType']!='REQUEST' or '$request.header.Authorization' not in auth.get('IdentitySource',[]):raise ConfigurationError('Incompatible custom authorizer')
    if auth.get('AuthorizerResultTtlInSeconds',300)>0 and '$context.routeKey' not in auth['IdentitySource']:raise ConfigurationError('Incompatible authorizer cache')
    for route in pages(api,'get_routes','Items',ApiId=api_id):
        if route['RouteKey'].split(' ',1)[-1] in ('/mcp','/mcp/','/health') and route['RouteId'] not in owned:
            raise ConfigurationError('Conflicting supplied route; existing resources will not be adopted')
    auth_function=re.search(r'(arn:aws:lambda:[^/]+:function:[^/]+)/invocations',auth.get('AuthorizerUri',''))
    if not auth_function:raise ConfigurationError('Expected supplied Lambda REQUEST authorizer')
    arn=auth_function[1];parts=arn.split(':');account=session.client('sts').get_caller_identity()['Account']
    if parts[3]!=args.region or parts[4]!=account:raise ConfigurationError('Same-account/same-region authorizer required')
    policy=json.loads(lam.get_policy(FunctionName=arn)['Policy'])
    import fnmatch
    desired=f'arn:aws:execute-api:{args.region}:{account}:{api_id}/authorizers/{authorizer_id}'
    permitted=False
    for statement in policy.get('Statement',[]):
        condition=statement.get('Condition',{})
        source=condition.get('ArnLike',{}).get('AWS:SourceArn',condition.get('ArnEquals',{}).get('AWS:SourceArn',''))
        if statement.get('Effect')=='Allow' and statement.get('Principal')=={'Service':'apigateway.amazonaws.com'} and statement.get('Action')=='lambda:InvokeFunction' and fnmatch.fnmatchcase(desired,source):permitted=True
    if not permitted:raise ConfigurationError('Supplied authorizer invocation permission unavailable')
    config_digest,labels=registry_identity(session,parameters['ImageUri'])
    if labels['org.opencontainers.image.revision']!=parameters['SourceCommit'] or labels['tradingview.lock-sha256']!=parameters['LockSha256']:raise ConfigurationError('Image source/lock parameter mismatch')
    settings=lam.get_account_settings()
    available=settings['AccountLimit'].get('UnreservedConcurrentExecutions',0)
    previous_reservation=0
    if previous:
        old=optional_read(lam,'get_function_concurrency',FunctionName=args.stack)
        previous_reservation=(old or {}).get('ReservedConcurrentExecutions',0)
    if available+previous_reservation-int(parameters['ReservedConcurrency'])<100:
        raise ConfigurationError('Insufficient reserved concurrency headroom; choose sizing explicitly')
    print('Preflight passed: private parameters, supplied resources, release identity, and quota checked. No resources changed.')
    return 0


def main(argv=None):
    class Parser(argparse.ArgumentParser):
        def error(self,message):
            self.exit(3,'Invalid arguments; use --help for required options.\n')
    parser=Parser(description=__doc__)
    subs=parser.add_subparsers(dest='mode',required=True)
    local=subs.add_parser('local')
    local.add_argument('--baseline-image');local.add_argument('--lambda-image');local.add_argument('--expected-image-uri')
    local.add_argument('--report',required=True)
    live=subs.add_parser('live')
    live.add_argument('--region',required=True);live.add_argument('--stack',required=True)
    live.add_argument('--additional-stack',action='append',default=[])
    live.add_argument('--expected-image-uri',required=True);live.add_argument('--log-attempts',type=int,choices=range(1,13),default=3)
    live.add_argument('--report',required=True)
    combine=subs.add_parser('combine')
    combine.add_argument('--local-report',required=True);combine.add_argument('--live-report',required=True)
    combine.add_argument('--lifecycle-evidence');combine.add_argument('--report',required=True)
    pre=subs.add_parser('preflight')
    pre.add_argument('--region',required=True);pre.add_argument('--stack',required=True);pre.add_argument('--parameters-file',required=True)
    args=parser.parse_args(argv)
    try:
        if args.mode=='preflight':return preflight(args)
        if args.mode=='local':report=local_mode(args)
        elif args.mode=='live':report=live_mode(args)
        else:
            lifecycle=json.loads(Path(args.lifecycle_evidence).read_text()) if args.lifecycle_evidence else None
            report=combine_reports(json.loads(Path(args.local_report).read_text()),json.loads(Path(args.live_report).read_text()),lifecycle)
        validate(report)
        # Final defense against known credentials accidentally entering any evidence/report.
        forbidden=[os.environ.get(k,'') for k in ['TRADINGVIEW_MCP_TOKEN','MARKETAUX_API_TOKEN','PROXY_PASSWORD','PROXY_USERNAME_PREFIX']]
        text=json.dumps(report)
        if any(value and value in text for value in forbidden):raise ConfigurationError('Sensitive value in report')
        write_json(args.report,report)
        print(f'{args.mode}: {sum(s["status"]=="pass" for s in report["stages"])}/16 stages passed; full_deployment_success={report["full_deployment_success"]}')
        return exit_code(report)
    except Exception as exc:
        # Never print raw SDK/provider/validation exception payloads or environments.
        code=getattr(exc,'response',{}).get('Error',{}).get('Code')
        if args.mode=='live' and (type(exc).__name__ in ('NoCredentialsError','CredentialRetrievalError','ProfileNotFound','EndpointConnectionError') or code in ('AccessDenied','AccessDeniedException','UnrecognizedClientException','ExpiredToken','ExpiredTokenException','InvalidClientTokenId','RequestExpired')):
            report=new_report('live',args.expected_image_uri)
            stage(report,'release_identity','not_run','AWS observation credentials, permissions, or connectivity unavailable')
            report['completed_at']=now();validate(report);write_json(args.report,report)
            print('live: incomplete; AWS observation prerequisites unavailable')
            return 2
        message=str(exc) if isinstance(exc,ConfigurationError) else type(exc).__name__
        print('Invalid configuration/evidence or unavailable operation: '+message+'; no success claimed.',file=sys.stderr)
        return 3


if __name__=='__main__':
    raise SystemExit(main())
