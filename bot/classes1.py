import os
import json
import pprint
from pathlib import Path
from dotenv import load_dotenv

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QFrame,
    QLabel,
    QPushButton,
    QCheckBox,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QScrollArea,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QInputDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QSizePolicy,
    QStackedWidget,
)


load_dotenv()


class Screen(object):
    """Base screen: header + body, stored as a widget that can be stacked."""

    def __init__(self, parent: QWidget):
        super(Screen, self).__init__()
        self.parent = parent

        # In PyQt the "frame" is a QWidget we place in the QStackedWidget.
        self.frame = QWidget(parent)
        self.frame_layout = QVBoxLayout(self.frame)
        self.frame_layout.setContentsMargins(0, 0, 0, 0)
        self.frame_layout.setSpacing(0)

        self.header = None
        self.body = None

    def _screen_header(self, title: str, subtitle: str):
        header = QWidget(self.frame)
        hl = QVBoxLayout(header)
        hl.setContentsMargins(0, 0, 0, 16)
        hl.setSpacing(6)

        title_lbl = QLabel(title, header)
        f = title_lbl.font()
        f.setPointSize(14)
        f.setBold(True)
        title_lbl.setFont(f)
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        sub_lbl = QLabel(subtitle, header)
        subf = sub_lbl.font()
        subf.setPointSize(9)
        sub_lbl.setFont(subf)
        sub_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        hl.addWidget(title_lbl)
        hl.addWidget(sub_lbl)

        self.header = header
        self.frame_layout.addWidget(self.header)
        return self.header

    def _screen_body(self):
        body = QWidget(self.frame)
        body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.body = body
        self.frame_layout.addWidget(self.body, 1)
        return self.body

    def setup(self, title: str, subtitle: str):
        self._screen_header(title, subtitle)
        self._screen_body()

        if self.header is None or self.body is None:
            raise Exception("Header and Body widget incomplete")


class TestsScreen(Screen):
    def __init__(self, parent, run_tests_callback=None):
        super().__init__(parent)
        self.test_log = None
        self.run_tests_callback = run_tests_callback

    def _build_body(self):
        layout = QVBoxLayout(self.body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.test_log = QPlainTextEdit(self.body)
        self.test_log.setReadOnly(True)
        layout.addWidget(self.test_log, 1)

        btn_row = QHBoxLayout()
        run_btn = QPushButton("Run tests", self.body)
        run_btn.clicked.connect(self.run_tests)
        btn_row.addWidget(run_btn, 0, Qt.AlignmentFlag.AlignLeft)
        btn_row.addStretch(1)

        layout.addLayout(btn_row)

    def _append_log(self, msg: str):
        self.test_log.appendPlainText(msg)
        self.test_log.verticalScrollBar().setValue(self.test_log.verticalScrollBar().maximum())

    def run_tests(self):
        self.test_log.clear()
        self._append_log("Starting tests...")

        if self.run_tests_callback is None:
            self._append_log("No test callback configured.")
            return

        tests_results = self.run_tests_callback()
        for results in tests_results:
            self._append_log(str(results))

        self._append_log("All tests completed.")

    def setup(self, title, subtitle):
        super().setup(title, subtitle)

        if self.run_tests_callback is None:
            QMessageBox.warning(self.frame, "Warning", "parameters/methods are missing.")
            return

        self._build_body()


class APIScreen(Screen):
    def __init__(self, parent, _save_config, save_env, apis_config=None):
        super().__init__(parent)
        self.apis_config = apis_config

        # methods
        self._save_config = _save_config
        self.save_env = save_env

        # State for dynamic UI
        self.api_vars = {}          # api_name -> {"enabled":..., "api_secret":..., "base_endpoint":..., "card":...}

        self.scroll_area = None
        self.inner_widget = None
        self.inner_layout = None

    # ---- Alt reveal logic (same idea as before) ----
    class _AltRevealFilter(QWidget):
        def __init__(self, line_edit: QLineEdit):
            super().__init__()
            self.line_edit = line_edit

        def eventFilter(self, obj, event):
            if obj is self.line_edit:
                if event.type() == event.Type.KeyPress and event.key() == Qt.Key.Key_Alt:
                    if self.line_edit.hasFocus():
                        self.line_edit.setEchoMode(QLineEdit.EchoMode.Normal)
                elif event.type() == event.Type.KeyRelease and event.key() == Qt.Key.Key_Alt:
                    self.line_edit.setEchoMode(QLineEdit.EchoMode.Password)
                elif event.type() == event.Type.FocusOut:
                    self.line_edit.setEchoMode(QLineEdit.EchoMode.Password)
            return False

    def _build_body(self):
        """
        Build scroll area ONCE.
        Add all existing API cards into the inner layout.
        """
        layout = QVBoxLayout(self.body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # Scroll area once
        self.scroll_area = QScrollArea(self.body)
        self.scroll_area.setWidgetResizable(True)  # key setting for good behavior [web:46]
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.inner_widget = QWidget()
        self.inner_layout = QVBoxLayout(self.inner_widget)
        self.inner_layout.setContentsMargins(0, 0, 0, 0)
        self.inner_layout.setSpacing(10)

        self.scroll_area.setWidget(self.inner_widget)
        layout.addWidget(self.scroll_area, 1)

        # Add existing APIs as cards (fast, no canvas hacks)
        if self.apis_config:
            for api_name, values in self.apis_config.items():
                self._add_api_card(api_name, values)

        self.inner_layout.addStretch(1)

        # Bottom bar once
        bottom = QHBoxLayout()
        add_btn = QPushButton("Add", self.body)
        add_btn.clicked.connect(self._add)

        save_btn = QPushButton("Save", self.body)
        save_btn.clicked.connect(self._save)

        bottom.addWidget(add_btn)
        bottom.addStretch(1)
        bottom.addWidget(save_btn)
        layout.addLayout(bottom)

    def _add_api_card(self, api_name: str, values: dict):
        """
        Create ONE API card widget and insert it into the scroll area's inner layout.
        """
        card = QFrame(self.inner_widget)
        card.setFrameShape(QFrame.Shape.StyledPanel)

        grid = QGridLayout(card)
        grid.setContentsMargins(10, 10, 10, 10)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        title_lbl = QLabel(api_name, card)
        f = title_lbl.font()
        f.setPointSize(14)
        f.setBold(True)
        title_lbl.setFont(f)

        enabled_cb = QCheckBox("Enable/Disable", card)
        enabled_cb.setChecked(bool(values.get("enabled", False)))

        env_key_name = values.get("api_key", "")
        api_secret = os.getenv(env_key_name, "")
        api_secret_entry = QLineEdit(card)
        api_secret_entry.setText(api_secret)
        api_secret_entry.setEchoMode(QLineEdit.EchoMode.Password)
        api_secret_entry.installEventFilter(self._AltRevealFilter(api_secret_entry))

        base_endpoint_entry = QLineEdit(card)
        base_endpoint_entry.setText(values.get("base_endpoint", ""))

        delete_btn = QPushButton("Delete", card)
        delete_btn.clicked.connect(lambda _=False, name=api_name: self._delete(name))

        r = 0
        grid.addWidget(title_lbl, r, 0)
        grid.addWidget(enabled_cb, r, 1, Qt.AlignmentFlag.AlignRight)
        grid.addWidget(delete_btn, r, 2, Qt.AlignmentFlag.AlignRight)

        r += 1
        grid.addWidget(QLabel("API Secret (press alt to view):", card), r, 0)
        grid.addWidget(api_secret_entry, r, 1, 1, 2)

        r += 1
        grid.addWidget(QLabel("Base Endpoint:", card), r, 0)
        grid.addWidget(base_endpoint_entry, r, 1, 1, 2)

        # Store references for _save() and _delete()
        self.api_vars[api_name] = {
            "enabled": enabled_cb,
            "api_secret": api_secret_entry,
            "base_endpoint": base_endpoint_entry,
            "card": card,
        }

        # Insert above the stretch (stretch is last item)
        insert_at = max(0, self.inner_layout.count() - 1)
        self.inner_layout.insertWidget(insert_at, card)

    def _add(self):
        name, ok = QInputDialog.getText(self.frame, "Input", "API name")
        if not ok or not name.strip():
            return
        api_name = name.strip()

        if api_name in self.apis_config:
            QMessageBox.warning(self.frame, "Exists", f"'{api_name}' already exists.")
            return

        # You must decide defaults; keeping config structure the same.
        # Using API_KEY_NAME placeholder so you can edit config later.
        self.apis_config[api_name] = {
            "api_key": f"{api_name.upper().replace(' ', '_')}_API_KEY",
            "api_secret": "",
            "enabled": True,
            "base_endpoint": "",
        }

        self._add_api_card(api_name, self.apis_config[api_name])

    def _delete(self, api_name: str):
        reply = QMessageBox.question(self.frame, "Confirm delete", f"Delete '{api_name}'?")
        if reply != QMessageBox.StandardButton.Yes:
            return

        entry = self.api_vars.pop(api_name, None)
        if entry and entry.get("card"):
            entry["card"].setParent(None)
            entry["card"].deleteLater()

        self.apis_config.pop(api_name, None)

        # Save immediately (keeps your old behavior)
        self._save()

    def _save(self):
        if not self.api_vars:
            QMessageBox.warning(self.frame, "Nothing to save", "No API fields were found.")
            return

        for api_name, vars_ in self.api_vars.items():
            self.apis_config[api_name] = {
                "api_key": self.apis_config[api_name]["api_key"],
                "api_secret": "",  # unchanged behavior
                "enabled": bool(vars_["enabled"].isChecked()),
                "base_endpoint": vars_["base_endpoint"].text().strip(),
            }

        self._save_config()
        QMessageBox.information(self.frame, "Saved", "Config Updated!")

    def setup(self, title, subtitle):
        super().setup(title, subtitle)
        if self.apis_config is None:
            QMessageBox.warning(self.frame, "Warning", "configs and parameters/methods are missing.")
            return
        self._build_body()


class ExchangesScreen(Screen):
    def __init__(self, parent, _save_config, exchange_config=None):
        super().__init__(parent)
        self.exchange_config = exchange_config
        self.tree = None
        self.right = None

        self.stock_vars = {}
        self._save_config = _save_config

    def _build_exchange_tree(self):
        layout = QHBoxLayout(self.body)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal, self.body)
        layout.addWidget(splitter, 1)

        left = QWidget(splitter)
        left_l = QVBoxLayout(left)
        left_l.setContentsMargins(0, 0, 0, 0)

        right = QWidget(splitter)
        right_l = QVBoxLayout(right)
        right_l.setContentsMargins(0, 0, 0, 0)

        self.right = right

        self.tree = QTreeWidget(left)
        self.tree.setHeaderHidden(True)
        left_l.addWidget(self.tree, 1)

        # Populate
        exchanges = self.exchange_config or {}
        for ex_key, ex in exchanges.items():
            ex_enabled = bool(ex.get("enabled", True))
            ex_text = f"{ex_key} - {ex.get('name', ex_key)}"

            ex_item = QTreeWidgetItem([ex_text])
            ex_item.setData(0, Qt.ItemDataRole.UserRole, ("ex", ex_key))
            if not ex_enabled:
                ex_item.setForeground(0, ex_item.foreground(0).color().fromString("#9aa0a6"))

            self.tree.addTopLevelItem(ex_item)

            stocks = ex.get("stocks", {}) or {}
            for ticker, stock in stocks.items():
                stock_enabled = ex_enabled and bool(stock.get("enabled", True))
                st_text = f"{ticker} - {stock.get('full_name', ticker)}"

                st_item = QTreeWidgetItem([st_text])
                st_item.setData(0, Qt.ItemDataRole.UserRole, ("st", ex_key, ticker))
                if not stock_enabled:
                    st_item.setForeground(0, st_item.foreground(0).color().fromString("#9aa0a6"))

                ex_item.addChild(st_item)

                social = stock.get("social_sources", {}) or {}
                if social:
                    grp = QTreeWidgetItem(["Social sources"])
                    grp.setData(0, Qt.ItemDataRole.UserRole, ("grp_social", ex_key, ticker))
                    st_item.addChild(grp)
                    for src_name, src_cfg in social.items():
                        src_enabled = stock_enabled and bool(src_cfg.get("enabled", True))
                        it = QTreeWidgetItem([src_name])
                        it.setData(0, Qt.ItemDataRole.UserRole, ("src_social", ex_key, ticker, src_name))
                        if not src_enabled:
                            it.setForeground(0, it.foreground(0).color().fromString("#9aa0a6"))
                        grp.addChild(it)

                news = stock.get("news_sources", []) or []
                if news:
                    grp = QTreeWidgetItem(["News sources"])
                    grp.setData(0, Qt.ItemDataRole.UserRole, ("grp_news", ex_key, ticker))
                    st_item.addChild(grp)
                    for i, src_cfg in enumerate(news):
                        src_name = src_cfg.get("name", f"news_{i}")
                        src_enabled = stock_enabled and bool(src_cfg.get("enabled", True))
                        it = QTreeWidgetItem([src_name])
                        it.setData(0, Qt.ItemDataRole.UserRole, ("src_news", ex_key, ticker, i))
                        if not src_enabled:
                            it.setForeground(0, it.foreground(0).color().fromString("#9aa0a6"))
                        grp.addChild(it)

                fin = stock.get("financial_sources", {}) or {}
                if fin:
                    grp = QTreeWidgetItem(["Financial sources"])
                    grp.setData(0, Qt.ItemDataRole.UserRole, ("grp_fin", ex_key, ticker))
                    st_item.addChild(grp)
                    for src_name, src_cfg in fin.items():
                        src_enabled = stock_enabled and bool(src_cfg.get("enabled", True))
                        it = QTreeWidgetItem([src_name])
                        it.setData(0, Qt.ItemDataRole.UserRole, ("src_fin", ex_key, ticker, src_name))
                        if not src_enabled:
                            it.setForeground(0, it.foreground(0).color().fromString("#9aa0a6"))
                        grp.addChild(it)

        self.tree.expandToDepth(0)
        self.tree.currentItemChanged.connect(self._on_tree_select)

        right_l.addWidget(QLabel("Select an item on the left"), 0, Qt.AlignmentFlag.AlignTop)
        right_l.addStretch(1)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

    def _on_tree_select(self, current, _previous):
        for i in reversed(range(self.right.layout().count())):
            item = self.right.layout().itemAt(i)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

        if current is None:
            self.right.layout().addWidget(QLabel("Select an item on the left"))
            self.right.layout().addStretch(1)
            return

        text = current.text(0)
        self.right.layout().addWidget(QLabel(f"Selected: {text}"), 0, Qt.AlignmentFlag.AlignTop)
        self.right.layout().addStretch(1)

    def setup(self, title, subtitle):
        super().setup(title, subtitle)

        if self.exchange_config is None:
            QMessageBox.warning(self.frame, "Warning", "configs and parameters/methods are missing.")
            return

        self._build_exchange_tree()


class Panel(object):
    def __init__(self, screens, config, save_config, save_env):
        super(Panel, self).__init__()
        self.screens = screens
        self.config = config

        # methods
        self.save_config = save_config
        self.save_env = save_env

        # Qt main window + central layout
        self.window = QMainWindow()
        self.central = QWidget(self.window)
        self.window.setCentralWidget(self.central)

        self.nav = None
        self.stack = None

        # screen_key -> index in stack
        self._screen_index = {}

    def show_screen(self, name: str):
        if name not in self._screen_index:
            return
        self.stack.setCurrentIndex(self._screen_index[name])

    def _save_config(self):
        self.save_config(complete_config=json.dumps(self.config, indent=3))

    def _setup_nav(self, root_layout: QVBoxLayout):
        nav = QWidget(self.central)
        nav_l = QHBoxLayout(nav)
        nav_l.setContentsMargins(0, 0, 0, 0)
        nav_l.setSpacing(8)

        for screen_key in self.screens:
            btn = QPushButton(self.screens[screen_key]["title"], nav)
            btn.clicked.connect(lambda _=False, key=screen_key: self.show_screen(key))
            nav_l.addWidget(btn)

        nav_l.addStretch(1)
        self.nav = nav
        root_layout.addWidget(self.nav, 0)

    def _setup_content_frame(self, root_layout: QVBoxLayout):
        self.stack = QStackedWidget(self.central)
        root_layout.addWidget(self.stack, 1)

    def _setup_screens(self):
        for screen_key in self.screens:
            match screen_key:
                case "Tests":
                    scr = TestsScreen(self.stack, self.screens[screen_key]["run_tests_callback"])
                case "APIs":
                    scr = APIScreen(self.stack, self._save_config, self.save_env, apis_config=self.config["apis"])
                case "Exchanges":
                    scr = ExchangesScreen(self.stack, self._save_config, exchange_config=self.config["exchanges"])
                case _:
                    scr = Screen(self.stack)

            scr.setup(self.screens[screen_key]["title"], self.screens[screen_key]["subtitle"])
            idx = self.stack.addWidget(scr.frame)
            self.screens[screen_key]["screen"] = scr
            self._screen_index[screen_key] = idx

    def setup(self):
        if self.screens is None or self.config is None:
            QMessageBox.warning(self.window, "Warning", "screens and config are missing.")
            return

        self.window.setWindowTitle("Bot configuration")
        self.window.resize(900, 600)

        root_layout = QVBoxLayout(self.central)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(10)

        self._setup_nav(root_layout)
        self._setup_content_frame(root_layout)

        if self.nav is None or self.stack is None:
            raise Exception("Navigation and Content frame incomplete")

        self._setup_screens()
        pprint.pprint(self.screens)

        all_screens = list(self.screens.keys())
        if len(all_screens) == 0:
            raise Exception("Screens setup incomplete")

        self.show_screen(all_screens[-1])


