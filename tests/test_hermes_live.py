"""Opt-in tests against the installer-managed Hermes runtime on Windows."""

import os

import pytest

from omnix.hermes_browser import HermesBrowserAdapter
from omnix.hermes_runtime import hermes_python, installed_hermes_source


@pytest.mark.skipif(os.environ.get("OMNIX_HERMES_LIVE") != "1", reason="requires installed Hermes browser runtime")
def test_installed_hermes_browser_navigation_screenshot_and_shutdown():
    assert installed_hermes_source() is not None
    assert hermes_python() is not None
    browser = HermesBrowserAdapter(approver=lambda _: True)
    output = browser.execute(
        'new_tab("https://example.com"); wait_for_load(); goto_url("https://www.iana.org/domains/example"); wait_for_load(); print(page_info()); capture_screenshot()',
        timeout_s=90,
    )
    assert "iana.org" in output
    assert "Example Domains" in output or "Example Domain" in output
    assert "workspace" in output
    assert "Browser sessions shut down" in browser.shutdown()
    # Recovery: a clean lifecycle restart must be able to create a new session.
    recovered = browser.execute('new_tab("https://example.com"); wait_for_load(); print(page_info())', timeout_s=90)
    assert "example.com" in recovered
    assert "Browser sessions shut down" in browser.shutdown()
