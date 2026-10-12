import re
from dataclasses import dataclass
from typing import Optional

from playwright.sync_api import sync_playwright

BASE_URL = "https://aclclouds.com"
PROJECTS_URL = f"{BASE_URL}/dashboard/projects"
ONLINE_TEXTS = ("Online", "ONLINE", "En ligne", "在线")
OFFLINE_TEXTS = ("Offline", "OFFLINE", "Stopped", "STOPPED", "Hors ligne", "离线", "已停止")
START_TEXTS = ("Start", "Démarrer", "启动", "开始")
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
    if any(item in lines for item in ("starting", "démarrage", "启动中")):
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


def first_visible_text(page, texts, timeout_ms=1800):
    per_item = max(250, timeout_ms // max(1, len(texts)))
    for text in texts:
        try:
            locator = page.get_by_text(text, exact=True).first
            if locator.is_visible(timeout=per_item):
                return locator
        except Exception:
            pass
    return None


def read_server_state(page) -> str:
    for text in ONLINE_TEXTS:
        try:
            if page.get_by_text(text, exact=True).first.is_visible(timeout=250):
                return "online"
        except Exception:
            pass
    for text in OFFLINE_TEXTS:
        try:
            if page.get_by_text(text, exact=True).first.is_visible(timeout=250):
                return "offline"
        except Exception:
            pass
    try:
        return extract_server_state_from_text(page.locator("body").inner_text(timeout=1800))
    except Exception:
        return "unknown"


def find_start_button(page):
    for text in START_TEXTS:
        try:
            button = page.get_by_role(
                "button", name=re.compile(rf"^\s*{re.escape(text)}\s*$", re.I)
            ).first
            if button.is_visible(timeout=350):
                return button
        except Exception:
            pass
    return first_visible_text(page, START_TEXTS, timeout_ms=1200)


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


def open_server(page, configured_server_url: Optional[str]) -> Optional[str]:
    server_url = validate_server_url(configured_server_url or "")
    if server_url:
        try:
            page.goto(server_url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(1000)
            if not page_is_login(page) and not page_is_blocked(page):
                return page.url or server_url
        except Exception:
            pass

    server_url = discover_server_url(page)
    if not server_url:
        return None
    if page.url != server_url:
        page.goto(server_url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(1000)
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
                page.wait_for_timeout(700)
            except Exception:
                pass
    return read_server_state(page) == "online"


def run_check(cookie_header: str, configured_server_url: Optional[str]) -> CheckResult:
    cookies = parse_cookie_header(cookie_header)
    if not cookies:
        return CheckResult(False, "cookie_invalid", "Cookie is empty or could not be parsed.")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(locale="en-US")
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

            state = read_server_state(page)
            if state == "online":
                return CheckResult(
                    True,
                    "online",
                    "Bot is Online.",
                    server_url=server_url,
                    online_verified=True,
                )

            start = find_start_button(page)
            if not start:
                return CheckResult(
                    False,
                    "status_unknown",
                    "Bot is not Online, but the Start button could not be found.",
                    server_url=server_url,
                )
            try:
                if not start.is_enabled():
                    return CheckResult(
                        True,
                        "starting",
                        "Start is disabled; the bot may already be starting.",
                        server_url=server_url,
                    )
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
