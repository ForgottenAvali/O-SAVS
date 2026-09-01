import os, asyncio, logging, vrchatapi, json, http.cookiejar


from vrchatapi.api import authentication_api, users_api
from vrchatapi.models.two_factor_email_code import TwoFactorEmailCode
from vrchatapi.exceptions import UnauthorizedException


from dotenv import load_dotenv


from urllib.parse import quote


load_dotenv()
VRCUSER = os.getenv("VRC_USER")
VRCPASS = os.getenv("VRC_PASS")
CONTACT = os.getenv("CONTACT")

encoded_user = quote(VRCUSER) if VRCUSER else None
encoded_pass = quote(VRCPASS) if VRCPASS else None
encoded_contact = quote(CONTACT) if CONTACT else None


config = vrchatapi.Configuration(username=encoded_user, password=encoded_pass)
client = vrchatapi.ApiClient(config)
client.user_agent = f"O-SAVS/1.0.0 (contact: {encoded_contact})"


auth_api = authentication_api.AuthenticationApi(client)
users_api_instance = users_api.UsersApi(client)


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


async def get_vrchat_user(user_id: str) -> dict | None:
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: users_api_instance.get_user(user_id)
        )

        username = getattr(result, "display_name", None) or getattr(result, "username", "Unknown")
        bio = getattr(result, "bio", None)
        verification = getattr(result, "age_verified")
        status = getattr(result, "status_description")

        return {
            "id": getattr(result, "id", user_id),
            "username": username,
            "bio": bio,
            "verification": verification,
            "status": status
        }
    except Exception as e:
        logging.exception(f"[VRChat] Failed to fetch user from user id ({user_id})")
        return None