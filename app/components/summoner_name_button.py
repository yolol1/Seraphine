from PyQt5.QtWidgets import QLabel, QSizePolicy
from PyQt5.QtCore import Qt, pyqtSignal
from ..common.qfluentwidgets import ToolTipPosition, ToolTipFilter


class SummonerName(QLabel):
    clicked = pyqtSignal(bool)

    def __init__(self, text, isPublic=True, color=None, tagLine=None, tips="", parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self._displayName = text if isPublic else f"{text}🔒"
        self.tagLine = tagLine
        self._tips = tips

        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(False)
        # Long Riot IDs must not change the width of an entire game-history
        # column. Elide them to the available width and keep the full name in
        # the tooltip / search callback.
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setProperty('pressed', False)
        if color:
            self.setStyleSheet(f"color: {color}")

        self.installEventFilter(ToolTipFilter(self, 0, ToolTipPosition.BOTTOM))
        self._refresh_display_text()
        self._refresh_tooltip()

    def _full_search_name(self) -> str:
        name = self._displayName.replace("🔒", "")
        if self.tagLine:
            name += f"#{self.tagLine}"
        return name

    def _refresh_display_text(self):
        available = max(0, self.contentsRect().width() - 12)
        text = self._displayName
        if available and self.fontMetrics().horizontalAdvance(text) > available:
            text = self.fontMetrics().elidedText(
                text, Qt.ElideRight, available)
        QLabel.setText(self, text)
        self._refresh_tooltip()

    def _refresh_tooltip(self):
        parts = [self._full_search_name()]
        if self._tips:
            parts.append(str(self._tips))
        self.setToolTip("\n".join(parts))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh_display_text()

    def text(self) -> str:
        return self._full_search_name()

    def mousePressEvent(self, ev) -> None:
        self.setProperty('pressed', True)
        self.style().polish(self)

        return super().mousePressEvent(ev)

    def mouseReleaseEvent(self, a0) -> None:
        self.setProperty("pressed", False)
        self.style().polish(self)

        self.clicked.emit(True)

        return super().mouseReleaseEvent(a0)
