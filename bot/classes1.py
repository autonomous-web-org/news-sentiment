import re
import os
import json
import pprint
from pathlib import Path
from dotenv import load_dotenv

from PyQt6.QtCore import Qt, QTimeZone
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
    QFormLayout, QComboBox
)
from PyQt6.QtGui import QBrush, QColor





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

    def _apply_enabled_style(self, item, enabled: bool):
        # Keep selectable; only change appearance.
        color = QColor("#fff") if enabled else QColor("#9aa0a6")
        item.setForeground(0, QBrush(color))  # gray-out via foreground role 

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
        self.scroll_area.setWidgetResizable(True)  # key setting for good behavior 
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
        # MOVE IT TO FORM LAYOUT
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
        # api_secret_entry.setEchoMode(QLineEdit.EchoMode.Password)
        api_secret_entry.setReadOnly(True)
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

        # Only A-Z, a-z, 0-9, _
        if not re.fullmatch(r"[A-Za-z0-9_]+", api_name):
            QMessageBox.warning(
                self.frame,
                "Invalid name",
                "Use only letters, digits, and underscore (_). No spaces or other characters.",
            )
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
        self._save()

    def _delete(self, api_name: str):
        reply = QMessageBox.question(self.frame, "Confirm delete", f"Delete '{api_name}'?")
        if reply != QMessageBox.StandardButton.Yes:
            return

        entry = self.api_vars.pop(api_name, None)
        if entry and entry.get("card"):
            entry["card"].setParent(None)
            entry["card"].deleteLater()

        self.apis_config.pop(api_name, None)

        # Save immediately
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
    def __init__(self, parent, _save_config, exchange_config=None, apis_config=None, rss_config=None):
        super().__init__(parent)
        self.exchange_config = exchange_config
        self.apis_config = apis_config or {}   # allow empty apis
        self.rss_config = rss_config           # can be None for now

        self.tree = None
        self.right = None
        self._save_config = _save_config

    # ---------- styling ----------
    def _apply_enabled_style(self, item: QTreeWidgetItem, enabled: bool):
        # If enabled, clear override so it uses theme default; if disabled, force grey. 
        if enabled:
            item.setData(0, Qt.ItemDataRole.ForegroundRole, None)  # clear override
        else:
            item.setForeground(0, QBrush(QColor("#9aa0a6")))

    # ---------- tree building ----------
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

        exchanges = self.exchange_config or {}
        for ex_key, ex in exchanges.items():
            ex_enabled = bool(ex.get("enabled", True))
            ex_text = f"{ex_key} - {ex.get('name', ex_key)}"
            ex_item = QTreeWidgetItem([ex_text])
            ex_item.setData(0, Qt.ItemDataRole.UserRole, ("ex", ex_key))
            self.tree.addTopLevelItem(ex_item)

            self._apply_enabled_style(ex_item, ex_enabled)

            stocks = ex.get("stocks", {}) or {}
            for ticker_key, stock in stocks.items():
                stock_enabled = ex_enabled and bool(stock.get("enabled", True))
                st_text = f"{ticker_key} - {stock.get('full_name', ticker_key)}"
                st_item = QTreeWidgetItem([st_text])
                st_item.setData(0, Qt.ItemDataRole.UserRole, ("st", ex_key, ticker_key))
                ex_item.addChild(st_item)

                self._apply_enabled_style(st_item, stock_enabled)

                # Social group
                social = stock.get("social_sources", {}) or {}
                if social:
                    grp = QTreeWidgetItem(["Social sources"])
                    grp.setData(0, Qt.ItemDataRole.UserRole, ("grp_social", ex_key, ticker_key))
                    st_item.addChild(grp)
                    self._apply_enabled_style(grp, stock_enabled)

                    for src_name, src_cfg in social.items():
                        src_enabled = stock_enabled and bool(src_cfg.get("enabled", True))
                        it = QTreeWidgetItem([src_name])
                        it.setData(0, Qt.ItemDataRole.UserRole, ("src_social", ex_key, ticker_key, src_name))
                        grp.addChild(it)
                        self._apply_enabled_style(it, src_enabled)

                # News group (list)
                news = stock.get("news_sources", []) or []
                if news:
                    grp = QTreeWidgetItem(["News sources"])
                    grp.setData(0, Qt.ItemDataRole.UserRole, ("grp_news", ex_key, ticker_key))
                    st_item.addChild(grp)
                    self._apply_enabled_style(grp, stock_enabled)

                    for i, src_cfg in enumerate(news):
                        src_name = src_cfg.get("name", f"news_{i}")
                        src_enabled = stock_enabled and bool(src_cfg.get("enabled", True))
                        it = QTreeWidgetItem([src_name])
                        it.setData(0, Qt.ItemDataRole.UserRole, ("src_news", ex_key, ticker_key, i))
                        grp.addChild(it)
                        self._apply_enabled_style(it, src_enabled)

                # Financial group
                fin = stock.get("financial_sources", {}) or {}
                if fin:
                    grp = QTreeWidgetItem(["Financial sources"])
                    grp.setData(0, Qt.ItemDataRole.UserRole, ("grp_fin", ex_key, ticker_key))
                    st_item.addChild(grp)
                    self._apply_enabled_style(grp, stock_enabled)

                    for src_name, src_cfg in fin.items():
                        src_enabled = stock_enabled and bool(src_cfg.get("enabled", True))
                        it = QTreeWidgetItem([src_name])
                        it.setData(0, Qt.ItemDataRole.UserRole, ("src_fin", ex_key, ticker_key, src_name))
                        grp.addChild(it)
                        self._apply_enabled_style(it, src_enabled)

        self.tree.expandToDepth(0)
        self.tree.currentItemChanged.connect(self._on_tree_select)

        right_l.addWidget(QLabel("Select an item on the left"), 0, Qt.AlignmentFlag.AlignTop)
        right_l.addStretch(1)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

    # ---------- editors ----------
    def _build_exchange_editor(self, ex_key: str, tree_item: QTreeWidgetItem):
        ex = self.exchange_config[ex_key]

        wrapper = QWidget(self.right)
        v = QVBoxLayout(wrapper)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(12)

        title = QLabel(f"Exchange: {ex_key}", wrapper)
        f = title.font()
        f.setPointSize(13)
        f.setBold(True)
        title.setFont(f)
        v.addWidget(title)

        form = QFormLayout()
        v.addLayout(form)

        name_in = QLineEdit(wrapper)
        name_in.setText(ex.get("name", ""))

        symbol_in = QLineEdit(wrapper)
        symbol_in.setText(ex.get("symbol", ""))  # field only

        enabled_in = QCheckBox("Enabled", wrapper)
        enabled_in.setChecked(bool(ex.get("enabled", True)))

        tz_in = QComboBox(wrapper)
        tz_ids = [bytes(z).decode("utf-8", "ignore") for z in QTimeZone.availableTimeZoneIds()]
        tz_ids.sort()
        tz_in.addItems(tz_ids)
        cur_tz = ex.get("timezone", "UTC")
        if cur_tz in tz_ids:
            tz_in.setCurrentText(cur_tz)
        else:
            tz_in.insertItem(0, cur_tz)
            tz_in.setCurrentIndex(0)

        form.addRow("Name", name_in)
        form.addRow("Symbol", symbol_in)
        form.addRow("Timezone", tz_in)
        form.addRow("", enabled_in)

        btns = QHBoxLayout()
        btns.addStretch(1)
        save_btn = QPushButton("Save exchange", wrapper)
        btns.addWidget(save_btn)
        v.addLayout(btns)

        def on_save():
            ex["name"] = name_in.text().strip()
            ex["symbol"] = symbol_in.text().strip()
            ex["timezone"] = tz_in.currentText().strip()
            ex["enabled"] = bool(enabled_in.isChecked())

            tree_item.setText(0, f"{ex_key} - {ex.get('name', ex_key)}")
            self._apply_enabled_style(tree_item, ex["enabled"])
            self._refresh_children_styles_for_exchange(ex_key, tree_item)

            self._save_config()
            QMessageBox.information(self.frame, "Saved", "Exchange updated.")

        save_btn.clicked.connect(on_save)

        self.right.layout().addWidget(wrapper)
        self.right.layout().addStretch(1)

    def _build_stock_editor(self, ex_key: str, ticker_key: str, tree_item: QTreeWidgetItem):
        stock = self.exchange_config[ex_key]["stocks"][ticker_key]

        wrapper = QWidget(self.right)
        v = QVBoxLayout(wrapper)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(12)

        title = QLabel(f"Stock: {ex_key} / {ticker_key}", wrapper)
        f = title.font()
        f.setPointSize(13)
        f.setBold(True)
        title.setFont(f)
        v.addWidget(title)

        form = QFormLayout()
        v.addLayout(form)

        ticker_in = QLineEdit(wrapper)
        ticker_in.setText(stock.get("ticker", ticker_key))  # field only

        full_name_in = QLineEdit(wrapper)
        full_name_in.setText(stock.get("full_name", ""))

        enabled_in = QCheckBox("Enabled", wrapper)
        enabled_in.setChecked(bool(stock.get("enabled", True)))

        form.addRow("Ticker", ticker_in)
        form.addRow("Full name", full_name_in)
        form.addRow("", enabled_in)

        btns = QHBoxLayout()
        btns.addStretch(1)
        save_btn = QPushButton("Save stock", wrapper)
        btns.addWidget(save_btn)
        v.addLayout(btns)

        def on_save():
            stock["ticker"] = ticker_in.text().strip()
            stock["full_name"] = full_name_in.text().strip()
            stock["enabled"] = bool(enabled_in.isChecked())

            tree_item.setText(0, f"{ticker_key} - {stock.get('full_name', ticker_key)}")

            ex_enabled = bool(self.exchange_config[ex_key].get("enabled", True))
            stock_effective = ex_enabled and bool(stock.get("enabled", True))
            self._apply_enabled_style(tree_item, stock_effective)

            # also restyle the stock subtree (groups/sources)
            self._refresh_stock_subtree_styles(ex_key, ticker_key, tree_item)

            self._save_config()
            QMessageBox.information(self.frame, "Saved", "Stock updated.")

        save_btn.clicked.connect(on_save)

        self.right.layout().addWidget(wrapper)
        self.right.layout().addStretch(1)

    def _build_news_source_editor(self, ex_key: str, ticker_key: str, idx: int, tree_item: QTreeWidgetItem):
        stock = self.exchange_config[ex_key]["stocks"][ticker_key]
        news_list = stock.get("news_sources", []) or []

        if idx < 0 or idx >= len(news_list):
            # The tree payload is stale (likely right after a delete). Avoid crashing.
            self.right.layout().addWidget(QLabel("This news source no longer exists. Select another item."))
            self.right.layout().addStretch(1)
            return

        src = news_list[idx]

        wrapper = QWidget(self.right)
        v = QVBoxLayout(wrapper)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(12)

        title = QLabel(f"News source: {ex_key} / {ticker_key} / #{idx}", wrapper)
        f = title.font()
        f.setPointSize(13)
        f.setBold(True)
        title.setFont(f)
        v.addWidget(title)

        form = QFormLayout()
        v.addLayout(form)

        enabled_in = QCheckBox("Enabled", wrapper)
        enabled_in.setChecked(bool(src.get("enabled", True)))

        type_in = QComboBox(wrapper)
        type_in.setEditable(False)
        type_in.addItems(["rss", "api"])
        cur_type = src.get("type", "rss")
        if cur_type in ("rss", "api"):
            type_in.setCurrentText(cur_type)

        name_in = QComboBox(wrapper)
        name_in.setEditable(False)

        query_in = QLineEdit(wrapper)
        query_in.setText(src.get("query", ""))
        query_in.setMaxLength(800)

        form.addRow("", enabled_in)
        form.addRow("Type", type_in)
        form.addRow("Name", name_in)
        form.addRow("Query (<=100 words)", query_in)

        def repopulate_name_dropdown():
            name_in.blockSignals(True)
            name_in.clear()

            t = type_in.currentText().strip()
            cur = src.get("name", "")

            if t == "api":
                api_names = sorted(list((self.apis_config or {}).keys()))
                if api_names:
                    name_in.addItems(api_names)
                    if cur in api_names:
                        name_in.setCurrentText(cur)
                    else:
                        name_in.setCurrentIndex(0)
            else:
                # RSS config not present yet -> empty dropdown is fine. 
                rss_names = sorted(list((self.rss_config or {}).keys())) if self.rss_config else []
                if rss_names:
                    name_in.addItems(rss_names)
                    if cur in rss_names:
                        name_in.setCurrentText(cur)
                    else:
                        name_in.setCurrentIndex(0)

            name_in.blockSignals(False)

        repopulate_name_dropdown()
        type_in.currentTextChanged.connect(lambda _t: repopulate_name_dropdown())

        btns = QHBoxLayout()
        delete_btn = QPushButton("Delete news source", wrapper)
        save_btn = QPushButton("Save news source", wrapper)
        btns.addWidget(delete_btn)
        btns.addStretch(1)
        btns.addWidget(save_btn)
        v.addLayout(btns)

        def _effective_stock_enabled():
            ex_enabled = bool(self.exchange_config[ex_key].get("enabled", True))
            st_enabled = bool(stock.get("enabled", True))
            return ex_enabled and st_enabled

        def on_save():
            q = query_in.text().strip()
            if q and len(q.split()) > 100:
                QMessageBox.warning(self.frame, "Invalid query", "Query too long (max 100 words).")
                return

            src["enabled"] = bool(enabled_in.isChecked())
            src["type"] = type_in.currentText().strip()
            src["name"] = name_in.currentText().strip()  # can be ""
            src["query"] = q

            display_name = src.get("name") or f"news_{idx}"
            tree_item.setText(0, display_name)

            effective = _effective_stock_enabled() and bool(src.get("enabled", True))
            self._apply_enabled_style(tree_item, effective)

            self._save_config()
            QMessageBox.information(self.frame, "Saved", "News source updated.")

        def on_delete():
            reply = QMessageBox.question(self.frame, "Confirm delete", f"Delete this news source (#{idx})?")
            if reply != QMessageBox.StandardButton.Yes:
                return

            # 1) Remove from backing list
            stock["news_sources"].pop(idx)

            # 2) Remove from tree safely
            parent = tree_item.parent()
            if parent is not None:
                row = parent.indexOfChild(tree_item)
                removed = parent.takeChild(row)  # detaches item 
                del removed
            else:
                # shouldn't happen for src_news, but keep safe
                row = self.tree.indexOfTopLevelItem(tree_item)
                removed = self.tree.takeTopLevelItem(row)  # 
                del removed

            if parent is not None:
                self.tree.setCurrentItem(parent, 0)

            # 3) Re-index remaining src_news items under the same "News sources" group
            self._reindex_news_items_under_group(parent, ex_key, ticker_key)

            # 4) Clear right panel + save config
            self._clear_right()
            self.right.layout().addWidget(QLabel("Deleted. Select another item."))
            self.right.layout().addStretch(1)

            self._save_config()

        save_btn.clicked.connect(on_save)
        delete_btn.clicked.connect(on_delete)

        self.right.layout().addWidget(wrapper)
        self.right.layout().addStretch(1)

    # ---------- delete helper: reindex after pop ----------
    def _reindex_news_items_under_group(self, news_group_item: QTreeWidgetItem, ex_key: str, ticker_key: str):
        """
        After deleting a list element, the remaining tree items must have their ("src_news", ex, ticker, idx)
        updated to match the new list indices.
        """
        if news_group_item is None:
            return

        stock = self.exchange_config[ex_key]["stocks"][ticker_key]
        for child_row in range(news_group_item.childCount()):
            it = news_group_item.child(child_row)
            payload = it.data(0, Qt.ItemDataRole.UserRole)
            if payload and payload[0] == "src_news":
                it.setData(0, Qt.ItemDataRole.UserRole, ("src_news", ex_key, ticker_key, child_row))

                # Also update text from config (optional but nice)
                if child_row < len(stock.get("news_sources", [])):
                    name = stock["news_sources"][child_row].get("name", f"news_{child_row}")
                    it.setText(0, name)

    # ---------- style refresh ----------
    def _refresh_stock_subtree_styles(self, ex_key: str, ticker_key: str, st_item: QTreeWidgetItem):
        ex = self.exchange_config[ex_key]
        stock = ex.get("stocks", {}).get(ticker_key, {})
        ex_enabled = bool(ex.get("enabled", True))
        st_enabled = bool(stock.get("enabled", True))
        stock_effective = ex_enabled and st_enabled

        # groups + children
        for j in range(st_item.childCount()):
            grp = st_item.child(j)
            self._apply_enabled_style(grp, stock_effective)

            grp_payload = grp.data(0, Qt.ItemDataRole.UserRole) or ()
            grp_type = grp_payload[0] if grp_payload else ""

            if grp_type == "grp_news":
                news_list = stock.get("news_sources", []) or []
                for k in range(grp.childCount()):
                    src_item = grp.child(k)
                    src_payload = src_item.data(0, Qt.ItemDataRole.UserRole) or ()
                    if src_payload and src_payload[0] == "src_news":
                        idx = src_payload[3]
                        src_cfg = news_list[idx] if idx < len(news_list) else {}
                        src_effective = stock_effective and bool(src_cfg.get("enabled", True))
                        self._apply_enabled_style(src_item, src_effective)
            elif grp_type == "grp_social":
                social = stock.get("social_sources", {}) or {}
                for k in range(grp.childCount()):
                    src_item = grp.child(k)
                    src_payload = src_item.data(0, Qt.ItemDataRole.UserRole) or ()
                    if src_payload and src_payload[0] == "src_social":
                        name = src_payload[3]
                        src_cfg = social.get(name, {})
                        src_effective = stock_effective and bool(src_cfg.get("enabled", True))
                        self._apply_enabled_style(src_item, src_effective)
            elif grp_type == "grp_fin":
                fin = stock.get("financial_sources", {}) or {}
                for k in range(grp.childCount()):
                    src_item = grp.child(k)
                    src_payload = src_item.data(0, Qt.ItemDataRole.UserRole) or ()
                    if src_payload and src_payload[0] == "src_fin":
                        name = src_payload[3]
                        src_cfg = fin.get(name, {})
                        src_effective = stock_effective and bool(src_cfg.get("enabled", True))
                        self._apply_enabled_style(src_item, src_effective)

    def _refresh_children_styles_for_exchange(self, ex_key: str, ex_item: QTreeWidgetItem):
        ex = self.exchange_config[ex_key]
        ex_enabled = bool(ex.get("enabled", True))

        for i in range(ex_item.childCount()):
            st_item = ex_item.child(i)
            payload = st_item.data(0, Qt.ItemDataRole.UserRole)
            if not payload or payload[0] != "st":
                continue

            ticker_key = payload[2]
            stock = ex.get("stocks", {}).get(ticker_key, {})
            stock_effective = ex_enabled and bool(stock.get("enabled", True))
            self._apply_enabled_style(st_item, stock_effective)
            self._refresh_stock_subtree_styles(ex_key, ticker_key, st_item)

    # ---------- selection ----------
    def _on_tree_select(self, current, _previous):
        if current is None:
            return

        payload = current.data(0, Qt.ItemDataRole.UserRole)
        self._clear_right()

        if not payload:
            self.right.layout().addWidget(QLabel("Select an item on the left"))
            self.right.layout().addStretch(1)
            return

        node_type = payload[0]
        if node_type == "ex":
            self._build_exchange_editor(payload[1], current)
        elif node_type == "st":
            self._build_stock_editor(payload[1], payload[2], current)
        elif node_type == "src_news":
            self._build_news_source_editor(payload[1], payload[2], payload[3], current)
        else:
            self.right.layout().addWidget(QLabel(current.text(0)))
            self.right.layout().addStretch(1)

    def _clear_right(self):
        lay = self.right.layout()
        if lay is None:
            lay = QVBoxLayout(self.right)
            lay.setContentsMargins(0, 0, 0, 0)

        while lay.count():
            item = lay.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

    def setup(self, title, subtitle):
        super().setup(title, subtitle)

        if self.exchange_config is None:
            QMessageBox.warning(self.frame, "Warning", "exchange_config is missing.")
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
                    scr = ExchangesScreen(self.stack, self._save_config, exchange_config=self.config["exchanges"], apis_config=self.config["apis"])
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


