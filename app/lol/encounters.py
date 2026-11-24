"""Helpers for indexing players who appeared in the same match.

The cache stores every participant-to-participant relationship for a match.
That lets the UI answer "did these two players meet before?" when viewing any
summoner, rather than only the currently logged-in account.
"""
from datetime import datetime
from typing import Optional


AI_PUUID = "00000000-0000-0000-0000-000000000000"


def normalize_game_id(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def game_id_signal_value(value) -> str:
    """Encode large match IDs so Qt cannot truncate them to 32-bit ints."""
    return str(normalize_game_id(value))


def _format_duration(seconds) -> str:
    try:
        seconds = max(0, int(seconds or 0))
    except (TypeError, ValueError):
        seconds = 0
    return f"{seconds // 60}:{seconds % 60:02d}"


def _format_timestamp(milliseconds) -> str:
    try:
        milliseconds = int(milliseconds or 0)
    except (TypeError, ValueError):
        return ""
    if milliseconds <= 0:
        return ""
    return datetime.fromtimestamp(milliseconds / 1000).strftime(
        "%Y-%m-%d %H:%M")


def _player_name(player: dict) -> str:
    return str(
        player.get("riotIdGameName")
        or player.get("gameName")
        or player.get("summonerName")
        or player.get("displayName")
        or "未知玩家"
    )


def _player_tag_line(player: dict) -> str:
    return str(
        player.get("riotIdTagline")
        or player.get("tagLine")
        or ""
    )


def encounter_game_from_raw(raw_game: dict) -> Optional[dict]:
    """Normalize an LCU or SGP match payload for encounter indexing."""
    if not isinstance(raw_game, dict):
        return None
    game = raw_game.get("json") if isinstance(raw_game.get("json"), dict) \
        else raw_game
    if not isinstance(game, dict):
        return None

    participants = game.get("participants") or []
    identities = {
        item.get("participantId"): item.get("player") or {}
        for item in (game.get("participantIdentities") or [])
        if isinstance(item, dict)
    }

    normalized = []
    for participant in participants:
        if not isinstance(participant, dict):
            continue
        participant_id = participant.get("participantId")
        identity = identities.get(participant_id, participant)
        puuid = participant.get("puuid") or identity.get("puuid")
        if not puuid or puuid == AI_PUUID:
            continue

        stats = participant.get("stats")
        if not isinstance(stats, dict):
            stats = participant

        team_id = participant.get("teamId")
        if game.get("queueId") == 1700:
            placement = stats.get("subteamPlacement")
            if placement is not None:
                team_id = int(placement) * 100

        normalized.append({
            "puuid": puuid,
            "name": _player_name(identity),
            "summonerName": _player_name(identity),
            "tagLine": _player_tag_line(identity),
            "teamId": team_id,
            "championId": participant.get("championId", 0) or 0,
            "championIcon": "",
            "championLevel": stats.get("champLevel", 0) or 0,
            "kills": stats.get("kills", 0) or 0,
            "deaths": stats.get("deaths", 0) or 0,
            "assists": stats.get("assists", 0) or 0,
            "cs": (stats.get("totalMinionsKilled", 0) or 0)
            + (stats.get("neutralMinionsKilled", 0) or 0),
            "gold": stats.get("goldEarned", 0) or 0,
            "damage": stats.get("totalDamageDealtToChampions", 0) or 0,
            "visionScore": stats.get("visionScore", 0) or 0,
            "win": bool(stats.get("win", False)),
            "remake": bool(
                stats.get("gameEndedInEarlySurrender", False)
                or stats.get("teamEarlySurrendered", False)
            ),
        })

    if not normalized:
        return None
    return {
        "gameId": normalize_game_id(game.get("gameId")),
        "queueId": game.get("queueId"),
        "modeName": game.get("gameMode") or "",
        "gameTime": _format_timestamp(game.get("gameCreation")),
        "gameCreation": game.get("gameCreation", 0) or 0,
        "gameDuration": _format_duration(game.get("gameDuration")),
        "participants": normalized,
    }


def encounter_game_from_parsed(detail: dict) -> Optional[dict]:
    """Normalize an already rendered GameDetail for encounter indexing."""
    if not isinstance(detail, dict):
        return None

    participants = []
    for team_key, team in (detail.get("teams") or {}).items():
        if not isinstance(team, dict):
            continue
        try:
            team_id = int(team_key)
        except (TypeError, ValueError):
            team_id = team_key
        for player in team.get("summoners") or []:
            if not isinstance(player, dict):
                continue
            puuid = player.get("puuid")
            if not puuid or puuid == AI_PUUID:
                continue
            participants.append({
                "puuid": puuid,
                "name": player.get("summonerName") or "未知玩家",
                "summonerName": player.get("summonerName") or "未知玩家",
                "tagLine": player.get("tagLine", ""),
                "teamId": team_id,
                "championId": player.get("championId", 0) or 0,
                "championIcon": player.get("championIcon", ""),
                "championLevel": player.get("champLevel", 0) or 0,
                "kills": player.get("kills", 0) or 0,
                "deaths": player.get("deaths", 0) or 0,
                "assists": player.get("assists", 0) or 0,
                "cs": player.get("cs", 0) or 0,
                "gold": player.get("gold", 0) or 0,
                "damage": player.get("damage", 0) or 0,
                "visionScore": player.get("visionScore", 0) or 0,
                "win": bool(team.get("win", False)),
                "remake": bool(detail.get("remake", False)),
            })

    if not participants:
        return None
    return {
        "gameId": normalize_game_id(detail.get("gameId")),
        "queueId": detail.get("queueId"),
        "modeName": detail.get("modeName") or "",
        "gameTime": detail.get("gameCreation") or "",
        "gameCreation": detail.get("gameCreationTimestamp", 0) or 0,
        "gameDuration": detail.get("gameDuration") or "",
        "participants": participants,
    }
