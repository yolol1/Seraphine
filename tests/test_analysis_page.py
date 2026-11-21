from app.view.analysis_page import (
    _formatTimestamp, _mergeTeam, _timelineEvents,
)


def test_timestamp_is_rendered_as_match_clock():
    assert _formatTimestamp(95_000) == "01:35"
    assert _formatTimestamp(None) == "--:--"


def test_merge_team_preserves_analysis_fields():
    merged = _mergeTeam([{
        "participantId": 4,
        "summonerName": "Tester",
        "gold": 12000,
        "goldSpent": 11000,
        "damageToTurrets": 2500,
        "damageToObjectives": 5000,
        "runeIds": [1, 2, 3],
        "runeNames": ["A", "B", "C"],
        "itemIds": [1001],
        "itemNames": ["Item"],
    }], [])

    assert merged[0]["participantId"] == 4
    assert merged[0]["goldSpent"] == 11000
    assert merged[0]["damageToObjectives"] == 5000
    assert merged[0]["runeNames"] == ["A", "B", "C"]
    assert merged[0]["itemNames"] == ["Item"]


def test_timeline_events_are_readable_and_localized():
    game = {
        "teams": {
            100: {"summoners": [
                {"participantId": 1, "summonerName": "Alpha"},
            ]},
            200: {"summoners": [
                {"participantId": 6, "summonerName": "Beta"},
            ]},
        },
    }
    timeline = {
        "frames": [{
            "timestamp": 95_000,
            "events": [
                {
                    "type": "CHAMPION_KILL",
                    "killerId": 1,
                    "victimId": 6,
                    "assistingParticipantIds": [],
                },
                {
                    "type": "ELITE_MONSTER_KILL",
                    "killerTeamId": 100,
                    "monsterType": "DRAGON",
                    "monsterSubType": "FIRE_DRAGON",
                },
                {
                    "type": "BUILDING_KILL",
                    "teamId": 200,
                    "buildingType": "TOWER_BUILDING",
                    "laneType": "MID_LANE",
                },
            ],
        }],
    }

    events = _timelineEvents(timeline, game)
    assert events[0]["time"] == "01:35"
    assert events[0]["text"] == "Alpha 击杀 Beta"
    assert "小龙 · 火龙" in events[1]["text"]
    assert events[2]["text"] == "红队的防御塔 · 中路被摧毁"


def test_empty_timeline_is_safe():
    assert _timelineEvents(None, {}) == []
    assert _timelineEvents({}, {}) == []
