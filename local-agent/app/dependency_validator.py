from __future__ import annotations

import re


URL_PATTERNS = [
    re.compile(r"^https?://"),
    re.compile(r"^git://"),
    re.compile(r"^git\+https?://"),
    re.compile(r"^git\+ssh://"),
    re.compile(r"^git@[\w.-]+:"),
    re.compile(r"^file://"),
]

PATH_PATTERNS = [
    re.compile(r"^/"),
    re.compile(r"^~"),
    re.compile(r"^\./"),
    re.compile(r"^\../"),
]

REGISTRY_SPEC_PATTERN = re.compile(
    r"^[a-zA-Z0-9_. -]+"
    r"(?:/[a-zA-Z0-9_. -]+)?"
    r"(?:@[a-zA-Z0-9_.+-]+)?"
    r"$"
)


def validate_lib_deps(lib_deps: list[str]) -> tuple[bool, str | None]:
    """
    Validates lib_deps for PlatformIO Registry packages only.
    Returns (is_valid, error_message).
    """
    for dep in lib_deps:
        dep_stripped = dep.strip()

        if not dep_stripped:
            return False, "Empty library specification"

        for pattern in URL_PATTERNS:
            if pattern.match(dep_stripped):
                return False, f"URL-based dependency not allowed: {dep_stripped}"

        for pattern in PATH_PATTERNS:
            if pattern.match(dep_stripped):
                return False, f"Local path dependency not allowed: {dep_stripped}"

        if not REGISTRY_SPEC_PATTERN.match(dep_stripped):
            return False, f"Invalid library specification format: {dep_stripped}"

    return True, None