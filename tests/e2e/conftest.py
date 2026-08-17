"""Playwright + Streamlit fixtures for customer browser smoke tests."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = REPO_ROOT / "artifacts" / "e2e"
APP_PATH = REPO_ROOT / "streamlit_app.py"
E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

from helpers import ARTIFACTS as HELPERS_ARTIFACTS  # noqa: E402


def _free_port() -> int:
    configured = os.environ.get("CEL_E2E_PORT")
    if configured:
        return int(configured)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_http(url: str, *, timeout: float = 60.0) -> None:
    import urllib.request

    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:  # noqa: S310
                if response.status < 500:
                    return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(0.4)
    raise RuntimeError(f"Streamlit did not become ready at {url}: {last_error}")


@pytest.fixture(scope="session")
def e2e_base_url() -> str:
    pytest.importorskip("playwright")
    port = _free_port()
    env = os.environ.copy()
    env.pop("CEL_APP_MODE", None)  # force CUSTOMER default
    env["CEL_ZERO_ENTRY_STUB"] = "1"
    env["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(APP_PATH),
        "--server.headless=true",
        "--server.port",
        str(port),
        "--server.address",
        "127.0.0.1",
        "--browser.gatherUsageStats=false",
        "--global.developmentMode=false",
    ]
    proc = subprocess.Popen(  # noqa: S603
        command,
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        _wait_http(url)
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


@pytest.fixture(scope="session")
def browser_context(e2e_base_url: str):
    from playwright.sync_api import sync_playwright

    headed = os.environ.get("CEL_E2E_HEADED", "").strip() in {"1", "true", "yes"}
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(
                headless=not headed, channel="chrome"
            )
        except Exception:
            browser = playwright.chromium.launch(headless=not headed)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="zh-TW",
        )
        context.set_default_timeout(30_000)
        yield context, e2e_base_url
        context.close()
        browser.close()


@pytest.fixture
def page(browser_context, request):
    context, base_url = browser_context
    page = context.new_page()
    console_errors: list[str] = []
    page_errors: list[str] = []

    def _on_console(msg) -> None:
        if msg.type == "error":
            text = msg.text
            if any(
                noise in text
                for noise in (
                    "favicon.ico",
                    "net::ERR_CONNECTION_REFUSED",
                    "ResizeObserver loop",
                )
            ):
                return
            console_errors.append(text)

    def _on_page_error(exc) -> None:
        page_errors.append(str(exc))

    page.on("console", _on_console)
    page.on("pageerror", _on_page_error)
    page.emulate_media(reduced_motion="no-preference")
    page._cel_console_errors = console_errors  # type: ignore[attr-defined]
    page._cel_page_errors = page_errors  # type: ignore[attr-defined]
    page._cel_base_url = base_url  # type: ignore[attr-defined]

    HELPERS_ARTIFACTS.mkdir(parents=True, exist_ok=True)

    yield page

    failed = getattr(request.node, "rep_call", None)
    if failed is not None and failed.failed:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        name = request.node.name.replace("/", "_")
        path = HELPERS_ARTIFACTS / f"{name}_{stamp}.png"
        try:
            page.screenshot(path=str(path), full_page=True)
            meta = HELPERS_ARTIFACTS / f"{name}_{stamp}.txt"
            meta.write_text(
                f"test={request.node.name}\nurl={page.url}\n",
                encoding="utf-8",
            )
        except Exception:  # noqa: BLE001
            pass
    page.close()


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    setattr(item, f"rep_{report.when}", report)
