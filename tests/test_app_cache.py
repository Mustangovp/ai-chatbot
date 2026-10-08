"""The app shell is not stored; landing and static caching stay route-local."""
import pytest
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit
from flask import template_rendered

import app as appmod


@pytest.mark.parametrize("path", ["/app", "/app?lang=en", "/app?lang=bg"])
def test_app_shell_versions_canonical_mutable_assets_with_one_release_revision(path):
    class ScriptSources(HTMLParser):
        def __init__(self):
            super().__init__()
            self.sources = []

        def handle_starttag(self, tag, attrs):
            if tag == "script":
                source = dict(attrs).get("src")
                if source:
                    self.sources.append(source)

    response = appmod.app.test_client().get(path)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    scripts = ScriptSources()
    scripts.feed(response.get_data(as_text=True))
    revisions = []
    for asset in ("/static/exercise_instruction_library.js",
                  "/static/exercise/visuals/v1/manifest.js"):
        sources = [source for source in scripts.sources if urlsplit(source).path == asset]
        assert len(sources) == 1
        assert asset not in scripts.sources
        url = urlsplit(sources[0])
        assert not url.scheme and not url.netloc and not url.fragment
        query = parse_qs(url.query, keep_blank_values=True)
        assert set(query) == {"v"}
        assert len(query["v"]) == 1 and query["v"][0]
        revisions.append(query["v"][0])
        asset_response = appmod.app.test_client().get(sources[0])
        assert asset_response.status_code == 200
        assert asset_response.cache_control.no_store is False
        assert asset_response.headers["ETag"]
    # Bump this shared explicit revision when either canonical mutable asset changes.
    assert revisions == ["canonical-workout-r3", "canonical-workout-r3"]


@pytest.mark.parametrize("path", ["/app", "/app?lang=en", "/app?lang=bg"])
def test_app_shell_is_not_stored_and_renders_current_progress_wiring(path):
    response = appmod.app.test_client().get(path)
    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert response.headers["Cache-Control"] == "no-store"
    assert "case 'progress': showProgress();" in response.get_data(as_text=True)
    assert b'<meta name="robots" content="noindex">' in response.data


@pytest.mark.parametrize("path,template_name,language", [
    ("/", "landing.html", "bg"), ("/en", "landing_en.html", "en")])
def test_landing_routes_keep_existing_templates_and_cache_behavior(path, template_name, language):
    rendered = []
    def capture(sender, template, context, **extra):
        rendered.append(template.name)
    template_rendered.connect(capture, appmod.app)
    try:
        response = appmod.app.test_client().get(path)
    finally:
        template_rendered.disconnect(capture, appmod.app)
    assert response.status_code == 200
    assert rendered == [template_name]
    assert f'<html lang="{language}">'.encode() in response.data
    assert "Cache-Control" not in response.headers


@pytest.mark.parametrize("path", ["/static/logo.png",
    "/static/exercise/visuals/v1/dumbbell.front_squat--thumb.webp"])
def test_static_assets_are_not_globally_forced_to_no_store(path):
    response = appmod.app.test_client().get(path)
    assert response.status_code == 200
    assert response.cache_control.no_store is False
    assert response.headers["ETag"]
    assert response.headers["Last-Modified"]


def test_static_conditional_revalidation_remains_available():
    client = appmod.app.test_client()
    response = client.get("/static/logo.png")
    revalidated = client.get("/static/logo.png", headers={"If-None-Match": response.headers["ETag"]})
    assert revalidated.status_code == 304
    assert revalidated.cache_control.no_store is False


@pytest.mark.parametrize("path", ["/", "/en", "/app"])
def test_existing_security_headers_remain_intact(path):
    response = appmod.app.test_client().get(path)
    expected = {"X-Frame-Options": "DENY", "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "strict-origin-when-cross-origin",
                "Permissions-Policy": "camera=(), microphone=(self), geolocation=()"}
    for header, value in expected.items():
        assert response.headers[header] == value
