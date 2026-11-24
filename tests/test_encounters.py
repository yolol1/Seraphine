import json
import sqlite3

from app.lol.encounters import (
    encounter_game_from_raw,
    game_id_signal_value,
)
from app.lol.persistent_cache import PersistentCache


def _player(puuid, name, team_id, champion_id=1):
    return {
        "puuid": puuid,
        "summonerName": name,
        "championId": champion_id,
        "championIcon": f"{champion_id}.png",
        "champLevel": 10,
        "kills": 3,
        "deaths": 2,
        "assists": 7,
        "cs": 120,
        "gold": 9000,
        "damage": 15000,
        "visionScore": 12,
    }


def _detail(game_id, blue_players, red_players):
    return {
        "gameId": game_id,
        "queueId": 420,
        "modeName": "Ranked Solo",
        "gameCreation": f"2026-11-{game_id:02d} 20:00",
        "gameCreationTimestamp": game_id,
        "gameDuration": "30:00",
        "remake": False,
        "teams": {
            100: {
                "win": True,
                "summoners": blue_players,
            },
            200: {
                "win": False,
                "summoners": red_players,
            },
        },
    }


def test_raw_game_normalization_recognizes_ally_and_enemy():
    raw = {
        "gameId": 10,
        "queueId": 420,
        "gameCreation": 1_700_000_000_000,
        "gameDuration": 1800,
        "participantIdentities": [
            {"participantId": 1, "player": {
                "puuid": "a", "gameName": "Alpha", "tagLine": "0001"}},
            {"participantId": 2, "player": {
                "puuid": "b", "gameName": "Beta", "tagLine": "0002"}},
            {"participantId": 6, "player": {
                "puuid": "c", "gameName": "Gamma", "tagLine": "0003"}},
        ],
        "participants": [
            {"participantId": 1, "teamId": 100, "championId": 1,
             "stats": {"win": True, "kills": 4, "deaths": 1, "assists": 5}},
            {"participantId": 2, "teamId": 100, "championId": 2,
             "stats": {"win": True, "kills": 2, "deaths": 2, "assists": 8}},
            {"participantId": 6, "teamId": 200, "championId": 3,
             "stats": {"win": False, "kills": 1, "deaths": 5, "assists": 3}},
        ],
    }

    game = encounter_game_from_raw(raw)

    assert [p["name"] for p in game["participants"]] == [
        "Alpha", "Beta", "Gamma"]
    assert game["participants"][1]["teamId"] == 100
    assert game["participants"][2]["teamId"] == 200


def test_encounter_row_game_id_round_trip_does_not_truncate():
    game_id = 901144181699
    low_32 = game_id & 0xFFFFFFFF
    signed_32 = low_32 - (1 << 32) if low_32 >= (1 << 31) else low_32

    signal_value = game_id_signal_value(game_id)

    assert signal_value == "901144181699"
    assert int(signal_value) == game_id
    assert signed_32 == -798950461
    assert signal_value != str(signed_32)


def test_cache_marks_both_teammates_and_opponents(tmp_path):
    db = PersistentCache(str(tmp_path / "encounters.db"))
    first = _detail(
        1,
        [_player("a", "Alpha", 100), _player("b", "Beta", 100)],
        [_player("c", "Gamma", 200)],
    )
    second = _detail(
        2,
        [_player("a", "Alpha", 100), _player("c", "Gamma", 100)],
        [_player("b", "Beta", 200)],
    )
    db.set_game_detail(1, first)
    db.set_game_detail(2, second)

    previous_only = db.get_encounter_marks(
        "a", ["b", "c"], exclude_game_id=2)

    assert previous_only["b"]["count"] == 1
    assert previous_only["b"]["lastRelationship"] == "ally"
    assert previous_only["c"]["count"] == 1
    assert previous_only["c"]["lastRelationship"] == "enemy"

    all_shared = db.get_encounter_marks("a", ["b", "c"])
    assert all_shared["b"]["count"] == 2
    assert all_shared["c"]["count"] == 2

    history = db.get_encounter_history("a", "c")
    assert [item["game_id"] for item in history] == [2, 1]
    assert history[0]["player"]["summonerName"] == "Gamma"
    assert history[0]["relationship"] == "ally"

    players = db.get_encounter_players("a")
    by_uuid = {player["puuid"]: player for player in players}
    assert set(by_uuid) == {"b", "c"}
    assert by_uuid["b"]["count"] == 2
    assert by_uuid["b"]["allyCount"] == 1
    assert by_uuid["b"]["enemyCount"] == 1


def test_cache_skips_current_game_for_badge_counts(tmp_path):
    db = PersistentCache(str(tmp_path / "encounters.db"))
    detail = _detail(
        3,
        [_player("a", "Alpha", 100)],
        [_player("b", "Beta", 200)],
    )
    db.set_game_detail(3, detail)

    assert db.get_encounter_marks(
        "a", ["b"], exclude_game_id=3) == {}
    assert db.get_encounter_marks("a", ["b"])["b"]["count"] == 1


def test_v1_cache_is_migrated_without_dropping_match_details(tmp_path):
    path = tmp_path / "old.db"
    detail = _detail(
        4,
        [_player("a", "Alpha", 100)],
        [_player("b", "Beta", 200)],
    )
    conn = sqlite3.connect(str(path))
    conn.executescript("""
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE game_details (
            game_id INTEGER PRIMARY KEY,
            detail_json TEXT,
            updated_at REAL
        );
        INSERT INTO meta VALUES ('schema_version', '1');
    """)
    conn.execute(
        "INSERT INTO game_details VALUES (4, ?, 1)",
        (json.dumps(detail, ensure_ascii=False),),
    )
    conn.commit()
    conn.close()

    db = PersistentCache(str(path))

    assert db.get_game_detail(4)["gameId"] == 4
    assert db.get_encounter_marks("a", ["b"])["b"]["count"] == 1
