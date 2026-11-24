import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.lol import tools


def _raw_game_without_queue_id():
    stats = {
        "win": True,
        "gameEndedInEarlySurrender": False,
        "champLevel": 11,
        "kills": 3,
        "deaths": 2,
        "assists": 7,
        "goldEarned": 9000,
        "perk0": 8005,
        "item0": 1001,
        "item1": 0,
        "item2": 0,
        "item3": 0,
        "item4": 0,
        "item5": 0,
        "item6": 0,
        "totalMinionsKilled": 100,
        "neutralMinionsKilled": 20,
        "totalDamageDealtToChampions": 15000,
    }
    return {
        "gameId": 9001,
        "gameCreation": 1_700_000_000_000,
        "gameDuration": 1800,
        "gameMode": "KIWI",
        "mapId": 12,
        "teams": [{
            "teamId": 100,
            "win": True,
            "bans": [],
            "baronKills": 0,
            "dragonKills": 2,
            "riftHeraldKills": 1,
            "hordeKills": 0,
            "towerKills": 5,
            "inhibitorKills": 1,
        }],
        "participantIdentities": [{
            "participantId": 1,
            "player": {"puuid": "player-a", "gameName": "Player"},
        }],
        "participants": [{
            "participantId": 1,
            "teamId": 100,
            "championId": 1,
            "spell1Id": 4,
            "spell2Id": 7,
            "stats": stats,
        }],
    }


def test_parse_game_detail_infers_queue_id_from_game_mode(monkeypatch):
    manager = SimpleNamespace(
        getNameMapByQueueId=lambda queue_id: {
            "name": "海克斯大乱斗" if queue_id == 2400 else "自定义",
            "map": "嚎哭深渊",
        },
        getMapNameById=lambda map_id: "嚎哭深渊",
        getMapIconByMapId=lambda map_id, win: "map.png",
        getPerkStyles=lambda: {},
        getRuneName=lambda rune_id: "Rune",
        getItemName=lambda item_id: "Item" if item_id else "",
    )
    monkeypatch.setattr(tools.connector, "manager", manager)
    monkeypatch.setattr(
        tools.connector, "getSummonerByPuuid",
        AsyncMock(return_value={"privacy": "PUBLIC"}))
    monkeypatch.setattr(
        tools.connector, "getChampionIcon", AsyncMock(return_value="champ.png"))
    monkeypatch.setattr(
        tools.connector, "getSummonerSpellIcon",
        AsyncMock(return_value="spell.png"))
    monkeypatch.setattr(
        tools.connector, "getRuneIcon", AsyncMock(return_value="rune.png"))
    monkeypatch.setattr(
        tools.connector, "getItemIcon", AsyncMock(return_value="item.png"))
    monkeypatch.setattr(tools.cfg, "get", lambda _: False)
    monkeypatch.setattr(tools.sqlite_cache, "set_game_detail", lambda *_: None)
    monkeypatch.setattr(tools, "ToolsTranslator", lambda: SimpleNamespace(
        top="TOP", jungle="JUG", middle="MID", bottom="BOT", support="SUP"))

    detail = asyncio.run(
        tools.parseGameDetailData("player-a", _raw_game_without_queue_id()))

    assert detail["queueId"] == 2400
    assert detail["modeName"] == "海克斯大乱斗"
    assert detail["win"] is True


def test_parse_game_detail_falls_back_when_subject_is_absent(monkeypatch):
    manager = SimpleNamespace(
        getNameMapByQueueId=lambda queue_id: {
            "name": "排位赛 单排/双排",
            "map": "召唤师峡谷",
        },
        getMapNameById=lambda map_id: "召唤师峡谷",
        getMapIconByMapId=lambda map_id, win: "map.png",
        getPerkStyles=lambda: {},
        getRuneName=lambda rune_id: "Rune",
        getItemName=lambda item_id: "Item" if item_id else "",
    )
    monkeypatch.setattr(tools.connector, "manager", manager)
    monkeypatch.setattr(
        tools.connector, "getSummonerByPuuid",
        AsyncMock(return_value={"privacy": "PUBLIC"}))
    monkeypatch.setattr(
        tools.connector, "getChampionIcon", AsyncMock(return_value="champ.png"))
    monkeypatch.setattr(
        tools.connector, "getSummonerSpellIcon",
        AsyncMock(return_value="spell.png"))
    monkeypatch.setattr(
        tools.connector, "getRuneIcon", AsyncMock(return_value="rune.png"))
    monkeypatch.setattr(
        tools.connector, "getItemIcon", AsyncMock(return_value="item.png"))
    monkeypatch.setattr(tools.cfg, "get", lambda _: False)
    monkeypatch.setattr(tools.sqlite_cache, "set_game_detail", lambda *_: None)
    monkeypatch.setattr(tools, "ToolsTranslator", lambda: SimpleNamespace(
        top="TOP", jungle="JUG", middle="MID", bottom="BOT", support="SUP"))

    raw = _raw_game_without_queue_id()
    raw["queueId"] = 420
    detail = asyncio.run(tools.parseGameDetailData("missing-player", raw))

    assert detail is not None
    assert detail["gameId"] == raw["gameId"]
    assert detail["win"] is True
    assert not detail["teams"][100]["summoners"][0]["isCurrent"]
