import re
from dataclasses import dataclass
from typing import Optional

from playwright.sync_api import sync_playwright

BASE_URL = "https://aclclouds.com"
PROJECTS_URL = f"{BASE_URL}/dashboard/projects"

RENEW_TEXTS = [
    "Renew now",
    "Renew",
    "Renouveler maintenant",
    "Renouveler",
    "立即续期",
    "续期",
]
CONFIRM_TEXTS = ["Confirm", "Confirmer", "确认"]
START_TEXTS = ["Start", "Démarrer", "开机"]
OFFLINE_TEXTS = ["OFFLINE", "Offline", "Hors ligne", "离线"]
MANAGE_TEXTS = ["Manage", "Gérer", "管理"]

EXPIRY_MARKERS = (
    r"expires?\s+in",
    r"time\s+remaining",
    r"expire\s+dans",
    r"expiration\s+dans",
    r"temps\s+restant",
    r"剩余时间",
    r"到期剩余",
)


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


def parse_duration_minutes(text: str) -> Optional[int]:
    """Parse ACLClouds-style durations such as ``2d 3h`` or ``2j 3h``."""
    if not text:
        return None

    normalized = text.replace("\xa0", " ").strip().lower()
    total = 0
    found = False

    unit_patterns = (
        (1440, r"(\d+)\s*(?:d|day|days|j|jour|jours)\b"),
        (60, r"(\d+)\s*(?:h|hr|hrs|hour|hours|heure|heures)\b"),
        (1, r"(\d+)\s*(?:m|min|mins|minute|minutes)\b"),
    )
    for multiplier, pattern in unit_patterns:
        match = re.search(pattern, normalized, re.IGNORECASE)
        if match:
            total += int(match.group(1)) * multiplier
            found = True

    zh_days = re.search(r"(\d+)\s*天", normalized)
    zh_hours = re.search(r"(\d+)\s*小时", normalized)
    zh_minutes = re.search(r"(\d+)\s*分钟", normalized)
    for multiplier, match in ((1440, zh_days), (60, zh_hours), (1, zh_minutes)):
        if match:
            total += int(match.group(1)) * multiplier
            found = True

    return total if found else None


def extract_remaining_minutes_from_text(body: str) -> Optional[int]:
    if not body:
        return None

    text = body.replace("\xa0", " ")
    marker_pattern = "|".join(EXPIRY_MARKERS)
    matches = re.finditer(
        rf"(?:{marker_pattern})\s*:?\s*([^\n\r]{{1,90}})",
        text,
        re.IGNORECASE,
    )
    for match in matches:
        parsed = parse_duration_minutes(match.group(1))
        if parsed is not None:
            return parsed
    return None


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
    return extract_remaining_minutes_from_text(body)


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


def expand_first_service(page) -> bool:
    """Expand the first service card on the current My Projects layout.

    ACLClouds currently exposes the expiry only after the small arrow next to the
    service type (for example ``golang generic``) is clicked. Prefer semantic
    ``aria-expanded`` controls, then fall back to the compact button adjacent to
    a ``* generic`` label. No destructive button is ever selected.
    """
    if extract_remaining_minutes(page) is not None:
        return True

    selectors = (
        "main button[aria-expanded='false']",
        "main [role='button'][aria-expanded='false']",
        "button[aria-expanded='false']",
        "[role='button'][aria-expanded='false']",
    )
    for selector in selectors:
        try:
            candidates = page.locator(selector)
            count = min(candidates.count(), 20)
            for i in range(count):
                candidate = candidates.nth(i)
                try:
                    label = (candidate.inner_text(timeout=300) or "").strip().lower()
                except Exception:
                    label = ""
                if label in {"manage", "delete", "gérer", "supprimer", "管理", "删除"}:
                    continue
                try:
                    if candidate.is_visible(timeout=300) and candidate.is_enabled():
                        candidate.click(timeout=1500)
                        page.wait_for_timeout(650)
                        if extract_remaining_minutes(page) is not None:
                            return True
                except Exception:
                    continue
        except Exception:
            continue

    try:
        clicked = page.evaluate(
            r"""
            () => {
              const blocked = new Set(['manage', 'delete', 'gérer', 'supprimer', '管理', '删除']);
              const nodes = [...document.querySelectorAll('main *, body *')];
              const labels = nodes.filter((el) => {
                const text = (el.textContent || '').trim();
                return /\bgeneric\s*$/i.test(text) && text.length < 90;
              });

              for (const label of labels) {
                const containers = [label.parentElement, label.parentElement?.parentElement].filter(Boolean);
                for (const container of containers) {
                  const controls = [...container.querySelectorAll('button,[role="button"]')];
                  const target = controls.find((control) => {
                    const text = (control.textContent || '').trim().toLowerCase();
                    return !blocked.has(text) && !control.disabled;
                  });
                  if (target) {
                    target.click();
                    return true;
                  }
                }
              }
              return false;
            }
            """
        )
        if clicked:
            page.wait_for_timeout(700)
            if extract_remaining_minutes(page) is not None:
                return True
    except Exception:
        pass

    return extract_remaining_minutes(page) is not None


def discover_project_url(page) -> Optional[str]:
    page.goto(PROJECTS_URL, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(1500)
    if page_is_login(page) or page_is_blocked(page):
        return None

    if expand_first_service(page):
        return page.url or PROJECTS_URL

    # Backward compatibility with the older layout that linked to a dedicated
    # project/server page.
    for link in page.locator("a").all():
        try:
            href = link.get_attribute("href") or ""
        except Exception:
            continue
        if href.startswith("/dashboard/projects/"):
            return f"{BASE_URL}{href}"
        if "/server/" in href:
            return href if href.startswith("http") else f"{BASE_URL}{href}"

    # Some layouts expose a Manage button instead of an anchor. Clicking Manage
    # is non-destructive and may navigate to a dedicated details page.
    manage = first_visible_text(page, MANAGE_TEXTS, timeout_ms=1200)
    if manage:
        try:
            manage.click(timeout=3000)
            page.wait_for_timeout(1000)
            if not page_is_login(page) and not page_is_blocked(page):
                if expand_first_service(page) or extract_remaining_minutes(page) is not None:
                    return page.url or PROJECTS_URL
        except Exception:
            pass
    return None


def open_project(page, cached_project_url: Optional[str]) -> Optional[str]:
    if cached_project_url:
        try:
            page.goto(cached_project_url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(1200)
            if not page_is_login(page) and not page_is_blocked(page):
                expand_first_service(page)
                if extract_remaining_minutes(page) is not None:
                    return page.url or cached_project_url
        except Exception:
            pass

    project_url = discover_project_url(page)
    if not project_url:
        return None

    if page.url != project_url:
        page.goto(project_url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(1300)
    expand_first_service(page)
    return page.url or project_url


def try_renew(page, previous_remaining: Optional[int]):
    button = first_visible_text(page, RENEW_TEXTS, timeout_ms=2400)
    if not button:
        return False, False, previous_remaining, "Renew button is not available yet."
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
    page.wait_for_timeout(1500)
    expand_first_service(page)
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
                    "The ACLClouds session appears expired. Update this account's Cookie in Settings.",
                )
            if not project_url:
                return CheckResult(
                    False,
                    "project_not_found",
                    "No readable ACLClouds service could be found under My services.",
                )

            remaining = extract_remaining_minutes(page)
            if remaining is None:
                return CheckResult(
                    False,
                    "parse_error",
                    "Expiry could not be read. The project card may not have expanded or ACLClouds may have changed the page layout.",
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
