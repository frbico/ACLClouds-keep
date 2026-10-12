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

from automation import parse_cookie_header, run_check, validate_server_url
from crypto_utils import decrypt_text, encrypt_text
from probe import HeartbeatMonitor, fetch_probe_nodes
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
INSTANCE_NAME = "ACLClouds Online Keeper"

PROBE_API_URL = os.environ.get("PROBE_API_URL", "https://tz.ssxi.de/api/servers").strip()
PROBE_POLL_SECONDS = max(15, int(os.environ.get("PROBE_POLL_SECONDS", "30")))
PROBE_STALE_SECONDS = max(60, int(os.environ.get("PROBE_STALE_SECONDS", "180")))
PROBE_CONFIRMATIONS = max(1, int(os.environ.get("PROBE_CONFIRMATIONS", "2")))
PROBE_API_FALLBACK_SECONDS = max(
    60, int(os.environ.get("PROBE_API_FALLBACK_SECONDS", "60"))
)
PROBE_TRIGGER_COOLDOWN_MINUTES = max(
    1, int(os.environ.get("PROBE_TRIGGER_COOLDOWN_MINUTES", "10"))
)
EXPIRY_GRACE_MINUTES = max(1, int(os.environ.get("EXPIRY_GRACE_MINUTES", "70")))
RETRY_MINUTES = int(os.environ.get("RETRY_MINUTES", "5"))
BLOCKED_RETRY_HOURS = int(os.environ.get("BLOCKED_RETRY_HOURS", "24"))
SCHEDULER_TICK_MINUTES = int(os.environ.get("SCHEDULER_TICK_MINUTES", "1"))

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
heartbeat_monitor = HeartbeatMonitor(PROBE_API_URL)
PROBE_FALLBACK_NODES = {}
PROBE_FALLBACK_FETCHED_AT = None
PROBE_FALLBACK_ERROR = ""

init_db()
if get_value("auto_enabled", "") == "":
    set_bool("auto_enabled", True)

if get_value("admin_username", "") == "":
    set_value("admin_username", ENV_WEB_USERNAME)
if get_value("admin_password_hash", "") == "":
    if len(ENV_WEB_PASSWORD) < 8:
        raise RuntimeError("WEB_PASSWORD must be at least 8 characters for the first startup.")
    set_value("admin_password_hash", generate_password_hash(ENV_WEB_PASSWORD))


def now_utc():
    return datetime.now(timezone.utc)


def parse_iso(value: str):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def fmt_dt(value: str):
    dt = parse_iso(value)
    if not dt:
        return "—"
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


app.jinja_env.filters["fmt_dt"] = fmt_dt


def read_current_version() -> str:
    try:
        return VERSION_FILE.read_text(encoding="utf-8").strip() or "dev"
    except Exception:
        return "dev"


def version_tuple(version: str):
    match = re.match(r"^\s*v?(\d+)\.(\d+)\.(\d+)", version or "")
    return tuple(int(part) for part in match.groups()) if match else (0, 0, 0)


def fetch_latest_version() -> str:
    req = urllib.request.Request(
        LATEST_VERSION_URL, headers={"User-Agent": "ACLClouds-Online-Keeper"}
    )
    with urllib.request.urlopen(req, timeout=6) as response:
        latest = response.read(64).decode("utf-8", "replace").strip()
    if not re.match(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$", latest):
        raise ValueError("GitHub returned an invalid VERSION value.")
    return latest


def get_admin_username() -> str:
    return get_value("admin_username", ENV_WEB_USERNAME).strip() or "admin"


def verify_admin_password(password: str) -> bool:
    try:
        return check_password_hash(get_value("admin_password_hash", ""), password)
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
    encrypted = get_value("cookie_enc", "")
    if not encrypted:
        return
    create_account(
        "账号 1",
        encrypted,
        project_url=get_value("project_url", ""),
        next_check_at=(now_utc() + timedelta(minutes=1)).isoformat(),
        last_status="migrated",
        last_message="Legacy account migrated to Online Keeper.",
    )
    add_event("info", "Legacy single-account data was migrated.")


migrate_legacy_cookie()


def migrate_online_keeper_state():
    if get_value("online_keeper_v2_migrated", ""):
        return
    first_check = (now_utc() + timedelta(minutes=1)).isoformat()
    for account in list_accounts():
        cached_url = account.get("project_url") or ""
        if not validate_server_url(cached_url):
            cached_url = ""
        update_account(
            account["id"],
            project_url=cached_url,
            remaining_minutes="",
            last_renew_at="",
            next_check_at=first_check,
            last_status="migration_pending",
            last_message="Migrated to Online Keeper. Waiting for Online verification.",
        )
    set_value("online_keeper_v2_migrated", "1")


migrate_online_keeper_state()


def migrate_probe_keeper_state():
    if get_value("probe_keeper_v3_migrated", ""):
        return
    for account in list_accounts():
        update_account(
            account["id"],
            next_check_at="",
            next_check_reason="",
            probe_status="unconfigured" if not account.get("probe_node_id") else "waiting",
            probe_miss_count=0,
            probe_last_trigger_at="",
            last_message="Probe heartbeat mode enabled. Bind a probe node in Settings.",
        )
    set_value("probe_keeper_v3_migrated", "1")
    add_event("info", "Probe heartbeat mode enabled; fixed control-panel polling was disabled.")


migrate_probe_keeper_state()
if get_bool("auto_enabled", True):
    heartbeat_monitor.update_ids(
        account.get("probe_node_id") for account in list_accounts(include_disabled=False)
    )
heartbeat_monitor.start()


def decrypt_account_cookie(account) -> str:
    encrypted = (account or {}).get("cookie_enc", "")
    if not encrypted:
        return ""
    try:
        return decrypt_text(encrypted, APP_SECRET)
    except Exception as exc:
        add_event("error", f"[{account.get('name', 'unknown')}] Cookie decryption failed: {exc}")
        return ""


def set_next_check(account_id: int, when, reason: str):
    update_account(
        account_id,
        next_check_at=when.astimezone(timezone.utc).isoformat(),
        next_check_reason=reason,
    )


def clear_next_check(account_id: int):
    update_account(account_id, next_check_at="", next_check_reason="")


def probe_node_options():
    try:
        nodes = fetch_probe_nodes(PROBE_API_URL)
        return sorted(nodes.values(), key=lambda node: (node.name.lower(), node.id)), ""
    except Exception as exc:
        return [], str(exc)


def checked_probe_node(raw: str, account_id: int | None = None):
    node_id = (raw or "").strip()
    if not node_id:
        return "", ""
    if not re.fullmatch(r"[0-9a-fA-F-]{16,64}", node_id):
        raise ValueError("探针节点 ID 格式无效。")
    for account in list_accounts():
        if account["id"] != account_id and account.get("probe_node_id") == node_id:
            raise ValueError(f"该探针已绑定到账号 {account['name']}，不能重复绑定。")
        if account["id"] == account_id and account.get("probe_node_id") == node_id:
            return node_id, account.get("probe_node_name") or node_id
    nodes = fetch_probe_nodes(PROBE_API_URL)
    node = nodes.get(node_id)
    if not node:
        raise ValueError("探针 API 中找不到所选节点，请刷新设置页后重试。")
    return node.id, node.name


def account_event(account, level: str, message: str):
    add_event(level, f"[{account['name']}] {message}")


def perform(account_id: int, source: str = "manual"):
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

        started_at = now_utc()
        update_account(
            account_id,
            last_check_at=started_at.isoformat(),
            last_status="running",
            last_message=f"{source}: checking Online status.",
        )
        account_event(account, "info", f"{source}: checking Bot Online status.")

        result = run_check(cookie, account.get("project_url") or None)
        fields = {"last_status": result.status, "last_message": result.message}
        if result.server_url:
            fields["project_url"] = result.server_url
        if result.remaining_minutes is not None:
            fields["remaining_minutes"] = str(result.remaining_minutes)
        if result.start_clicked:
            fields["last_renew_at"] = now_utc().isoformat()
        update_account(account_id, **fields)

        if result.online_verified:
            level = "success" if result.start_clicked else "info"
            account_event(account, level, result.message)
            if result.remaining_minutes is not None:
                set_next_check(
                    account_id,
                    now_utc() + timedelta(
                        minutes=result.remaining_minutes + EXPIRY_GRACE_MINUTES
                    ),
                    "expiry-fallback",
                )
            else:
                clear_next_check(account_id)
            return True, result.message

        if result.status == "starting":
            account_event(account, "warning", result.message)
            set_next_check(account_id, now_utc() + timedelta(minutes=2), "starting-retry")
            return True, result.message

        cooldown = (
            timedelta(hours=BLOCKED_RETRY_HOURS)
            if result.status in {"cookie_expired", "cookie_invalid", "blocked"}
            else timedelta(minutes=max(1, RETRY_MINUTES))
        )
        set_next_check(account_id, now_utc() + cooldown, "error-retry")
        account_event(account, "error", f"{result.status}: {result.message}")
        return False, result.message
    except Exception as exc:
        update_account(account_id, last_status="internal_error", last_message=str(exc))
        set_next_check(
            account_id,
            now_utc() + timedelta(minutes=max(1, RETRY_MINUTES)),
            "error-retry",
        )
        account_event(account, "error", f"Internal error: {exc}")
        return False, str(exc)
    finally:
        RUN_LOCK.release()

def probe_tick():
    global PROBE_FALLBACK_NODES, PROBE_FALLBACK_FETCHED_AT, PROBE_FALLBACK_ERROR

    if not get_bool("auto_enabled", True):
        heartbeat_monitor.update_ids([])
        set_value("probe_api_status", "paused")
        return
    accounts = list_accounts(include_disabled=False)
    node_ids = [account.get("probe_node_id") for account in accounts if account.get("probe_node_id")]
    heartbeat_monitor.update_ids(node_ids)
    if not node_ids:
        for account in accounts:
            update_account(account["id"], probe_status="unconfigured", probe_miss_count=0)
        set_value("probe_api_status", "idle")
        return
    snapshot = heartbeat_monitor.snapshot()
    current = now_utc()
    last_message = snapshot.get("last_message_at")
    websocket_healthy = bool(
        last_message and current - last_message <= timedelta(seconds=PROBE_STALE_SECONDS)
    )

    fallback_nodes = {}
    if not websocket_healthy:
        should_fetch = (
            PROBE_FALLBACK_FETCHED_AT is None
            or current - PROBE_FALLBACK_FETCHED_AT
            >= timedelta(seconds=PROBE_API_FALLBACK_SECONDS)
        )
        if should_fetch:
            try:
                PROBE_FALLBACK_NODES = fetch_probe_nodes(PROBE_API_URL)
                PROBE_FALLBACK_FETCHED_AT = current
                PROBE_FALLBACK_ERROR = ""
            except Exception as exc:
                PROBE_FALLBACK_NODES = {}
                PROBE_FALLBACK_FETCHED_AT = current
                PROBE_FALLBACK_ERROR = str(exc)
        fallback_nodes = PROBE_FALLBACK_NODES

    monitoring_available = websocket_healthy or bool(fallback_nodes)
    if websocket_healthy:
        set_value("probe_api_status", "websocket")
        set_value("probe_api_last_error", "")
        set_value("probe_api_last_checked_at", last_message.isoformat())
    elif fallback_nodes:
        set_value("probe_api_status", "api_fallback")
        set_value("probe_api_last_error", snapshot.get("last_error") or "")
        set_value("probe_api_last_checked_at", PROBE_FALLBACK_FETCHED_AT.isoformat())
    else:
        previous_status = get_value("probe_api_status", "")
        set_value("probe_api_status", "error")
        error = PROBE_FALLBACK_ERROR or snapshot.get("last_error") or "No heartbeat received."
        set_value("probe_api_last_error", error)
        if previous_status != "error":
            add_event("error", f"Probe heartbeat unavailable; no Bot action will be taken: {error}")

    for account in accounts:
        node_id = account.get("probe_node_id") or ""
        if not node_id:
            update_account(account["id"], probe_status="unconfigured", probe_miss_count=0)
            continue
        if not monitoring_available:
            update_account(account["id"], probe_status="monitor_error", probe_miss_count=0)
            continue

        node_name = account.get("probe_node_name") or node_id
        if websocket_healthy:
            last_seen = snapshot["heartbeats"].get(node_id)
            subscribed_since = snapshot["subscribed_since"].get(node_id, current)
            age_seconds = (
                (current - last_seen).total_seconds()
                if last_seen
                else (current - subscribed_since).total_seconds()
            )
            report_at = last_seen
            report_interval = 60
        else:
            node = fallback_nodes.get(node_id)
            if node:
                elapsed = max(0, (current - PROBE_FALLBACK_FETCHED_AT).total_seconds())
                age_seconds = node.report_age_seconds + elapsed
                report_at = datetime.fromtimestamp(node.report_at_ms / 1000, tz=timezone.utc)
                report_interval = node.report_interval_seconds
                node_name = node.name
            else:
                age_seconds = PROBE_STALE_SECONDS + 1
                report_at = None
                report_interval = 60

        threshold = max(PROBE_STALE_SECONDS, report_interval * 3)
        if age_seconds <= threshold:
            if account.get("probe_status") in {
                "suspect",
                "offline",
                "api_error",
                "monitor_error",
            }:
                account_event(account, "success", f"Probe heartbeat recovered: {node_name}.")
            update_account(
                account["id"],
                probe_node_name=node_name,
                probe_last_report_at=report_at.isoformat() if report_at else "",
                probe_status="online",
                probe_miss_count=0,
            )
            continue

        misses = int(account.get("probe_miss_count") or 0) + 1
        status = "offline" if misses >= PROBE_CONFIRMATIONS else "suspect"
        update_account(
            account["id"],
            probe_node_name=node_name,
            probe_last_report_at=report_at.isoformat() if report_at else "",
            probe_status=status,
            probe_miss_count=misses,
        )
        if misses < PROBE_CONFIRMATIONS:
            continue

        last_trigger = parse_iso(account.get("probe_last_trigger_at", ""))
        if last_trigger and current - last_trigger < timedelta(
            minutes=PROBE_TRIGGER_COOLDOWN_MINUTES
        ):
            continue
        update_account(account["id"], probe_last_trigger_at=current.isoformat())
        account_event(
            account,
            "warning",
            f"Probe heartbeat stale for {node_name}; opening its bound Bot control panel.",
        )
        perform(account["id"], source="probe-offline")

def scheduler_tick():
    if not get_bool("auto_enabled", True):
        return
    current = now_utc()
    for account in list_accounts(include_disabled=False):
        if not account.get("cookie_enc"):
            continue
        next_at = parse_iso(account.get("next_check_at", ""))
        if next_at and current >= next_at:
            reason = account.get("next_check_reason") or "scheduled"
            clear_next_check(account["id"])
            perform(account["id"], source=reason)


scheduler.add_job(
    probe_tick,
    "interval",
    seconds=PROBE_POLL_SECONDS,
    id="aclclouds_probe_tick",
    max_instances=1,
    coalesce=True,
)
scheduler.add_job(
    scheduler_tick,
    "interval",
    minutes=max(1, SCHEDULER_TICK_MINUTES),
    id="aclclouds_fallback_tick",
    max_instances=1,
    coalesce=True,
)
scheduler.start()

def summary_state(accounts):
    enabled = [account for account in accounts if account.get("enabled")]
    online = [account for account in enabled if account.get("last_status") in {"online", "started"}]
    bound = [account for account in enabled if account.get("probe_node_id")]
    probe_online = [account for account in bound if account.get("probe_status") == "online"]
    next_checks = [parse_iso(a.get("next_check_at", "")) for a in enabled]
    last_starts = [parse_iso(a.get("last_renew_at", "")) for a in enabled]
    return {
        "auto_enabled": get_bool("auto_enabled", True),
        "account_count": len(accounts),
        "enabled_count": len(enabled),
        "online_count": len(online),
        "bound_count": len(bound),
        "probe_online_count": len(probe_online),
        "next_check_at": min((v for v in next_checks if v), default=None),
        "last_start_at": max((v for v in last_starts if v), default=None),
        "probe_api_status": get_value("probe_api_status", "waiting"),
        "probe_last_checked_at": get_value("probe_api_last_checked_at", ""),
        "probe_poll_seconds": PROBE_POLL_SECONDS,
        "probe_stale_seconds": PROBE_STALE_SECONDS,
    }

@app.route("/health")
def health():
    return {
        "ok": True,
        "instance": INSTANCE_NAME,
        "version": read_current_version(),
        "accounts": count_accounts(),
        "mode": "probe-heartbeat-keeper",
        "probe_api_status": get_value("probe_api_status", "waiting"),
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
        "keeper_index.html",
        instance_name=INSTANCE_NAME,
        state=summary_state(accounts),
        accounts=accounts,
        events=list_events(18),
    )


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    current_username = get_admin_username()
    if request.method == "POST":
        requested_username = request.form.get("admin_username", "").strip()
        current_password = request.form.get("current_admin_password", "")
        new_password = request.form.get("new_admin_password", "")
        confirm_password = request.form.get("confirm_admin_password", "")
        if not requested_username or len(requested_username) > 64:
            flash("管理员账号不能为空且不能超过 64 个字符。", "error")
            return redirect(url_for("settings"))

        credentials_changed = (
            requested_username != current_username or bool(new_password) or bool(confirm_password)
        )
        if credentials_changed:
            if not current_password or not verify_admin_password(current_password):
                flash("修改管理员凭据前请输入当前密码。", "error")
                return redirect(url_for("settings"))
            if new_password or confirm_password:
                if len(new_password) < 8 or new_password != confirm_password:
                    flash("新密码至少 8 位，且两次输入必须一致。", "error")
                    return redirect(url_for("settings"))

        set_bool("auto_enabled", bool(request.form.get("auto_enabled")))
        if credentials_changed:
            set_value("admin_username", requested_username)
            if new_password:
                set_value("admin_password_hash", generate_password_hash(new_password))
            session["admin_username"] = requested_username
        flash("设置已保存。", "success")
        return redirect(url_for("settings"))

    nodes, probe_error = probe_node_options()
    return render_template(
        "keeper_settings.html",
        instance_name=INSTANCE_NAME,
        auto_enabled=get_bool("auto_enabled", True),
        admin_username=current_username,
        accounts=list_accounts(),
        probe_nodes=nodes,
        probe_error=probe_error,
        probe_api_url=PROBE_API_URL,
        probe_poll_seconds=PROBE_POLL_SECONDS,
        probe_stale_seconds=PROBE_STALE_SECONDS,
        probe_confirmations=PROBE_CONFIRMATIONS,
        current_version=read_current_version(),
        latest_version=get_value("latest_version", ""),
        update_available=get_bool("update_available", False),
    )

def account_name(raw: str, fallback: str) -> str:
    return ((raw or "").strip() or fallback)[:64]


def checked_server_url(raw: str):
    raw = (raw or "").strip()
    if not raw:
        return ""
    parsed = validate_server_url(raw)
    if not parsed:
        raise ValueError("Bot 控制面板 URL 必须是 https://aclclouds.com/server/编号")
    return parsed


@app.post("/accounts/add")
@login_required
def account_add():
    name = account_name(request.form.get("account_name", ""), f"账号 {count_accounts() + 1}")
    cookie = request.form.get("cookie", "").strip()
    if not parse_cookie_header(cookie):
        flash("必须填写可解析的完整 Cookie。", "error")
        return redirect(url_for("settings"))
    try:
        server_url = checked_server_url(request.form.get("server_url", ""))
        node_id, node_name = checked_probe_node(request.form.get("probe_node_id", ""))
    except Exception as exc:
        flash(f"保存失败：{exc}", "error")
        return redirect(url_for("settings"))

    create_account(
        name,
        encrypt_text(cookie, APP_SECRET),
        project_url=server_url,
        probe_node_id=node_id,
        probe_node_name=node_name,
        probe_status="waiting" if node_id else "unconfigured",
        next_check_at=(now_utc() + timedelta(minutes=1)).isoformat(),
        next_check_reason="initial-verification",
        last_status="cookie_added",
        last_message="Account added. Waiting for initial Online verification.",
    )
    add_event("info", f"[{name}] Account added to Online Keeper; probe: {node_name or 'unbound'}.")
    flash(f"已添加 {name}，约 1 分钟内首次确认控制面板状态。", "success")
    return redirect(url_for("settings"))

@app.post("/accounts/<int:account_id>/update")
@login_required
def account_update(account_id: int):
    account = get_account(account_id)
    if not account:
        flash("账号不存在。", "error")
        return redirect(url_for("settings"))
    try:
        server_url = checked_server_url(request.form.get("server_url", ""))
        node_id, node_name = checked_probe_node(
            request.form.get("probe_node_id", ""), account_id=account_id
        )
    except Exception as exc:
        flash(f"保存失败：{exc}", "error")
        return redirect(url_for("settings"))

    name = account_name(request.form.get("account_name", ""), account["name"])
    probe_changed = node_id != (account.get("probe_node_id") or "")
    fields = {
        "name": name,
        "enabled": bool(request.form.get("enabled")),
        "project_url": server_url,
        "probe_node_id": node_id,
        "probe_node_name": node_name,
    }
    if probe_changed:
        fields.update(
            probe_status="waiting" if node_id else "unconfigured",
            probe_miss_count=0,
            probe_last_report_at="",
            probe_last_trigger_at="",
        )
    cookie = request.form.get("cookie", "").strip()
    if cookie:
        if not parse_cookie_header(cookie):
            flash(f"{name} 的 Cookie 格式无法解析。", "error")
            return redirect(url_for("settings"))
        fields["cookie_enc"] = encrypt_text(cookie, APP_SECRET)
    if cookie or server_url != (account.get("project_url") or ""):
        fields.update(
            next_check_at=(now_utc() + timedelta(minutes=1)).isoformat(),
            next_check_reason="account-update-verification",
            last_status="account_updated",
            last_message="Cookie or Bot URL updated. Waiting for verification.",
        )
    update_account(account_id, **fields)
    add_event("info", f"[{name}] Account settings updated; probe: {node_name or 'unbound'}.")
    flash(f"{name} 已保存。", "success")
    return redirect(url_for("settings"))

@app.post("/accounts/<int:account_id>/delete")
@login_required
def account_delete(account_id: int):
    account = get_account(account_id)
    if account and delete_account(account_id):
        add_event("warning", f"[{account['name']}] Account deleted.")
        flash(f"已删除 {account['name']}。", "success")
    else:
        flash("账号不存在。", "error")
    return redirect(url_for("settings"))


@app.post("/action/check/<int:account_id>")
@login_required
def action_check(account_id: int):
    ok, message = perform(account_id, source="manual")
    flash(message, "success" if ok else "error")
    return redirect(url_for("index"))


@app.post("/action/check-all")
@login_required
def action_check_all():
    accounts = list_accounts(include_disabled=False)
    success = 0
    failed = 0
    for account in accounts:
        ok, _ = perform(account["id"], source="manual-all")
        success += int(ok)
        failed += int(not ok)
    flash(
        f"检查完成：成功 {success} 个，失败 {failed} 个。",
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
        flash(
            f"发现新版本 v{latest}。" if available else f"已是最新版 v{current}。",
            "success",
        )
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        flash(f"检查更新失败：{exc}", "error")
    return redirect(url_for("settings"))


@app.route("/logs")
@login_required
def logs():
    return render_template(
        "logs.html", instance_name=INSTANCE_NAME, events=list_events(200)
    )
