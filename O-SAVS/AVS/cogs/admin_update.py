import os, aiohttp

from dotenv import load_dotenv

GITHUB_API = "https://api.github.com"

load_dotenv()
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")


def _gh_headers(accept: str = "application/vnd.github+json") -> dict:
    headers = {
        "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers

async def get_latest_release() -> dict:
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return {"success": False, "error": "Update checking is not configured on the server."}

    url = f"{GITHUB_API}/repos/{GITHUB_REPO}/releases/latest"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=_gh_headers(), timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return {"success": False, "error": f"GitHub API returned status {resp.status}."}
                data = await resp.json()
    except aiohttp.ClientError as e:
        return {"success": False, "error": f"Could not reach GitHub: {e}"}

    asset = next((a for a in data.get("assets", []) if a.get("name", "").lower().endswith(".exe")), None)
    if not asset:
        return {"success": False, "error": "Latest release has no .exe asset attached."}

    return {
        "success": True,
        "tag_name": data.get("tag_name", ""),
        "notes": data.get("body", "") or "",
        "published_at": data.get("published_at"),
        "asset_id": asset["id"],
        "asset_name": asset["name"],
        "asset_size": asset["size"],
    }

async def stream_release_asset(asset_id: int, write_chunk):
    if not GITHUB_TOKEN or not GITHUB_REPO:
        raise RuntimeError("Update checking is not configured on the server.")

    url = f"{GITHUB_API}/repos/{GITHUB_REPO}/releases/assets/{asset_id}"
    async with aiohttp.ClientSession() as session:
        async with session.get(
            url, headers=_gh_headers(accept="application/octet-stream"), timeout=aiohttp.ClientTimeout(total=300)
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"GitHub returned status {resp.status} fetching the release asset.")
            async for chunk in resp.content.iter_chunked(65536):
                await write_chunk(chunk)
