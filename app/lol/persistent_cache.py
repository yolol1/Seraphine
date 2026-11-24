"""SQLite 持久缓存: 战绩/对局详情/战犯评级.

仅做离线降级展示用, 不替代 LCU 数据源.
"""
import json
import os
import sqlite3
import threading
from json import JSONDecodeError
from typing import Optional

from app.common.config import LOCAL_PATH
from app.common.logger import logger
from app.lol.encounters import (
    encounter_game_from_parsed,
    encounter_game_from_raw,
    normalize_game_id,
)
TAG = "PersistentCache"
DB_NAME = "seraphine_cache.db"
SCHEMA_VERSION = 2
MAX_GAMES_PER_PUUID = 1000
MAX_GAME_DETAILS = 500


class PersistentCache:
    def __init__(self, db_path: str = ""):
        self._path = db_path or os.path.join(LOCAL_PATH, DB_NAME)
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            try:
                self._conn = self._open(self._path)
                self._init_schema()
            except sqlite3.OperationalError as e:
                if "readonly" not in str(e).lower():
                    raise
                # Packaged/read-only profiles must not crash gameplay. Keep the
                # current session usable with an in-memory cache.
                if self._conn is not None:
                    self._conn.close()
                self._conn = self._open(":memory:")
                self._init_schema()
        return self._conn

    @staticmethod
    def _open(path: str) -> sqlite3.Connection:
        conn = sqlite3.connect(path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_schema(self):
        c = self._conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        version = c.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        self._create_tables()
        if version is None:
            c.execute("INSERT OR REPLACE INTO meta VALUES ('schema_version', ?)",
                      (str(SCHEMA_VERSION),))
        elif int(version["value"]) < SCHEMA_VERSION:
            # Schema upgrades are additive. Rebuilding the cache here would
            # discard match details and idle-game history from older builds.
            if int(version["value"]) < 2:
                self._backfill_encounters(c)
            c.execute("INSERT OR REPLACE INTO meta VALUES ('schema_version', ?)",
                      (str(SCHEMA_VERSION),))
        self._conn.commit()
        c.close()

    def _create_tables(self):
        c = self._conn.cursor()
        c.executescript("""
            CREATE TABLE IF NOT EXISTS games (
                game_id INTEGER NOT NULL,
                puuid TEXT NOT NULL,
                queue_id INTEGER,
                champion_id INTEGER,
                kills INTEGER, deaths INTEGER, assists INTEGER,
                win INTEGER, creation INTEGER, duration INTEGER,
                champion_level INTEGER, cs INTEGER, gold INTEGER,
                position TEXT, game_type TEXT, map_id INTEGER,
                remake INTEGER, time_str TEXT,
                game_json TEXT,
                updated_at REAL NOT NULL DEFAULT (julianday('now')),
                PRIMARY KEY (game_id, puuid)
            );
            CREATE INDEX IF NOT EXISTS idx_games_puuid ON games(puuid);
            CREATE INDEX IF NOT EXISTS idx_games_creation ON games(creation DESC);

            CREATE TABLE IF NOT EXISTS game_details (
                game_id INTEGER PRIMARY KEY,
                detail_json TEXT,
                updated_at REAL NOT NULL DEFAULT (julianday('now'))
            );

            CREATE TABLE IF NOT EXISTS verdicts (
                game_id INTEGER PRIMARY KEY,
                winner_rating TEXT,
                loser_rating TEXT,
                updated_at REAL NOT NULL DEFAULT (julianday('now'))
            );

            CREATE TABLE IF NOT EXISTS summoners (
                puuid TEXT PRIMARY KEY,
                game_name TEXT, tag_line TEXT,
                profile_icon TEXT, level INTEGER,
                updated_at REAL NOT NULL DEFAULT (julianday('now'))
            );  -- ponytail: summoners table unused, no write-through from connector

            CREATE TABLE IF NOT EXISTS encounters (
                game_id INTEGER NOT NULL,
                subject_puuid TEXT NOT NULL,
                player_puuid TEXT NOT NULL,
                relationship TEXT NOT NULL,
                player_name TEXT,
                tag_line TEXT,
                team_id INTEGER,
                win INTEGER,
                game_time TEXT,
                game_creation INTEGER,
                queue_id INTEGER,
                game_duration TEXT,
                mode_name TEXT,
                player_json TEXT,
                updated_at REAL NOT NULL DEFAULT (julianday('now')),
                PRIMARY KEY (game_id, subject_puuid, player_puuid)
            );
            CREATE INDEX IF NOT EXISTS idx_encounters_subject
                ON encounters(subject_puuid, player_puuid);
            CREATE INDEX IF NOT EXISTS idx_encounters_game
                ON encounters(game_id);
        """)
        self._conn.commit()
        c.close()

    def _drop_tables(self):
        c = self._conn.cursor()
        c.executescript(
            "DROP TABLE IF EXISTS games; "
            "DROP TABLE IF EXISTS game_details; "
            "DROP TABLE IF EXISTS verdicts; "
            "DROP TABLE IF EXISTS summoners; "
            "DROP TABLE IF EXISTS encounters;"
        )
        self._conn.commit()
        c.close()

    def _backfill_encounters(self, c: sqlite3.Cursor):
        """Populate the encounter index from match details cached by v1."""
        rows = c.execute("SELECT detail_json FROM game_details").fetchall()
        for row in rows:
            try:
                detail = json.loads(row["detail_json"])
            except (JSONDecodeError, TypeError):
                continue
            normalized = encounter_game_from_parsed(detail)
            if normalized:
                self._replace_encounters(c, normalized)

    @staticmethod
    def _replace_encounters(c: sqlite3.Cursor, game: dict):
        game_id = game.get("gameId")
        if game_id is None:
            return
        participants = game.get("participants") or []
        c.execute("DELETE FROM encounters WHERE game_id=?", (game_id,))
        rows = []
        for subject in participants:
            subject_puuid = subject.get("puuid")
            if not subject_puuid:
                continue
            for player in participants:
                player_puuid = player.get("puuid")
                if not player_puuid or player_puuid == subject_puuid:
                    continue
                relationship = (
                    "ally"
                    if subject.get("teamId") == player.get("teamId")
                    else "enemy"
                )
                rows.append((
                    game_id,
                    subject_puuid,
                    player_puuid,
                    relationship,
                    player.get("name", ""),
                    player.get("tagLine", ""),
                    player.get("teamId"),
                    1 if player.get("win") else 0,
                    game.get("gameTime", ""),
                    game.get("gameCreation", 0) or 0,
                    game.get("queueId"),
                    game.get("gameDuration", ""),
                    game.get("modeName", ""),
                    json.dumps(player, ensure_ascii=False),
                ))
        if rows:
            c.executemany("""
                INSERT OR REPLACE INTO encounters
                (game_id, subject_puuid, player_puuid, relationship,
                 player_name, tag_line, team_id, win, game_time,
                 game_creation, queue_id, game_duration, mode_name,
                 player_json, updated_at)
                VALUES (?,?,?,?, ?,?,?,?,?, ?,?,?,?,?,julianday('now'))
            """, rows)

    # ---- games (match history) ----

    def set_games(self, puuid: str, games: list) -> int:
        logger.debug("set_games puuid=%s n=%d" % (puuid, len(games)), TAG)
        count = 0
        with self._lock:
            conn = self._get_conn()
            c = conn.cursor()
            for g in games:
                c.execute("""
                    INSERT OR REPLACE INTO games
                    (game_id, puuid, queue_id, champion_id,
                     kills, deaths, assists, win, creation, duration,
                     champion_level, cs, gold, position, game_type, map_id,
                     remake, time_str, game_json, updated_at)
                    VALUES (?,?,?,?, ?,?,?,?,?,?, ?,?,?,?,?,?, ?,?,?,julianday('now'))
                """, (
                    g["gameId"], puuid, g.get("queueId"), g.get("championId"),
                    g.get("kills", 0), g.get("deaths", 0), g.get("assists", 0),
                    1 if g.get("win") else 0, g.get("timeStamp", 0), g.get("duration"),
                    g.get("champLevel", 0), g.get("cs", 0), g.get("gold", 0),
                    g.get("position"), g.get("name"), g.get("map"),
                    1 if g.get("remake") else 0, g.get("time"),
                    json.dumps(g, ensure_ascii=False),
                ))
                count += 1
            self._prune_games_for_puuid(c, puuid)
            conn.commit()
            c.close()
        return count

    def get_games(self, puuid: str, limit: int = 20, offset: int = 0) -> list:
        with self._lock:
            c = self._get_conn().cursor()
            rows = c.execute("""
                SELECT game_json FROM games
                WHERE puuid=?
                ORDER BY creation DESC
                LIMIT ? OFFSET ?
            """, (puuid, limit, offset)).fetchall()
            c.close()
        result = []
        for row in rows:
            try:
                result.append(json.loads(row["game_json"]))
            except (JSONDecodeError, TypeError):
                pass
        return result

    def _prune_games_for_puuid(self, c: sqlite3.Cursor, puuid: str):
        c.execute("""
            DELETE FROM games WHERE game_id IN (
                SELECT game_id FROM games WHERE puuid=?
                ORDER BY creation DESC
                LIMIT -1 OFFSET ?
            )
        """, (puuid, MAX_GAMES_PER_PUUID))

    # ---- game details ----

    def set_game_detail(self, game_id: int, detail: dict):
        logger.debug("set_game_detail gid=%s" % game_id, TAG)
        with self._lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("""
                INSERT OR REPLACE INTO game_details
                (game_id, detail_json, updated_at)
                VALUES (?,?,julianday('now'))
            """, (game_id, json.dumps(detail, ensure_ascii=False)))
            normalized = encounter_game_from_parsed(detail)
            if normalized:
                self._replace_encounters(c, normalized)
            self._prune_game_details(c)
            conn.commit()
            c.close()

    def get_game_detail(self, game_id: int) -> Optional[dict]:
        with self._lock:
            c = self._get_conn().cursor()
            row = c.execute(
                "SELECT detail_json FROM game_details WHERE game_id=?",
                (game_id,)
            ).fetchone()
            c.close()
        if row is None:
            return None
        try:
            result = json.loads(row["detail_json"])
            if result and "teams" in result:
                result["teams"] = {int(k): v for k, v in result["teams"].items()}
            return result
        except (JSONDecodeError, TypeError):
            return None

    def _prune_game_details(self, c: sqlite3.Cursor):
        c.execute("""
            DELETE FROM game_details WHERE game_id IN (
                SELECT game_id FROM game_details
                ORDER BY updated_at DESC
                LIMIT -1 OFFSET ?
            )
        """, (MAX_GAME_DETAILS,))

    # ---- encounters ----

    def set_encounters_from_raw_game(self, raw_game: dict) -> int:
        """Index every co-participant relationship in one LCU/SGP match."""
        normalized = encounter_game_from_raw(raw_game)
        if not normalized:
            return 0
        with self._lock:
            conn = self._get_conn()
            c = conn.cursor()
            self._replace_encounters(c, normalized)
            conn.commit()
            c.close()
        return len(normalized.get("participants") or [])

    def has_game_encounters(self, subject_puuid: str, game_id: int) -> bool:
        game_id = normalize_game_id(game_id)
        with self._lock:
            c = self._get_conn().cursor()
            row = c.execute("""
                SELECT 1 FROM encounters
                WHERE subject_puuid=? AND game_id=?
                LIMIT 1
            """, (subject_puuid, game_id)).fetchone()
            c.close()
        return row is not None

    def get_encounter_marks(self, subject_puuid: str, player_puuids: list,
                            exclude_game_id: int = None) -> dict:
        """Return previous-meeting counts for several players at once."""
        players = [
            puuid for puuid in dict.fromkeys(player_puuids or [])
            if puuid and puuid != subject_puuid
        ]
        if not subject_puuid or not players:
            return {}
        exclude_game_id = (
            normalize_game_id(exclude_game_id)
            if exclude_game_id is not None else None
        )

        placeholders = ",".join("?" for _ in players)
        params = [subject_puuid] + players
        exclude_sql = ""
        if exclude_game_id is not None:
            exclude_sql = " AND game_id<>?"
            params.append(exclude_game_id)
        query = f"""
            SELECT player_puuid, game_id, relationship, game_time,
                   game_creation, queue_id, mode_name
            FROM encounters
            WHERE subject_puuid=? AND player_puuid IN ({placeholders})
            {exclude_sql}
            ORDER BY game_creation DESC, game_id DESC
        """
        try:
            with self._lock:
                c = self._get_conn().cursor()
                rows = c.execute(query, params).fetchall()
                c.close()
        except sqlite3.Error as e:
            logger.warning(f"get_encounter_marks failed: {e}", TAG)
            return {}

        marks = {}
        for row in rows:
            player_puuid = row["player_puuid"]
            mark = marks.get(player_puuid)
            if mark is None:
                mark = {
                    "count": 0,
                    "lastGameId": row["game_id"],
                    "lastRelationship": row["relationship"],
                    "lastGameTime": row["game_time"],
                    "lastQueueId": row["queue_id"],
                    "lastModeName": row["mode_name"],
                }
                marks[player_puuid] = mark
            mark["count"] += 1
        return marks

    def get_encounter_history(self, subject_puuid: str, player_puuid: str,
                              exclude_game_id: int = None,
                              limit: int = 30) -> list:
        """Return the other player's performance in shared matches."""
        if not subject_puuid or not player_puuid:
            return []
        exclude_game_id = (
            normalize_game_id(exclude_game_id)
            if exclude_game_id is not None else None
        )
        params = [subject_puuid, player_puuid]
        exclude_sql = ""
        if exclude_game_id is not None:
            exclude_sql = " AND game_id<>?"
            params.append(exclude_game_id)
        params.append(max(1, int(limit)))
        try:
            with self._lock:
                c = self._get_conn().cursor()
                rows = c.execute(f"""
                    SELECT game_id, relationship, player_name, tag_line, win,
                           game_time, queue_id, game_duration, mode_name,
                           player_json
                    FROM encounters
                    WHERE subject_puuid=? AND player_puuid=?
                    {exclude_sql}
                    ORDER BY game_creation DESC, game_id DESC
                    LIMIT ?
                """, params).fetchall()
                c.close()
        except sqlite3.Error as e:
            logger.warning(f"get_encounter_history failed: {e}", TAG)
            return []

        result = []
        for row in rows:
            item = dict(row)
            try:
                item["player"] = json.loads(item.pop("player_json") or "{}")
            except (JSONDecodeError, TypeError):
                item["player"] = {}
            result.append(item)
        return result

    def get_encounter_players(self, subject_puuid: str,
                              limit: int = 200) -> list:
        """Return every player who shares an indexed game with the subject."""
        if not subject_puuid:
            return []
        try:
            with self._lock:
                c = self._get_conn().cursor()
                rows = c.execute("""
                    SELECT player_puuid, player_name, tag_line,
                           relationship, game_id, game_time, queue_id, mode_name
                    FROM encounters
                    WHERE subject_puuid=?
                    ORDER BY game_creation DESC, game_id DESC
                """, (subject_puuid,)).fetchall()
                c.close()
        except sqlite3.Error as e:
            logger.warning(f"get_encounter_players failed: {e}", TAG)
            return []

        players = {}
        for row in rows:
            player_uuid = row["player_puuid"]
            item = players.get(player_uuid)
            if item is None:
                item = {
                    "puuid": player_uuid,
                    "name": row["player_name"] or "未知玩家",
                    "tagLine": row["tag_line"] or "",
                    "count": 0,
                    "allyCount": 0,
                    "enemyCount": 0,
                    "lastGameId": row["game_id"],
                    "lastGameTime": row["game_time"],
                    "lastQueueId": row["queue_id"],
                    "lastModeName": row["mode_name"],
                    "lastRelationship": row["relationship"],
                }
                players[player_uuid] = item
            item["count"] += 1
            if row["relationship"] == "ally":
                item["allyCount"] += 1
            else:
                item["enemyCount"] += 1

        result = sorted(
            players.values(),
            key=lambda item: (
                item["count"], item["lastGameId"] or 0),
            reverse=True,
        )
        return result[:max(1, int(limit))]

    # ---- verdicts ----

    def set_verdict(self, game_id: int, winner_rating: list, loser_rating: list):
        logger.debug("set_verdict gid=%s" % game_id, TAG)
        with self._lock:
            self._get_conn().execute("""
                INSERT OR REPLACE INTO verdicts
                (game_id, winner_rating, loser_rating, updated_at)
                VALUES (?,?,?,julianday('now'))
            """, (game_id,
                  json.dumps(winner_rating, ensure_ascii=False),
                  json.dumps(loser_rating, ensure_ascii=False)))
            self._get_conn().commit()

    def get_verdict(self, game_id: int) -> Optional[dict]:
        with self._lock:
            c = self._get_conn().cursor()
            row = c.execute(
                "SELECT winner_rating, loser_rating FROM verdicts WHERE game_id=?",
                (game_id,)
            ).fetchone()
            c.close()
        if row is None:
            return None
        try:
            return {
                "gameId": game_id,
                "winnerRating": json.loads(row["winner_rating"]),
                "loserRating": json.loads(row["loser_rating"]),
            }
        except (JSONDecodeError, TypeError):
            return None

    # ---- summoners ----

    # ponytail: dead, no caller — connector.getSummonerByPuuid never writes through
    def set_summoner(self, puuid: str, name: str = "", tag_line: str = "",
                     profile_icon: str = "", level: int = 0):
        with self._lock:
            self._get_conn().execute("""
                INSERT OR REPLACE INTO summoners
                (puuid, game_name, tag_line, profile_icon, level, updated_at)
                VALUES (?,?,?,?,?,julianday('now'))
            """, (puuid, name, tag_line, profile_icon, level))
            self._get_conn().commit()

    # ponytail: dead, no caller — no LCU-offline summoner fallback yet
    def get_summoner(self, puuid: str) -> Optional[dict]:
        with self._lock:
            c = self._get_conn().cursor()
            row = c.execute(
                "SELECT * FROM summoners WHERE puuid=?", (puuid,)
            ).fetchone()
            c.close()
        if row is None:
            return None
        return dict(row)

    def clear_all(self):
        with self._lock:
            c = self._get_conn().cursor()
            c.execute("DELETE FROM games")
            c.execute("DELETE FROM game_details")
            c.execute("DELETE FROM verdicts")
            c.execute("DELETE FROM summoners")
            c.execute("DELETE FROM encounters")
            self._get_conn().commit()
            c.close()

    # ---- close ----
    # ponytail: dead, connector.close() only closes aiohttp sessions; SQLite conn leaks until process exit
    def close(self):
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None

    # ---- stats ----
    # ponytail: dead, stats never surfaced in UI
    def get_stats(self) -> dict:
        with self._lock:
            c = self._get_conn().cursor()
            games = c.execute("SELECT COUNT(*) as n FROM games").fetchone()["n"]
            details = c.execute("SELECT COUNT(*) as n FROM game_details").fetchone()["n"]
            verdicts = c.execute("SELECT COUNT(*) as n FROM verdicts").fetchone()["n"]
            encounters = c.execute(
                "SELECT COUNT(*) as n FROM encounters").fetchone()["n"]
            c.close()
        return {
            "games": games,
            "game_details": details,
            "verdicts": verdicts,
            "encounters": encounters,
        }


cache = PersistentCache()

# ponytail: global lock, per-connection locks if contention measured
# ponytail: no migration framework, schema_version bump rebuilds tables
