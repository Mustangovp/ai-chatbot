"""Crawler-access contracts for the public APEX routes."""
from __future__ import annotations

import app as appmod


PUBLIC_DESTINATIONS = ("/", "/en", "/app")
PRIVATE_ACTIONS = ("/chat", "/verify-token", "/create-checkout-session")


def _robots_groups(body: str) -> dict[str, tuple[tuple[str, str], ...]]:
    groups: dict[str, list[tuple[str, str]]] = {}
    current_agent: str | None = None

    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition(":")
        if not separator:
            continue
        if key.lower() == "user-agent":
            current_agent = value.strip()
            groups.setdefault(current_agent, [])
        elif current_agent and key.lower() in {"allow", "disallow"}:
            groups[current_agent].append((key.title(), value.strip()))

    return {agent: tuple(directives) for agent, directives in groups.items()}


def _allows(directives: tuple[tuple[str, str], ...], path: str) -> bool:
    matches: list[tuple[int, str]] = []
    for directive, pattern in directives:
        exact = pattern.endswith("$")
        comparison = pattern[:-1] if exact else pattern
        if (path == comparison) if exact else path.startswith(comparison):
            matches.append((len(comparison), directive))

    if not matches:
        return True
    longest = max(length for length, _ in matches)
    return any(directive == "Allow" for length, directive in matches if length == longest)


def test_google_ads_robots_access_is_explicit_and_private_actions_stay_blocked():
    response = appmod.app.test_client().get("/robots.txt")

    assert response.status_code == 200
    assert response.mimetype == "text/plain"
    groups = _robots_groups(response.get_data(as_text=True))

    for agent in ("AdsBot-Google", "AdsBot-Google-Mobile"):
        assert agent in groups
        assert all(_allows(groups[agent], path) for path in PUBLIC_DESTINATIONS)
        assert all(not _allows(groups[agent], path) for path in PRIVATE_ACTIONS)

    assert not _allows(groups["*"], "/app")
    assert not _allows(groups["*"], "/app/success")


def test_public_routes_render_identically_for_google_ads_user_agents():
    client = appmod.app.test_client()
    route_markers = {
        "/": b'<html lang="bg">',
        "/en": b'<html lang="en">',
        "/app": b'<meta name="robots" content="noindex">',
    }

    for path, marker in route_markers.items():
        normal = client.get(path)
        desktop_ads = client.get(path, headers={"User-Agent": "AdsBot-Google"})
        mobile_ads = client.get(path, headers={"User-Agent": "AdsBot-Google-Mobile"})

        assert normal.status_code == desktop_ads.status_code == mobile_ads.status_code == 200
        assert marker in normal.data
        assert normal.data == desktop_ads.data == mobile_ads.data
