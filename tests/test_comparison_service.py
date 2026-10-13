from culturebridge.database import initialize_database
from culturebridge.domain.models import LearningLevel
from culturebridge.services import catalog_service
from culturebridge.services.comparison_service import (
    create_saved_comparison,
    get_saved_comparison,
    list_saved_comparisons,
)


def test_comparison_snapshot_survives_catalog_change(tmp_path, monkeypatch):
    path = tmp_path / "snapshots.db"
    initialize_database(path)
    result = create_saved_comparison("seokguram", "horyuji", LearningLevel.BEGINNER, path)
    original = get_saved_comparison(result.saved_id, path)
    altered = catalog_service.HERITAGES["seokguram"].model_copy(update={"name": "변경된 이름"})
    monkeypatch.setitem(catalog_service.HERITAGES, "seokguram", altered)
    source_id = original.sources[0].id
    altered_source = catalog_service.SOURCES[source_id].model_copy(update={"title": "변경된 출처"})
    monkeypatch.setitem(catalog_service.SOURCES, source_id, altered_source)
    assert get_saved_comparison(result.saved_id, path) == original
    assert list_saved_comparisons(path=path)[0].left_name == "석굴암"


def test_comparison_history_pagination(tmp_path):
    path = tmp_path / "history.db"
    initialize_database(path)
    first = create_saved_comparison("seokguram", "horyuji", LearningLevel.BEGINNER, path)
    second = create_saved_comparison("seokguram", "dayanta", LearningLevel.ADVANCED, path)
    assert list_saved_comparisons(limit=1, path=path)[0].id == second.saved_id
    assert list_saved_comparisons(limit=1, offset=1, path=path)[0].id == first.saved_id
