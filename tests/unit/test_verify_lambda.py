"""Semantic gates reject plausible but unrelated evidence."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import pytest

ROOT=Path(__file__).resolve().parents[2]


def verifier():
    spec=importlib.util.spec_from_file_location('verify_lambda',ROOT/'scripts/verify_lambda.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m


def cold_fixture():
    v=verifier();r=v.new_report('live')
    uri='123456789012.dkr.ecr.ca-central-1.amazonaws.com/repo@sha256:'+'a'*64
    r['release']['resolved_image_uri']=r['release']['expected_image_uri']=uri
    r['target'].update(stack_id='stack',function_arn='arn:aws:lambda:ca-central-1:123456789012:function:test',function_version='1')
    r['completed_at']=v.now()
    requests=[{'stage':kind,'gateway_request_id':'gateway-'+kind,'platform_request_id':'platform-'+kind,
        'function_arn':r['target']['function_arn'],'function_version':'1','log_stream':'stream-'+kind,
        'observed_at':r['started_at']} for kind in ['initialization','discovery','tool_execution']]
    cold=[{k:q[k] for k in ['function_arn','function_version','log_stream','platform_request_id','observed_at']} | {'resolved_image_uri':uri,'init_duration_ms':100} for q in requests[:2]]
    r['cold_start_evidence']=cold
    side={'run_id':r['run_id'],'resolved_image_uri':uri,'interactions':[{'interaction_id':'i','completed_success':True,'requests':requests}],
        'gateway_correlations':[q|{'status_code':200,'integration_status':'200'} for q in requests]}
    return v,r,side


def test_distinct_startup_requests_in_completed_interaction_count():
    v,r,s=cold_fixture()
    assert len(v.qualified_cold_starts(r,s))==2
    r['cold_start_evidence'].append(copy.deepcopy(r['cold_start_evidence'][0]))
    assert len(v.qualified_cold_starts(r,s))==2


@pytest.mark.parametrize('case',['health','failed','incomplete','wrong_release','wrong_run','wrong_time','unmatched_gateway','unmatched_platform','wrong_target'])
def test_unrelated_startup_records_do_not_count(case):
    v,r,s=cold_fixture()
    q=s['interactions'][0]
    if case=='health':q['requests'][0]['stage']='health'
    elif case=='failed':q['completed_success']=False
    elif case=='incomplete':q['requests'].pop()
    elif case=='wrong_release':s['resolved_image_uri']='other'
    elif case=='wrong_run':s['run_id']='other'
    elif case=='wrong_time':q['requests'][0]['observed_at']='2000-01-01T00:00:00+00:00'
    elif case=='unmatched_gateway':q['requests'][0]['gateway_request_id']='unmatched'
    elif case=='unmatched_platform':q['requests'][0]['platform_request_id']='unmatched'
    elif case=='wrong_target':q['requests'][0]['function_version']='999'
    assert len(v.qualified_cold_starts(r,s))<2


def test_import_and_pure_semantics_without_optional_aws_modules():
    code="""import sys,importlib.util
class Block:
 def find_spec(self,name,*a):
  if name.split('.')[0] in ('boto3','botocore','cfnlint'): raise ImportError('optional')
sys.meta_path.insert(0,Block())
s=importlib.util.spec_from_file_location('v','scripts/verify_lambda.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
assert m.exit_code(m.new_report('local'))==2
"""
    assert subprocess.run([sys.executable,'-c',code],cwd=ROOT).returncode==0


def test_pass_counts_and_exit_codes():
    v=verifier();r=v.new_report('local')
    v.validate(r);assert v.exit_code(r)==2
    v.stage(r,'health','fail','MCP can fail despite health')
    assert v.exit_code(r)==1
    r['counts']['passed_interactions']=1
    with pytest.raises(ValueError):v.validate(r)


def test_untrusted_evidence_digest_and_path_rejected(tmp_path):
    v=verifier();p=tmp_path/'evidence.json';v.write_json(p,{'observed':True})
    e=v.evidence(p,'observation')
    assert v.read_evidence(e)=={'observed':True}
    p.write_text('{}')
    with pytest.raises(ValueError):v.read_evidence(e)


def test_credentials_redacted_from_reports():
    v=verifier()
    assert 'token-value' not in v.sanitize('Authorization: Bearer token-value', ['token-value'])


def test_combine_rejects_release_and_local_authorization_mismatch():
    v=verifier();local=v.new_report('local');live=v.new_report('live')
    live['release']['dependency_lock_sha256']='b'*64
    with pytest.raises(ValueError):v.combine_reports(local,live,None)


def test_missing_live_and_lifecycle_never_full_success():
    v=verifier();local=v.new_report('local');live=v.new_report('live')
    result=v.combine_reports(local,live,None)
    assert not result['full_deployment_success'] and v.exit_code(result)==2


def test_lifecycle_cannot_claim_pass_with_unrelated_release():
    v=verifier();r=v.new_report('live')
    with pytest.raises(ValueError):v.validate_lifecycle(r,{'starting_image_uri':'other'})


def test_unperformed_lifecycle_example_is_schema_shaped():
    from jsonschema import Draft202012Validator,FormatChecker
    v=verifier();schema=json.loads(v.SCHEMA_PATH.read_text())
    uri='123456789012.dkr.ecr.ca-central-1.amazonaws.com/repo@sha256:'+'a'*64
    obj=v.lifecycle_example(uri,uri[:-64]+'b'*64,'stack')
    Draft202012Validator({'$ref':'#/$defs/lifecycleEvidence','$defs':schema['$defs']},format_checker=FormatChecker()).validate(obj)
    assert all(s['status']=='not_run' for s in obj['steps'].values())


@pytest.mark.parametrize('field',['source_commit','source_dirty','dependency_lock_sha256'])
def test_combine_preserves_source_and_dirty_identity(field):
    v=verifier();local=v.new_report('local');live=v.new_report('live')
    live['release'][field]=not local['release'][field] if field=='source_dirty' else ('a'*40 if field=='source_commit' else 'a'*64)
    with pytest.raises(ValueError):v.combine_reports(local,live,None)


def test_invalid_cli_arguments_exit_three_without_echoing_input():
    result=subprocess.run([sys.executable,str(ROOT/'scripts/verify_lambda.py'),'live','--token','sensitive-cli-input'],capture_output=True,text=True)
    assert result.returncode==3 and 'sensitive-cli-input' not in result.stderr


def full_fixture(tmp_path):
    """Synthetic evidence exercises acceptance semantics; never deployment evidence."""
    spec=importlib.util.spec_from_file_location('gateway_fixture',ROOT/'tests/integration/test_lambda_verifier.py')
    fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
    v=verifier();snapshot,alias=fixture.gateway()
    local=v.new_report('local');live=v.new_report('live')
    uri='123456789012.dkr.ecr.ca-central-1.amazonaws.com/repo@sha256:'+'a'*64
    for report in [local,live]:
        report['started_at']='2026-11-02T00:00:00+00:00';report['completed_at']='2026-11-02T00:01:00+00:00'
        report['release'].update(image_config_digest='sha256:'+'c'*64,expected_image_uri=uri,resolved_image_uri=uri)
    live['target'].update(account_id='123456789012',region='ca-central-1',stack_id='stack',function_arn=alias.removesuffix(':live'),function_version='1',alias='live',endpoint='https://abc123.execute-api.ca-central-1.amazonaws.com/mcp',gateway=v.assess_gateway(snapshot,alias,'123456789012','ca-central-1'))
    def save(name,data):
        path=tmp_path/(name+'.json');v.write_json(path,data);return v.evidence(path,name)
    ordinary=save('ordinary',{'kind':'synthetic_fixture'})
    for report in [local,live]:
        for name in v.STAGES:v.stage(report,name,'pass','Synthetic unit fixture',[ordinary])
    v.stage(local,'authorization','not_run','Not a local assertion')
    config=save('configuration',{'run_id':live['run_id'],'release':live['release'],'observations':[{'target':live['target'],'gateway':snapshot}]})
    proofs=[]
    for case in ['missing','invalid']:
        for path in ['/mcp','/mcp/','/health']:
            for operation in ([None] if path=='/health' else ['tools/list','tools/call']):
                proofs.append({'target_index':0,'credential_case':case,'path':path,'operation':operation,'gateway_request_id':str(len(proofs)),
                    'status_code':403,'service_invoked':False,'integration_status':'-','platform_request_id':'-'})
    denial=save('denials',{'run_id':live['run_id'],'denials':proofs})
    live['authorization_evidence']={'public_bypass_absent':True,'configuration_evidence':[config],
        'denied_requests':[{k:d[k] for k in ['credential_case','gateway_request_id','status_code','service_invoked']}|{'evidence':[denial]} for d in proofs]}
    side={'kind':'completed_interactions','run_id':live['run_id'],'resolved_image_uri':uri,'gateway_correlations':[],'interactions':[]}
    for i in range(20):
        requests=[{'stage':kind,'gateway_request_id':f'g{i}-{j}','platform_request_id':f'p{i}-{j}',
            'function_arn':live['target']['function_arn'],'function_version':'1','log_stream':f'stream-{j}',
            'observed_at':'2026-11-02T00:00:01+00:00'} for j,kind in enumerate(['initialization','discovery','tool_execution'])]
        side['interactions'].append({'interaction_id':str(i),'completed_success':True,'requests':requests,
            'started_at':'2026-11-02T00:00:00+00:00','completed_at':'2026-11-02T00:00:02+00:00'})
        side['gateway_correlations'].extend(q|{'status_code':200,'integration_status':'200'} for q in requests)
    ref=save('completed-interactions',side)
    v.stage(live,'tool_execution','pass','Synthetic completed interactions',[ref])
    live['cold_start_evidence']=[{k:q[k] for k in ['function_arn','function_version','log_stream','platform_request_id','observed_at']}|{'resolved_image_uri':uri,'init_duration_ms':100} for q in side['interactions'][0]['requests'][:2]]
    live['counts'].update(attempted_interactions=20,passed_interactions=20,concurrent_clients=5,passed_health_checks=10,evidenced_fresh_starts=2)
    lifecycle=v.lifecycle_example(uri,uri[:-64]+'b'*64,'stack')
    for step in lifecycle['steps'].values():step.update(status='pass',reason='Synthetic unit fixture',evidence=[ordinary])
    env=save('environment',{'kind':'environment_update_rollback','status':'pass','same_image_uri':uri,'starting_revision':'old','updated_revision':'new','rollback_revision':'old'})
    lifecycle['steps']['update']['evidence'].append(env)
    return v,local,live,lifecycle,side


def test_complete_correlated_fixture_can_pass_combine(tmp_path):
    v,local,live,lifecycle,_=full_fixture(tmp_path)
    result=v.combine_reports(local,live,lifecycle)
    assert result['full_deployment_success'] and v.exit_code(result)==0


@pytest.mark.parametrize('case',['health_only','failed_last_interaction','bad_gateway','missing_environment_update','wrong_image_config','denial_without_correlation','no_overlap','healthy_but_mcp_failed'])
def test_false_positive_full_success_rejected(tmp_path,case):
    v,local,live,lifecycle,side=full_fixture(tmp_path)
    if case in ('health_only','failed_last_interaction','no_overlap'):
        if case=='health_only':side['interactions'][0]['requests'][0]['stage']='health'
        if case=='failed_last_interaction':side['interactions'][-1]['completed_success']=False
        if case=='no_overlap':
            for i,obj in enumerate(side['interactions']):
                obj['started_at']=f'2026-11-02T00:00:{i*2:02}+00:00';obj['completed_at']=f'2026-11-02T00:00:{i*2+1:02}+00:00'
        path=tmp_path/'completed-interactions.json';v.write_json(path,side)
        v.stage(live,'tool_execution','pass','Synthetic fixture',[v.evidence(path,'changed sidecar')])
    if case=='bad_gateway':
        ref=live['authorization_evidence']['configuration_evidence'][0];data=v.read_evidence(ref)
        data['observations'][0]['gateway']['routes'][0]['AuthorizationType']='NONE'
        v.write_json(ref['ref'],data);live['authorization_evidence']['configuration_evidence']=[v.evidence(ref['ref'],'changed configuration')]
    if case=='missing_environment_update':lifecycle['steps']['update']['evidence'].pop()
    if case=='wrong_image_config':local['release']['image_config_digest']='sha256:'+'d'*64
    if case=='denial_without_correlation':
        ref=live['authorization_evidence']['denied_requests'][0]['evidence'][0];data=v.read_evidence(ref)
        data['denials'][0]['integration_status']='200';v.write_json(ref['ref'],data)
        for d in live['authorization_evidence']['denied_requests']:d['evidence']=[v.evidence(ref['ref'],'changed denials')]
    if case=='healthy_but_mcp_failed':v.stage(live,'client_initialization','fail','Observed MCP failure')
    try:result=v.combine_reports(local,live,lifecycle)
    except ValueError:return
    assert not result['full_deployment_success']


def test_known_local_image_with_unperformed_live_report_is_incomplete():
    v=verifier();local=v.new_report('local');live=v.new_report('live')
    local['release']['image_config_digest']='sha256:'+'c'*64
    result=v.combine_reports(local,live,None)
    assert v.exit_code(result)==2 and not result['full_deployment_success']
