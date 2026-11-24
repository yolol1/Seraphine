from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout,
    QWidget,
)

from app.common.qfluentwidgets import (
    MessageBoxBase, TitleLabel, isDarkTheme,
)
from app.lol.persistent_cache import cache


class _EncounterGameRow(QFrame):
    selected = pyqtSignal(int)

    def __init__(self, item: dict, parent=None):
        super().__init__(parent)
        dark = isDarkTheme()
        self._game_id = item["game_id"]
        self.setObjectName("encounterGameRow")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(74)
        self.setStyleSheet(
            "QFrame#encounterGameRow {"
            "background: %s; border: 1px solid %s; border-radius: 8px;"
            "}"
            "QFrame#encounterGameRow:hover {"
            "background: %s; border-color: rgba(23,199,162,0.45);"
            "}" % (
                "rgba(255,255,255,0.035)" if dark else "rgba(0,0,0,0.025)",
                "rgba(255,255,255,0.07)" if dark else "rgba(0,0,0,0.07)",
                "rgba(23,199,162,0.10)" if dark else "rgba(23,199,162,0.07)",
            )
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(12)

        player = item.get("player") or {}
        relationship = "队友" if item.get("relationship") == "ally" else "对手"
        result = "胜利" if item.get("win") else "失败"
        result_color = "#5ECB83" if item.get("win") else "#E36C72"
        text_color = "#EEF3F7" if dark else "#202733"
        sub_color = "#9AA6B4" if dark else "#6F7885"

        mode = item.get("mode_name") or "未知模式"
        queue_id = item.get("queue_id")
        mode_text = f"{mode}  ·  {relationship}"
        if queue_id is not None:
            mode_text += f"  ·  队列 {queue_id}"

        info = QVBoxLayout()
        info.setSpacing(4)
        title = QLabel(mode_text)
        title.setStyleSheet(
            f"color: {text_color}; font: bold 12px 'Microsoft YaHei UI';")
        info.addWidget(title)

        when = item.get("game_time") or "时间未知"
        duration = item.get("game_duration") or "--:--"
        meta = QLabel(f"{when}  ·  {duration}")
        meta.setStyleSheet(
            f"color: {sub_color}; font: 11px 'Microsoft YaHei UI';")
        info.addWidget(meta)

        performance = QLabel(
            f"{player.get('kills', 0)}/{player.get('deaths', 0)}/"
            f"{player.get('assists', 0)}  ·  {player.get('cs', 0)} CS  ·  "
            f"{player.get('gold', 0):,} 金币  ·  "
            f"{player.get('damage', 0):,} 伤害"
        )
        performance.setStyleSheet(
            f"color: {sub_color}; font: 10px 'Microsoft YaHei UI';")
        info.addWidget(performance)
        layout.addLayout(info, 1)

        result_label = QLabel(result)
        result_label.setAlignment(Qt.AlignCenter)
        result_label.setFixedWidth(48)
        result_label.setStyleSheet(
            f"color: {result_color}; font: bold 12px 'Microsoft YaHei UI';")
        layout.addWidget(result_label)

        open_label = QLabel("查看对局  ›")
        open_label.setStyleSheet(
            "color: #19A98E; font: bold 11px 'Microsoft YaHei UI';")
        layout.addWidget(open_label)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.selected.emit(self._game_id)
        super().mouseReleaseEvent(event)


class _EncounterPlayerRow(QFrame):
    selected = pyqtSignal(str, str)

    def __init__(self, player: dict, parent=None):
        super().__init__(parent)
        dark = isDarkTheme()
        self._puuid = player["puuid"]
        self._name = player.get("name") or "未知玩家"
        self.setObjectName("encounterPlayerRow")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(66)
        self.setStyleSheet(
            "QFrame#encounterPlayerRow {"
            "background: %s; border: 1px solid %s; border-radius: 8px;"
            "}"
            "QFrame#encounterPlayerRow:hover {"
            "background: %s; border-color: rgba(23,199,162,0.45);"
            "}" % (
                "rgba(255,255,255,0.035)" if dark else "rgba(0,0,0,0.025)",
                "rgba(255,255,255,0.07)" if dark else "rgba(0,0,0,0.07)",
                "rgba(23,199,162,0.10)" if dark else "rgba(23,199,162,0.07)",
            )
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        text_color = "#EEF3F7" if dark else "#202733"
        sub_color = "#9AA6B4" if dark else "#6F7885"
        name = self._name
        if player.get("tagLine") and "#" not in name:
            name += f"#{player['tagLine']}"

        info = QVBoxLayout()
        info.setSpacing(4)
        name_label = QLabel(name)
        name_label.setStyleSheet(
            f"color: {text_color}; font: bold 12px 'Microsoft YaHei UI';")
        info.addWidget(name_label)

        last_time = player.get("lastGameTime") or "时间未知"
        relation = "队友" if player.get("lastRelationship") == "ally" else "对手"
        meta = QLabel(
            f"共 {player.get('count', 0)} 局  ·  "
            f"队友 {player.get('allyCount', 0)} / "
            f"对手 {player.get('enemyCount', 0)}  ·  "
            f"最近一次 {relation}  ·  {last_time}"
        )
        meta.setStyleSheet(
            f"color: {sub_color}; font: 10px 'Microsoft YaHei UI';")
        info.addWidget(meta)
        layout.addLayout(info, 1)

        open_label = QLabel("查看共同对局  ›")
        open_label.setStyleSheet(
            "color: #19A98E; font: bold 11px 'Microsoft YaHei UI';")
        layout.addWidget(open_label)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.selected.emit(self._puuid, self._name)
        super().mouseReleaseEvent(event)


class EncounterHistoryDialog(MessageBoxBase):
    """List shared matches and let the user jump to one of them."""

    def __init__(self, subject_puuid: str, player_puuid: str,
                 player_name: str = "", exclude_game_id: int = None,
                 parent=None):
        super().__init__(parent=parent)
        self.selectedGameId = None
        self.yesButton.setVisible(False)
        self.cancelButton.setVisible(False)

        close_button = QPushButton(self.tr("Close"))
        close_button.setObjectName("cancelButton")
        close_button.clicked.connect(self.accept)
        self.buttonLayout.addWidget(close_button)

        self.widget.setFixedWidth(680)
        self.widget.setFixedHeight(540)
        self.viewLayout.setContentsMargins(20, 18, 20, 12)
        self.viewLayout.setSpacing(10)

        title = TitleLabel(self.tr("共同对局"))
        self.viewLayout.addWidget(title)

        history = cache.get_encounter_history(
            subject_puuid, player_puuid, exclude_game_id=exclude_game_id)
        display_name = player_name or "该玩家"
        ally_count = sum(
            1 for item in history if item.get("relationship") == "ally")
        enemy_count = sum(
            1 for item in history if item.get("relationship") == "enemy")
        subtitle = QLabel(
            f"与 {display_name} 已记录 {len(history)} 场共同对局"
            f"（队友 {ally_count} / 对手 {enemy_count}），"
            "点击任意一场查看该玩家当时的表现。"
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(
            "color: #8B97A5; font: 11px 'Microsoft YaHei UI';")
        self.viewLayout.addWidget(subtitle)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 4, 0)
        content_layout.setSpacing(7)

        if history:
            for item in history:
                row = _EncounterGameRow(item)
                row.selected.connect(self._select_game)
                content_layout.addWidget(row)
        else:
            empty = QLabel(
                self.tr("No shared matches have been indexed yet."))
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet(
                "color: #8B97A5; padding: 40px; "
                "font: 12px 'Microsoft YaHei UI';")
            content_layout.addWidget(empty)

        content_layout.addStretch(1)
        scroll.setWidget(content)
        self.viewLayout.addWidget(scroll, 1)

    def _select_game(self, game_id: int):
        self.selectedGameId = int(game_id)
        self.accept()


class EncounterPlayersDialog(MessageBoxBase):
    """Show every indexed player met by the current summoner."""

    def __init__(self, subject_puuid: str, parent=None):
        super().__init__(parent=parent)
        self.selectedPlayerPuuid = None
        self.selectedPlayerName = ""
        self.yesButton.setVisible(False)
        self.cancelButton.setVisible(False)

        close_button = QPushButton(self.tr("Close"))
        close_button.setObjectName("cancelButton")
        close_button.clicked.connect(self.accept)
        self.buttonLayout.addWidget(close_button)

        self.widget.setFixedWidth(700)
        self.widget.setFixedHeight(560)
        self.viewLayout.setContentsMargins(20, 18, 20, 12)
        self.viewLayout.setSpacing(10)

        players = cache.get_encounter_players(subject_puuid)
        title = TitleLabel("相遇记录")
        self.viewLayout.addWidget(title)

        ally_total = sum(player["allyCount"] for player in players)
        enemy_total = sum(player["enemyCount"] for player in players)
        subtitle = QLabel(
            f"已记录 {len(players)} 名玩家、{ally_total + enemy_total} 次共同出场"
            f"（队友 {ally_total} / 对手 {enemy_total}）。"
            "点击玩家可查看具体共同对局。"
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(
            "color: #8B97A5; font: 11px 'Microsoft YaHei UI';")
        self.viewLayout.addWidget(subtitle)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }")
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 4, 0)
        content_layout.setSpacing(7)

        if players:
            for player in players:
                row = _EncounterPlayerRow(player)
                row.selected.connect(self._select_player)
                content_layout.addWidget(row)
        else:
            empty = QLabel(
                "暂未索引到共同对局。打开生涯页或具体对局详情后会自动建立记录。")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet(
                "color: #8B97A5; padding: 40px; "
                "font: 12px 'Microsoft YaHei UI';")
            content_layout.addWidget(empty)

        content_layout.addStretch(1)
        scroll.setWidget(content)
        self.viewLayout.addWidget(scroll, 1)

    def _select_player(self, puuid: str, name: str):
        self.selectedPlayerPuuid = puuid
        self.selectedPlayerName = name
        self.accept()
