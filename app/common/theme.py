"""Keep QFluent styles and the native Qt palette on the same theme."""

from PyQt5.QtGui import QColor, QPalette
from PyQt5.QtWidgets import QApplication

from .qfluentwidgets import Theme, qconfig, setTheme


def _makePalette(theme: Theme) -> QPalette:
    palette = QPalette()
    if theme == Theme.DARK:
        window = QColor("#202020")
        base = QColor("#282828")
        alternate = QColor("#303030")
        text = QColor("#f2f2f2")
        muted = QColor("#9a9a9a")
        button = QColor("#2b2b2b")
        palette.setColor(QPalette.Window, window)
        palette.setColor(QPalette.WindowText, text)
        palette.setColor(QPalette.Base, base)
        palette.setColor(QPalette.AlternateBase, alternate)
        palette.setColor(QPalette.Text, text)
        palette.setColor(QPalette.Button, button)
        palette.setColor(QPalette.ButtonText, text)
        palette.setColor(QPalette.ToolTipBase, alternate)
        palette.setColor(QPalette.ToolTipText, text)
        palette.setColor(QPalette.PlaceholderText, muted)
        palette.setColor(QPalette.Link, QColor("#4cc2ff"))
        palette.setColor(QPalette.Highlight, QColor("#009faa"))
        palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    else:
        window = QColor("#fafafa")
        base = QColor("#ffffff")
        alternate = QColor("#f3f3f3")
        text = QColor("#1a1a1a")
        muted = QColor("#767676")
        button = QColor("#f7f7f7")
        palette.setColor(QPalette.Window, window)
        palette.setColor(QPalette.WindowText, text)
        palette.setColor(QPalette.Base, base)
        palette.setColor(QPalette.AlternateBase, alternate)
        palette.setColor(QPalette.Text, text)
        palette.setColor(QPalette.Button, button)
        palette.setColor(QPalette.ButtonText, text)
        palette.setColor(QPalette.ToolTipBase, base)
        palette.setColor(QPalette.ToolTipText, text)
        palette.setColor(QPalette.PlaceholderText, muted)
        palette.setColor(QPalette.Link, QColor("#0078d4"))
        palette.setColor(QPalette.Highlight, QColor("#009faa"))
        palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))

    disabled = QColor("#777777") if theme == Theme.DARK else QColor("#9a9a9a")
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        palette.setColor(QPalette.Disabled, role, disabled)
    return palette


def applyTheme(theme: Theme = None) -> Theme:
    """Apply a concrete QFluent theme and keep the Qt palette in sync."""
    resolved = qconfig.theme if theme in (None, Theme.AUTO) else theme
    # QFluent's QConfig.set() can short-circuit before updating its resolved
    # `_theme` when themeMode is AUTO. Set the resolved value explicitly so
    # widget QSS, icon colors and the native palette never disagree.
    qconfig.theme = resolved
    setTheme(resolved)
    app = QApplication.instance()
    if app is not None:
        app.setPalette(_makePalette(resolved))
    return resolved
