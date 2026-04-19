import pandas as pd

from brown_team_daai.manager_assignment import get_manager_on_date


def test_get_manager_on_date_uses_inclusive_date_ranges():
    spells_df = pd.DataFrame(
        [
            {
                "spell_id": 1,
                "team": "Galatasaray",
                "manager_name": "Manager A",
                "start_date": "2023-07-01",
                "end_date": "2023-09-15",
            },
            {
                "spell_id": 2,
                "team": "Galatasaray",
                "manager_name": "Manager B",
                "start_date": "2023-09-16",
                "end_date": None,
            },
            {
                "spell_id": 3,
                "team": "Fenerbahce",
                "manager_name": "Manager C",
                "start_date": "2023-07-01",
                "end_date": "2023-12-31",
            },
            {
                "spell_id": 4,
                "team": "Besiktas",
                "manager_name": "Caretaker D",
                "start_date": "2023-10-01",
                "end_date": "2023-10-10",
            },
            {
                "spell_id": 5,
                "team": "Besiktas",
                "manager_name": "Manager E",
                "start_date": "2023-10-11",
                "end_date": None,
            },
        ]
    )

    assert get_manager_on_date("Galatasaray", "2023-09-15", spells_df) == "Manager A"
    assert get_manager_on_date("Galatasaray", "2023-09-16", spells_df) == "Manager B"
    assert get_manager_on_date("Fenerbahce", "2023-09-16", spells_df) == "Manager C"
    assert get_manager_on_date("Besiktas", "2023-10-10", spells_df) == "Caretaker D"
    assert get_manager_on_date("Trabzonspor", "2023-09-16", spells_df) is None
