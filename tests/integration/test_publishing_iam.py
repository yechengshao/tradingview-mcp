"""Service publishing IAM invariants (spec 001 T045). No AWS calls."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PUSH_ACTIONS = {'ecr:BatchCheckLayerAvailability', 'ecr:CompleteLayerUpload', 'ecr:UploadLayerPart',
                'ecr:InitiateLayerUpload', 'ecr:PutImage', 'ecr:BatchGetImage', 'ecr:GetDownloadUrlForLayer'}


def template():
    return json.loads((ROOT / 'infra/lambda/publishing-iam.yaml').read_text())


def test_github_oidc_provider_is_created_once_and_retained():
    r = template()['Resources']
    providers = [v for v in r.values() if v['Type'] == 'AWS::IAM::OIDCProvider']
    assert len(providers) == 1
    provider = providers[0]
    assert provider['DeletionPolicy'] == 'Retain' and provider['UpdateReplacePolicy'] == 'Retain'
    assert provider['Properties']['Url'] == 'https://token.actions.githubusercontent.com'
    assert provider['Properties']['ClientIdList'] == ['sts.amazonaws.com']


def test_publisher_role_trusts_only_the_publication_environment():
    t = template()
    role = t['Resources']['PublisherRole']['Properties']
    statement = role['AssumeRolePolicyDocument']['Statement']
    assert len(statement) == 1
    s = statement[0]
    assert s['Action'] == 'sts:AssumeRoleWithWebIdentity'
    assert s['Principal'] == {'Federated': {'Ref': 'GitHubOidcProvider'}}
    assert s['Condition']['StringEquals']['token.actions.githubusercontent.com:aud'] == 'sts.amazonaws.com'
    assert s['Condition']['StringEquals']['token.actions.githubusercontent.com:sub'] == {
        'Fn::Sub': '${GithubSubjectPrefix}:environment:${PublicationEnvironment}'}
    # Immutable subject claims: GitHub's sub uses owner/repo IDs, not names.
    assert t['Parameters']['GithubSubjectPrefix']['Default'] == 'repo:yechengshao@7886247/tradingview-mcp@1423980237'
    assert 'GithubRepository' not in t['Parameters']
    assert t['Parameters']['PublicationEnvironment']['Default'] == 'lambda-publication'


def test_publisher_permissions_are_limited_to_pushing_one_repository():
    role = template()['Resources']['PublisherRole']['Properties']
    statements = [s for p in role['Policies'] for s in p['PolicyDocument']['Statement']]
    assert all(s['Effect'] == 'Allow' for s in statements)
    push = [s for s in statements if set(s['Action']) == PUSH_ACTIONS]
    assert len(push) == 1
    assert push[0]['Resource'] == {'Fn::Sub': 'arn:${AWS::Partition}:ecr:${AWS::Region}:${AWS::AccountId}:repository/${RepositoryName}'}
    login = [s for s in statements if s.get('Action') == 'ecr:GetAuthorizationToken']
    assert login and login[0]['Resource'] == '*'
    actions = {a for s in statements for a in (s['Action'] if isinstance(s['Action'], list) else [s['Action']])}
    assert actions == PUSH_ACTIONS | {'ecr:GetAuthorizationToken'}
    assert not any('*' in a for a in actions)
    assert 'RepositoryName' in template()['Parameters']


def test_outputs_are_nonsecret_identifiers_only():
    t = template()
    assert set(t['Outputs']) == {'PublisherRoleArn', 'GitHubOidcProviderArn'}
    text = json.dumps(t['Outputs'])
    assert 'Secret' not in text and 'Password' not in text
