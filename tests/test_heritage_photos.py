import hashlib

import pytest
from fastapi.testclient import TestClient
from nicegui import Client

from culturebridge.config import get_settings
from culturebridge.database import initialize_database
from culturebridge.main import app
from culturebridge.ui.heritage_photos import PHOTO_DIR, PHOTOS


@pytest.mark.parametrize("identity", PHOTOS)
def test_reviewed_photograph_has_expected_bytes_and_individual_license(identity):
    photo = PHOTOS[identity]
    raw = (PHOTO_DIR / photo["file"]).read_bytes()
    assert raw.startswith(b"\xff\xd8")
    assert hashlib.sha256(raw).hexdigest() == photo["sha256"]
    assert photo["source"].startswith("https://commons.wikimedia.org/wiki/File:")
    assert photo["author"] and photo["license_url"] and photo["alt"]


def test_course_photos_are_local_lazy_accessible_and_not_agent_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "photos.db")
    initialize_database()
    with TestClient(app) as client:
        response = client.get("/courses/pagoda-materials")
        assert response.status_code == 200
        page = next(reversed(list(Client.instances.values())))
        images = [e for e in page.elements.values() if "cb-heritage-photo" in e._classes]
        assert len(images) == 2
        for image in images:
            assert image._props["loading"] == "lazy" and "실제 사진" in image._props["alt"]
            assert image._props["role"] == "img" and image._props["aria-label"]
            assert "wikimedia" not in str(image._props["src"])
            assert client.get(image._props["src"]).status_code == 200
        assert client.get("/api/learning/conversations").json() == []
