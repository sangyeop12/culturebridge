from xml.etree import ElementTree

import pytest
from fastapi.testclient import TestClient

from culturebridge.config import get_settings
from culturebridge.data.learning_courses import COURSES
from culturebridge.database import initialize_database
from culturebridge.main import app
from culturebridge.ui.heritage_art import COURSE_ART, MOTIFS, course_art, heritage_art


@pytest.mark.parametrize("kind", list(MOTIFS))
def test_original_illustrations_are_accessible_local_svg(kind):
    svg = heritage_art(kind)
    root = ElementTree.fromstring(svg)
    assert root.attrib["role"] == "img"
    assert "창작 삽화" in root.attrib["aria-label"]
    assert "http" not in svg.replace("http://www.w3.org/2000/svg", "")
    assert "<script" not in svg and "<image" not in svg


def test_all_five_courses_have_distinct_illustrations():
    assert set(COURSE_ART) == set(COURSES)
    assert len({course_art(identity) for identity in COURSES}) == 5
    assert heritage_art("<script>alert(1)</script>") == heritage_art("hall")
    ElementTree.fromstring(heritage_art(panoramic=True))


def test_illustrated_learning_pages_keep_navigation_and_disclosure(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "db_path", tmp_path / "design.db")
    initialize_database()
    with TestClient(app) as client:
        home = client.get("/")
        assert home.status_code == 200 and "cb-illustrated" in home.text
        assert "실제 모습이나 복원도가 아니에요" in home.text
        courses = client.get("/courses")
        assert courses.status_code == 200 and "cb-course-grid" in courses.text
        for identity in COURSES:
            assert f"/courses/{identity}" in courses.text
        detail = client.get("/courses/pagoda-materials")
        assert detail.status_code == 200 and "cb-course-banner" in detail.text
        assert "창작 삽화" in detail.text
