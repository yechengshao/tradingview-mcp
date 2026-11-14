"""Structural deployment invariants; no AWS calls."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def template(name):
    # Templates use CloudFormation JSON, which is also valid YAML.
    return json.loads((ROOT / f'infra/lambda/{name}.yaml').read_text())


def test_ecr_is_private_immutable_scanned_retained_and_scoped():
    t = template('ecr')
    r = t['Resources']['Repository']
    p = r['Properties']
    assert p['ImageTagMutability'] == 'IMMUTABLE'
    assert p['ImageScanningConfiguration']['ScanOnPush'] is True
    assert p['EncryptionConfiguration']['EncryptionType'] == 'AES256'
    assert r['DeletionPolicy'] == r['UpdateReplacePolicy'] == 'Retain'
    policy = p['RepositoryPolicyText']['Statement'][0]
    assert set(policy['Action']) == {'ecr:BatchGetImage', 'ecr:GetDownloadUrlForLayer'}
    assert policy['Principal'] == {'Service': 'lambda.amazonaws.com'}
    assert '${AWS::AccountId}' in json.dumps(policy['Condition'])
    assert set(t['Outputs']) == {'RepositoryName', 'RepositoryUri'}


def test_runtime_security_ownership_and_native_settings():
    t=template('runtime')
    resources=t['Resources']
    types=[r['Type'] for r in resources.values()]
    assert 'AWS::Lambda::Url' not in types
    for forbidden in ['AWS::ApiGatewayV2::Api','AWS::ApiGatewayV2::Stage','AWS::ApiGatewayV2::Authorizer','AWS::Cognito::UserPool']:
        assert forbidden not in types
    f=resources['Function']['Properties']
    assert f['Architectures']==['arm64'] and f['PackageType']=='Image'
    assert 'VpcConfig' not in f
    assert '@sha256:' in t['Parameters']['ImageUri']['AllowedPattern']
    env=f['Environment']['Variables']
    assert set(['MARKETAUX_API_TOKEN','MARKETAUX_DAILY_BUDGET','PROXY_HOST','PROXY_PORT','PROXY_USERNAME_PREFIX','PROXY_PASSWORD','PROXY_SESSION_MIN','PROXY_SESSION_MAX','PROXY_ENABLED']) <= env.keys()
    for p in ['MarketauxApiToken','ProxyPassword','ProxyUsernamePrefix']:
        assert t['Parameters'][p]['NoEcho'] is True and t['Parameters'][p]['Default']==''
        assert p not in t['Outputs']
    actions=resources['ExecutionRole']['Properties']['Policies'][0]['PolicyDocument']['Statement'][0]['Action']
    assert set(actions)=={'logs:CreateLogStream','logs:PutLogEvents'}
    routes=[r['Properties'] for r in resources.values() if r['Type']=='AWS::ApiGatewayV2::Route']
    assert {r['RouteKey'] for r in routes}=={'ANY /mcp','ANY /mcp/','GET /health'}
    assert all(r['AuthorizationType']=='CUSTOM' and r['AuthorizerId']=={'Ref':'AuthorizerId'} for r in routes)
    permissions=[r['Properties'] for r in resources.values() if r['Type']=='AWS::Lambda::Permission']
    assert len(permissions)==3
    assert all(p['FunctionName']=={'Ref':'LiveAlias'} and p['Principal']=='apigateway.amazonaws.com' and p['SourceAccount']=={'Ref':'AWS::AccountId'} for p in permissions)
    assert all('${ApiId}/$default/' in p['SourceArn']['Fn::Sub'] for p in permissions)
    integration=resources['Integration']['Properties']
    assert integration['PayloadFormatVersion']=='2.0' and integration['TimeoutInMillis']==30000
    assert integration['IntegrationUri']=={'Ref':'LiveAlias'}


def test_release_lifecycle_environment_snapshots_and_outputs():
    t=template('runtime')
    r=t['Resources']
    version=r['PublishedVersion']
    assert version['DeletionPolicy']==version['UpdateReplacePolicy']=='Retain'
    assert version['Properties']['Description']=={'Fn::Sub':'Revision ${DeploymentRevision}'}
    assert r['Function']['Properties']['Environment']['Variables']['TRADINGVIEW_MCP_DEPLOYMENT_REVISION']=={'Ref':'DeploymentRevision'}
    assert r['LiveAlias']['Properties']['FunctionVersion']=={'Fn::If':['UseRollback',{'Ref':'RollbackVersion'},{'Fn::GetAtt':['PublishedVersion','Version']}]}
    assert t['Parameters']['RollbackVersion']['Default']==''
    expected={'ApiId','ApiEndpoint','ApiStageName','AuthorizerId','IntegrationId','McpRouteId','McpSlashRouteId','HealthRouteId','McpEndpoint','HealthUrl','FunctionArn','AliasArn','PublishedVersion','ActiveVersion','ImageUri','SourceCommit','LockSha256','DeploymentRevision','LogGroupName'}
    assert set(t['Outputs'])==expected
    # Sensitive refs may occur only in the function environment, never outputs/metadata.
    forbidden=['MarketauxApiToken','ProxyUsernamePrefix','ProxyPassword']
    assert all(p not in json.dumps(t['Outputs']) for p in forbidden)
    assert all('DeletionPolicy' not in x for k,x in r.items() if k.endswith('Route') or k=='Integration')


def test_startup_quota_scope_matches_complete_configured_environment():
    from tradingview_mcp.lambda_server import CONFIGURED_KEYS
    assert set(template('runtime')['Resources']['Function']['Properties']['Environment']['Variables'])==CONFIGURED_KEYS


def test_mcp_tracing_is_opt_in_and_has_only_conditional_export_rights():
    t=template('runtime')
    p=t['Parameters'];f=t['Resources']['Function']['Properties']
    assert p['TracingMode']['Default']=='PassThrough'
    assert p['TracingMode']['AllowedValues']==['PassThrough','Active']
    assert 'TraceSampleRate' not in p
    assert f['TracingConfig']=={'Mode':{'Ref':'TracingMode'}}
    assert t['Conditions']['TracingEnabled']=={'Fn::Equals':[{'Ref':'TracingMode'},'Active']}
    conditional=t['Resources']['ExecutionRole']['Properties']['Policies'][1]['Fn::If']
    assert conditional[0]=='TracingEnabled' and conditional[2]=={'Ref':'AWS::NoValue'}
    statements=conditional[1]['PolicyDocument']['Statement']
    assert statements==[{'Effect':'Allow','Action':['xray:PutTraceSegments','xray:PutTelemetryRecords'],'Resource':'*'}]
    env=f['Environment']['Variables']
    assert 'TRADINGVIEW_MCP_TRACING_ENABLED' not in env and 'TRADINGVIEW_MCP_TRACE_SAMPLE_RATE' not in env
    assert not any(r['Type'] in ('AWS::CloudWatch::Alarm','AWS::CloudWatch::Dashboard') for r in t['Resources'].values())


def test_native_monitoring_adds_no_dependency_and_preserves_original_launch_files():
    import tomllib
    py=tomllib.loads((ROOT/'pyproject.toml').read_text())
    assert 'observability' not in py['project'].get('optional-dependencies',{})
    assert not any('opentelemetry' in value for value in py['project']['dependencies'])
    assert '--extra observability' not in (ROOT/'Dockerfile.lambda').read_text()
    assert '--extra observability' not in (ROOT/'Dockerfile').read_text()


def test_rest_runtime_is_function_only_and_leaves_gateway_wiring_to_access():
    # T052: service stack for the REST profile. Access owns every API Gateway attachment.
    t = template('runtime-rest')
    resources = t['Resources']
    types = [r['Type'] for r in resources.values()]
    for forbidden in ['AWS::ApiGatewayV2::Api', 'AWS::ApiGatewayV2::Integration', 'AWS::ApiGatewayV2::Route',
                      'AWS::ApiGatewayV2::Stage', 'AWS::ApiGatewayV2::Authorizer', 'AWS::ApiGateway::Method',
                      'AWS::ApiGateway::Resource', 'AWS::ApiGateway::Deployment', 'AWS::ApiGateway::RestApi',
                      'AWS::Lambda::Permission', 'AWS::Lambda::Url', 'AWS::Cognito::UserPool']:
        assert forbidden not in types
    assert {'LogGroup', 'ExecutionRole', 'Function', 'PublishedVersion', 'LiveAlias'} == set(resources)
    f = resources['Function']['Properties']
    assert f['Architectures'] == ['arm64'] and f['PackageType'] == 'Image' and 'VpcConfig' not in f
    assert '@sha256:' in t['Parameters']['ImageUri']['AllowedPattern']
    assert f['Timeout'] == {'Ref': 'TimeoutSeconds'}
    assert int(t['Parameters']['TimeoutSeconds']['Default']) <= 25
    assert f['Timeout'] and resources['LiveAlias']['Properties']['Name'] == 'live'
    assert set(t['Parameters']) >= {'RestApiId'} and 'ApiId' not in t['Parameters'] and 'AuthorizerId' not in t['Parameters']
    variables = f['Environment']['Variables']
    assert variables['TRADINGVIEW_MCP_PUBLIC_HOST'] == {'Fn::Sub': '${RestApiId}.execute-api.${AWS::Region}.amazonaws.com'}
    assert set(variables) == set(template('runtime')['Resources']['Function']['Properties']['Environment']['Variables'])
    expected = {'FunctionArn', 'AliasArn', 'PublishedVersion', 'ActiveVersion', 'ImageUri', 'SourceCommit',
                'LockSha256', 'DeploymentRevision', 'LogGroupName'}
    assert set(t['Outputs']) == expected
    assert all(p not in json.dumps(t['Outputs']) for p in ['MarketauxApiToken', 'ProxyUsernamePrefix', 'ProxyPassword'])


def test_rest_runtime_reserved_concurrency_is_optional_for_low_quota_accounts():
    # New accounts can lack the unreserved concurrency needed for a reservation; 0 omits it.
    t = template('runtime-rest')
    param = t['Parameters']['ReservedConcurrency']
    assert param['Default'] == 0 and param['MinValue'] == 0
    assert 'HasReservedConcurrency' in t['Conditions']
    f = t['Resources']['Function']['Properties']
    assert f['ReservedConcurrentExecutions'] == {'Fn::If': ['HasReservedConcurrency', {'Ref': 'ReservedConcurrency'}, {'Ref': 'AWS::NoValue'}]}


def test_rest_runtime_defaults_to_memory_that_fits_lambda_init_window():
    # At 1024 MB the server import alone took ~8.9 s of the 10 s init limit; 2048 MB halves it.
    t = template('runtime-rest')
    param = t['Parameters']['MemorySize']
    assert param['Default'] >= 2048
    assert param['MinValue'] <= param['Default'] <= param['MaxValue']


# T047/T050 audit: the MCP service must not reach any AWS, billing or identity service (spec 001 boundary).
FORBIDDEN_IMPORTS = {'boto3', 'botocore', 'aiobotocore', 'awscrt', 'stripe', 'jwt', 'jose', 'authlib', 'cognito_idp'}
ALLOWED_RUNTIME_ACTIONS = {'logs:CreateLogStream', 'logs:PutLogEvents', 'xray:PutTraceSegments', 'xray:PutTelemetryRecords'}


def _collect_actions(node, acc):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == 'Action':
                acc |= set(value if isinstance(value, list) else [value])
            else:
                _collect_actions(value, acc)
    elif isinstance(node, list):
        for item in node:
            _collect_actions(item, acc)
    return acc


def test_service_source_imports_no_aws_billing_or_identity_sdk():
    import ast
    root = Path(__file__).resolve().parents[2] / 'src' / 'tradingview_mcp'
    offenders = []
    for path in root.rglob('*.py'):
        for node in ast.walk(ast.parse(path.read_text())):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name.split('.')[0] in FORBIDDEN_IMPORTS:
                    offenders.append(f'{path.name}:{name}')
    assert offenders == []


def test_lambda_image_installs_no_deployment_or_extra_dependency_groups():
    dockerfile = (Path(__file__).resolve().parents[2] / 'Dockerfile.lambda').read_text()
    assert '--no-dev' in dockerfile
    for flag in ('--group', '--all-groups', '--extra', '--all-extras', '--with '):
        assert flag not in dockerfile


def test_runtime_roles_grant_only_logs_and_optional_trace_export():
    for name in ('runtime.yaml', 'runtime-rest.yaml'):
        t = json.loads((ROOT / 'infra/lambda' / name).read_text())
        roles = {k: v for k, v in t['Resources'].items() if v['Type'] == 'AWS::IAM::Role'}
        granted = set()
        for role in roles.values():
            granted |= _collect_actions(role['Properties'].get('Policies', []), set())
        assert granted <= ALLOWED_RUNTIME_ACTIONS, name


def test_rest_runtime_has_no_function_url_or_invoke_permission():
    t = json.loads((ROOT / 'infra/lambda/runtime-rest.yaml').read_text())
    types = {v['Type'] for v in t['Resources'].values()}
    assert not types & {'AWS::Lambda::Url', 'AWS::Lambda::Permission', 'AWS::ApiGateway::RestApi', 'AWS::ApiGateway::Method'}
