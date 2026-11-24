import json
import pytest

from omnix.service_adapters import GitHubAdapter, ServiceAdapterError


class Response:
    status = 200
    headers = {}
    def __enter__(self): return self
    def __exit__(self, *_): return None
    def read(self, _limit): return json.dumps({"ok": True}).encode()


def test_github_adapter_uses_allowlisted_official_api(monkeypatch):
    seen = {}
    class Opener:
        def open(self, request, timeout):
            seen.update(url=request.full_url)
            return Response()
    monkeypatch.setattr("omnix.service_adapters.urllib.request.build_opener", lambda *_: Opener())
    result = GitHubAdapter("https://api.github.com", "scoped-token", {"api.github.com"}).repository("e9aj", "omni-x")
    assert result.body == {"ok": True}
    assert seen["url"] == "https://api.github.com/repos/e9aj/omni-x"


def test_adapter_rejects_unapproved_or_insecure_endpoint():
    with pytest.raises(ValueError):
        GitHubAdapter("http://api.github.com", "token", {"api.github.com"})
    adapter = GitHubAdapter("https://api.github.com", "token", {"api.github.com"})
    with pytest.raises(ServiceAdapterError):
        adapter.request("GET", "/../secrets")
