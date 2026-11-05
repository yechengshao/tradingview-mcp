"""Separate-process, real-wire parity against a frozen catalog."""
import asyncio
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).parent/'support'))
from provider_fixture import ROOT, baseline, baseline_source, http_server, http_probe, stdio_probe


@pytest.mark.parametrize('provider,key',[('success','catalog'),('failure','failure_results')])
def test_lambda_wire_matches_frozen_baseline(provider,key):
    data=baseline()
    with http_server(provider=provider) as url:
        actual=asyncio.run(http_probe(url))
    if provider=='success':
        assert actual==data[key]
        assert len(actual['tools'])==39
    else:
        assert actual['results']==data[key]


def test_pinned_baseline_matches_captured_expectations():
    with baseline_source() as source:
        assert asyncio.run(stdio_probe(source))==baseline()['catalog']


def test_concurrent_and_replaced_processes_need_no_shared_session():
    async def concurrent(url):
        return await asyncio.gather(*(http_probe(url) for _ in range(5)))
    for _ in range(2):
        with http_server() as url:
            assert all(result==baseline()['catalog'] for result in asyncio.run(concurrent(url)))


def test_frozen_expectations_detect_matching_candidate_drift():
    expected=baseline()['catalog']['tools']
    stdio=asyncio.run(stdio_probe(drift=True))['tools']
    with http_server(drift=True) as url:
        candidate=asyncio.run(http_probe(url))['tools']
    assert stdio==candidate
    assert candidate!=expected
