
from PyQt5.QtWidgets import (QHBoxLayout, QWidget, QLabel, QFrame,
                             QVBoxLayout, QSpacerItem, QSizePolicy)
from PyQt5.QtCore import Qt, pyqtSignal, QEasingCurve
from qasync import asyncSlot

from app.components.animation_frame import ColorAnimationFrame
from app.components.champion_icon_widget import RoundIcon, RoundedLabel
from app.common.signals import signalBus
from app.common.style_sheet import StyleSheet
from app.common.qfluentwidgets import (
    BodyLabel, SmoothScrollArea, FlowLayout, isDarkTheme, qconfig,
    themeColor)


class TierInterface(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.vBoxLayout = QVBoxLayout(self)
        self.tierList = TierListWidget()

        self.__initWidget()
        self.__initLayout()

        StyleSheet.OPGG_TIER_INTERFACE.apply(self)

    def __initWidget(self):
        pass

    def __initLayout(self):
        self.vBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.vBoxLayout.addWidget(self.tierList)


class TierListWidget(QFrame):
    def __init__(self, parent=None):
        '''
        英雄梯队列表组件

        观前警告：
            为了实现该死的上下对齐，该类实现中含有大量魔法数字
            请自备降压药
        '''

        super().__init__(parent)

        self.vBoxLayout = QVBoxLayout(self)

        self.titleBar = ListTitleBar()

        self.scrollArea = SmoothScrollArea()
        self.scrollWidget = QFrame()
        self.scrollLayout = FlowLayout(needAni=True, isTight=True)

        self.allChampionShowing = True

        self.items: list[ListItem] = []

        self.__initWidget()
        self.__initLayout()

    def __initWidget(self):
        self.scrollArea.setObjectName("scrollArea")
        self.scrollWidget.setObjectName("scrollWidget")

        self.titleBar.sortRequested.connect(self.__onSortRequested)

    def __initLayout(self):
        self.scrollLayout.setContentsMargins(0, 0, 0, 0)
        self.scrollLayout.setAlignment(Qt.AlignTop)
        self.scrollLayout.setVerticalSpacing(3)
        self.scrollLayout.setAnimation(450, QEasingCurve.Type.OutQuart)
        self.scrollWidget.setLayout(self.scrollLayout)
        self.scrollArea.setWidget(self.scrollWidget)
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setViewportMargins(6, 6, 17, 6)

        self.vBoxLayout.setSpacing(0)
        self.vBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.vBoxLayout.setAlignment(Qt.AlignTop)
        self.vBoxLayout.addWidget(self.titleBar)
        self.vBoxLayout.addWidget(self.scrollArea)

    def updateList(self, data: list):
        if len(self.items) != 0:
            self.scrollLayout.takeAllWidgets()

        self.scrollArea.delegate.vScrollBar.resetValue(0)
        self.scrollArea.verticalScrollBar().setSliderPosition(0)

        self.items = [ListItem(0, x) for x in data]
        self.__update()
        self.titleBar.resetSelected()

    def __update(self):
        self.scrollLayout.removeAllWidgets()

        for i, x in enumerate(self.items, start=1):
            x.setCounter(i)
            self.scrollLayout.addWidget(x)

    @asyncSlot(str)
    async def __onSortRequested(self, key: str):
        if self.items[0].info.get(key) is None:
            return

        if key == 'rank':
            def fun(x): return x.info.get(key)
        else:
            def fun(x): return -x.info.get(key)

        self.items.sort(key=fun)
        self.__update()

    def filterChampions(self, type: str, x):
        self.allChampionShowing = False

        '''
        通过两种方式来筛选英雄：
        - `type` 为 `championId` 时，通过判断英雄 id 在不在列表 `x` 中筛选
        - `type` 为 `name` 时，通过判断字符串 `x` 在不在英雄名中筛选
        '''

        if type == 'championId':
            for item in self.items:
                item.setVisible(item.info['championId'] in x)

        else:
            for item in self.items:
                item.setVisible(x in item.info['name'])

    def showAllChampions(self):
        if self.allChampionShowing:
            return

        self.allChampionShowing = True

        for item in self.items:
            item.setVisible(True)


class SortLabel(QLabel):
    clicked = pyqtSignal()

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self._selected = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(32)
        self.setAlignment(Qt.AlignCenter)
        qconfig.themeChangedFinished.connect(self._refreshStyle)
        self._refreshStyle()

    def setSelected(self, selected: bool):
        self._selected = bool(selected)
        self._refreshStyle()

    def _refreshStyle(self):
        dark = isDarkTheme()
        accent = themeColor().name()
        if self._selected:
            color = accent
            border = f"2px solid {accent}"
        else:
            color = "rgba(255,255,255,0.72)" if dark else "rgba(0,0,0,0.66)"
            border = "2px solid transparent"
        self.setStyleSheet(
            "SortLabel {"
            f" color: {color}; background-color: transparent;"
            f" border: none; border-bottom: {border}; padding: 5px 4px 7px 4px;"
            " font: bold 13px 'Microsoft YaHei UI', 'Segoe UI';"
            "}")

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class ListTitleBar(QFrame):
    sortRequested = pyqtSignal(str)

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.hBoxLayout = QHBoxLayout(self)

        # self.setStyleSheet("border: 1px solid black;")

        self.counterLabel = QLabel("#")
        self.championLabel = QLabel(self.tr("Champion"))
        self.rankLabel = SortLabel(self.tr("Tier"))
        self.winRateLabel = SortLabel(self.tr("Win Rate"))
        self.pickRateLabel = SortLabel(self.tr("Pick Rate"))
        self.banRateLabel = SortLabel(self.tr("Ban Rate"))
        self.countersLabel = QLabel(self.tr("Counters"))

        self.selected: SortLabel = self.rankLabel

        self.__initWidget()
        self.__initLayout()

    def __initLayout(self):
        self.hBoxLayout.setContentsMargins(17, 6, 28, 6)

        self.hBoxLayout.addWidget(self.counterLabel, alignment=Qt.AlignCenter)
        # self.hBoxLayout.addSpacing()
        self.hBoxLayout.addWidget(self.championLabel, alignment=Qt.AlignCenter)
        self.hBoxLayout.addSpacerItem(QSpacerItem(
            0, 0, QSizePolicy.Expanding, QSizePolicy.Fixed))
        self.hBoxLayout.addWidget(self.rankLabel, alignment=Qt.AlignCenter)
        self.hBoxLayout.addSpacing(13)
        self.hBoxLayout.addWidget(self.winRateLabel, alignment=Qt.AlignCenter)
        self.hBoxLayout.addSpacing(1)
        self.hBoxLayout.addWidget(self.pickRateLabel, alignment=Qt.AlignCenter)
        self.hBoxLayout.addWidget(self.banRateLabel, alignment=Qt.AlignCenter)
        self.hBoxLayout.addSpacing(8)
        self.hBoxLayout.addWidget(self.countersLabel, alignment=Qt.AlignCenter)

    def __initWidget(self):
        self.counterLabel.setFixedWidth(30)
        self.counterLabel.setObjectName("counterLabel")
        self.counterLabel.setAlignment(Qt.AlignCenter)
        self.countersLabel.setAlignment(Qt.AlignCenter)
        self.countersLabel.setObjectName("countersLabel")
        self.championLabel.setAlignment(Qt.AlignCenter)
        self.championLabel.setObjectName("championLabel")

        for button in (self.rankLabel, self.winRateLabel,
                       self.pickRateLabel, self.banRateLabel):
            button.setObjectName("tierSortButton")

        self.rankLabel.setFixedWidth(50)
        self.winRateLabel.setFixedWidth(70)
        self.pickRateLabel.setFixedWidth(70)
        self.banRateLabel.setFixedWidth(70)
        self.countersLabel.setFixedWidth(80)

        self.rankLabel.clicked.connect(
            lambda: self.__onSortButtonClicked("rank"))
        self.winRateLabel.clicked.connect(
            lambda: self.__onSortButtonClicked("winRate"))
        self.pickRateLabel.clicked.connect(
            lambda: self.__onSortButtonClicked("pickRate"))
        self.banRateLabel.clicked.connect(
            lambda: self.__onSortButtonClicked("banRate"))

        self.resetSelected()

    def __onSortButtonClicked(self, type):
        widget: SortLabel = getattr(self, f"{type}Label")
        self.__setSelected(widget)

        self.sortRequested.emit(type)

    def __setSelected(self, widget: SortLabel):
        self.selected.setSelected(False)
        widget.setSelected(True)

        self.selected = widget

    def resetSelected(self):
        self.__setSelected(self.rankLabel)


class ListItem(ColorAnimationFrame):
    def __init__(self, number, info, parent: QWidget = None):
        super().__init__(type=f"tier{info['tier']}", parent=parent)
        # super().__init__(type="default", parent=parent)

        # self.setStyleSheet("border: 1px solid black;")
        self.setFixedWidth(589)

        self.championId = info['championId']
        self.name = info['name']

        self.info = info

        tierIcon = f"app/resource/images/icon-tier-{info['tier']}.svg"

        self.hBoxLayout = QHBoxLayout(self)

        self.numberLabel = BodyLabel(str(number))
        self.nameLabel = BodyLabel(info.get("name"))
        self.championIcon = RoundIcon(info.get("icon"), 28, 2, 2)
        self.tierLabel = RoundedLabel(tierIcon, borderWidth=0, radius=0)

        if info['winRate']:
            self.winRateLabel = BodyLabel(f"{info['winRate']*100:.2f}%")
        else:
            self.winRateLabel = BodyLabel("--")

        if info['pickRate']:
            self.pickRateLabel = BodyLabel(f"{info['pickRate']*100:.2f}%")
        else:
            self.pickRateLabel = BodyLabel("--")

        if info['banRate']:
            self.banRateLabel = BodyLabel(f"{info['banRate']*100:.2f}%")
        else:
            self.banRateLabel = BodyLabel("--")

        self.countersLabel = QWidget()
        self.countersLayout = QHBoxLayout(self.countersLabel)

        self.countersLayout.setAlignment(Qt.AlignCenter)

        counters = info.get("counters")
        if counters:
            for c in counters:
                icon = RoundIcon(c['icon'], 22, 2, 2)
                self.countersLayout.addWidget(icon)
        else:
            icon = BodyLabel("--")
            self.countersLayout.addWidget(icon)

        self.__initWidget()
        self.__initLayout()

    def __initWidget(self):
        self.numberLabel.setFixedWidth(30)
        self.numberLabel.setAlignment(Qt.AlignCenter)
        self.winRateLabel.setAlignment(Qt.AlignCenter)
        self.pickRateLabel.setAlignment(Qt.AlignCenter)
        self.banRateLabel.setAlignment(Qt.AlignCenter)

        width = 70

        self.tierLabel.setFixedWidth(50)
        self.winRateLabel.setFixedWidth(width)
        self.pickRateLabel.setFixedWidth(width)
        self.banRateLabel.setFixedWidth(width)
        self.countersLabel.setFixedWidth(80)

        self.nameLabel.setContentsMargins(0, 0, 0, 2)
        # self.tierLabel.setContentsMargins(0, 0, 0, 2)
        # self.winRateLabel.setContentsMargins(0, 0, 0, 2)
        # self.pickRateLabel.setContentsMargins(0, 0, 0, 2)
        # self.banRateLabel.setContentsMargins(0, 0, 0, 2)

        self.clicked.connect(self.__onClicked)

    def __initLayout(self):
        self.hBoxLayout.setContentsMargins(17, 6, 28, 6)
        self.hBoxLayout.setSpacing(0)
        self.countersLayout.setContentsMargins(0, 0, 0, 0)
        self.countersLayout.setSpacing(2)

        self.hBoxLayout.addWidget(self.numberLabel, alignment=Qt.AlignCenter)
        self.hBoxLayout.addSpacing(6)
        self.hBoxLayout.addWidget(self.championIcon, alignment=Qt.AlignCenter)
        self.hBoxLayout.addSpacing(6)
        self.hBoxLayout.addWidget(self.nameLabel, alignment=Qt.AlignCenter)
        self.hBoxLayout.addSpacerItem(QSpacerItem(
            0, 0, QSizePolicy.Expanding, QSizePolicy.Fixed))
        self.hBoxLayout.addWidget(self.tierLabel, alignment=Qt.AlignCenter)
        self.hBoxLayout.addSpacing(13)
        self.hBoxLayout.addWidget(self.winRateLabel, alignment=Qt.AlignCenter)
        self.hBoxLayout.addWidget(self.pickRateLabel, alignment=Qt.AlignCenter)
        self.hBoxLayout.addWidget(self.banRateLabel, alignment=Qt.AlignCenter)
        self.hBoxLayout.addSpacing(8)
        self.hBoxLayout.addWidget(self.countersLabel, alignment=Qt.AlignCenter)

    def setCounter(self, x):
        self.numberLabel.setText(str(x))

    def __onClicked(self):
        signalBus.toOpggBuildInterface.emit(self.championId, "", "")
