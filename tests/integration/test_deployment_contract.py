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
