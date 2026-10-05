"""The app shell is not stored; landing and static caching stay route-local."""
import pytest
from flask import template_rendered

import app as appmod


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
