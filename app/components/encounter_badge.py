from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QLabel

from app.common.qfluentwidgets import isDarkTheme
from app.common.signals import signalBus


class EncounterBadge(QLabel):
    """Compact, clickable marker for a previously met player."""

    clicked = pyqtSignal()

    def __init__(self, count: int, relationship: str = "", parent=None):
        super().__init__(parent)
        self.count = max(0, int(count or 0))
        text = f"遇过 {self.count} 次"
        self.setText(text)
        self.setCursor(Qt.PointingHandCursor)
        self.setAlignment(Qt.AlignCenter)
        self.setFixedHeight(20)
        self.setMinimumWidth(62)
        self.setAttribute(Qt.WA_StyledBackground, True)

        relation_text = (
            "最近一次是队友" if relationship == "ally"
            else "最近一次是对手" if relationship == "enemy"
            else "曾与当前召唤师同场"
        )
        self.setToolTip(
            f"与当前召唤师在另外 {self.count} 局同场，{relation_text}\n"
            "点击查看共同对局"
        )

        dark = isDarkTheme()
        color = "#8FE7D5" if dark else "#087B68"
        background = (
            "rgba(23, 199, 162, 0.16)"
            if dark else "rgba(11, 150, 122, 0.10)"
        )
        border = (
            "rgba(111, 224, 197, 0.36)"
            if dark else "rgba(8, 123, 104, 0.24)"
        )
        self.setStyleSheet(
            "QLabel {"
            f"color: {color}; background: {background};"
            f"border: 1px solid {border}; border-radius: 9px;"
            "padding: 0 6px; font: bold 10px 'Microsoft YaHei UI';"
            "}"
            "QLabel:hover {"
            "background: rgba(23, 199, 162, 0.24);"
            "}"
        )

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


def makeEncounterBadge(player: dict, subject_puuid: str):
    """Create a badge bound to this player's shared-match history."""
    if not subject_puuid:
        return None
    info = player.get("encounterInfo") or {}
    count = int(info.get("count", 0) or 0)
    player_puuid = player.get("puuid")
    if count <= 0 or not player_puuid or player_puuid == subject_puuid:
        return None

    badge = EncounterBadge(count, info.get("lastRelationship", ""))
    player_name = (
        player.get("summonerName") or player.get("name") or "未知玩家")
    tag_line = player.get("tagLine")
    if tag_line and "#" not in str(player_name):
        player_name = f"{player_name}#{tag_line}"
    badge.clicked.connect(
        lambda: signalBus.encounterHistoryRequested.emit(
            subject_puuid, player_puuid, player_name)
    )
    return badge
