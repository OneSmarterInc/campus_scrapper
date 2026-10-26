"""Search must reject unrelated SERPs before fetching or model assessment."""
import httpx
import pytest
from campusscraper.discovery_services import CachedSearch, ConfigurationError, DiscoveryDB
from campusscraper.search_candidates import unrelated_result

QUERY = 'engineering colleges Mumbai faculty directory site:.ac.in'
BAD = {'url': 'https://www.bath.ac.uk/campaigns/what-is-engineering/',
       'title': 'What is engineering? - University of Bath',
       'content': 'Engineering is designing and building machines using maths and science.',
       'engines': ['bing']}
GOOD = {'url': 'https://college.example/faculty', 'title': 'Mumbai engineering college faculty', 'engines': ['google']}


def test_quality_gate_preserves_sparse_acronym_and_relevant_sources():
    assert unrelated_result(QUERY, BAD)
    assert not unrelated_result(QUERY, GOOD)
    assert not unrelated_result('VJTI', {'url': 'https://vjti.ac.in/', 'title': 'Home'})
    assert not unrelated_result(QUERY, {'url': 'https://college.example/'})


def test_bad_search_recovers_once_and_caches_good_urls(tmp_path):
    db = DiscoveryDB(tmp_path / 'db')
    calls = []
    def handle(req):
        calls.append(req)
        assert req.url.params['q'] == QUERY
        assert req.url.params['safesearch'] == '2'
        result = GOOD if 'engines' in req.url.params else BAD
        return httpx.Response(200, json={'results': [result]})
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        search = CachedSearch(db, 'job', 'http://localhost:8080', client=client)
        assert search.search(QUERY) == [GOOD['url']]
        assert search.search(QUERY) == [GOOD['url']]
        assert search.search_details[QUERY]['initial_rejected_results'] == [BAD | {'content': BAD['content']}]
    assert len(calls) == 2
    assert 'bing' not in calls[-1].url.params['engines']
    db.db.close()


@pytest.mark.parametrize('fallback', [[], [BAD]])
def test_bad_search_never_becomes_success_or_infinite_retry(tmp_path, fallback):
    db = DiscoveryDB(tmp_path / 'db')
    calls = []
    def handle(req):
        calls.append(req)
        return httpx.Response(200, json={'results': fallback if len(calls) > 1 else [BAD]})
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        search = CachedSearch(db, 'job', 'http://localhost:8080', client=client)
        with pytest.raises(ConfigurationError, match='unrelated'):
            search.search(QUERY)
        assert search.search_details[QUERY]['rejected_results'] == [BAD]
    assert len(calls) == 2
    db.db.close()


def test_fallback_outage_evidence_is_serializable(tmp_path):
    import json
    db = DiscoveryDB(tmp_path / 'db')
    calls = []
    def handle(req):
        calls.append(req)
        if len(calls) == 2:
            return httpx.Response(503)
        return httpx.Response(200, json={'results': [BAD]})
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        search = CachedSearch(db, 'job', 'http://localhost:8080', client=client)
        with pytest.raises(ConfigurationError):
            search.search(QUERY)
        json.dumps(search.search_details)
        assert search.search_details[QUERY]['fallback_used']
    db.db.close()
