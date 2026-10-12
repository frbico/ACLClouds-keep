import re
from dataclasses import dataclass
from typing import Optional

from playwright.sync_api import sync_playwright

BASE_URL = "https://aclclouds.com"
PROJECTS_URL = f"{BASE_URL}/dashboard/projects"
ONLINE_TEXTS = ("Online", "ONLINE", "Running", "RUNNING", "En ligne", "在线", "运行中")
OFFLINE_TEXTS = ("Offline", "OFFLINE", "Stopped", "STOPPED", "Hors ligne", "离线", "已停止")
START_TEXTS = ("Start", "Démarrer", "启动", "开始")
STOP_TEXTS = ("Stop", "Arrêter", "停止")
RESTART_TEXTS = ("Restart", "Redémarrer", "重启")
STARTING_TEXTS = ("Starting", "Démarrage", "启动中")
DETAIL_TEXTS = ("View service details", "Service details", "Voir les détails", "查看服务详情")


@dataclass
class CheckResult:
    ok: bool
    status: str
    message: str
    server_url: Optional[str] = None
    start_clicked: bool = False
    online_verified: bool = False


def parse_cookie_header(raw: str):
    cookies = []
    for part in (raw or "").strip().split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, value = part.split("=", 1)
        name = name.strip()
        value = value.strip().replace("\r", "").replace("\n", "")
        if name:
            cookies.append({"name": name, "value": value, "url": f"{BASE_URL}/"})
    return cookies


def validate_server_url(raw: str) -> Optional[str]:
    value = (raw or "").strip().rstrip("/")
    if not value:
        return None
    if re.fullmatch(r"https://aclclouds\.com/server/[A-Za-z0-9_-]+", value):
        return value
    return None


def extract_server_state_from_text(body: str) -> str:
    text = (body or "").replace("\xa0", " ")
    lines = {line.strip().lower() for line in text.splitlines() if line.strip()}
    if any(item.lower() in lines for item in ONLINE_TEXTS):
        return "online"
    if any(item.lower() in lines for item in OFFLINE_TEXTS):
        return "offline"
    if any(item.lower() in lines for item in STARTING_TEXTS):
        return "starting"
    return "unknown"


def page_is_login(page) -> bool:
    url = (page.url or "").lower()
    if any(token in url for token in ("login", "signin", "sign-in")):
        return True
    try:
        body = (page.locator("body").inner_text(timeout=2500) or "").lower()
    except Exception:
        return False
    markers = ("sign in", "log in", "se connecter", "connexion")
    return any(marker in body for marker in markers) and "/server/" not in url


def page_is_blocked(page) -> bool:
    try:
        title = (page.title() or "").lower()
        body = (page.locator("body").inner_text(timeout=2500) or "").lower()
    except Exception:
        return False
    markers = (
        "verify you are human",
        "just a moment",
        "attention required",
        "checking your browser",
        "access denied",
        "cloudflare",
    )
    return any(marker in title or marker in body for marker in markers)


def first_visible_locator(locator, timeout_ms=1000):
    try:
        count = min(locator.count(), 30)
    except Exception:
        return None
    if count == 0:
        return None

    per_match = max(100, timeout_ms // count)
    for index in range(count):
        candidate = locator.nth(index)
        try:
            if candidate.is_visible(timeout=per_match):
                return candidate
        except Exception:
            continue
    return None


def first_visible_text(page, texts, timeout_ms=1800):
    per_item = max(250, timeout_ms // max(1, len(texts)))
    for text in texts:
        try:
            candidate = first_visible_locator(
                page.get_by_text(text, exact=True), timeout_ms=per_item
            )
            if candidate:
                return candidate
        except Exception:
            pass
    return None


def find_button(page, texts, timeout_ms=1200):
    per_item = max(200, timeout_ms // max(1, len(texts)))
    for text in texts:
        try:
            candidate = first_visible_locator(
                page.get_by_role(
                    "button", name=re.compile(rf"^\s*{re.escape(text)}\s*$", re.I)
                ),
                timeout_ms=per_item,
            )
            if candidate:
                return candidate
        except Exception:
            pass
    return None


def locator_is_enabled(locator) -> bool:
    if not locator:
        return False
    try:
        return locator.is_enabled()
    except Exception:
        return False


def read_server_state(page) -> str:
    if first_visible_text(page, ONLINE_TEXTS, timeout_ms=500):
        return "online"
    if first_visible_text(page, OFFLINE_TEXTS, timeout_ms=500):
        return "offline"
    if first_visible_text(page, STARTING_TEXTS, timeout_ms=400):
        return "starting"

    try:
        body_state = extract_server_state_from_text(
            page.locator("body").inner_text(timeout=1200)
        )
        if body_state != "unknown":
            return body_state
    except Exception:
        pass

    start = find_button(page, START_TEXTS, timeout_ms=500)
    stop = find_button(page, STOP_TEXTS, timeout_ms=400)
    restart = find_button(page, RESTART_TEXTS, timeout_ms=400)
    if start:
        try:
            if start.is_enabled():
                return "offline"
        except Exception:
            pass
        # ACLClouds disables Start while the service is Online. Stop or Restart
        # remaining enabled is a reliable fallback when the status badge is
        # rendered without accessible text.
        if locator_is_enabled(stop) or locator_is_enabled(restart):
            return "online"
        return "starting"
    return "unknown"


def find_start_button(page, timeout_ms=1200):
    return find_button(page, START_TEXTS, timeout_ms=timeout_ms) or first_visible_text(
        page, START_TEXTS, timeout_ms=timeout_ms
    )


def wait_for_control_panel(page, timeout_seconds=25):
    attempts = max(1, timeout_seconds * 2)
    for _ in range(attempts):
        state = read_server_state(page)
        start = find_start_button(page, timeout_ms=300)
        if state == "online" or start:
            return state, start
        page.wait_for_timeout(500)
    return read_server_state(page), find_start_button(page, timeout_ms=800)


def expand_first_service(page) -> bool:
    if page.locator("a[href*='/server/']").count():
        return True

    blocked = (
        "renew",
        "cancel",
        "delete",
        "stop",
        "restart",
        "start",
        "support",
        "invoice",
        "csv",
        "filter",
    )
    for selector in (
        "main button[aria-expanded='false']",
        "main [role='button'][aria-expanded='false']",
        "main button:has(svg)",
    ):
        try:
            candidates = page.locator(selector)
            for index in range(min(candidates.count(), 40)):
                candidate = candidates.nth(index)
                try:
                    text = (candidate.inner_text(timeout=250) or "").strip().lower()
                    label = " ".join(
                        filter(
                            None,
                            (
                                candidate.get_attribute("aria-label"),
                                candidate.get_attribute("title"),
                            ),
                        )
                    ).strip().lower()
                    combined = f"{text} {label}".strip()
                    if any(word in combined for word in blocked):
                        continue
                    if (
                        selector.endswith(":has(svg)")
                        and text
                        and candidate.get_attribute("aria-expanded") != "false"
                    ):
                        continue
                    if candidate.is_visible(timeout=250) and candidate.is_enabled():
                        candidate.click(timeout=1600)
                        page.wait_for_timeout(500)
                        if (
                            page.locator("a[href*='/server/']").count()
                            or first_visible_text(page, DETAIL_TEXTS, 600)
                        ):
                            return True
                except Exception:
                    continue
        except Exception:
            continue
    return first_visible_text(page, DETAIL_TEXTS, 600) is not None


def discover_server_url(page) -> Optional[str]:
    page.goto(PROJECTS_URL, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(1200)
    if page_is_login(page) or page_is_blocked(page):
        return None

    for _ in range(2):
        try:
            links = page.locator("a[href*='/server/']")
            for index in range(min(links.count(), 20)):
                href = links.nth(index).get_attribute("href") or ""
                if "/server/" in href:
                    return href if href.startswith("http") else f"{BASE_URL}{href}"
        except Exception:
            pass
        if not expand_first_service(page):
            break

    details = first_visible_text(page, DETAIL_TEXTS, timeout_ms=1600)
    if details:
        try:
            details.click(timeout=4000)
            page.wait_for_url(re.compile(r".*/server/[^/?#]+"), timeout=12000)
            return page.url
        except Exception:
            if "/server/" in (page.url or ""):
                return page.url
    return None


def settle_page(page):
    try:
        page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        pass
    page.wait_for_timeout(1500)


def open_server(page, configured_server_url: Optional[str]) -> Optional[str]:
    server_url = validate_server_url(configured_server_url or "")
    if server_url:
        try:
            page.goto(server_url, wait_until="domcontentloaded", timeout=45000)
            settle_page(page)
            if not page_is_login(page) and not page_is_blocked(page):
                return page.url or server_url
        except Exception:
            pass

    server_url = discover_server_url(page)
    if not server_url:
        return None
    if page.url != server_url:
        page.goto(server_url, wait_until="domcontentloaded", timeout=45000)
        settle_page(page)
    return page.url or server_url


def wait_until_online(page, server_url: str, timeout_seconds: int = 120) -> bool:
    attempts = max(1, timeout_seconds // 5)
    for attempt in range(attempts):
        if read_server_state(page) == "online":
            return True
        page.wait_for_timeout(5000)
        if attempt and attempt % 3 == 0:
            try:
                page.goto(server_url, wait_until="domcontentloaded", timeout=45000)
                settle_page(page)
            except Exception:
                pass
    return read_server_state(page) == "online"


def run_check(cookie_header: str, configured_server_url: Optional[str]) -> CheckResult:
    cookies = parse_cookie_header(cookie_header)
    if not cookies:
        return CheckResult(False, "cookie_invalid", "Cookie is empty or could not be parsed.")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            locale="en-US", viewport={"width": 1600, "height": 1000}
        )
        try:
            context.add_cookies(cookies)
        except Exception as exc:
            browser.close()
            return CheckResult(False, "cookie_invalid", f"Browser rejected the Cookie: {exc}")

        page = context.new_page()
        try:
            server_url = open_server(page, configured_server_url)
            if page_is_blocked(page):
                return CheckResult(
                    False,
                    "blocked",
                    "ACLClouds displayed an anti-bot or human-verification page.",
                )
            if page_is_login(page):
                return CheckResult(
                    False,
                    "cookie_expired",
                    "The ACLClouds session has expired. Update this account's Cookie.",
                )
            if not server_url:
                return CheckResult(
                    False,
                    "server_not_found",
                    "No server details page was found. Set the Bot control-panel URL in Settings.",
                )

            state, start = wait_for_control_panel(page)
            if state == "online":
                return CheckResult(
                    True,
                    "online",
                    "Bot is Online.",
                    server_url=server_url,
                    online_verified=True,
                )

            if not start:
                return CheckResult(
                    False,
                    "status_unknown",
                    "The control panel did not expose a visible Start button within 25 seconds.",
                    server_url=server_url,
                )

            try:
                start_enabled = start.is_enabled()
            except Exception as exc:
                return CheckResult(
                    False,
                    "status_unknown",
                    f"Start button state could not be read: {exc}",
                    server_url=server_url,
                )

            if not start_enabled:
                if wait_until_online(page, server_url, timeout_seconds=45):
                    return CheckResult(
                        True,
                        "online",
                        "Bot is Online (verified from the control-button state).",
                        server_url=server_url,
                        online_verified=True,
                    )
                return CheckResult(
                    True,
                    "starting",
                    "Start is disabled and Online is not confirmed yet; it will be checked again.",
                    server_url=server_url,
                )

            try:
                start.click(timeout=5000)
            except Exception as exc:
                return CheckResult(
                    False,
                    "start_failed",
                    f"Start could not be clicked: {exc}",
                    server_url=server_url,
                )

            if wait_until_online(page, server_url):
                return CheckResult(
                    True,
                    "started",
                    "Start was clicked and Online status was verified.",
                    server_url=server_url,
                    start_clicked=True,
                    online_verified=True,
                )
            return CheckResult(
                False,
                "start_unverified",
                "Start was clicked, but Online was not confirmed within 120 seconds.",
                server_url=server_url,
                start_clicked=True,
            )
        finally:
            context.close()
            browser.close()
