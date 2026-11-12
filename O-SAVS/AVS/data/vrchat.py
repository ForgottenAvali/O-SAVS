import os, asyncio, logging, vrchatapi, json, http.cookiejar

from vrchatapi.api import authentication_api, users_api, friends_api
from vrchatapi.models.two_factor_email_code import TwoFactorEmailCode
from vrchatapi.exceptions import UnauthorizedException
from dotenv import load_dotenv

load_dotenv()
VRCUSER = os.getenv("VRC_USER")
VRCPASS = os.getenv("VRC_PASS")
CONTACT = os.getenv("CONTACT")

BOT_VRC_NAME = "Noodle's Nexus"

config = vrchatapi.Configuration(username=VRCUSER, password=VRCPASS)

_existing_client = globals().get("client")
client = _existing_client if _existing_client is not None else vrchatapi.ApiClient(config)
client.user_agent = f"O-SAVS/1.4.0 (contact: {CONTACT})"

auth_api = authentication_api.AuthenticationApi(client)
users_api_instance = users_api.UsersApi(client)
friends_api_instance = friends_api.FriendsApi(client)

AUTH_TOKEN_FILE = os.path.join(os.path.dirname(__file__), "..", "utils", "vrc_auth_token.json")


async def login_vrc():
    loop = asyncio.get_running_loop()

    if os.path.exists(AUTH_TOKEN_FILE):
        try:
            with open(AUTH_TOKEN_FILE, "r") as f:
                saved = json.load(f)
                token = saved.get("auth")
                if token:
                    client.rest_client.cookie_jar.set_cookie(
                        http.cookiejar.Cookie(
                            version=0,
                            name="auth",
                            value=token,
                            port=None,
                            port_specified=False,
                            domain="api.vrchat.cloud",
                            domain_specified=True,
                            domain_initial_dot=False,
                            path="/",
                            path_specified=True,
                            secure=True,
                            expires=None,
                            discard=False,
                            comment=None,
                            comment_url=None,
                            rest={},
                            rfc2109=False
                        )
                    )

                    user = await loop.run_in_executor(None, auth_api.get_current_user)
                    print(f"[VRChat] Reused existing auth token as {user.display_name}")
                    return user
        except Exception as e:
            logging.warning(f"[VRChat] Failed to use saved auth token: {e}")

    try:
        user = await loop.run_in_executor(None, auth_api.get_current_user)
        print(f"[VRChat] Logged in as {user.display_name} (no 2FA required)")

        for cookie in client.rest_client.cookie_jar:
            if cookie.name == "auth":
                with open(AUTH_TOKEN_FILE, "w") as f:
                    json.dump({"auth": cookie.value}, f)
                print("[VRChat] Saved new auth token")
                break

        return user

    except vrchatapi.exceptions.UnauthorizedException as e:
        body = getattr(e, "body", None)
        if body:
            try:
                body_json = json.loads(body)
                if "requiresTwoFactorAuth" in body_json:
                    factors = body_json["requiresTwoFactorAuth"]

                    if "emailOtp" in factors:
                        code = input("[VRChat] Enter your VRChat Email 2FA code: ")
                        await loop.run_in_executor(
                            None,
                            lambda: auth_api.verify2_fa_email_code(TwoFactorEmailCode(code=code))
                        )
                        user = await loop.run_in_executor(None, auth_api.get_current_user)

                    elif "totp" in factors:
                        code = input("[VRChat] Enter your VRChat Authenticator code: ")
                        await loop.run_in_executor(None, lambda: auth_api.verify2_fa({"code": code}))
                        user = await loop.run_in_executor(None, auth_api.get_current_user)

                    for cookie in client.rest_client.cookie_jar:
                        if cookie.name == "auth":
                            with open(AUTH_TOKEN_FILE, "w") as f:
                                json.dump({"auth": cookie.value}, f)
                            print("[VRChat] Saved new auth token")
                            break

                    return user

            except json.JSONDecodeError:
                logging.error(f"[VRChat] Could not parse error body: {body}")

        logging.error(f"[VRChat] Login failed: {e}")
        raise

async def _call(func, *args):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args))

async def get_vrchat_bio(user_id: str) -> dict | None:
    try:
        result = await _call(users_api_instance.get_public_profile, user_id)

        username = getattr(result, "display_name", None) or getattr(result, "username", "Unknown")
        verification = getattr(result, "age_verified")
        bio = getattr(result, "bio", None)

        return {
            "id": getattr(result, "id", user_id),
            "username": username,
            "verification": verification,
            "bio": bio,
        }
    except Exception as e:
        logging.exception(f"[VRChat] Failed to fetch user from user id ({user_id})")
        return None

get_vrchat_user = get_vrchat_bio

async def get_vrchat_status(user_id: str) -> dict | None:
    try:
        result = await _call(users_api_instance.get_user, user_id)

        status = getattr(result, "status", None)
        return {
            "id": getattr(result, "id", user_id),
            "username": getattr(result, "display_name", None) or "Unknown",
            "verification": bool(getattr(result, "age_verified", False)),
            "status": getattr(status, "value", status),
            "status_description": getattr(result, "status_description", None) or "",
            "is_friend": bool(getattr(result, "is_friend", False)),
        }
    except Exception as e:
        logging.exception(f"[VRChat] Failed to fetch status for user id ({user_id})")
        return None

async def send_friend_request(user_id: str) -> dict:
    try:
        status = await _call(friends_api_instance.get_friend_status, user_id)
        if getattr(status, "is_friend", False):
            return {"success": True, "already_friends": True}
        if getattr(status, "outgoing_request", False):
            return {"success": True, "already_pending": True}

        await _call(friends_api_instance.friend, user_id)
        return {"success": True}
    except vrchatapi.exceptions.ApiException as e:
        logging.error(f"[VRChat] Friend request to {user_id} failed: {e.status} {e.reason}")
        return {"success": False, "error": "rate_limited" if e.status == 429 else "failed"}
    except Exception as e:
        logging.exception(f"[VRChat] Friend request to {user_id} failed")
        return {"success": False, "error": "failed"}

def _is_not_found_error(e: "vrchatapi.exceptions.ApiException") -> bool:
    if e.status in (400, 404):
        return True
    body = (getattr(e, "body", None) or "").lower()
    return any(s in body for s in ("not friends", "not a friend", "no outgoing", "friend request not found", "not found"))

async def _try_remove(func, user_id: str, label: str) -> bool:
    try:
        await _call(func, user_id)
        return True
    except vrchatapi.exceptions.ApiException as e:
        if _is_not_found_error(e):
            return True
        logging.error(f"[VRChat] {label} for {user_id} failed: {e.status} {e.reason}")
        return False
    except Exception:
        logging.exception(f"[VRChat] {label} for {user_id} failed")
        return False

async def remove_friend(user_id: str) -> bool:
    unfriended = await _try_remove(friends_api_instance.unfriend, user_id, "Unfriend")
    retracted = await _try_remove(friends_api_instance.delete_friend_request, user_id, "Retract friend request")
    return unfriended and retracted
