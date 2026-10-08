"""Every live registry identity requires exact, bilingual, local visual coverage."""
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import shutil
import struct
import subprocess
from urllib.parse import parse_qs, urlsplit

import pytest

import app as appmod
from training_engine import load_exercise_library


ROOT = Path(__file__).parents[1]


def _manifest_source():
    class Scripts(HTMLParser):
        def __init__(self):
            super().__init__()
            self.sources = []

        def handle_starttag(self, tag, attrs):
            if tag == "script":
                source = dict(attrs).get("src", "")
                if urlsplit(source).path == "/static/exercise/visuals/v1/manifest.js":
                    self.sources.append(source)

    parser = Scripts()
    parser.feed(appmod.app.test_client().get("/app").get_data(as_text=True))
    assert len(parser.sources) == 1
    return parser.sources[0]


@pytest.fixture(scope="module")
def registry_visuals():
    ids = [exercise.exercise_id for exercise in load_exercise_library().exercises]
    node = shutil.which("node")
    assert node, "Node is required to exercise the production manifest resolver"
    script = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const context = { URL, window: { document: { currentScript: { src: process.argv[2] } } } };
vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'), context);
const api = context.window.ApexExerciseVisuals;
const ids = JSON.parse(fs.readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify({
  entries: ids.map(id => [id, api.resolve(id)]),
  unknown: ['bodyweight.unmapped', '__proto__', 'Push-Up', 'push_up', null]
    .map(id => api.resolve(id))
}));
"""
    result = subprocess.run(
        [node, "-e", script, str(ROOT / "static/exercise/visuals/v1/manifest.js"),
         "https://apex.test" + _manifest_source()],
        input=json.dumps(ids), capture_output=True, text=True, encoding="utf-8", check=True,
    )
    resolved = json.loads(result.stdout)
    assert resolved["unknown"] == [None] * 5
    return dict(resolved["entries"])


def _webp_dimensions(data):
    assert data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    assert struct.unpack_from("<I", data, 4)[0] + 8 == len(data)
    offset = 12
    while offset + 8 <= len(data):
        kind = data[offset:offset + 4]
        length = struct.unpack_from("<I", data, offset + 4)[0]
        chunk = data[offset + 8:offset + 8 + length]
        assert len(chunk) == length
        if kind == b"VP8 ":
            assert chunk[3:6] == b"\x9d\x01\x2a"
            width, height = struct.unpack_from("<HH", chunk, 6)
            return width & 0x3FFF, height & 0x3FFF
        if kind == b"VP8L":
            assert chunk[0] == 0x2F
            bits = int.from_bytes(chunk[1:5], "little")
            return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
        if kind == b"VP8X":
            return int.from_bytes(chunk[4:7], "little") + 1, int.from_bytes(chunk[7:10], "little") + 1
        offset += 8 + length + length % 2
    pytest.fail("WebP image has no supported dimensions header")


def test_every_current_registry_id_has_exact_bilingual_visuals(registry_visuals):
    # This set comes from the current registry, so a future uncovered ID fails.
    missing = [identity for identity, entry in registry_visuals.items() if entry is None]
    assert missing == [], f"Missing canonical artwork: {missing}"
    expected_query = parse_qs(urlsplit(_manifest_source()).query)
    for identity, entry in registry_visuals.items():
        assert entry["exercise_id"] == identity
        assert set(entry["alt"]) == {"bg", "en"}
        assert all(value.strip() for value in entry["alt"].values())
        assert entry["alt"]["bg"] != entry["alt"]["en"]
        for variant in ("thumb", "protocol"):
            url = urlsplit(entry[variant])
            assert url.path == f"/static/exercise/visuals/v1/{identity}--{variant}.webp"
            assert parse_qs(url.query) == expected_query
            assert parse_qs(url.query) == {"v": ["canonical-workout-r4"]}


def test_every_resolved_visual_is_unique_exact_webp_and_http_200(registry_visuals):
    client = appmod.app.test_client()
    hashes = {"thumb": set(), "protocol": set()}
    expected_files = set()
    for identity, entry in registry_visuals.items():
        assert entry is not None, identity
        for variant, dimensions in (("thumb", (320, 240)), ("protocol", (960, 720))):
            path = ROOT / urlsplit(entry[variant]).path.lstrip("/")
            expected_files.add(path.name)
            assert path.is_file(), identity
            data = path.read_bytes()
            assert _webp_dimensions(data) == dimensions, str(path)
            digest = hashlib.sha256(data).hexdigest()
            assert digest not in hashes[variant], f"Reused artwork for {identity}"
            hashes[variant].add(digest)
            response = client.get(entry[variant])
            assert response.status_code == 200, identity
            # Windows may not register WebP in its platform MIME table.
            assert response.mimetype in {"image/webp", "application/octet-stream"}
            assert response.data == data
            assert not response.cache_control.no_store
    actual_files = {path.name for path in (ROOT / "static/exercise/visuals/v1").glob("*.webp")}
    assert actual_files == expected_files


def test_image_revision_is_inherited_from_script_url_not_a_separate_token():
    script = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const context = { URL, window: { document: { currentScript: {
  src: 'https://apex.test/static/exercise/visuals/v1/manifest.js?v=release-check'
} } } };
vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'), context);
process.stdout.write(JSON.stringify(context.window.ApexExerciseVisuals.resolve('barbell.bench_press')));
"""
    result = subprocess.run(
        [shutil.which("node"), "-e", script, str(ROOT / "static/exercise/visuals/v1/manifest.js")],
        capture_output=True, text=True, check=True,
    )
    entry = json.loads(result.stdout)
    for variant in ("thumb", "protocol"):
        assert parse_qs(urlsplit(entry[variant]).query) == {"v": ["release-check"]}
