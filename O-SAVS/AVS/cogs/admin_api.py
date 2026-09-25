import logging, os, secrets, time

from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from aiohttp import web
from discord.ext import commands

from cogs import admin_core
from cogs import admin_app_db as db
from cogs import admin_update

TOKEN_TTL_HOURS = 12

load_dotenv()
API_HOST = os.getenv("ADMIN_API_HOST")
API_PORT = os.getenv("ADMIN_API_PORT")

LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 15 * 60

_sessions: dict[str, dict] = {}
_login_attempts: dict[str, dict] = {}


def _client_ip(request: web.Request) -> str:
    return request.remote or "unknown"

def _is_locked_out(ip: str) -> bool:
    record = _login_attempts.get(ip)
    if not record:
        return False
    return record["locked_until"] > time.monotonic()

def _record_failed_login(ip: str):
    record = _login_attempts.setdefault(ip, {"count": 0, "locked_until": 0})
    record["count"] += 1
    if record["count"] >= LOGIN_MAX_ATTEMPTS:
        record["locked_until"] = time.monotonic() + LOGIN_LOCKOUT_SECONDS
        record["count"] = 0

def _clear_failed_logins(ip: str):
    _login_attempts.pop(ip, None)

def _new_token(username, discord_id):
    token = secrets.token_urlsafe(32)
    _sessions[token] = {
        "username": username,
        "discord_id": discord_id,
        "expires": datetime.now(timezone.utc) + timedelta(hours=TOKEN_TTL_HOURS),
    }
    return token

def _check_auth(request) -> dict | None:
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

        app = web.Application(middlewares=[error_middleware])
        app.add_routes(
            [
                web.post("/login", self.login),
                web.post("/api/link", self.link),
                web.post("/api/unlink", self.unlink),
                web.post("/api/ban", self.ban),
                web.post("/api/unban", self.unban),
                web.get("/api/ban_check", self.ban_check),
                web.get("/api/logs", self.logs),
                web.get("/api/servers", self.servers),
                web.post("/api/server_invite", self.server_invite),
                web.get("/api/users", self.users),
                web.get("/api/banned", self.banned),
                web.get("/api/update/latest", self.update_latest),
                web.get("/api/update/download", self.update_download),
            ]
        )
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, API_HOST, API_PORT)
        await site.start()
        logging.info(f"[AdminAPI] Listening on {API_HOST}:{API_PORT}")

    async def cog_unload(self):
        if self.runner:
            await self.runner.cleanup()

    def _require_auth(self, request) -> dict:
        session = _check_auth(request)
        if not session:
            raise web.HTTPUnauthorized(
                text='{"success": false, "error": "Not authenticated."}',
                content_type="application/json",
            )
        return session

    async def login(self, request: web.Request):
        ip = _client_ip(request)
        if _is_locked_out(ip):
            return web.json_response(
                {"success": False, "error": "Too many failed attempts. Try again in a few minutes."}, status=429
            )

        body = await request.json()
        username = body.get("username", "")
        password = body.get("password", "")

        account = await db.verify_login(username, password)
        if not account:
            _record_failed_login(ip)
            return web.json_response({"success": False, "error": "Invalid credentials."}, status=401)

        if account["discord_id"] and not admin_core.is_user_allowed(account["discord_id"]):
            _record_failed_login(ip)
            return web.json_response({"success": False, "error": "This account is not authorized."}, status=403)

        _clear_failed_logins(ip)
        token = _new_token(account["username"], account["discord_id"])
        return web.json_response({"success": True, "token": token, "username": account["username"]})

    async def servers(self, request: web.Request):
        self._require_auth(request)
        servers_list = await admin_core.get_bot_servers(self.bot)
        return web.json_response({"success": True, "servers": servers_list})

    async def users(self, request: web.Request):
        self._require_auth(request)
        linked = await admin_core.get_all_linked_users()
        return web.json_response({"success": True, "users": linked})

    async def banned(self, request: web.Request):
        self._require_auth(request)
        banned_list = await admin_core.get_all_banned()
        return web.json_response({"success": True, "banned": banned_list})

    async def server_invite(self, request: web.Request):
        session = self._require_auth(request)
        try:
            body = await request.json()
            guild_id_raw = body.get("guild_id") or body.get("server_id")
            if not guild_id_raw:
                return web.json_response({"success": False, "error": "Missing server/guild ID."}, status=400)
            guild_id = int(guild_id_raw)
        except (ValueError, TypeError):
            return web.json_response({"success": False, "error": "Invalid server ID format."}, status=400)

        result = await admin_core.generate_and_send_invite(
            self.bot,
            guild_id=guild_id,
            admin_discord_id=session.get("discord_id")
        )
        await db.log_action(session["username"], "invite_request", str(guild_id), None, str(result))
        return web.json_response(result)

    async def link(self, request: web.Request):
        session = self._require_auth(request)
        body = await request.json()
        target_user_id = int(body["target_user_id"])
        vrchat_id = str(body["vrchat_id"])
        reason = body.get("reason")

        result = await admin_core.perform_link(
            self.bot, session["discord_id"], session["username"], target_user_id, vrchat_id, reason
        )
        await db.log_action(session["username"], "link", str(target_user_id), reason, str(result))
        return web.json_response(result)

    async def unlink(self, request: web.Request):
        session = self._require_auth(request)
        body = await request.json()
        target_user_id = int(body["target_user_id"])
        reason = body.get("reason")

        result = await admin_core.perform_unlink(
            self.bot, session["discord_id"], session["username"], target_user_id, reason
        )
        await db.log_action(session["username"], "unlink", str(target_user_id), reason, str(result))
        return web.json_response(result)

    async def ban(self, request: web.Request):
        session = self._require_auth(request)
        body = await request.json()
        target_input = str(body["target_input"])
        reason = str(body["reason"])

        result = await admin_core.perform_ban(self.bot, session["discord_id"], session["username"], target_input, reason)
        await db.log_action(session["username"], "ban", target_input, reason, str(result))
        return web.json_response(result)

    async def unban(self, request: web.Request):
        session = self._require_auth(request)
        body = await request.json()
        target_input = str(body["target_input"])
        reason = str(body["reason"])

        result = await admin_core.perform_unban(self.bot, session["discord_id"], session["username"], target_input, reason)
        await db.log_action(session["username"], "unban", target_input, reason, str(result))
        return web.json_response(result)

    async def ban_check(self, request: web.Request):
        self._require_auth(request)
        target_input = request.query.get("target", "")
        result = await admin_core.perform_get_ban(self.bot, target_input)
        return web.json_response(result)

    async def logs(self, request: web.Request):
        self._require_auth(request)
        query = request.query.get("q", "")
        rows = await db.search_logs(query)
        return web.json_response({"success": True, "logs": rows})

    async def update_latest(self, request: web.Request):
        self._require_auth(request)
        result = await admin_update.get_latest_release()
        return web.json_response(result)

    async def update_download(self, request: web.Request):
        self._require_auth(request)
        asset_id_raw = request.query.get("asset_id", "")
        if not asset_id_raw.isdigit():
            return web.json_response({"success": False, "error": "Missing or invalid asset_id."}, status=400)

        response = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "application/octet-stream",
                "Content-Disposition": "attachment; filename=update.exe",
            },
        )
        await response.prepare(request)

        async def _write(chunk: bytes):
            await response.write(chunk)

        try:
            await admin_update.stream_release_asset(int(asset_id_raw), _write)
        except Exception as e:
            logging.error(f"[AdminAPI] Update download failed: {e}")

        await response.write_eof()
        return response

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminAPI(bot))
