import re

from typing import Optional

_VRCHAT_ID = r"usr_[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}"
_VRCHAT_ID_RE = re.compile(_VRCHAT_ID, re.IGNORECASE)
_VRCHAT_PROFILE_RE = re.compile(rf"https?://vrchat\.com/home/user/({_VRCHAT_ID})/?", re.IGNORECASE)

_MARKDOWN_SPECIALS_RE = re.compile(r"([\\*_~|`>\[\]<])")
LINK_TEXT_MAX_LENGTH = 64


def find_vrchat_id(text: Optional[str]) -> Optional[str]:
    match = _VRCHAT_ID_RE.search(text or "")
    return match.group(0).lower() if match else None

def parse_vrchat_id(value: Optional[str]) -> Optional[str]:
    value = (value or "").strip()
    if _VRCHAT_ID_RE.fullmatch(value):
        return value.lower()
    match = _VRCHAT_PROFILE_RE.fullmatch(value)
    return match.group(1).lower() if match else None

def looks_like_discord_id(value) -> bool:
    value = str(value).strip()
    return value.isdigit() and 16 <= len(value) <= 22

def escape_link_text(text: Optional[str]) -> str:
    text = " ".join((text or "").split())[:LINK_TEXT_MAX_LENGTH]
    return _MARKDOWN_SPECIALS_RE.sub(r"\\\1", text)
