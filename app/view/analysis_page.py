from typing import Optional

import asyncio
import math

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import (QPixmap, QPainter, QPainterPath, QColor, QFont,
                         QLinearGradient, QPen)
from PyQt5.QtWidgets import (QVBoxLayout, QHBoxLayout,
                             QLabel, QFrame, QWidget, QSizePolicy,
                             QSpacerItem, QPushButton)

from app.common.qfluentwidgets import (isDarkTheme, SmoothScrollArea)
from app.components.encounter_badge import makeEncounterBadge
from app.lol.connector import connector
from app.lol.persistent_cache import cache as sqlite_cache
from app.lol.war_criminal_cache import getVerdict
from app.lol.war_criminal_ui import METRIC_NAMES


# ── Design Tokens ──────────────────────────────────────────

_DARK_BG = '#07111D'
_PANEL_BG = '#101D2C'
_CARD_BG = '#162739'
_BLUE = '#2EA7FF'
_RED = '#E6525B'
_GOLD = '#F5C35B'
_TEXTP = '#FFFFFF'
_TEXTS = '#B0B8C4'
_BORDER = 'rgba(255,255,255,0.08)'

_SCORE_COLORS = [
    (1.0, _GOLD),   # z≥1.0 gold (grade 1)
    (0.3, _BLUE),   # z≥0.3 blue (grade 2)
    (-0.3, '#00D4AA'),  # z≥-0.3 cyan (grade 3)
    (-1.0, '#8B95A5'),  # z≥-1.0 grey (grade 4)
    (-999, _RED),   # z<-1.0 red (grade 5)
]

# ── Helpers ────────────────────────────────────────────────

def _mergeTeam(summoners: list, ratingList: list) -> list:
    byPuuid = {r.get('puuid'): r for r in (ratingList or [])}
    merged = []
    for s in summoners:
        puuid = s.get('puuid')
        rating = byPuuid.get(puuid, {})
        merged.append({
            'puuid': puuid,
            'participantId': s.get('participantId'),
            'summonerName': s.get('summonerName', '?'),
            'championIcon': s.get('championIcon', ''),
            'spell1Icon': s.get('spell1Icon', ''),
            'spell2Icon': s.get('spell2Icon', ''),
            'runeIcon': s.get('runeIcon', ''),
            'runeIds': s.get('runeIds', []),
            'runeNames': s.get('runeNames', []),
            'primaryStyle': s.get('primaryStyle', ''),
            'subStyle': s.get('subStyle', ''),
            'itemIcons': s.get('itemIcons', []),
            'itemIds': s.get('itemIds', []),
            'itemNames': s.get('itemNames', []),
            'kills': s.get('kills', 0), 'deaths': s.get('deaths', 0),
            'assists': s.get('assists', 0),
            'cs': s.get('cs', 0), 'gold': s.get('gold', 0),
            'goldSpent': s.get('goldSpent', 0),
            'champLevel': s.get('champLevel', 0),
            'tier': s.get('tier', ''), 'division': s.get('division', ''),
            'rankIcon': s.get('rankIcon', ''),
            'damage': s.get('damage', 0),
            'damageTaken': s.get('damageTaken', 0),
            'damageToTurrets': s.get('damageToTurrets', 0),
            'damageToObjectives': s.get('damageToObjectives', 0),
            'visionScore': s.get('visionScore', 0),
            'ccTime': s.get('ccTime', 0),
            'lane': s.get('lane', ''), 'role': s.get('role', ''),
            'score': rating.get('score', 0), 'grade': rating.get('grade', 3),
            'label': rating.get('label', ''),
            'evidence': rating.get('evidence', []),
        })
    merged.sort(key=lambda x: x['score'], reverse=True)
    return merged


def _isWin(winField) -> bool:
    if isinstance(winField, str):
        return winField.lower() in ('win', 'true')
    return bool(winField) if winField is not None else False


def _formatGold(gold: int) -> str:
    if gold >= 1000:
        return f"{gold/1000:.1f}k"
    return str(gold)


def _teamTotals(players: list) -> dict:
    return {
        'totalDamage': sum(p.get('damage', 0) for p in players),
        'totalGold': sum(p.get('gold', 0) for p in players),
        'totalKills': sum(p.get('kills', 0) for p in players),
    }


def _pct(val: float, total: float) -> str:
    if total <= 0:
        return '0%'
    return f"{val / total * 100:.0f}%"


def _scoreColor(score: float) -> str:
    for threshold, color in _SCORE_COLORS:
        if score >= threshold:
            return color
    return _RED


def _buildInsights(bluePlayers: list, redPlayers: list) -> list:
    allPlayers = [('蓝', p) for p in bluePlayers] + [('红', p) for p in redPlayers]
    items = []
    for team_label, p in allPlayers:
        for e in (p.get('evidence') or []):
            z = e.get('zScore', 0)
            metric = METRIC_NAMES.get(e.get('metric', ''), e.get('metric', ''))
            items.append((abs(z), team_label, p['summonerName'], metric, z))
    items.sort(key=lambda x: x[0], reverse=True)
    insights = []
    seen = set()
    for _, team_label, name, metric, z in items:
        if len(insights) >= 4:
            break
        key = (name, metric)
        if key in seen:
            continue
        seen.add(key)
        if z >= 1.5:
            insights.append(f"🟢 {name}({team_label}) {metric} z={z:+.1f}")
        elif z <= -1.5:
            insights.append(f"🔴 {name}({team_label}) {metric} z={z:+.1f}")
    return insights


def _teamRadarVals(players: list, pool: list = None) -> list:
    metrics = ['damage', 'damage_taken', 'gold', 'cc', 'vision', 'kill_participation']
    stat_keys = ['damage', 'damageTaken', 'gold', 'ccTime', 'visionScore', None]

    pool = pool or players
    result = []
    for m, key in zip(metrics, stat_keys):
        if m == 'kill_participation':
            total = sum(p.get('kills', 0) for p in pool)
            vals = [((p.get('kills', 0) or 0) + (p.get('assists', 0) or 0)) / max(total, 1) for p in pool]
        else:
            vals = [p.get(key, 0) or 0 for p in pool]
        mean = sum(vals) / max(len(vals), 1)
        variance = sum((v - mean) ** 2 for v in vals) / max(len(vals), 1) if len(vals) > 1 else 0
        std = math.sqrt(variance) if variance > 0 else 1

        team_vals = []
        for p in players:
            if m == 'kill_participation':
                total = sum(pp.get('kills', 0) for pp in pool)
                v = ((p.get('kills', 0) or 0) + (p.get('assists', 0) or 0)) / max(total, 1)
            else:
                v = p.get(key, 0) or 0
            team_vals.append(v)

        avg_z = sum((v - mean) / std for v in team_vals) / max(len(team_vals), 1)
        result.append((math.tanh(avg_z / 2.5) + 1) / 2)
    return result


_TEAM_RADAR_LABELS = ['输出', '承伤', '经济', '控制', '视野', '参团']

# ── Tab Utilities ──────────────────────────────────────────

_TAB_NAMES = ['总览', '数据', '经济', '符文', '装备', '时间线']

def _tabStyle(dark: bool, active: bool) -> str:
    font = "'Segoe UI', 'Microsoft YaHei'"
    color = '#2EA7FF' if active else ('#8B95A5' if dark else '#888')
    bg = 'rgba(46, 167, 255, 0.12)' if (active and dark) else \
         'rgba(46, 167, 255, 0.10)' if active else 'transparent'
    return (
        f"font-family: {font}; font-size: 12px; font-weight: bold; "
        f"color: {color}; background: {bg}; "
        f"border-radius: 4px; padding: 2px 10px;")


def _smallIcon(path: str, size: int = 18) -> QLabel:
    """Create a small icon QLabel from an image path."""
    lbl = QLabel()
    lbl.setFixedSize(size, size)
    if path:
        p = QPixmap(path)
        if not p.isNull():
            lbl.setPixmap(p.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
    lbl.setStyleSheet("border-radius: 2px;")
    return lbl


def _formatNumber(value) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "--"


def _formatTimestamp(timestampMs) -> str:
    try:
        seconds = max(0, int(timestampMs) // 1000)
    except (TypeError, ValueError):
        return "--:--"
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _asInt(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _teamParticipantIds(gameData: dict, teamId: int) -> set:
    teams = (gameData or {}).get('teams') or {}
    team = teams.get(teamId) or teams.get(str(teamId)) or {}
    ids = {
        _asInt(player.get('participantId'))
        for player in (team.get('summoners') or [])
        if _asInt(player.get('participantId')) > 0
    }
    return ids


def _economySeries(timeline: dict, gameData: dict) -> list:
    """Build cumulative team-gold samples from match-v5 timeline frames.

    Each sample totals participantFrames.totalGold for team 100 and team 200.
    currentGold is intentionally ignored because it only reflects unspent gold.
    """
    if not isinstance(timeline, dict):
        return []

    frames = timeline.get('frames') or []
    if not isinstance(frames, list) or not frames:
        return []

    blueIds = _teamParticipantIds(gameData, 100)
    redIds = _teamParticipantIds(gameData, 200)

    if not blueIds or not redIds:
        frameIds = set()
        for frame in frames:
            participantFrames = frame.get('participantFrames') or {}
            if isinstance(participantFrames, dict):
                frameIds.update(
                    _asInt(participantId)
                    for participantId in participantFrames
                    if _asInt(participantId) > 0
                )
        if not blueIds:
            blueIds = {participantId for participantId in frameIds
                       if participantId <= 5}
        if not redIds:
            redIds = {participantId for participantId in frameIds
                      if participantId > 5}

    if not blueIds and not redIds:
        return []

    samples = []
    for frame in frames:
        participantFrames = frame.get('participantFrames') or {}
        if not isinstance(participantFrames, dict) or not participantFrames:
            continue

        byParticipant = {
            _asInt(participantId): participant
            for participantId, participant in participantFrames.items()
            if isinstance(participant, dict)
        }

        def teamGold(ids):
            return sum(
                max(0, _asInt((byParticipant.get(participantId) or {})
                              .get('totalGold')))
                for participantId in ids
            )

        blueGold = teamGold(blueIds)
        redGold = teamGold(redIds)
        if blueGold == 0 and redGold == 0:
            continue

        timestamp = max(0, _asInt(frame.get('timestamp')))
        samples.append({
            'timestamp': timestamp,
            'blue': blueGold,
            'red': redGold,
            'diff': blueGold - redGold,
        })

    samples.sort(key=lambda sample: sample['timestamp'])
    return samples


def _timelineEvents(timeline: dict, gameData: dict) -> list:
    """Convert raw match-v5 timeline frames into readable analysis events."""
    if not isinstance(timeline, dict):
        return []

    monsterNames = {
        'DRAGON': '小龙',
        'RIFTHERALD': '峡谷先锋',
        'BARON_NASHOR': '纳什男爵',
        'HORDE': '虚空巢虫',
    }
    monsterSubtypeNames = {
        'FIRE_DRAGON': '火龙',
        'WATER_DRAGON': '水龙',
        'EARTH_DRAGON': '土龙',
        'AIR_DRAGON': '风龙',
        'HEXTECH_DRAGON': '海克斯龙',
        'CHEMTECH_DRAGON': '炼金龙',
        'ELDER_DRAGON': '远古龙',
    }
    buildingNames = {
        'TOWER_BUILDING': '防御塔',
        'INHIBITOR_BUILDING': '水晶',
    }
    laneNames = {
        'TOP_LANE': '上路',
        'MID_LANE': '中路',
        'BOT_LANE': '下路',
    }

    participantNames = {}
    for team in (gameData.get('teams') or {}).values():
        for player in (team or {}).get('summoners', []) or []:
            participantId = player.get('participantId')
            if participantId:
                participantNames[int(participantId)] = player.get(
                    'summonerName') or f"P{participantId}"

    def name(participantId):
        return participantNames.get(int(participantId or 0), "未知玩家")

    def teamName(teamId):
        return "蓝队" if int(teamId or 100) == 100 else "红队"

    result = []
    for frame in timeline.get('frames', []) or []:
        timestamp = frame.get('timestamp', 0)
        for event in frame.get('events', []) or []:
            eventType = event.get('type')
            text = ""
            accent = _TEXTS
            if eventType == 'CHAMPION_KILL':
                killer = name(event.get('killerId'))
                victim = name(event.get('victimId'))
                assists = [name(pid) for pid in event.get('assistingParticipantIds', [])]
                text = f"{killer} 击杀 {victim}"
                if assists:
                    text += "，助攻：" + "、".join(assists)
                accent = _GOLD
            elif eventType == 'ELITE_MONSTER_KILL':
                monsterType = event.get('monsterType')
                monster = monsterNames.get(monsterType, monsterType or "大型野怪")
                subtype = event.get('monsterSubType')
                if subtype:
                    monster += f" · {monsterSubtypeNames.get(subtype, subtype)}"
                text = f"{teamName(event.get('killerTeamId'))} 击杀 {monster}"
                accent = '#00D4AA'
            elif eventType == 'BUILDING_KILL':
                buildingType = event.get('buildingType')
                building = buildingNames.get(
                    buildingType, buildingType or "建筑")
                lane = event.get('laneType')
                if lane:
                    building += f" · {laneNames.get(lane, lane)}"
                text = f"{teamName(event.get('teamId'))}的{building}被摧毁"
                accent = _BLUE
            elif eventType == 'GAME_END':
                text = f"比赛结束，{teamName(event.get('winningTeam'))}获胜"
                accent = _GOLD

            if text:
                result.append({
                    'time': _formatTimestamp(timestamp),
                    'text': text,
                    'accent': accent,
                })
    return result


def _statLabel(text, width=None, color=None, bold=False):
    dark = isDarkTheme()
    label = QLabel(str(text))
    if width is not None:
        label.setFixedWidth(width)
    label.setAlignment(Qt.AlignCenter)
    label.setStyleSheet(
        f"color: {color or (_TEXTP if dark else '#222')};"
        f"font: {'bold ' if bold else ''}12px 'Microsoft YaHei UI', 'Segoe UI';"
        "background: transparent;")
    return label


class AnalysisStatTable(QFrame):
    """Compact comparison table used by Data and Economy tabs."""

    def __init__(self, title: str, groups: list, columns: list,
                 subtitle: str = "", parent=None):
        super().__init__(parent)
        dark = isDarkTheme()
        panel = _PANEL_BG if dark else '#F0F2F5'
        border = _BORDER if dark else 'rgba(0,0,0,0.08)'
        self.setStyleSheet(
            f"AnalysisStatTable {{ background: {panel}; "
            f"border: 1px solid {border}; border-radius: 10px; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(6)

        titleLabel = QLabel(title)
        titleLabel.setStyleSheet(
            f"color: {_TEXTP if dark else '#222'}; background: transparent;"
            "font: bold 17px 'Microsoft YaHei UI', 'Segoe UI';")
        layout.addWidget(titleLabel)
        if subtitle:
            subtitleLabel = QLabel(subtitle)
            subtitleLabel.setStyleSheet(
                f"color: {_TEXTS if dark else '#777'}; background: transparent;"
                "font: 12px 'Microsoft YaHei UI', 'Segoe UI';")
            layout.addWidget(subtitleLabel)

        header = QFrame()
        headerLayout = QHBoxLayout(header)
        headerLayout.setContentsMargins(8, 0, 8, 4)
        headerLayout.setSpacing(4)
        playerHeader = _statLabel("玩家", color=_TEXTS, bold=True)
        playerHeader.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        headerLayout.addWidget(playerHeader, 1)
        for name, width, _ in columns:
            headerLayout.addWidget(
                _statLabel(name, width, _TEXTS, bold=True))
        layout.addWidget(header)

        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet(
            f"background: {border}; border: none;")
        layout.addWidget(divider)

        for groupName, players, accent in groups:
            groupLabel = QLabel(
                f"{groupName}  ·  {sum(p.get('gold', 0) for p in players):,} 金币")
            groupLabel.setStyleSheet(
                f"color: {accent}; background: transparent; padding: 5px 4px 2px 4px;"
                "font: bold 12px 'Microsoft YaHei UI', 'Segoe UI';")
            layout.addWidget(groupLabel)

            for index, player in enumerate(players):
                row = QFrame()
                rowBg = (
                    'rgba(255,255,255,0.035)' if dark and index % 2 == 0
                    else 'rgba(0,0,0,0.025)' if not dark and index % 2 == 0
                    else 'transparent')
                row.setStyleSheet(
                    f"QFrame {{ background: {rowBg}; border-radius: 6px; }}")
                rowLayout = QHBoxLayout(row)
                rowLayout.setContentsMargins(8, 3, 8, 3)
                rowLayout.setSpacing(4)

                playerWidget = QWidget()
                playerLayout = QHBoxLayout(playerWidget)
                playerLayout.setContentsMargins(0, 0, 0, 0)
                playerLayout.setSpacing(6)
                iconLabel = QLabel()
                iconLabel.setFixedSize(24, 24)
                pixmap = QPixmap(player.get('championIcon', ''))
                if not pixmap.isNull():
                    iconLabel.setPixmap(pixmap.scaled(
                        24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                playerLayout.addWidget(iconLabel)
                nameLabel = QLabel(player.get('summonerName', '?'))
                nameLabel.setStyleSheet(
                    f"color: {_TEXTP if dark else '#222'}; background: transparent;"
                    "font: bold 12px 'Microsoft YaHei UI', 'Segoe UI';")
                playerLayout.addWidget(nameLabel)
                encounter_badge = makeEncounterBadge(
                    player, player.get("encounterSubjectPuuid"))
                if encounter_badge:
                    playerLayout.addWidget(encounter_badge)
                playerLayout.addStretch(1)
                rowLayout.addWidget(playerWidget, 1)

                teamKills = sum(p.get('kills', 0) for p in players)
                for _, width, renderer in columns:
                    cell = renderer(player, teamKills)
                    if isinstance(cell, str):
                        cell = _statLabel(cell, width)
                    else:
                        cell.setFixedWidth(width)
                    rowLayout.addWidget(cell)
                layout.addWidget(row)


class TimelineEventsView(QFrame):
    def __init__(self, events: list, status: str = "", parent=None):
        super().__init__(parent)
        dark = isDarkTheme()
        panel = _PANEL_BG if dark else '#F0F2F5'
        border = _BORDER if dark else 'rgba(0,0,0,0.08)'
        self.setStyleSheet(
            f"TimelineEventsView {{ background: {panel}; "
            f"border: 1px solid {border}; border-radius: 10px; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(6)
        title = QLabel("对局时间线")
        title.setStyleSheet(
            f"color: {_TEXTP if dark else '#222'}; background: transparent;"
            "font: bold 17px 'Microsoft YaHei UI', 'Segoe UI';")
        layout.addWidget(title)

        if status:
            statusLabel = QLabel(status)
            statusLabel.setWordWrap(True)
            statusLabel.setStyleSheet(
                f"color: {_TEXTS if dark else '#777'}; background: transparent;"
                "font: 12px 'Microsoft YaHei UI', 'Segoe UI'; padding: 8px 0;")
            layout.addWidget(statusLabel)

        for event in events:
            row = QFrame()
            row.setStyleSheet(
                f"QFrame {{ background: {'rgba(255,255,255,0.03)' if dark else 'rgba(0,0,0,0.025)'};"
                "border-radius: 6px; }}")
            rowLayout = QHBoxLayout(row)
            rowLayout.setContentsMargins(8, 4, 8, 4)
            rowLayout.setSpacing(10)
            timeLabel = QLabel(event['time'])
            timeLabel.setFixedWidth(48)
            timeLabel.setStyleSheet(
                f"color: {_TEXTS if dark else '#777'}; background: transparent;"
                "font: bold 12px Consolas, monospace;")
            textLabel = QLabel(event['text'])
            textLabel.setStyleSheet(
                f"color: {event['accent'] if dark else '#31566f'};"
                "background: transparent; font: 12px 'Microsoft YaHei UI';")
            rowLayout.addWidget(timeLabel)
            rowLayout.addWidget(textLabel, 1)
            layout.addWidget(row)

        layout.addStretch(1)

# ── HexagonScore ───────────────────────────────────────────

class HexagonScore(QWidget):
    """Compact score badge: colored hexagon with score number in center."""
    def __init__(self, score: float, size=76, parent=None):
        super().__init__(parent)
        self._score = score
        self._color_str = _scoreColor(score)
        self._color = QColor(self._color_str)
        self.setFixedSize(size, size)
        self._size = size

    def paintEvent(self, event):
        _renderBuf(self, self._draw)

    def _draw(self, p, w, h):
        r = self._size / 2 - 2
        cx, cy = w / 2, h / 2
        n = 6

        path = QPainterPath()
        for i in range(n + 1):
            angle = -math.pi / 2 + i * 2 * math.pi / n
            x = cx + r * math.cos(angle)
            y = cy + r * math.sin(angle)
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)

        p.setBrush(self._color)
        p.setPen(Qt.NoPen)
        p.drawPath(path)

        inner = QPainterPath()
        ir = r * 0.7
        for i in range(n + 1):
            angle = -math.pi / 2 + i * 2 * math.pi / n
            x = cx + ir * math.cos(angle)
            y = cy + ir * math.sin(angle)
            if i == 0:
                inner.moveTo(x, y)
            else:
                inner.lineTo(x, y)
        bg = QColor(self._color_str)
        bg.setAlpha(40)
        p.setBrush(bg)
        p.drawPath(inner)

        p.setFont(QFont('Consolas', int(self._size / 4.5), QFont.Bold))
        p.setPen(QColor('#FFFFFF'))
        text = f"{self._score:.1f}"
        fm = p.fontMetrics()
        tw = fm.horizontalAdvance(text)
        th = fm.height()
        p.drawText(int(cx - tw / 2), int(cy + th / 4), text)


# ── PlayerCard ─────────────────────────────────────────────

class PlayerCard(QFrame):
    """Player card with spells, rune, items, and score hexagon."""
    def __init__(self, data: dict, teamTotals: dict, parent=None):
        super().__init__(parent)
        dark = isDarkTheme()
        font = "'Segoe UI', 'Microsoft YaHei'"
        bg = _CARD_BG if dark else '#E8ECF0'
        border = _BORDER if dark else 'rgba(0,0,0,0.08)'
        self.setStyleSheet(f"""
            PlayerCard {{
                background: {bg}; border: 1px solid {border};
                border-radius: 8px;
            }}
        """)

        hl = QHBoxLayout(self)
        hl.setContentsMargins(6, 4, 6, 4)
        hl.setSpacing(6)

        # ── Champion icon + level + spells + rune ──
        iconCol = QVBoxLayout()
        iconCol.setSpacing(2)
        iconCol.setAlignment(Qt.AlignCenter)

        # Champion icon with level overlay
        iconC = QWidget()
        iconC.setFixedSize(48, 48)
        ci = QLabel(iconC)
        ci.setFixedSize(48, 48)
        ci.move(0, 0)
        champ_icon = data.get('championIcon', '')
        pix = QPixmap(champ_icon) if champ_icon else QPixmap()
        if not pix.isNull():
            ci.setPixmap(pix.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        ci.setStyleSheet("border-radius: 4px;")

        lv = QLabel(str(data.get('champLevel', 1)))
        lv.setFixedSize(18, 15)
        lv.move(0, 33)
        lv.setAlignment(Qt.AlignCenter)
        lv.setStyleSheet(
            "background: rgba(0,0,0,0.75); color: #fff;"
            "font-size: 9px; font-weight: bold; border-radius: 2px;")
        iconCol.addWidget(iconC)

        # Spell + rune row
        srRow = QHBoxLayout()
        srRow.setSpacing(2)
        srRow.setAlignment(Qt.AlignCenter)

        srRow.addWidget(_smallIcon(data.get('spell1Icon', '')))
        srRow.addWidget(_smallIcon(data.get('spell2Icon', '')))
        srRow.addWidget(_smallIcon(data.get('runeIcon', '')))
        iconCol.addLayout(srRow)

        hl.addLayout(iconCol)

        # ── Middle info column ──
        vi = QVBoxLayout()
        vi.setSpacing(1)

        # Name
        nameLabel = QLabel(data.get('summonerName', '?'))
        nl_color = _TEXTP if dark else '#222'
        nameLabel.setStyleSheet(
            f"font-family: {font}; font-size: 11px; font-weight: bold; "
            f"color: {nl_color}; background: transparent;")
        name_row = QHBoxLayout()
        name_row.setContentsMargins(0, 0, 0, 0)
        name_row.setSpacing(5)
        name_row.addWidget(nameLabel)
        encounter_badge = makeEncounterBadge(
            data, data.get("encounterSubjectPuuid"))
        if encounter_badge:
            name_row.addWidget(encounter_badge)
        name_row.addStretch(1)
        vi.addLayout(name_row)

        # KDA + CS + Gold
        k = data.get('kills', 0)
        d = data.get('deaths', 0)
        a = data.get('assists', 0)
        cs = data.get('cs', 0)
        gold = _formatGold(data.get('gold', 0))
        stats_color = _TEXTS if dark else '#777'
        stats = QLabel(f"{k}/{d}/{a}  {cs}CS  {gold}")
        stats.setStyleSheet(
            f"font-family: {font}; font-size: 10px; color: {stats_color}; background: transparent;")
        vi.addWidget(stats)

        # Damage%, Gold%, KP%, Vision
        dmg = _pct(data.get('damage', 0), teamTotals.get('totalDamage', 0))
        gld = _pct(data.get('gold', 0), teamTotals.get('totalGold', 0))
        kp_val = None
        for e in (data.get('evidence') or []):
            if e.get('metric') == 'kill_participation':
                kp_val = f"{e.get('value', 0)*100:.0f}%" if e.get('value') is not None else None
        vis = data.get('visionScore', 0)
        subs = f"{dmg}  {gld}  {kp_val or '--'}  {int(vis)}"
        pct_color = '#8899aa' if dark else '#888'
        pctLabel = QLabel(subs)
        pctLabel.setStyleSheet(
            f"font-family: {font}; font-size: 9px; color: {pct_color}; background: transparent;")
        vi.addWidget(pctLabel)

        # Items row
        items = data.get('itemIcons', [])
        itemsRow = QHBoxLayout()
        itemsRow.setSpacing(2)
        itemsRow.setAlignment(Qt.AlignLeft)
        for itemPath in items[:7]:
            il = QLabel()
            il.setFixedSize(20, 20)
            if itemPath:
                p = QPixmap(itemPath)
                if not p.isNull():
                    il.setPixmap(p.scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            il.setStyleSheet("border-radius: 2px; background: rgba(0,0,0,0.2);")
            itemsRow.addWidget(il)
        vi.addLayout(itemsRow)

        hl.addLayout(vi, 1)

        # ── HexagonScore ──
        score = data.get('score', 0)
        hs = HexagonScore(score, size=76)
        hl.addWidget(hs)


# ── TeamRadar (Compare Center) ─────────────────────────────

class TeamRadar(QWidget):
    def __init__(self, blueVals: list, redVals: list, parent=None):
        super().__init__(parent)
        self._blueVals = blueVals
        self._redVals = redVals
        self._n = len(blueVals)
        self.setFixedSize(172, 180)

    def paintEvent(self, event):
        _renderBuf(self, self._draw)

    def _draw(self, p, w, h):
        n = self._n
        r = min(w, h) / 2 - 24
        cx, cy = w / 2, h / 2

        for ring in (0.25, 0.5, 0.75):
            path = QPainterPath()
            for i in range(n + 1):
                angle = -math.pi / 2 + i * 2 * math.pi / n
                x = cx + r * ring * math.cos(angle)
                y = cy + r * ring * math.sin(angle)
                if i == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            p.setBrush(QColor('#1A2D44'))
            p.setPen(QPen(QColor('rgba(255,255,255,0.15)'), 0.5))
            p.drawPath(path)

        for i in range(n):
            angle = -math.pi / 2 + i * 2 * math.pi / n
            x = cx + r * math.cos(angle)
            y = cy + r * math.sin(angle)
            p.setPen(QPen(QColor('rgba(255,255,255,0.12)'), 0.5))
            p.drawLine(int(cx), int(cy), int(x), int(y))

            label_x = cx + (r + 14) * math.cos(angle)
            label_y = cy + (r + 14) * math.sin(angle)
            p.setPen(QColor('#A0AAB8'))
            p.setFont(QFont('Segoe UI', 8))
            fm = p.fontMetrics()
            text = _TEAM_RADAR_LABELS[i]
            tw = fm.horizontalAdvance(text)
            p.drawText(int(label_x - tw / 2), int(label_y + 3), text)

        hasData = any(v != 0.5 for v in self._blueVals) or any(v != 0.5 for v in self._redVals)

        def _drawTeam(vals, color):
            path = QPainterPath()
            for i in range(n + 1):
                angle = -math.pi / 2 + i * 2 * math.pi / n
                v = vals[i % n]
                x = cx + r * v * math.cos(angle)
                y = cy + r * v * math.sin(angle)
                if i == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            c = QColor(color)
            c.setAlpha(200)
            fill = QColor(color)
            fill.setAlpha(100)
            p.setBrush(fill)
            p.setPen(QPen(c, 2.5))
            p.drawPath(path)

        if hasData:
            _drawTeam(self._blueVals, _BLUE)
            _drawTeam(self._redVals, _RED)

        p.setPen(QColor('#8B95A5'))
        p.setFont(QFont('Segoe UI', 9))
        p.drawText(4, 14, "● 蓝队")
        p.drawText(w - 50, 14, "● 红队")

        if not hasData:
            p.setPen(QColor('#5A6A7A'))
            p.setFont(QFont('Segoe UI', 10))
            p.drawText(int(cx - 45), int(cy + 4), "暂无评级数据")


# ── Insights Summary ───────────────────────────────────────

class InsightsSummary(QFrame):
    def __init__(self, insights: list, parent=None):
        super().__init__(parent)
        dark = isDarkTheme()
        font = "'Segoe UI', 'Microsoft YaHei'"
        bg = _CARD_BG if dark else '#E8ECF0'
        self.setStyleSheet(f"background: {bg}; border: none; border-radius: 8px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(3)

        for ins in (insights or []):
            row = QLabel(ins)
            row.setStyleSheet(
                f"font-family: {font}; font-size: 10px; color: {'#ccc' if dark else '#444'};"
                f"background: transparent;")
            layout.addWidget(row)

        if not insights:
            empty = QLabel("暂无突出数据")
            empty.setStyleSheet(
                f"font-family: {font}; font-size: 10px; color: {'#666' if dark else '#aaa'};"
                f"background: transparent;")
            layout.addWidget(empty)


# ── CenterCompare ──────────────────────────────────────────

class CenterCompare(QFrame):
    def __init__(self, bluePlayers: list, redPlayers: list,
                 blueWin: bool, blueTeam: Optional[dict] = None,
                 redTeam: Optional[dict] = None, parent=None):
        super().__init__(parent)
        dark = isDarkTheme()
        font = "'Segoe UI', 'Microsoft YaHei'"
        bg = _PANEL_BG if dark else '#F0F2F5'
        border = _BORDER if dark else 'rgba(0,0,0,0.08)'
        self.setStyleSheet(f"""
            CenterCompare {{
                background: {bg}; border: 1px solid {border};
                border-radius: 8px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignCenter)

        blueScore = sum(p['score'] for p in bluePlayers) / max(len(bluePlayers), 1)
        redScore = sum(p['score'] for p in redPlayers) / max(len(redPlayers), 1)

        scoreLabel = QLabel(f"{blueScore:+.1f}  vs  {redScore:+.1f}")
        sc = _BLUE if blueScore >= redScore else _RED
        scoreLabel.setAlignment(Qt.AlignCenter)
        scoreLabel.setStyleSheet(
            f"font-family: {font}; font-size: 14px; font-weight: bold; "
            f"color: {sc}; background: transparent;")
        layout.addWidget(scoreLabel)

        pool = bluePlayers + redPlayers
        blueVals = _teamRadarVals(bluePlayers, pool=pool)
        redVals = _teamRadarVals(redPlayers, pool=pool)
        layout.addWidget(TeamRadar(blueVals, redVals), 0, Qt.AlignCenter)

        bKills = sum(p['kills'] for p in bluePlayers)
        rKills = sum(p['kills'] for p in redPlayers)
        bGold = sum(p['gold'] for p in bluePlayers)
        rGold = sum(p['gold'] for p in redPlayers)
        ts_color = _TEXTS if dark else '#777'
        statsText = QLabel(
            f"击杀: {bKills} vs {rKills}    经济: {_formatGold(bGold)} vs {_formatGold(rGold)}")
        statsText.setAlignment(Qt.AlignCenter)
        statsText.setStyleSheet(
            f"font-family: {font}; font-size: 10px; color: {ts_color}; background: transparent;")
        layout.addWidget(statsText)

        # ── Resource Control ──
        bt = blueTeam or {}
        rt = redTeam or {}
        resources = [
            ('🔫 防御塔', bt.get('towerKills', 0), rt.get('towerKills', 0)),
            ('🐉 巨龙', bt.get('dragonKills', 0), rt.get('dragonKills', 0)),
            ('👹 先锋', bt.get('riftHeraldKills', 0), rt.get('riftHeraldKills', 0)),
            ('🐛 虚空虫', bt.get('hordeKills', 0), rt.get('hordeKills', 0)),
            ('👑 男爵', bt.get('baronKills', 0), rt.get('baronKills', 0)),
            ('🏛️ 水晶', bt.get('inhibitorKills', 0), rt.get('inhibitorKills', 0)),
        ]
        resLabel = QLabel('  '.join(
            f"{name} {b}/{r}" for name, b, r in resources if b or r))
        hasResources = any(b or r for _, b, r in resources)
        if not hasResources:
            resLabel.hide()
        resLabel.setWordWrap(True)
        resLabel.setAlignment(Qt.AlignCenter)
        rl_color = _TEXTS if dark else '#777'
        resLabel.setStyleSheet(
            f"font-family: {font}; font-size: 9px; color: {rl_color}; background: transparent;")
        layout.addWidget(resLabel)

        insights = _buildInsights(bluePlayers, redPlayers)
        if insights:
            layout.addWidget(InsightsSummary(insights))

        layout.addSpacerItem(QSpacerItem(1, 1, QSizePolicy.Minimum, QSizePolicy.Expanding))


# ── TeamPanel ──────────────────────────────────────────────

class TeamPanel(QFrame):
    def __init__(self, teamName: str, players: list, isWin: bool,
                 teamTotals: dict, parent=None):
        super().__init__(parent)
        dark = isDarkTheme()
        bg = _PANEL_BG if dark else '#F0F2F5'
        border = _BORDER if dark else 'rgba(0,0,0,0.08)'
        self.setStyleSheet(f"""
            TeamPanel {{
                background: {bg}; border: 1px solid {border};
                border-radius: 8px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        font = "'Segoe UI', 'Microsoft YaHei'"
        hColor = _BLUE if isWin else _RED
        avgScore = sum(p['score'] for p in players) / max(len(players), 1)
        header = QLabel(f"{teamName}  {avgScore:+.1f}")
        header.setStyleSheet(
            f"font-family: {font}; font-size: 12px; font-weight: bold; "
            f"color: {hColor}; background: transparent;")
        layout.addWidget(header)

        for p in players:
            layout.addWidget(PlayerCard(p, teamTotals))

        layout.addSpacerItem(QSpacerItem(1, 1, QSizePolicy.Minimum, QSizePolicy.Expanding))


# ── Bottom Chart Widgets ────────────────────────────────────

def _renderBuf(widget, drawFn):
    """Render widget content to offscreen QPixmap to avoid QPainter
    conflict with QGraphicsEffect applied by SmoothScrollArea."""
    w, h = widget.width(), widget.height()
    if w < 10 or h < 10:
        return
    buf = QPixmap(w, h)
    buf.fill(Qt.transparent)
    p = QPainter(buf)
    p.setRenderHint(QPainter.Antialiasing)
    try:
        drawFn(p, w, h)
    finally:
        p.end()
    p2 = QPainter(widget)
    p2.drawPixmap(0, 0, buf)
    p2.end()


def _chartToggleStyle(dark: bool, checked: bool) -> str:
    color = _BLUE if checked else (_TEXTS if dark else '#666')
    bg = 'rgba(46,167,255,0.16)' if checked else (
        'rgba(255,255,255,0.04)' if dark else 'rgba(0,0,0,0.035)')
    border = 'rgba(46,167,255,0.55)' if checked else (
        'rgba(255,255,255,0.10)' if dark else 'rgba(0,0,0,0.10)')
    return (
        f"QPushButton {{ color: {color}; background: {bg}; "
        f"border: 1px solid {border}; border-radius: 5px; "
        "padding: 4px 12px; font: bold 11px 'Microsoft YaHei UI'; }"
    )


class EconomyChart(QWidget):
    """Cumulative team gold chart with total and differential views."""

    def __init__(self, series: list, mode: str = "total", parent=None):
        super().__init__(parent)
        self._series = series or []
        self._mode = mode
        self._hoverIndex = -1
        self._plotRect = (0, 0, 0, 0)
        self.setMouseTracking(True)
        self.setMinimumHeight(300)
        self.setFixedHeight(300)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def setMode(self, mode: str):
        if mode not in ("total", "diff") or mode == self._mode:
            return
        self._mode = mode
        self._hoverIndex = -1
        self.update()

    def _range(self):
        if self._mode == "diff":
            maximum = max(
                (abs(sample.get('diff', 0)) for sample in self._series),
                default=1,
            )
            maximum = max(maximum * 1.12, 1000)
            return -maximum, maximum

        maximum = max(
            (max(sample.get('blue', 0), sample.get('red', 0))
             for sample in self._series),
            default=1,
        )
        return 0, max(maximum * 1.08, 1000)

    def _nearestIndex(self, x: float) -> int:
        if not self._series:
            return -1
        left, _, width, _ = self._plotRect
        if width <= 0:
            return -1
        start = 0
        end = max(self._series[-1]['timestamp'], 1)
        target = start + (x - left) / width * (end - start)
        return min(
            range(len(self._series)),
            key=lambda index: abs(self._series[index]['timestamp'] - target),
        )

    def mouseMoveEvent(self, event):
        left, top, width, height = self._plotRect
        if (
            width > 0
            and height > 0
            and left <= event.pos().x() <= left + width
            and top <= event.pos().y() <= top + height
        ):
            index = self._nearestIndex(event.pos().x())
            if index != self._hoverIndex:
                self._hoverIndex = index
                self.update()
        elif self._hoverIndex >= 0:
            self._hoverIndex = -1
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._hoverIndex = -1
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        _renderBuf(self, self._draw)

    def _draw(self, p, w, h):
        dark = isDarkTheme()
        text = _TEXTP if dark else '#25303B'
        muted = _TEXTS if dark else '#707B86'
        grid = QColor('#FFFFFF')
        grid.setAlpha(24 if dark else 20)
        panel = QColor('#FFFFFF')
        panel.setAlpha(8 if dark else 14)

        left, right = 64, 20
        top, bottom = 38, 34
        plotWidth = max(1, w - left - right)
        plotHeight = max(1, h - top - bottom)
        plotRight = left + plotWidth
        plotBottom = top + plotHeight
        self._plotRect = (left, top, plotWidth, plotHeight)

        p.fillRect(left, top, plotWidth, plotHeight, panel)
        p.setFont(QFont('Microsoft YaHei UI', 9))

        lower, upper = self._range()
        span = max(upper - lower, 1)
        startMs = 0
        endMs = max(
            self._series[-1]['timestamp'] if self._series else 1,
            1,
        )

        def mapX(timestamp):
            return left + (timestamp - startMs) / (endMs - startMs) * plotWidth

        def mapY(value):
            return top + (upper - value) / span * plotHeight

        for step in range(5):
            y = top + plotHeight * step / 4
            p.setPen(QPen(grid, 1))
            p.drawLine(left, int(y), plotRight, int(y))
            value = upper - span * step / 4
            suffix = "k" if abs(value) >= 1000 else ""
            labelValue = value / 1000 if suffix else value
            label = f"{labelValue:.1f}{suffix}" if suffix else f"{int(value)}"
            p.setPen(QColor(muted))
            p.drawText(4, int(y + 4), label)

        for step in range(5):
            x = left + plotWidth * step / 4
            p.setPen(QPen(grid, 1))
            p.drawLine(int(x), top, int(x), plotBottom)
            timestamp = startMs + (endMs - startMs) * step / 4
            label = _formatTimestamp(timestamp)
            labelWidth = p.fontMetrics().horizontalAdvance(label)
            p.setPen(QColor(muted))
            p.drawText(
                int(min(max(x - labelWidth / 2, left),
                        plotRight - labelWidth)),
                plotBottom + 20,
                label,
            )

        if not self._series:
            p.setPen(QColor(muted))
            p.setFont(QFont('Microsoft YaHei UI', 11))
            message = "暂无经济时间线"
            messageWidth = p.fontMetrics().horizontalAdvance(message)
            p.drawText(
                int(left + (plotWidth - messageWidth) / 2),
                int(top + plotHeight / 2),
                message,
            )
            return

        if self._mode == "total":
            self._drawTotal(p, left, top, plotWidth, plotHeight,
                            mapX, mapY, dark)
        else:
            self._drawDifference(p, left, top, plotWidth, plotHeight,
                                 mapX, mapY)

        if 0 <= self._hoverIndex < len(self._series):
            self._drawHover(p, left, top, plotWidth, plotHeight,
                            mapX, mapY, dark, text)

    def _seriesPath(self, key, mapX, mapY):
        path = QPainterPath()
        for index, sample in enumerate(self._series):
            pointX = mapX(sample['timestamp'])
            pointY = mapY(sample[key])
            if index == 0:
                path.moveTo(pointX, pointY)
            else:
                path.lineTo(pointX, pointY)
        return path

    def _drawTotal(self, p, left, top, width, height, mapX, mapY, dark):
        baseline = top + height

        for key, color, label in (
            ('blue', _BLUE, '蓝队'),
            ('red', _RED, '红队'),
        ):
            path = self._seriesPath(key, mapX, mapY)
            area = QPainterPath(path)
            area.lineTo(mapX(self._series[-1]['timestamp']), baseline)
            area.lineTo(mapX(self._series[0]['timestamp']), baseline)
            area.closeSubpath()

            gradient = QLinearGradient(0, top, 0, baseline)
            fill = QColor(color)
            fill.setAlpha(80 if dark else 55)
            transparent = QColor(color)
            transparent.setAlpha(4)
            gradient.setColorAt(0, fill)
            gradient.setColorAt(1, transparent)
            p.fillPath(area, gradient)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(color), 2.4))
            p.drawPath(path)

        legendX = left + 8
        p.setFont(QFont('Microsoft YaHei UI', 9, QFont.Bold))
        for label, color, offset in (
            ('蓝队', _BLUE, 0),
            ('红队', _RED, 60),
        ):
            p.setPen(QColor(color))
            p.drawText(legendX + offset, 22, f"● {label}")

    def _drawDifference(self, p, left, top, width, height, mapX, mapY):
        zeroY = mapY(0)
        p.setPen(QPen(QColor('#8B95A5'), 1, Qt.DashLine))
        p.drawLine(left, int(zeroY), left + width, int(zeroY))

        points = [
            (mapX(sample['timestamp']), mapY(sample['diff']))
            for sample in self._series
        ]
        for (x1, y1), (x2, y2), sample in zip(
            points, points[1:], self._series[1:]
        ):
            color = _BLUE if sample['diff'] >= 0 else _RED
            p.setPen(QPen(QColor(color), 2.6))
            p.drawLine(int(x1), int(y1), int(x2), int(y2))
        if len(points) == 1:
            p.setBrush(QColor(_BLUE))
            p.setPen(Qt.NoPen)
            p.drawEllipse(int(points[0][0] - 3), int(points[0][1] - 3), 6, 6)

        p.setFont(QFont('Microsoft YaHei UI', 9, QFont.Bold))
        p.setPen(QColor(_BLUE))
        p.drawText(left + 8, 22, "▲ 蓝方领先")
        p.setPen(QColor(_RED))
        p.drawText(left + 118, 22, "▼ 红方领先")

    def _drawHover(self, p, left, top, width, height, mapX, mapY,
                   dark, text):
        sample = self._series[self._hoverIndex]
        x = mapX(sample['timestamp'])
        p.setPen(QPen(QColor('#FFFFFF' if dark else '#5C6975'),
                      1, Qt.DashLine))
        p.drawLine(int(x), top, int(x), top + height)

        for key, color in (('blue', _BLUE), ('red', _RED)):
            if self._mode == 'diff' and key != 'blue':
                continue
            valueKey = 'diff' if self._mode == 'diff' else key
            y = mapY(sample[valueKey])
            if self._mode == 'diff':
                color = _BLUE if sample['diff'] >= 0 else _RED
            p.setBrush(QColor(color))
            p.setPen(QPen(QColor('#FFFFFF' if dark else '#F7F9FB'), 1.5))
            p.drawEllipse(int(x - 4), int(y - 4), 8, 8)

        blueText = f"蓝队 {_formatNumber(sample['blue'])}"
        redText = f"红队 {_formatNumber(sample['red'])}"
        diff = sample['diff']
        diffText = f"经济差 {'+' if diff >= 0 else ''}{_formatNumber(diff)}"
        lines = [_formatTimestamp(sample['timestamp']), blueText, redText, diffText]

        boxWidth = 152
        boxHeight = 82
        boxX = int(x + 12)
        if boxX + boxWidth > left + width:
            boxX = int(x - boxWidth - 12)
        boxY = top + 10

        bg = QColor('#132235' if dark else '#FFFFFF')
        bg.setAlpha(245 if dark else 235)
        p.setBrush(bg)
        p.setPen(QPen(QColor('#FFFFFF' if dark else '#B8C2CC'), 1))
        p.drawRoundedRect(boxX, boxY, boxWidth, boxHeight, 7, 7)

        p.setFont(QFont('Microsoft YaHei UI', 9))
        for index, line in enumerate(lines):
            if index == 0:
                p.setPen(QColor(_TEXTS if dark else '#6F7A85'))
            elif index == 1:
                p.setPen(QColor(_BLUE))
            elif index == 2:
                p.setPen(QColor(_RED))
            else:
                p.setPen(QColor(text))
            p.drawText(boxX + 10, boxY + 18 + index * 17, line)


class EconomyChartPanel(QFrame):
    def __init__(self, series: list, status: str = "", parent=None):
        super().__init__(parent)
        self._dark = isDarkTheme()
        bg = _PANEL_BG if self._dark else '#F0F2F5'
        border = _BORDER if self._dark else 'rgba(0,0,0,0.08)'
        self.setStyleSheet(
            f"EconomyChartPanel {{ background: {bg}; "
            f"border: 1px solid {border}; border-radius: 10px; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 10)
        layout.setSpacing(5)

        header = QHBoxLayout()
        header.setSpacing(8)
        title = QLabel("经济走势")
        title.setStyleSheet(
            f"color: {_TEXTP if self._dark else '#222'}; background: transparent;"
            "font: bold 17px 'Microsoft YaHei UI', 'Segoe UI';")
        header.addWidget(title)
        header.addStretch(1)

        self.totalButton = QPushButton("总经济")
        self.diffButton = QPushButton("经济差")
        for button in (self.totalButton, self.diffButton):
            button.setCursor(Qt.PointingHandCursor)
            button.setFixedHeight(27)
            header.addWidget(button)
        layout.addLayout(header)

        note = status or "每帧汇总双方累计总经济；悬停曲线可查看具体数值"
        self.noteLabel = QLabel(note)
        self.noteLabel.setWordWrap(True)
        self.noteLabel.setStyleSheet(
            f"color: {_TEXTS if self._dark else '#777'}; background: transparent;"
            "font: 11px 'Microsoft YaHei UI', 'Segoe UI';")
        layout.addWidget(self.noteLabel)

        self.chart = EconomyChart(series, mode="total", parent=self)
        layout.addWidget(self.chart)

        self.totalButton.clicked.connect(lambda: self._setMode("total"))
        self.diffButton.clicked.connect(lambda: self._setMode("diff"))
        self._setMode("total")

    def _setMode(self, mode: str):
        self.chart.setMode(mode)
        self.totalButton.setStyleSheet(
            _chartToggleStyle(self._dark, mode == "total"))
        self.diffButton.setStyleSheet(
            _chartToggleStyle(self._dark, mode == "diff"))


# ── AnalysisPage ───────────────────────────────────────────

class AnalysisPage(QFrame):
    backRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._game = None
        self._teamContainer = None
        self._bluePlayers = []
        self._redPlayers = []
        self._blueTeam = {}
        self._redTeam = {}
        self._timelineLoading = False
        self._timelineStatus = ""
        self._activeTab = 0
        self._tabLabels = []
        font = "'Segoe UI', 'Microsoft YaHei'"
        dark = isDarkTheme()

        self.setStyleSheet(f"AnalysisPage {{ background: {_DARK_BG if dark else '#E8ECF0'}; }}")

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        # ── Header ──
        self.headerWidget = QWidget()
        self.headerWidget.setFixedHeight(80)
        hb = _PANEL_BG if dark else '#FFFFFF'
        hborder = _BORDER if dark else 'rgba(0,0,0,0.08)'
        self.headerWidget.setStyleSheet(
            f"background: {hb}; border-bottom: 1px solid {hborder};")

        headerRow = QHBoxLayout(self.headerWidget)
        headerRow.setContentsMargins(16, 6, 16, 6)
        headerRow.setSpacing(12)

        # Back button
        self.backBtn = QLabel("←  赛后复盘")
        self.backBtn.setCursor(Qt.PointingHandCursor)
        self.backBtn.setStyleSheet(
            f"font-family: {font}; font-size: 15px; font-weight: bold; "
            f"color: {_BLUE}; background: transparent;")
        headerRow.addWidget(self.backBtn)

        # Tab bar
        tabBar = QHBoxLayout()
        tabBar.setSpacing(2)
        tabBar.setAlignment(Qt.AlignCenter)
        for i, name in enumerate(_TAB_NAMES):
            tab = QLabel(name)
            tab.setCursor(Qt.PointingHandCursor)
            tab.setFixedHeight(28)
            tab.setAlignment(Qt.AlignCenter)
            tab.setStyleSheet(_tabStyle(dark, i == 0))
            tab.mousePressEvent = lambda e, idx=i: self._switchTab(idx)
            tabBar.addWidget(tab)
            self._tabLabels.append(tab)
        headerRow.addLayout(tabBar, 1)

        # Game info
        self.infoLabel = QLabel("")
        ic = _TEXTS if dark else '#888'
        self.infoLabel.setStyleSheet(
            f"font-family: {font}; font-size: 13px; color: {ic}; background: transparent;")
        headerRow.addWidget(self.infoLabel)

        self._layout.addWidget(self.headerWidget)

        self.scrollArea = SmoothScrollArea()
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }")
        self.contentWidget = QWidget()
        self.contentWidget.setStyleSheet("background: transparent;")
        self.contentLayout = QVBoxLayout(self.contentWidget)
        self.contentLayout.setContentsMargins(0, 0, 0, 0)
        self.contentLayout.setSpacing(0)
        self.scrollArea.setWidget(self.contentWidget)
        self._layout.addWidget(self.scrollArea, 1)

        self.backBtn.mousePressEvent = lambda e: self.backRequested.emit()

    def _switchTab(self, idx: int):
        if idx == self._activeTab:
            return
        if self._game is None:
            return
        self._setActiveTab(idx)
        self._renderTab(idx)

    def _setActiveTab(self, idx: int):
        dark = isDarkTheme()
        for i, tab in enumerate(self._tabLabels):
            tab.setStyleSheet(_tabStyle(dark, i == idx))
        self._activeTab = idx

    def _clearTabContent(self):
        while self.contentLayout.count():
            item = self.contentLayout.takeAt(0)
            if item.widget():
                widget = item.widget()
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        self._teamContainer = None

    def _addTabShell(self, widget):
        shell = QWidget()
        layout = QVBoxLayout(shell)
        layout.setContentsMargins(12, 8, 12, 10)
        layout.setSpacing(8)
        layout.addWidget(widget)
        layout.addStretch(1)
        self.contentLayout.addWidget(shell)

    def _renderTab(self, idx: int):
        self._clearTabContent()
        if idx == 0:
            self._buildOverview()
        elif idx == 1:
            self._addTabShell(self._buildDataTab())
        elif idx == 2:
            self._addTabShell(self._buildEconomyTab())
        elif idx == 3:
            self._addTabShell(self._buildRuneTab())
        elif idx == 4:
            self._addTabShell(self._buildItemTab())
        elif idx == 5:
            self._buildTimelineTab()

    def loadGame(self, gameData: dict, preserveTab: bool = False,
                 subjectPuuid: str = None):
        activeTab = self._activeTab if preserveTab else 0
        self._game = gameData
        self._subjectPuuid = subjectPuuid
        self._timelineLoading = False
        self._timelineStatus = ""

        gameId = gameData.get('gameId')
        verdict = getVerdict(gameId) if gameId else None
        winnerRating = (verdict or {}).get('winnerRating') or []
        loserRating = (verdict or {}).get('loserRating') or []

        teams = gameData.get('teams', {})
        team100 = teams.get(100) or teams.get('100') or {}
        team200 = teams.get(200) or teams.get('200') or {}

        win100 = _isWin(team100.get('win'))
        winTeam = team100 if win100 else team200
        loseTeam = team200 if win100 else team100
        self._bluePlayers = _mergeTeam(
            team100.get('summoners', []),
            winnerRating if win100 else loserRating)
        self._redPlayers = _mergeTeam(
            team200.get('summoners', []),
            loserRating if win100 else winnerRating)
        self._blueTeam = team100
        self._redTeam = team200

        # Legacy cached data may not have both explicit team dictionaries.
        if not self._bluePlayers:
            self._bluePlayers = _mergeTeam(
                winTeam.get('summoners', []), winnerRating)
        if not self._redPlayers:
            self._redPlayers = _mergeTeam(
                loseTeam.get('summoners', []), loserRating)

        if subjectPuuid:
            player_puuids = [
                player.get("puuid")
                for player in self._bluePlayers + self._redPlayers
            ]
            marks = sqlite_cache.get_encounter_marks(
                subjectPuuid, player_puuids,
                exclude_game_id=gameData.get("gameId"))
            for player in self._bluePlayers + self._redPlayers:
                player["encounterInfo"] = marks.get(
                    player.get("puuid"), {})
                player["encounterSubjectPuuid"] = subjectPuuid

        modeName = gameData.get('modeName', '')
        mapName = gameData.get('mapName', '')
        duration = gameData.get('gameDuration', '')
        self.infoLabel.setText(f"{mapName}  ·  {modeName}  ·  {duration}")
        activeTab = min(max(activeTab, 0), len(_TAB_NAMES) - 1)
        self._setActiveTab(activeTab)
        self._renderTab(activeTab)

    def _buildOverview(self):
        bluePlayers = self._bluePlayers
        redPlayers = self._redPlayers
        team100 = self._blueTeam
        team200 = self._redTeam
        win100 = _isWin(team100.get('win'))
        self._teamContainer = QWidget()
        cl = QVBoxLayout(self._teamContainer)
        cl.setContentsMargins(12, 8, 12, 8)
        cl.setSpacing(0)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.setContentsMargins(0, 0, 0, 0)

        blueTotals = _teamTotals(bluePlayers)
        redTotals = _teamTotals(redPlayers)

        row.addWidget(TeamPanel(
            "蓝队",
            bluePlayers, win100, blueTotals), 8)

        row.addWidget(CenterCompare(
            bluePlayers, redPlayers, win100,
            blueTeam=team100, redTeam=team200), 9)

        row.addWidget(TeamPanel(
            "红队",
            redPlayers, not win100, redTotals), 8)

        cl.addLayout(row, 1)

        self.contentLayout.addWidget(self._teamContainer)

    def _buildDataTab(self):
        columns = [
            ("K/D/A", 72, lambda p, _: (
                f"{p.get('kills', 0)}/{p.get('deaths', 0)}/"
                f"{p.get('assists', 0)}")),
            ("伤害", 82, lambda p, _: _formatNumber(p.get('damage', 0))),
            ("承伤", 82, lambda p, _: _formatNumber(p.get('damageTaken', 0))),
            ("补刀", 64, lambda p, _: _formatNumber(p.get('cs', 0))),
            ("视野", 64, lambda p, _: _formatNumber(p.get('visionScore', 0))),
            ("参团", 64, lambda p, teamKills: (
                f"{(p.get('kills', 0) + p.get('assists', 0)) / max(teamKills, 1) * 100:.0f}%")),
        ]
        return AnalysisStatTable(
            "数据总览",
            [("蓝队", self._bluePlayers, _BLUE),
             ("红队", self._redPlayers, _RED)],
            columns,
            "伤害为对英雄伤害，参团率按队伍总击杀计算")

    def _buildEconomyTab(self):
        timeline = self._game.get('timeline') if self._game else None
        series = _economySeries(timeline, self._game or {})
        if self._timelineLoading:
            chartStatus = "正在从 SGP 获取对局时间线…"
        elif self._timelineStatus:
            chartStatus = self._timelineStatus
        elif series:
            chartStatus = "每帧汇总双方累计总经济；悬停曲线可查看具体数值"
        else:
            chartStatus = "该对局暂未包含经济时间线，正在尝试获取…"

        columns = [
            ("获得金币", 92, lambda p, _: _formatNumber(p.get('gold', 0))),
            ("花费金币", 92, lambda p, _: _formatNumber(p.get('goldSpent', 0))),
            ("补刀", 64, lambda p, _: _formatNumber(p.get('cs', 0))),
            ("对塔伤害", 92, lambda p, _: _formatNumber(p.get('damageToTurrets', 0))),
            ("目标伤害", 92, lambda p, _: _formatNumber(p.get('damageToObjectives', 0))),
        ]
        blueGold = sum(p.get('gold', 0) for p in self._bluePlayers)
        redGold = sum(p.get('gold', 0) for p in self._redPlayers)
        table = AnalysisStatTable(
            "经济与资源",
            [("蓝队", self._bluePlayers, _BLUE),
             ("红队", self._redPlayers, _RED)],
            columns,
            f"团队获得金币：蓝队 {_formatNumber(blueGold)} · "
            f"红队 {_formatNumber(redGold)}")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(EconomyChartPanel(series, chartStatus))
        layout.addWidget(table)

        if not timeline and not self._timelineLoading:
            self._timelineLoading = True
            asyncio.ensure_future(self._loadTimeline())
        return container

    def _buildRuneTab(self):
        dark = isDarkTheme()

        def runeNamesCell(player, _):
            names = [n for n in (player.get('runeNames') or []) if n]
            text = " · ".join(names) if names else "本局未提供符文明细"
            label = QLabel(text)
            label.setToolTip("\n".join(names) if names else text)
            label.setStyleSheet(
                f"color: {_TEXTS if dark else '#555'}; background: transparent;"
                "font: 11px 'Microsoft YaHei UI', 'Segoe UI';")
            return label

        columns = [
            ("主系", 112, lambda p, _: p.get('primaryStyle') or "--"),
            ("副系", 112, lambda p, _: p.get('subStyle') or "--"),
            ("符文", 430, runeNamesCell),
        ]
        return AnalysisStatTable(
            "符文配置",
            [("蓝队", self._bluePlayers, _BLUE),
             ("红队", self._redPlayers, _RED)],
            columns,
            "悬停符文列可查看完整名称；旧缓存可能不含符文详情")

    def _buildItemTab(self):
        def itemCell(player, _):
            widget = QWidget()
            layout = QHBoxLayout(widget)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(3)
            paths = player.get('itemIcons') or []
            names = player.get('itemNames') or []
            for index, path in enumerate(paths[:7]):
                label = QLabel()
                label.setFixedSize(22, 22)
                pixmap = QPixmap(path) if path else QPixmap()
                if not pixmap.isNull():
                    label.setPixmap(pixmap.scaled(
                        22, 22, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                name = names[index] if index < len(names) else ""
                label.setToolTip(name or "装备图标")
                label.setStyleSheet("border-radius: 3px;")
                layout.addWidget(label)
            layout.addStretch(1)
            return widget

        columns = [("最终装备", 360, itemCell)]
        return AnalysisStatTable(
            "装备记录",
            [("蓝队", self._bluePlayers, _BLUE),
             ("红队", self._redPlayers, _RED)],
            columns,
            "显示对局结束时的装备；新拉取的对局可悬停查看装备名称")

    def _buildTimelineTab(self):
        timeline = self._game.get('timeline') if self._game else None
        events = _timelineEvents(timeline, self._game or {})
        if events:
            status = f"共 {len(events)} 个关键事件"
        elif self._timelineLoading:
            status = "正在从 SGP 获取对局时间线…"
        elif self._timelineStatus:
            status = self._timelineStatus
        else:
            status = "该对局暂未包含时间线，正在尝试获取…"
        self._addTabShell(TimelineEventsView(events, status))
        if not timeline and not self._timelineLoading:
            self._timelineLoading = True
            asyncio.ensure_future(self._loadTimeline())

    async def _loadTimeline(self):
        gameId = self._game.get('gameId') if self._game else None
        try:
            timeline = await connector.getGameTimelineViaSgpQuietly(gameId)
        except Exception:
            timeline = None
        if not self._game or self._game.get('gameId') != gameId:
            return
        self._timelineLoading = False
        if timeline:
            self._game['timeline'] = timeline
            self._timelineStatus = ""
        else:
            self._timelineStatus = (
                "无法获取时间线：LCU 对局详情不包含回放事件，"
                "且当前 SGP 服务未返回该局的 DETAILS 数据。")
        if self._activeTab in (2, 5):
            self._renderTab(self._activeTab)
