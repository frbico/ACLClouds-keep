import os
import re
import threading
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

from automation import parse_cookie_header, run_check
from crypto_utils import decrypt_text, encrypt_text
from storage import (
    add_event,
    count_accounts,
    create_account,
    delete_account,
    get_account,
    get_bool,
    get_value,
    init_db,
    list_accounts,
    list_events,
    set_bool,
    set_value,
    update_account,
)

APP_SECRET = os.environ.get("APP_SECRET", "").strip()
ENV_WEB_USERNAME = os.environ.get("WEB_USERNAME", "admin").strip() or "admin"
ENV_WEB_PASSWORD = os.environ.get("WEB_PASSWORD", "").strip()
INSTANCE_NAME = "ACLClouds-Keep"

TARGET_REMAINING_HOURS = int(os.environ.get("TARGET_REMAINING_HOURS", "24"))
RETRY_HOURS = int(os.environ.get("RETRY_HOURS", "6"))
BLOCKED_RETRY_HOURS = int(os.environ.get("BLOCKED_RETRY_HOURS", "24"))
SCHEDULER_TICK_MINUTES = int(os.environ.get("SCHEDULER_TICK_MINUTES", "10"))

VERSION_FILE = Path(__file__).with_name("VERSION")
LATEST_VERSION_URL = "https://raw.githubusercontent.com/frbico/ACLClouds-keep/main/VERSION"

if len(APP_SECRET) < 24:
    raise RuntimeError("APP_SECRET is required and should be at least 24 characters.")

app = Flask(__name__)
app.secret_key = APP_SECRET
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("WEB_SECURE_COOKIE", "false").lower()
    in {"1", "true", "yes", "on"},
    PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
)

CSRFProtect(app)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

RUN_LOCK = threading.Lock()
scheduler = BackgroundScheduler(timezone="UTC")

init_db()

if get_value("auto_enabled", "") == "":
    set_bool("auto_enabled", True)
if get_value("auto_start", "") == "":
    set_bool("auto_start", False)
if get_value("target_remaining_hours", "") == "":
    set_value("target_remaining_hours", TARGET_REMAINING_HOURS)
if get_value("retry_hours", "") == "":
    set_value("retry_hours", RETRY_HOURS)

if get_value("admin_username", "") == "":
    set_value("admin_username", ENV_WEB_USERNAME)

if get_value("admin_password_hash", "") == "":
    if len(ENV_WEB_PASSWORD) < 8:
        raise RuntimeError(
            "WEB_PASSWORD must be at least 8 characters for the first startup."
        )
    set_value("admin_password_hash", generate_password_hash(ENV_WEB_PASSWORD))


def now_utc():
    return datetime.now(timezone.utc)


def parse_iso(value: str):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


def fmt_dt(value: str):
    dt = parse_iso(value)
    if not dt:
        return "—"
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def fmt_remaining(minutes_raw):
    try:
        total = int(minutes_raw)
    except Exception:
        return "—"
    days, remainder = divmod(max(0, total), 1440)
    hours, minutes = divmod(remainder, 60)
    return f"{days}d {hours}h {minutes}m"


app.jinja_env.filters["fmt_dt"] = fmt_dt
app.jinja_env.filters["fmt_remaining"] = fmt_remaining


def read_current_version() -> str:
    try:
        version = VERSION_FILE.read_text(encoding="utf-8").strip()
        return version or "dev"
    except Exception:
        return "dev"


def version_tuple(version: str):
    match = re.match(r"^s*v?(d+).(d+).(d+)", version or "")
    if not match:
        return (0, 0, 0)
    return tuple(int(part) for part in match.groups())


def fetch_latest_version() -> str:
    req = urllib.request.Request(
        LATEST_VERSION_URL,
        headers={"User-Agent": "ACLClouds-Keep-update-check"},
    )
    with urllib.request.urlopen(req, timeout=6) as response:
        latest = response.read(64).decode("utf-8", "replace").strip()

    if not re.match(r"^d+.d+.d+(?:[-+][0-9A-Za-z.-]+)?$", latest):
        raise ValueError("GitHub returned an invalid VERSION value.")
    return latest


def get_admin_username() -> str:
    return get_value("admin_username", ENV_WEB_USERNAME).strip() or "admin"


def verify_admin_password(password: str) -> bool:
    stored_hash = get_value("admin_password_hash", "")
    if not stored_hash:
        return False
    try:
        return check_password_hash(stored_hash, password)
    except Exception:
        return False


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("authenticated"):
            return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)

    return wrapper


def migrate_legacy_cookie():
    if count_accounts() != 0:
        return

    legacy_cookie = get_value("cookie_enc", "")
    if not legacy_cookie:
        return

    create_account(
        "账号 1",
        legacy_cookie,
        enabled=True,
        project_url=get_value("project_url", ""),
        remaining_minutes=get_value("remaining_minutes", ""),
        last_check_at=get_value("last_check_at", ""),
        last_renew_at=get_value("last_renew_at", ""),
        next_check_at=get_value("next_check_at", ""),
        last_status=get_value("last_status", "never"),
        last_message=get_value("last_message", ""),
    )
    add_event("info", "Legacy single-account Cookie was migrated to account 1.")


migrate_legacy_cookie()


def decrypt_account_cookie(account) -> str:
    encrypted = (account or {}).get("cookie_enc", "")
    if not encrypted:
        return ""
    try:
        return decrypt_text(encrypted, APP_SECRET)
    except Exception as exc:
        name = (account or {}).get("name", "unknown")
        add_event("error", f"[{name}] Stored Cookie could not be decrypted: {exc}")
        return ""


def set_account_next_check(account_id: int, dt):
    update_account(
        account_id,
        next_check_at=dt.astimezone(timezone.utc).isoformat(),
    )


def schedule_from_remaining(remaining_minutes: int, target_hours: int):
    target_minutes = max(1, target_hours) * 60
    delay_minutes = max(5, remaining_minutes - target_minutes)
    return now_utc() + timedelta(minutes=delay_minutes)


def account_event(account, level: str, message: str):
    add_event(level, f"[{account['name']}] {message}")


def perform(account_id: int, action: str, source: str = "manual"):
    account = get_account(account_id)
    if not account:
        return False, "Account does not exist."

    if not RUN_LOCK.acquire(blocking=False):
        return False, "Another account check is already running."

    try:
        cookie = decrypt_account_cookie(account)
        if not cookie:
            update_account(
                account_id,
                last_status="cookie_invalid",
                last_message="Cookie is not configured or could not be decrypted.",
            )
            return False, "Cookie is not configured or could not be decrypted."

        target_hours = int(
            get_value("target_remaining_hours", str(TARGET_REMAINING_HOURS))
        )
        retry_hours = int(get_value("retry_hours", str(RETRY_HOURS)))
        auto_start = get_bool("auto_start", False)

        update_account(
            account_id,
            last_check_at=now_utc().isoformat(),
            last_status="running",
            last_message=f"{source}: check is running.",
        )
        account_event(account, "info", f"{source}: starting ACLClouds {action} check.")

        result = run_check(
            cookie_header=cookie,
            cached_project_url=account.get("project_url") or None,
            action=action,
            target_remaining_hours=target_hours,
            auto_start=auto_start,
        )

        fields = {
            "last_status": result.status,
            "last_message": result.message,
        }
        if result.project_url:
            fields["project_url"] = result.project_url
        if result.remaining_minutes is not None:
            fields["remaining_minutes"] = str(result.remaining_minutes)
        update_account(account_id, **fields)

        if not result.ok:
            cooldown = (
                BLOCKED_RETRY_HOURS
                if result.status in {"cookie_expired", "cookie_invalid", "blocked"}
                else retry_hours
            )
            set_account_next_check(account_id, now_utc() + timedelta(hours=cooldown))
            account_event(account, "error", f"{result.status}: {result.message}")
            return False, result.message

        if result.renewed and result.renewal_verified:
            update_account(
                account_id,
                last_renew_at=now_utc().isoformat(),
                last_status="renewed",
            )
            account_event(account, "success", "Renewal verified successfully.")
        elif result.renewed:
            update_account(account_id, last_status="renew_clicked_unverified")
            account_event(account, "warning", result.message)
        else:
            account_event(account, "info", result.message)

        if result.started:
            account_event(account, "success", "Server Start was clicked.")

        remaining = result.remaining_minutes
        if result.renewed and not result.renewal_verified:
            next_dt = now_utc() + timedelta(hours=retry_hours)
        elif (
            remaining is not None
            and remaining <= target_hours * 60
            and not result.renewed
        ):
            next_dt = now_utc() + timedelta(hours=retry_hours)
        elif remaining is not None:
            next_dt = schedule_from_remaining(remaining, target_hours)
        else:
            next_dt = now_utc() + timedelta(hours=retry_hours)

        set_account_next_check(account_id, next_dt)
        return True, result.message

    except Exception as exc:
        retry_hours = int(get_value("retry_hours", str(RETRY_HOURS)))
        update_account(
            account_id,
            last_status="internal_error",
            last_message=str(exc),
        )
        set_account_next_check(account_id, now_utc() + timedelta(hours=retry_hours))
        account_event(account, "error", f"Internal error: {exc}")
        return False, str(exc)
    finally:
        RUN_LOCK.release()


def scheduler_tick():
    if not get_bool("auto_enabled", True):
        return

    for account in list_accounts(include_disabled=False):
        if not account.get("cookie_enc"):
            continue

        next_dt = parse_iso(account.get("next_check_at", ""))
        if not next_dt:
            set_account_next_check(account["id"], now_utc() + timedelta(minutes=5))
            continue

        if now_utc() >= next_dt:
            perform(account["id"], "auto", source="scheduler")


scheduler.add_job(
    scheduler_tick,
    "interval",
    minutes=max(1, SCHEDULER_TICK_MINUTES),
    id="aclclouds_tick",
    max_instances=1,
    coalesce=True,
)
scheduler.start()


def _summary_state(accounts):
    enabled = [a for a in accounts if a.get("enabled")]

    remaining_values = []
    next_checks = []
    last_checks = []
    last_renews = []
    for account in enabled:
        try:
            remaining_values.append(int(account.get("remaining_minutes", "")))
        except Exception:
            pass
        for source, target in (
            (account.get("next_check_at", ""), next_checks),
            (account.get("last_check_at", ""), last_checks),
            (account.get("last_renew_at", ""), last_renews),
        ):
            parsed = parse_iso(source)
            if parsed:
                target.append(parsed)

    return {
        "auto_enabled": get_bool("auto_enabled", True),
        "auto_start": get_bool("auto_start", False),
        "account_count": len(accounts),
        "enabled_count": len(enabled),
        "nearest_remaining": min(remaining_values) if remaining_values else "",
        "next_check_at": min(next_checks).isoformat() if next_checks else "",
        "last_check_at": max(last_checks).isoformat() if last_checks else "",
        "last_renew_at": max(last_renews).isoformat() if last_renews else "",
        "target_remaining_hours": get_value(
            "target_remaining_hours", str(TARGET_REMAINING_HOURS)
        ),
        "retry_hours": get_value("retry_hours", str(RETRY_HOURS)),
    }


@app.route("/health")
def health():
    return {
        "ok": True,
        "instance": INSTANCE_NAME,
        "version": read_current_version(),
        "accounts": count_accounts(),
    }


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("authenticated"):
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if username == get_admin_username() and verify_admin_password(password):
            session.clear()
            session["authenticated"] = True
            session["admin_username"] = username
            session.permanent = True
            return redirect(url_for("index"))

        flash("管理员账号或密码不正确。", "error")

    return render_template("login.html", instance_name=INSTANCE_NAME)


@app.post("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    accounts = list_accounts()
    return render_template(
        "index.html",
        instance_name=INSTANCE_NAME,
        state=_summary_state(accounts),
        accounts=accounts,
        events=list_events(18),
    )


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    current_username = get_admin_username()

    if request.method == "POST":
        try:
            target = min(
                40,
                max(
                    8,
                    int(request.form.get("target_remaining_hours", "24")),
                ),
            )
            retry = min(
                12,
                max(
                    2,
                    int(request.form.get("retry_hours", "6")),
                ),
            )
        except ValueError:
            flash("时间参数必须是数字。", "error")
            return redirect(url_for("settings"))

        requested_username = request.form.get("admin_username", "").strip()
        current_password = request.form.get("current_admin_password", "")
        new_password = request.form.get("new_admin_password", "")
        confirm_password = request.form.get("confirm_admin_password", "")

        if not requested_username:
            flash("管理员账号不能为空。", "error")
            return redirect(url_for("settings"))

        if len(requested_username) > 64:
            flash("管理员账号不能超过 64 个字符。", "error")
            return redirect(url_for("settings"))

        credentials_changed = (
            requested_username != current_username
            or bool(new_password)
            or bool(confirm_password)
        )

        if credentials_changed:
            if not current_password or not verify_admin_password(current_password):
                flash("修改管理员账号或密码前，请输入当前管理员密码。", "error")
                return redirect(url_for("settings"))

            if new_password or confirm_password:
                if len(new_password) < 8:
                    flash("新管理员密码至少需要 8 个字符。", "error")
                    return redirect(url_for("settings"))
                if new_password != confirm_password:
                    flash("两次输入的新密码不一致。", "error")
                    return redirect(url_for("settings"))

        set_bool("auto_enabled", bool(request.form.get("auto_enabled")))
        set_bool("auto_start", bool(request.form.get("auto_start")))
        set_value("target_remaining_hours", target)
        set_value("retry_hours", retry)

        if credentials_changed:
            set_value("admin_username", requested_username)
            if new_password:
                set_value(
                    "admin_password_hash",
                    generate_password_hash(new_password),
                )
            session["admin_username"] = requested_username
            add_event("info", "Administrator credentials were updated.")

        flash("全局设置已保存。", "success")
        return redirect(url_for("settings"))

    return render_template(
        "settings.html",
        instance_name=INSTANCE_NAME,
        auto_enabled=get_bool("auto_enabled", True),
        auto_start=get_bool("auto_start", False),
        target_remaining_hours=get_value(
            "target_remaining_hours", str(TARGET_REMAINING_HOURS)
        ),
        retry_hours=get_value("retry_hours", str(RETRY_HOURS)),
        admin_username=current_username,
        accounts=list_accounts(),
        current_version=read_current_version(),
        latest_version=get_value("latest_version", ""),
        update_available=get_bool("update_available", False),
        last_update_check_at=get_value("last_update_check_at", ""),
    )


def _validated_account_name(raw: str, fallback: str = "ACLClouds 账号") -> str:
    name = (raw or "").strip() or fallback
    return name[:64]


@app.post("/accounts/add")
@login_required
def account_add():
    name = _validated_account_name(
        request.form.get("account_name", ""),
        fallback=f"账号 {count_accounts() + 1}",
    )
    cookie = request.form.get("cookie", "").strip()
    if not cookie:
        flash("新增账号时必须填写 Cookie。", "error")
        return redirect(url_for("settings"))
    if not parse_cookie_header(cookie):
        flash("Cookie 格式无法解析，请粘贴完整请求头 Cookie。", "error")
        return redirect(url_for("settings"))

    account_id = create_account(
        name,
        encrypt_text(cookie, APP_SECRET),
        enabled=True,
        next_check_at=(now_utc() + timedelta(minutes=5)).isoformat(),
        last_status="cookie_added",
        last_message="Cookie added. Waiting for the first check.",
    )
    add_event("info", f"[{name}] Account #{account_id} was added.")
    flash(f"已添加 {name}，首次自动检查将在约 5 分钟后进行。", "success")
    return redirect(url_for("settings"))


@app.post("/accounts/<int:account_id>/update")
@login_required
def account_update(account_id: int):
    account = get_account(account_id)
    if not account:
        flash("账号不存在。", "error")
        return redirect(url_for("settings"))

    name = _validated_account_name(request.form.get("account_name", ""), account["name"])
    fields = {
        "name": name,
        "enabled": bool(request.form.get("enabled")),
    }

    cookie = request.form.get("cookie", "").strip()
    if cookie:
        if not parse_cookie_header(cookie):
            flash(f"{name} 的 Cookie 格式无法解析。", "error")
            return redirect(url_for("settings"))
        fields.update(
            cookie_enc=encrypt_text(cookie, APP_SECRET),
            project_url="",
            next_check_at=(now_utc() + timedelta(minutes=5)).isoformat(),
            last_status="cookie_updated",
            last_message="Cookie updated. Waiting for verification.",
        )

    update_account(account_id, **fields)
    add_event("info", f"[{name}] Account settings were updated.")
    flash(f"{name} 已保存。", "success")
    return redirect(url_for("settings"))


@app.post("/accounts/<int:account_id>/delete")
@login_required
def account_delete(account_id: int):
    account = get_account(account_id)
    if not account:
        flash("账号不存在。", "error")
        return redirect(url_for("settings"))
    name = account["name"]
    delete_account(account_id)
    add_event("warning", f"[{name}] Account and encrypted Cookie were deleted.")
    flash(f"已删除 {name}。", "success")
    return redirect(url_for("settings"))


@app.post("/action/check/<int:account_id>")
@login_required
def action_check(account_id: int):
    ok, message = perform(account_id, "check", source="manual-check")
    flash(message, "success" if ok else "error")
    return redirect(url_for("index"))


@app.post("/action/auto/<int:account_id>")
@login_required
def action_auto(account_id: int):
    ok, message = perform(account_id, "auto", source="manual-auto")
    flash(message, "success" if ok else "error")
    return redirect(url_for("index"))


@app.post("/action/renew/<int:account_id>")
@login_required
def action_renew(account_id: int):
    ok, message = perform(account_id, "renew", source="manual-renew")
    flash(message, "success" if ok else "error")
    return redirect(url_for("index"))


@app.post("/action/auto-all")
@login_required
def action_auto_all():
    accounts = list_accounts(include_disabled=False)
    if not accounts:
        flash("没有启用中的 ACLClouds 账号。", "error")
        return redirect(url_for("index"))

    success = 0
    failed = 0
    for account in accounts:
        ok, _ = perform(account["id"], "auto", source="manual-all")
        if ok:
            success += 1
        else:
            failed += 1
    flash(
        f"批量检查完成：成功 {success} 个，失败 {failed} 个。",
        "success" if failed == 0 else "error",
    )
    return redirect(url_for("index"))


@app.post("/action/check-update")
@login_required
def action_check_update():
    current = read_current_version()

    try:
        latest = fetch_latest_version()
        available = version_tuple(latest) > version_tuple(current)

        set_value("latest_version", latest)
        set_bool("update_available", available)
        set_value("last_update_check_at", now_utc().isoformat())

        if available:
            flash(
                f"发现新版本：v{latest}。当前版本为 v{current}。",
                "success",
            )
        else:
            flash(f"已是最新版：v{current}。", "success")

        add_event(
            "info",
            f"Update check completed: current={current}, latest={latest}.",
        )
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        flash(f"检查更新失败：{exc}", "error")
        add_event("warning", f"Update check failed: {exc}")

    return redirect(url_for("settings"))


@app.route("/logs")
@login_required
def logs():
    return render_template(
        "logs.html",
        instance_name=INSTANCE_NAME,
        events=list_events(200),
    )
