#!/usr/bin/env python3
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

DASHBOARD_URL = "https://aclclouds.com/dashboard"
PROJECTS_URL = "https://aclclouds.com/dashboard/projects"
SCREENSHOT_DIR = Path("screenshots")
SCREENSHOT_DIR.mkdir(exist_ok=True)

RENEW_TEXTS = ["Renew", "Renouveler", "续期"]
RENEW_NOW_TEXTS = ["Renew now", "Renouveler maintenant", "立即续期"]
CONFIRM_TEXTS = ["Confirm", "Confirmer", "确认"]
REACTIVATE_TEXTS = ["Reactivate", "Réactiver", "重新激活"]
START_TEXTS = ["Start", "Démarrer", "开机"]


def log(message: str) -> None:
    print(message, flush=True)


def safe_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", value)[:80]


def save_screenshot(page, name: str) -> None:
    try:
        path = SCREENSHOT_DIR / f"{safe_name(name)}.png"
        page.screenshot(path=str(path), full_page=True)
        log(f"  📸 Saved diagnostic screenshot: {path}")
    except Exception as exc:
        log(f"  ⚠️ Screenshot failed: {exc}")


def parse_cookie_secret(raw: str):
    """
    Accept either:
      1. A Cookie request-header value:
         key1=value1; key2=value2
      2. A JSON array exported from a browser/Playwright cookie store.
    """
    raw = raw.strip()
    if not raw:
        return []

    if raw.startswith("["):
        data = json.loads(raw)
        cookies = []
        for item in data:
            if not isinstance(item, dict) or "name" not in item or "value" not in item:
                continue

            cookie = {
                "name": str(item["name"]),
                "value": str(item["value"]),
                "domain": item.get("domain") or "aclclouds.com",
                "path": item.get("path") or "/",
            }

            if "httpOnly" in item:
                cookie["httpOnly"] = bool(item["httpOnly"])
            if "secure" in item:
                cookie["secure"] = bool(item["secure"])
            if "sameSite" in item and item["sameSite"] in ("Strict", "Lax", "None"):
                cookie["sameSite"] = item["sameSite"]

            cookies.append(cookie)
        return cookies

    cookies = []
    for part in raw.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, value = part.split("=", 1)
        cookie_name = name.strip()
        cookie_value = value.strip().replace("\r", "").replace("\n", "")
        if not cookie_name:
            continue
        cookies.append(
            {
                "name": cookie_name,
                "value": cookie_value,
                "url": "https://aclclouds.com/",
            }
        )
    return cookies


def first_visible_text(page, texts, timeout_ms=2500):
    per_item = max(250, timeout_ms // max(1, len(texts)))
    for text in texts:
        try:
            locator = page.get_by_text(text, exact=True).first
            if locator.is_visible(timeout=per_item):
                return locator
        except Exception:
            pass
    return None


def page_is_login(page) -> bool:
    url = (page.url or "").lower()
    if any(marker in url for marker in ("login", "signin", "sign-in")):
        return True

    try:
        title = (page.title() or "").lower()
        return "login" in title or "sign in" in title
    except Exception:
        return False


def page_is_blocked(page) -> bool:
    try:
        title = (page.title() or "").lower()
        body = (page.locator("body").inner_text(timeout=2000) or "").lower()
    except Exception:
        return False

    markers = (
        "just a moment",
        "attention required",
        "access denied",
        "verify you are human",
        "checking your browser",
        "cloudflare",
    )
    return any(marker in title or marker in body for marker in markers)


def extract_remaining_minutes(page) -> Optional[int]:
    try:
        body = page.locator("body").inner_text(timeout=4000)
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


def format_minutes(total: int) -> str:
    days = total // 1440
    hours = (total % 1440) // 60
    minutes = total % 60
    return f"{days}d {hours}h {minutes}m"


def maybe_click_confirm(page) -> bool:
    confirm = first_visible_text(page, CONFIRM_TEXTS, timeout_ms=3500)
    if not confirm:
        return False

    try:
        confirm.click()
        page.wait_for_timeout(1800)
        return True
    except Exception:
        return False


def try_renew(page, account_label: str, server_index: int) -> bool:
    button = first_visible_text(page, RENEW_NOW_TEXTS, timeout_ms=1800)
    if not button:
        button = first_visible_text(page, RENEW_TEXTS, timeout_ms=1800)
    if not button:
        return False

    try:
        if hasattr(button, "is_enabled") and not button.is_enabled():
            return False
    except Exception:
        pass

    try:
        log("  🔄 Renewal button available; clicking...")
        button.click()
        page.wait_for_timeout(1200)

        if maybe_click_confirm(page):
            log("  ✅ Confirmation clicked.")
        else:
            log("  ℹ️ No confirmation dialog appeared; renewal may have completed directly.")

        page.wait_for_timeout(2500)
        return True
    except Exception as exc:
        log(f"  ❌ Renewal click failed: {exc}")
        save_screenshot(page, f"{account_label}_server{server_index}_renew_error")
        raise


def maybe_reactivate(page) -> bool:
    reactivate = first_visible_text(page, REACTIVATE_TEXTS, timeout_ms=1800)
    if not reactivate:
        return False

    try:
        reactivate.click()
        page.wait_for_timeout(1200)
        maybe_click_confirm(page)
        page.wait_for_timeout(1500)
        log("♻️ Reactivate detected and clicked.")
        return True
    except Exception as exc:
        log(f"⚠️ Reactivate failed: {exc}")
        return False


def maybe_start_if_offline(page) -> bool:
    try:
        body = (page.locator("body").inner_text(timeout=3000) or "").lower()
    except Exception:
        return False

    offline_markers = ("offline", "离线", "hors ligne")
    if not any(marker in body for marker in offline_markers):
        return False

    start = first_visible_text(page, START_TEXTS, timeout_ms=3000)
    if not start:
        return False

    try:
        start.click()
        page.wait_for_timeout(1800)
        log("  ▶️ Server appears offline; Start was clicked.")
        return True
    except Exception as exc:
        log(f"  ⚠️ Start failed: {exc}")
        return False


def log_page_links(page, limit=80):
    """Log non-sensitive link metadata to diagnose dashboard route changes."""
    try:
        links = page.locator("a").all()
        log(f"  🔎 Page URL: {page.url}")
        log(f"  🔗 Found {len(links)} anchor element(s).")
        for i, link in enumerate(links[:limit], start=1):
            try:
                href = link.get_attribute("href") or ""
                text_value = " ".join((link.inner_text(timeout=500) or "").split())
                aria = link.get_attribute("aria-label") or ""
                title = link.get_attribute("title") or ""
                meta = " | ".join(x for x in [text_value, aria, title] if x)
                log(f"  LINK {i}: href={href!r} meta={meta!r}")
            except Exception:
                continue
    except Exception as exc:
        log(f"  ⚠️ Could not enumerate page links: {exc}")


def collect_server_hrefs(page):
    """Collect project detail links from the current ACLClouds projects page."""
    page.wait_for_timeout(1200)
    hrefs = []
    try:
        links = page.locator("a").all()
    except Exception:
        return hrefs

    for link in links:
        try:
            href = link.get_attribute("href")
        except Exception:
            href = None

        if not href:
            continue

        # Current dashboard uses /dashboard/projects for the list.
        # Keep only child/detail routes, not filters such as ?type=discord.
        if href.startswith("/dashboard/projects/") and href not in hrefs:
            hrefs.append(href)

        # Legacy/fallback pattern used by older panel versions.
        elif "/server/" in href and href not in hrefs:
            hrefs.append(href)

    return hrefs


def run_account(browser, account_no: int, cookie_secret: str) -> bool:
    label = f"account{account_no}"
    log(f"\n===== Account {account_no} =====")

    try:
        cookies = parse_cookie_secret(cookie_secret)
    except Exception as exc:
        log(f"❌ Account {account_no}: cookie parsing failed: {exc}")
        return False

    if not cookies:
        log(f"❌ Account {account_no}: cookie secret is empty or invalid.")
        return False

    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1440, "height": 1000},
        locale="en-US",
    )
    log(f"🍪 Parsed {len(cookies)} cookie(s).")
    try:
        context.add_cookies(cookies)
    except Exception as exc:
        log(f"❌ Account {account_no}: browser rejected the Cookie data: {exc}")
        context.close()
        return False

    page = context.new_page()

    try:
        log("🌐 Opening ACLClouds dashboard...")
        page.goto(DASHBOARD_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3500)

        if page_is_login(page):
            log(f"❌ Account {account_no}: cookie expired; redirected to login page.")
            save_screenshot(page, f"{label}_cookie_expired")
            return False

        if page_is_blocked(page):
            log(f"❌ Account {account_no}: anti-bot/Cloudflare challenge detected.")
            save_screenshot(page, f"{label}_blocked")
            return False

        if maybe_reactivate(page):
            page.goto(DASHBOARD_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2500)

        log("📁 Opening My services...")
        page.goto(PROJECTS_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)

        hrefs = collect_server_hrefs(page)
        if not hrefs:
            log(f"❌ Account {account_no}: no server links found.")
            log_page_links(page)
            save_screenshot(page, f"{label}_no_servers")
            return False

        log(f"🖥️ Found {len(hrefs)} server(s).")
        account_ok = True

        for idx, href in enumerate(hrefs, start=1):
            url = href if href.startswith("http") else f"https://aclclouds.com{href}"
            log(f"\n  --- Server {idx}/{len(hrefs)} ---")

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(3000)

                if page_is_login(page):
                    log("  ❌ Session expired while processing this server.")
                    save_screenshot(page, f"{label}_server{idx}_login")
                    account_ok = False
                    continue

                if page_is_blocked(page):
                    log("  ❌ Anti-bot/Cloudflare challenge detected.")
                    save_screenshot(page, f"{label}_server{idx}_blocked")
                    account_ok = False
                    continue

                remaining = extract_remaining_minutes(page)
                if remaining is not None:
                    log(f"  ⏳ Approx. time remaining: {format_minutes(remaining)}")
                else:
                    log("  ℹ️ Could not parse remaining time; checking renewal controls anyway.")

                renewed = try_renew(page, label, idx)
                if renewed:
                    page.reload(wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(2500)

                    new_remaining = extract_remaining_minutes(page)
                    if new_remaining is not None:
                        log(f"  ✅ Remaining time after renewal: {format_minutes(new_remaining)}")
                    else:
                        log("  ✅ Renewal action completed.")
                else:
                    log("  ✅ No active renewal button; likely outside the renewal window.")

                maybe_start_if_offline(page)

            except Exception as exc:
                account_ok = False
                log(f"  ❌ Server processing error: {exc}")
                save_screenshot(page, f"{label}_server{idx}_error")

        return account_ok

    finally:
        context.close()


def main() -> int:
    accounts = [
        os.getenv("ACL_COOKIES_1", "").strip(),
        os.getenv("ACL_COOKIES_2", "").strip(),
    ]

    configured = [(i + 1, value) for i, value in enumerate(accounts) if value]
    if not configured:
        log("❌ ACL_COOKIES_1 and ACL_COOKIES_2 are not configured.")
        return 2

    log(f"Configured ACLClouds accounts: {len(configured)}")

    proxy_url = os.getenv("PROXY_URL", "").strip()
    launch_kwargs = {"headless": True}

    if proxy_url:
        launch_kwargs["proxy"] = {"server": proxy_url}
        log("🌐 PROXY_URL is enabled.")

    overall_ok = True

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(**launch_kwargs)
        try:
            for account_no, cookie_secret in configured:
                result = run_account(browser, account_no, cookie_secret)
                overall_ok = overall_ok and result
        finally:
            browser.close()

    if overall_ok:
        log("\n🎉 All configured accounts completed without fatal errors.")
        return 0

    log("\n⚠️ At least one account failed. Check the logs and screenshot artifact.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
