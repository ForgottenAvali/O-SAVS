import json, logging, os, secrets, time

from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from aiohttp import web
from discord.ext import commands

from cogs import admin_core
from cogs import admin_app_db as db
from cogs import admin_update

TOKEN_TTL_DAYS = 7

UPDATE_TICKET_TTL = 120
ALLOW_LEGACY_UPDATE_DOWNLOAD = True

load_dotenv()
API_HOST = os.getenv("ADMIN_API_HOST")
API_PORT = os.getenv("ADMIN_API_PORT")

MAX_CREDENTIAL_LENGTH = 256
MAX_BODY_BYTES = 64 * 1024
MAX_REASON_LENGTH = 1000
MAX_TARGET_LENGTH = 200

LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 15 * 60

_sessions: dict[str, dict] = {}
_login_attempts: dict[str, dict] = {}
_update_tickets: dict[str, dict] = {}


def _bad_request(message: str) -> web.HTTPBadRequest:
    return web.HTTPBadRequest(
        text=json.dumps({"success": False, "error": message}), content_type="application/json"
    )

async def _read_json(request: web.Request) -> dict:
    try:
        body = await request.json()
    except ValueError:
        raise _bad_request("Request body must be valid JSON.")
    if not isinstance(body, dict):
        raise _bad_request("Request body must be a JSON object.")
    return body

def _to_id(value, message: str) -> int:
    if isinstance(value, (bool, float)):
        raise _bad_request(message)
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise _bad_request(message)
    if not 0 < number < 2**64:
        raise _bad_request(message)
    return number

def _text_field(body: dict, key: str, label: str, *, required: bool = True, allow_blank: bool = False, max_length: int = MAX_REASON_LENGTH) -> str | None:
    value = body.get(key)
    if value is None:
        if required:
            raise _bad_request(f"{label} is required.")
        return None
    if isinstance(value, (dict, list, bool)):
        raise _bad_request(f"{label} must be text.")
    text = str(value).strip()
    if len(text) > max_length:
        raise _bad_request(f"{label} must be {max_length} characters or fewer.")
    if not text and not allow_blank:
        if required:
            raise _bad_request(f"{label} is required.")
        return None
    return text

def _clean_for_log(text: str, limit: int = 64) -> str:
    text = " ".join(text.split())
    return "".join(ch for ch in text if ch.isprintable())[:limit]

def _client_key(request: web.Request) -> str:
    return request.remote or "unknown"

def _is_locked_out(key: str) -> bool:
    record = _login_attempts.get(key)
    if not record:
        return False
    return record["locked_until"] > time.monotonic()

def _record_failed_login(key: str):
    now = time.monotonic()
    if len(_login_attempts) > 2000:
        for stale in [k for k, r in _login_attempts.items()
                      if r["locked_until"] < now and now - r.get("last", 0) > LOGIN_LOCKOUT_SECONDS]:
            del _login_attempts[stale]
    record = _login_attempts.setdefault(key, {"count": 0, "locked_until": 0, "last": now})
    if now - record.get("last", now) > LOGIN_LOCKOUT_SECONDS:
        record["count"] = 0
    record["last"] = now
    record["count"] += 1
    if record["count"] >= LOGIN_MAX_ATTEMPTS:
        record["locked_until"] = time.monotonic() + LOGIN_LOCKOUT_SECONDS
        record["count"] = 0

def _clear_failed_logins(key: str):
    _login_attempts.pop(key, None)

def _prune_sessions():
    now = datetime.now(timezone.utc)
    for token in [t for t, s in _sessions.items() if s["expires"] < now]:
        del _sessions[token]

def _new_token(username, discord_id, epoch):
    _prune_sessions()
    token = secrets.token_urlsafe(32)
    _sessions[token] = {
        "username": username,
        "discord_id": discord_id,
        "epoch": epoch,
        "expires": datetime.now(timezone.utc) + timedelta(days=TOKEN_TTL_DAYS),
    }
    return token

def _issue_update_ticket(username: str, release: dict) -> str:
    now = time.monotonic()
    for old in [t for t, r in _update_tickets.items() if r["expires"] <= now or r["username"] == username]:
        del _update_tickets[old]
    ticket = secrets.token_urlsafe(32)
    _update_tickets[ticket] = {
        "username": username,
        "expires": now + UPDATE_TICKET_TTL,
        "asset_id": release["asset_id"],
        "asset_size": release["asset_size"],
    }
    return ticket

def _redeem_update_ticket(request) -> dict | None:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    record = _update_tickets.pop(auth[len("Bearer "):], None)
    if not record or record["expires"] <= time.monotonic():
        return None
    return record

async def _check_auth(request) -> dict | None:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[len("Bearer "):]
    session = _sessions.get(token)
    if not session:
        return None
    if session["expires"] < datetime.now(timezone.utc):
        _sessions.pop(token, None)
        return None
    if session["discord_id"] and not admin_core.is_user_allowed(session["discord_id"]):
        _sessions.pop(token, None)
        return None
    state = await db.get_session_state(session["username"])
    if state is None or state[1] or state[0] != session["epoch"]:
        _sessions.pop(token, None)
        return None
    return session

@web.middleware
async def error_middleware(request, handler):
    try:
        return await handler(request)
    except web.HTTPException:
        raise
    except Exception as e:
        logging.error(f"[AdminAPI] Unhandled error: {e}", exc_info=e)
        return web.json_response({"success": False, "error": "Internal server error."}, status=500)

class AdminAPI(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.runner: web.AppRunner | None = None

    async def cog_load(self):
        await db.init_db()

        app = web.Application(middlewares=[error_middleware], client_max_size=MAX_BODY_BYTES)
        app.add_routes(
            [
                web.post("/login", self.login),
                web.post("/logout", self.logout),
                web.post("/api/link", self.link),
                web.post("/api/unlink", self.unlink),
                web.post("/api/ban", self.ban),
                web.post("/api/unban", self.unban),
                web.get("/api/ban_check", self.ban_check),
                web.get("/api/logs", self.logs),
                web.get("/api/servers", self.servers),
                web.post("/api/server_invite", self.server_invite),
                web.post("/api/server_leave", self.server_leave),
                web.post("/api/server_ban", self.server_ban),
                web.post("/api/server_unban", self.server_unban),
                web.get("/api/users", self.users),
                web.get("/api/banned", self.banned),
                web.get("/api/banned_servers", self.banned_servers),
                web.get("/api/update/latest", self.update_latest),
                web.post("/api/update/ticket", self.update_ticket),
                web.get("/api/update/download", self.update_download),
                web.get("/api/maintenance", self.maintenance_status),
                web.post("/api/maintenance", self.maintenance_set),
            ]
        )
        self.runner = web.AppRunner(app, access_log=None)
        await self.runner.setup()
        site = web.TCPSite(self.runner, API_HOST, API_PORT)
        await site.start()
        logging.info("[AdminAPI] Listening.")

    @commands.Cog.listener()
    async def on_ready(self):
        await admin_core.enforce_server_bans(self.bot)

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        if await admin_core.is_server_banned(guild.id):
            logging.info(f"[AdminAPI] Joined banned server {guild.name} ({guild.id}), leaving.")
            await guild.leave()

    async def cog_unload(self):
        if self.runner:
            await self.runner.cleanup()

    async def _require_auth(self, request) -> dict:
        session = await _check_auth(request)
        if not session:
            self._unauthorized()
        return session

    def _unauthorized(self):
        raise web.HTTPUnauthorized(
            text='{"success": false, "error": "Not authenticated."}',
            content_type="application/json",
        )

    async def _auth_code_gate(self, request, session, auth_code, action, target, reason=None):
        keys = (f"authcode:user:{session['username']}", f"authcode:ip:{_client_key(request)}")
        if any(_is_locked_out(k) for k in keys):
            await db.log_action(session["username"], action, target, reason, "Denied: authorization code locked out")
            return web.json_response(
                {"success": False, "error": "Too many failed attempts. Try again in a few minutes."}, status=429
            )

        if not await db.has_auth_code(session["username"]):
            return web.json_response(
                {"success": False, "error": "Your account has no valid authorization code. Ask the owner to generate one."},
                status=403,
            )

        if not await db.verify_auth_code(session["username"], auth_code):
            for k in keys:
                _record_failed_login(k)
            await db.log_action(session["username"], action, target, reason, "Denied: bad authorization code")
            return web.json_response({"success": False, "error": "Invalid authorization code."}, status=403)

        for k in keys:
            _clear_failed_logins(k)
        return None

    async def login(self, request: web.Request):
        body = await _read_json(request)
        username = str(body.get("username", ""))
        password = str(body.get("password", ""))

        keys = (f"login:ip:{_client_key(request)}", f"login:user:{username.lower()[:64]}")
        if any(_is_locked_out(k) for k in keys):
            return web.json_response(
                {"success": False, "error": "Too many failed attempts. Try again in a few minutes."}, status=429
            )

        if len(username) > MAX_CREDENTIAL_LENGTH or len(password) > MAX_CREDENTIAL_LENGTH:
            for k in keys:
                _record_failed_login(k)
            return web.json_response({"success": False, "error": "Invalid credentials."}, status=401)

        account = await db.verify_login(username, password)
        if not account:
            for k in keys:
                _record_failed_login(k)
            await db.log_action(_clean_for_log(username) or "?", "login_failed", None, None, "Invalid credentials")
            return web.json_response({"success": False, "error": "Invalid credentials."}, status=401)

        if account["disabled"]:
            for k in keys:
                _record_failed_login(k)
            await db.log_action(account["username"], "login_failed", None, None, "Account disabled")
            return web.json_response({"success": False, "error": "Invalid credentials."}, status=401)

        if account["discord_id"] and not admin_core.is_user_allowed(account["discord_id"]):
            for k in keys:
                _record_failed_login(k)
            await db.log_action(account["username"], "login_failed", None, None, "Account not on admin allow-list")
            return web.json_response({"success": False, "error": "This account is not authorized."}, status=403)

        for k in keys:
            _clear_failed_logins(k)
        token = _new_token(account["username"], account["discord_id"], account["session_epoch"])
        return web.json_response({"success": True, "token": token, "username": account["username"]})

    async def logout(self, request: web.Request):
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            _sessions.pop(auth[len("Bearer "):], None)
        return web.json_response({"success": True})

    async def servers(self, request: web.Request):
        await self._require_auth(request)
        servers_list = await admin_core.get_bot_servers(self.bot)
        return web.json_response({"success": True, "servers": servers_list})

    async def users(self, request: web.Request):
        await self._require_auth(request)
        try:
            limit = int(request.query.get("limit", 100))
            offset = int(request.query.get("offset", 0))
            after_raw = request.query.get("after")
            after = max(0, int(after_raw)) if after_raw is not None else None
        except ValueError:
            return web.json_response({"success": False, "error": "limit, offset and after must be integers."}, status=400)
        limit = max(1, min(limit, 500))
        offset = max(0, offset)
        page = await admin_core.get_all_linked_users(limit, offset, after)

        body = {"success": True, "users": page["users"], "total": page["total"], "limit": page["limit"]}
        if after is not None:
            body["after"] = page["after"]
            body["next_after"] = page["next_after"]
        else:
            body["offset"] = page["offset"]
        return web.json_response(body)

    async def banned(self, request: web.Request):
        await self._require_auth(request)
        banned_list = await admin_core.get_all_banned()
        return web.json_response({"success": True, "banned": banned_list})

    async def banned_servers(self, request: web.Request):
        await self._require_auth(request)
        banned_list = await admin_core.get_all_banned_servers()
        return web.json_response({"success": True, "banned_servers": banned_list})

    async def server_invite(self, request: web.Request):
        session = await self._require_auth(request)
        body = await _read_json(request)
        guild_id_raw = body.get("guild_id") or body.get("server_id")
        if not guild_id_raw:
            return web.json_response({"success": False, "error": "Missing server/guild ID."}, status=400)
        guild_id = _to_id(guild_id_raw, "Invalid server ID format.")

        result = await admin_core.generate_and_send_invite(
            self.bot,
            guild_id=guild_id,
            admin_discord_id=session.get("discord_id")
        )
        await db.log_action(session["username"], "invite_request", str(guild_id), None, str(result))
        return web.json_response(result)

    async def server_leave(self, request: web.Request):
        session = await self._require_auth(request)
        body = await _read_json(request)
        guild_id = _to_id(body.get("guild_id"), "Invalid server ID format.")
        reason = _text_field(body, "reason", "A reason")
        auth_code = str(body.get("auth_code", ""))

        denied = await self._auth_code_gate(request, session, auth_code, "leave_server", str(guild_id), reason)
        if denied:
            return denied

        result = await admin_core.perform_leave_server(self.bot, guild_id)
        await db.log_action(session["username"], "leave_server", str(guild_id), reason, str(result))
        return web.json_response(result)

    async def server_ban(self, request: web.Request):
        session = await self._require_auth(request)
        body = await _read_json(request)
        server_id = _to_id(body.get("server_id"), "Invalid server ID format.")
        reason = _text_field(body, "reason", "A reason")

        denied = await self._auth_code_gate(
            request, session, str(body.get("auth_code", "")), "ban_server", str(server_id), reason
        )
        if denied:
            return denied

        result = await admin_core.perform_ban_server(
            self.bot, session["discord_id"], server_id, reason, operator_name=session["username"]
        )
        await db.log_action(session["username"], "ban_server", str(server_id), reason, str(result))
        return web.json_response(result)

    async def server_unban(self, request: web.Request):
        session = await self._require_auth(request)
        body = await _read_json(request)
        server_id = _to_id(body.get("server_id"), "Invalid server ID format.")
        reason = _text_field(body, "reason", "A reason")

        denied = await self._auth_code_gate(
            request, session, str(body.get("auth_code", "")), "unban_server", str(server_id), reason
        )
        if denied:
            return denied

        result = await admin_core.perform_unban_server(
            server_id, self.bot, session["discord_id"], session["username"], reason
        )
        await db.log_action(session["username"], "unban_server", str(server_id), reason, str(result))
        return web.json_response(result)

    async def maintenance_status(self, request: web.Request):
        await self._require_auth(request)
        return web.json_response({"success": True, "maintenance": await admin_core.get_maintenance_mode()})

    async def maintenance_set(self, request: web.Request):
        session = await self._require_auth(request)
        body = await _read_json(request)
        enabled = body.get("enabled")
        if not isinstance(enabled, bool):
            raise _bad_request("Invalid request.")

        auth_code = str(body.get("auth_code", ""))
        action = "maintenance_on" if enabled else "maintenance_off"

        denied = await self._auth_code_gate(request, session, auth_code, action, "bot")
        if denied:
            return denied

        result = await admin_core.perform_set_maintenance(self.bot, enabled)
        await db.log_action(session["username"], action, "bot", None, str(result))
        return web.json_response(result)

    async def link(self, request: web.Request):
        session = await self._require_auth(request)
        body = await _read_json(request)
        target_user_id = _to_id(body.get("target_user_id"), "Invalid user ID.")
        vrchat_id = _text_field(body, "vrchat_id", "A VRChat ID", max_length=MAX_TARGET_LENGTH)
        reason = _text_field(body, "reason", "A reason", required=False)

        result = await admin_core.perform_link(
            self.bot, session["discord_id"], session["username"], target_user_id, vrchat_id, reason
        )
        await db.log_action(session["username"], "link", str(target_user_id), reason, str(result))
        return web.json_response(result)

    async def unlink(self, request: web.Request):
        session = await self._require_auth(request)
        body = await _read_json(request)
        target_user_id = _to_id(body.get("target_user_id"), "Invalid user ID.")
        reason = _text_field(body, "reason", "A reason", required=False)

        result = await admin_core.perform_unlink(
            self.bot, session["discord_id"], session["username"], target_user_id, reason
        )
        await db.log_action(session["username"], "unlink", str(target_user_id), reason, str(result))
        return web.json_response(result)

    async def ban(self, request: web.Request):
        session = await self._require_auth(request)
        body = await _read_json(request)
        target_input = _text_field(body, "target_input", "A target", max_length=MAX_TARGET_LENGTH)
        reason = _text_field(body, "reason", "A reason", allow_blank=True)

        result = await admin_core.perform_ban(
            self.bot, session["discord_id"], session["username"], target_input, reason
        )
        await db.log_action(session["username"], "ban", target_input, reason, str(result))
        return web.json_response(result)

    async def unban(self, request: web.Request):
        session = await self._require_auth(request)
        body = await _read_json(request)
        target_input = _text_field(body, "target_input", "A target", max_length=MAX_TARGET_LENGTH)
        reason = _text_field(body, "reason", "A reason", allow_blank=True)

        result = await admin_core.perform_unban(self.bot, session["discord_id"], session["username"], target_input, reason)
        await db.log_action(session["username"], "unban", target_input, reason, str(result))
        return web.json_response(result)

    async def ban_check(self, request: web.Request):
        await self._require_auth(request)
        target_input = request.query.get("target", "")[:MAX_TARGET_LENGTH]
        result = await admin_core.perform_get_ban(self.bot, target_input)
        return web.json_response(result)

    async def logs(self, request: web.Request):
        await self._require_auth(request)
        query = request.query.get("q", "")[:MAX_TARGET_LENGTH]
        rows = await db.search_logs(query)
        return web.json_response({"success": True, "logs": rows})

    async def update_latest(self, request: web.Request):
        await self._require_auth(request)
        result = await admin_update.get_latest_release()
        return web.json_response(result)

    async def update_ticket(self, request: web.Request):
        session = await self._require_auth(request)
        release = await admin_update.get_latest_release()
        if not release.get("success"):
            return web.json_response(release, status=502)

        ticket = _issue_update_ticket(session["username"], release)
        await db.log_action(session["username"], "update_ticket", release["asset_name"], None, "Issued")
        return web.json_response({
            "success": True,
            "ticket": ticket,
            "tag_name": release["tag_name"],
            "asset_size": release["asset_size"],
            "asset_sha256": release["asset_sha256"],
        })

    async def update_download(self, request: web.Request):
        ticket = _redeem_update_ticket(request)
        if ticket:
            asset_id, asset_size = ticket["asset_id"], ticket["asset_size"]
        else:
            if not ALLOW_LEGACY_UPDATE_DOWNLOAD:
                self._unauthorized()
            await self._require_auth(request)
            asset_id_raw = request.query.get("asset_id", "")
            if not asset_id_raw.isdigit():
                return web.json_response({"success": False, "error": "Missing or invalid asset_id."}, status=400)
            release = await admin_update.get_latest_release()
            if not release.get("success") or release["asset_id"] != int(asset_id_raw):
                return web.json_response({"success": False, "error": "Not the latest release asset."}, status=404)
            asset_id, asset_size = release["asset_id"], release["asset_size"]

        response = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "application/octet-stream",
                "Content-Disposition": "attachment; filename=update.exe",
            },
        )
        response.content_length = asset_size
        await response.prepare(request)

        sent = 0

        async def _write(chunk: bytes):
            nonlocal sent
            sent += len(chunk)
            await response.write(chunk)

        try:
            await admin_update.stream_release_asset(asset_id, _write)
            complete = sent == asset_size
        except Exception as e:
            logging.error(f"[AdminAPI] Update download failed: {e}")
            complete = False

        if not complete:
            if request.transport is not None:
                request.transport.close()
            return response

        await response.write_eof()
        return response

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminAPI(bot))
