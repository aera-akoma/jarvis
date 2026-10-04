from __future__ import annotations

from concurrent.futures import Future
from pathlib import Path
import queue
import threading
from typing import Any, Callable
from urllib.parse import urlsplit


class BrowserController:
    """A persistent, headed browser session serialized on its owner thread."""

    def __init__(self, playwright_factory: Callable[[], Any] | None = None) -> None:
        self._playwright_factory = playwright_factory
        self._queue: queue.Queue[tuple[str, tuple, Future] | None] = queue.Queue()
        self._start_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._playwright = None
        self._browser = None
        self._page = None

    def _ensure_thread(self) -> None:
        with self._start_lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, name="JarvisBrowser", daemon=True)
                self._thread.start()

    def _dispatch(self, operation: str, *args):
        self._ensure_thread()
        future: Future = Future()
        self._queue.put((operation, args, future))
        return future.result()

    def _run(self) -> None:
        while True:
            task = self._queue.get()
            if task is None:
                return
            operation, args, future = task
            if not future.set_running_or_notify_cancel():
                continue
            try:
                result = getattr(self, f"_{operation}")(*args)
            except Exception as exc:
                future.set_result({"success": False, "error": str(exc)})
            else:
                future.set_result({"success": True, **result})

    def _start(self) -> None:
        if self._browser is not None:
            return
        factory = self._playwright_factory
        if factory is None:
            try:
                from playwright.sync_api import sync_playwright
            except ImportError as exc:
                raise RuntimeError("Browser tools require Playwright. Install project requirements, then use installed Microsoft Edge or Chrome.") from exc
            factory = sync_playwright
        self._playwright = factory().start()
        failures = []
        for channel in ("msedge", "chrome", None):
            try:
                if channel is None:
                    self._browser = self._playwright.chromium.launch(headless=False)
                else:
                    self._browser = self._playwright.chromium.launch(channel=channel, headless=False)
                break
            except Exception as exc:
                failures.append(f"{channel or 'Playwright Chromium'}: {exc}")
        if self._browser is None:
            self._playwright.stop()
            self._playwright = None
            raise RuntimeError("Could not launch a browser. Install Edge/Chrome or run `python -m playwright install chromium`. " + " | ".join(failures))

    @staticmethod
    def _validate_url(url: str) -> str:
        parsed = urlsplit((url or "").strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Browser URLs must use http:// or https:// and include a host.")
        if parsed.username or parsed.password:
            raise ValueError("Do not put credentials in browser URLs.")
        return parsed.geturl()

    def _open_browser(self, url: str) -> dict[str, Any]:
        target = self._validate_url(url)
        self._start()
        self._page = self._browser.new_page()
        self._page.set_default_timeout(10_000)
        response = self._page.goto(target, wait_until="domcontentloaded", timeout=15_000)
        self._validate_url(self._page.url)
        return {"url": self._page.url, "title": self._page.title(), "status": response.status if response else None}

    def _navigate_browser(self, url: str) -> dict[str, Any]:
        if self._page is None:
            raise RuntimeError("Open a browser page before navigating.")
        target = self._validate_url(url)
        response = self._page.goto(target, wait_until="domcontentloaded", timeout=15_000)
        self._validate_url(self._page.url)
        return {"url": self._page.url, "title": self._page.title(), "status": response.status if response else None}

    def _require_web_page(self):
        if self._page is None:
            raise RuntimeError("Open a browser page before interacting with it.")
        self._validate_url(self._page.url)
        return self._page

    def _locator(self, selector: str):
        page = self._require_web_page()
        if not selector or not selector.strip():
            raise ValueError("A CSS selector is required.")
        locator = page.locator(selector)
        count = locator.count()
        if count != 1:
            raise ValueError(f"Selector must identify exactly one element; it matched {count}.")
        return locator

    def _click_browser_element(self, selector: str) -> dict[str, Any]:
        self._locator(selector).click(timeout=10_000)
        return {"selector": selector, "clicked": True}

    def _type_browser(self, selector: str, text: str) -> dict[str, Any]:
        if len(text) > 20_000:
            raise ValueError("Browser text input is limited to 20,000 characters per action.")
        self._locator(selector).fill(text, timeout=10_000)
        return {"selector": selector, "characters_typed": len(text)}

    def _read_page(self) -> dict[str, Any]:
        page = self._require_web_page()
        text = page.locator("body").inner_text(timeout=10_000)
        return {"url": page.url, "title": page.title(), "text": text[:20_000], "truncated": len(text) > 20_000}

    def _take_browser_screenshot(self, path: str) -> dict[str, Any]:
        page = self._require_web_page()
        target = Path(path).expanduser()
        if target.suffix.lower() != ".png":
            raise ValueError("Browser screenshots must use the .png extension.")
        target.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(target), type="png")
        return {"path": str(target.resolve()), "image_path": str(target.resolve()), "format": "png", "url": page.url}

    def _close_browser(self) -> dict[str, Any]:
        if self._browser is None:
            return {"closed": False, "message": "No Jarvis browser session is open."}
        self._browser.close()
        self._browser = None
        self._page = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None
        return {"closed": True}

    def open_browser(self, url: str) -> dict[str, Any]:
        return self._dispatch("open_browser", url)

    def navigate_browser(self, url: str) -> dict[str, Any]:
        return self._dispatch("navigate_browser", url)

    def click_browser_element(self, selector: str) -> dict[str, Any]:
        return self._dispatch("click_browser_element", selector)

    def type_browser(self, selector: str, text: str) -> dict[str, Any]:
        return self._dispatch("type_browser", selector, text)

    def read_page(self) -> dict[str, Any]:
        return self._dispatch("read_page")

    def take_browser_screenshot(self, path: str) -> dict[str, Any]:
        return self._dispatch("take_browser_screenshot", path)

    def close_browser(self) -> dict[str, Any]:
        return self._dispatch("close_browser")
