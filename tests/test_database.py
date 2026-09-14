from pathlib import Path

from backend.database import initialize_database, summary


def test_database_initializes_with_empty_summary(tmp_path: Path) -> None:
    database_file = tmp_path / "trialguard.db"

    initialize_database(database_file)

    assert summary(database_file) == {
        "sites": 0,
        "patients": 0,
        "deviations": 0,
        "open_deviations": 0,
        "capa_reports": 0,
        "datasets": 0,
    }