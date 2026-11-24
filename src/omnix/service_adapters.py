"""Credential-scoped REST adapters for reviewed optional services.

These adapters perform no discovery or activation. A host must supply an
authorised token, exact HTTPS allowlist and an enabled IntegrationRegistry
entry before calling them.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
import urllib.request
from urllib.request import Request


class ServiceAdapterError(RuntimeError):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass(frozen=True)
class ServiceResponse:
    status: int
    body: dict | list | str


class AuthorizedRestAdapter:
    def __init__(self, base_url: str, token: str, allowed_hosts: set[str], *, timeout: float = 10.0):
        parsed = urlsplit(base_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.hostname not in allowed_hosts or parsed.username or parsed.password:
            raise ValueError("service endpoint is not authorised")
        if not token or timeout <= 0 or timeout > 60:
            raise ValueError("service adapter configuration is invalid")
        self.base_url = base_url.rstrip("/") + "/"
        self.token, self.allowed_hosts, self.timeout = token, frozenset(allowed_hosts), timeout

    def request(self, method: str, path: str, payload: dict | None = None) -> ServiceResponse:
        if not path.startswith("/") or ".." in path.split("/"):
            raise ServiceAdapterError("service path is invalid")
        url = urljoin(self.base_url, path.lstrip("/"))
        parsed = urlsplit(url)
        if parsed.hostname not in self.allowed_hosts or parsed.scheme != "https":
            raise ServiceAdapterError("service endpoint is not authorised")
        data = json.dumps(payload).encode() if payload is not None else None
        request = Request(url, data=data, method=method.upper(), headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json", "Content-Type": "application/json"})
        try:
            opener = urllib.request.build_opener(_NoRedirect)
            with opener.open(request, timeout=self.timeout) as response:
                raw = response.read(2_000_000)
                if len(raw) >= 2_000_000:
                    raise ServiceAdapterError("service response exceeds 2 MB")
                try:
                    body = json.loads(raw.decode())
                except (UnicodeDecodeError, json.JSONDecodeError):
                    body = raw.decode("utf-8", errors="replace")
                return ServiceResponse(int(response.status), body)
        except (HTTPError, URLError, TimeoutError) as exc:
            raise ServiceAdapterError("service request failed") from exc

    def health(self) -> ServiceResponse:
        return self.request("GET", "/")


class GitHubAdapter(AuthorizedRestAdapter):
    def repository(self, owner: str, repo: str) -> ServiceResponse:
        return self.request("GET", f"/repos/{owner}/{repo}")
    def create_issue(self, owner: str, repo: str, title: str, body: str = "") -> ServiceResponse:
        return self.request("POST", f"/repos/{owner}/{repo}/issues", {"title": title, "body": body})


class SupabaseAdapter(AuthorizedRestAdapter):
    def table_rows(self, table: str) -> ServiceResponse:
        return self.request("GET", f"/rest/v1/{table}")


class SalesforceAdapter(AuthorizedRestAdapter):
    def query(self, soql: str) -> ServiceResponse:
        from urllib.parse import quote
        return self.request("GET", f"/services/data/v60.0/query?q={quote(soql, safe='')}")


class GoogleWorkspaceAdapter(AuthorizedRestAdapter):
    def drive_files(self) -> ServiceResponse:
        return self.request("GET", "/drive/v3/files")


class Microsoft365Adapter(AuthorizedRestAdapter):
    def me(self) -> ServiceResponse:
        return self.request("GET", "/v1.0/me")


class OpenProjectAdapter(AuthorizedRestAdapter):
    def projects(self) -> ServiceResponse:
        return self.request("GET", "/api/v3/projects")


class CalDiyAdapter(AuthorizedRestAdapter):
    def availability(self) -> ServiceResponse:
        return self.request("GET", "/api/availability")


class ChatwootAdapter(AuthorizedRestAdapter):
    def conversations(self, account_id: str) -> ServiceResponse:
        return self.request("GET", f"/api/v1/accounts/{account_id}/conversations")


class OpenSEOAdapter(AuthorizedRestAdapter):
    def audit(self, url: str) -> ServiceResponse:
        return self.request("POST", "/api/audit", {"url": url})


class AppFlowyAdapter(AuthorizedRestAdapter):
    def workspaces(self) -> ServiceResponse:
        return self.request("GET", "/api/workspaces")


class CapAdapter(AuthorizedRestAdapter):
    def recordings(self) -> ServiceResponse:
        return self.request("GET", "/api/recordings")


class ComfyUIAdapter(AuthorizedRestAdapter):
    def queue_prompt(self, prompt: dict) -> ServiceResponse:
        return self.request("POST", "/prompt", {"prompt": prompt})
