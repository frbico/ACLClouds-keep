import re
from dataclasses import dataclass
from typing import Optional
from playwright.sync_api import sync_playwright

BASE_URL = "https://aclclouds.com"
PROJECTS_URL = f"{BASE_URL}/dashboard/projects"

RENEW_TEXTS = ["Renew now", "Renew", "Renouveler maintenant", "Renouveler", "立即续期", "续期"]
CONFIRM_TEXTS = ["Confirm", "Confirmer", "确认"]
START_TEXTS = ["Start", "Démarrer", "开机"]
OFFLINE_TEXTS = ["OFFLINE", "Offline", "Hors ligne", "离线"]


@dataclass
class CheckResult:
    ok: bool
    status: str
    message: str
    remaining_minutes: Optional[int] = None
    project_url: Optional[str] = None
    renewed: bool = False
    renewal_verified: bool = False
    started: bool = False


def parse_cookie_header(raw: str):
    cookies = []
    for part in raw.strip().split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, value = part.split("=", 1)
        name = name.strip()
        value = value.strip().replace("\r", "").replace("\n", "")
        if name:
            cookies.append({"name": name, "value": value, "url": f"{BASE_URL}/"})
    return cookies


def page_is_login(page) -> bool:
    url = (page.url or "").lower()
    if any(token in url for token in ("login", "signin", "sign-in")):
        return True
    try:
        body = (page.locator("body").inner_text(timeout=2500) or "").lower()
    except Exception:
        return False
    markers = ("sign in", "log in", "se connecter", "connexion")
    return any(marker in body for marker in markers) and "/dashboard" not in page.url


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


def extract_remaining_minutes(page) -> Optional[int]:
    try:
        body = page.locator("body").inner_text(timeout=3500)
    except Exception:
        return None
    match = re.search(
        r"(?:Time remaining|Temps restant|剩余时间)\s*:?\s*([^\n\r]+)",
        body,
        re.IGNORECASE,
    )
    if not match:
        return None
    segment = match.group(1)
    days = re.search(r"(\d+)\s*d\b", segment, re.IGNORECASE)
    hours = re.search(r"(\d+)\s*h\b", segment, re.IGNORECASE)
    minutes = re.search(r"(\d+)\s*(?:min|m)\b", segment, re.IGNORECASE)
    if not any((days, hours, minutes)):
        return None
    return (
        (int(days.group(1)) if days else 0) * 1440
        + (int(hours.group(1)) if hours else 0) * 60
        + (int(minutes.group(1)) if minutes else 0)
    )


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


def discover_project_url(page) -> Optional[str]:
    page.goto(PROJECTS_URL, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(1800)
    if page_is_login(page) or page_is_blocked(page):
        return None
    for link in page.locator("a").all():
        try:
            href = link.get_attribute("href") or ""
        except Exception:
            continue
        if href.startswith("/dashboard/projects/"):
            return f"{BASE_URL}{href}"
        if "/server/" in href:
            return href if href.startswith("http") else f"{BASE_URL}{href}"
    return None


def open_project(page, cached_project_url: Optional[str]) -> Optional[str]:
    if cached_project_url:
        try:
            page.goto(cached_project_url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(1500)
            if (
                not page_is_login(page)
                and not page_is_blocked(page)
                and extract_remaining_minutes(page) is not None
            ):
                return cached_project_url
        except Exception:
            pass
    project_url = discover_project_url(page)
    if not project_url:
        return None
    page.goto(project_url, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(1800)
    return project_url


def try_renew(page, previous_remaining: Optional[int]):
    button = first_visible_text(page, RENEW_TEXTS, timeout_ms=2200)
    if not button:
        return False, False, previous_remaining, "Renew button is not available."
    try:
        if not button.is_enabled():
            return False, False, previous_remaining, "Renew button is visible but disabled."
    except Exception:
        pass

    button.click(timeout=5000)
    page.wait_for_timeout(900)

    confirm = first_visible_text(page, CONFIRM_TEXTS, timeout_ms=2000)
    if confirm:
        try:
            if confirm.is_enabled():
                confirm.click(timeout=5000)
                page.wait_for_timeout(1400)
        except Exception:
            pass

    page.reload(wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(1700)
    new_remaining = extract_remaining_minutes(page)

    verified = False
    if previous_remaining is not None and new_remaining is not None:
        verified = new_remaining >= previous_remaining + 12 * 60

    if verified:
        return True, True, new_remaining, "Renewal completed and remaining time increased."
    return True, False, new_remaining, "Renew was clicked, but the new expiry could not be verified."


def maybe_start(page) -> bool:
    offline = first_visible_text(page, OFFLINE_TEXTS, timeout_ms=1200)
    if not offline:
        return False
    start = first_visible_text(page, START_TEXTS, timeout_ms=1500)
    if not start:
        return False
    try:
        if not start.is_enabled():
            return False
        start.click(timeout=5000)
        page.wait_for_timeout(1200)
        return True
    except Exception:
        return False


def run_check(
    cookie_header: str,
    cached_project_url: Optional[str],
    action: str,
    target_remaining_hours: int,
    auto_start: bool,
) -> CheckResult:
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
            project_url = open_project(page, cached_project_url)

            if page_is_blocked(page):
                return CheckResult(
                    False,
                    "blocked",
                    "ACLClouds displayed an anti-bot or human-verification page. Automatic checks are cooling down.",
                )
            if page_is_login(page):
                return CheckResult(
                    False,
                    "cookie_expired",
                    "The ACLClouds session appears expired. Update the Cookie in Settings.",
                )
            if not project_url:
                return CheckResult(False, "project_not_found", "No ACLClouds service could be found under My services.")

            remaining = extract_remaining_minutes(page)
            if remaining is None:
                return CheckResult(
                    False,
                    "parse_error",
                    "Remaining time could not be read. ACLClouds may have changed the page layout.",
                    project_url=project_url,
                )

            renewed = False
            verified = False
            message = "Status read successfully."

            should_renew = action == "renew" or (
                action == "auto" and remaining <= max(1, target_remaining_hours) * 60
            )

            if should_renew:
                renewed, verified, new_remaining, message = try_renew(page, remaining)
                if new_remaining is not None:
                    remaining = new_remaining

            started = maybe_start(page) if auto_start else False
            return CheckResult(
                True,
                "ok",
                message,
                remaining_minutes=remaining,
                project_url=project_url,
                renewed=renewed,
                renewal_verified=verified,
                started=started,
            )
        finally:
            context.close()
            browser.close()
