import re
import os
import json
import pprint
from pathlib import Path
from dotenv import load_dotenv
from dataclasses import dataclass
from typing import Optional, Any, Dict, Tuple, List

from PyQt6.QtCore import Qt, QTimeZone, pyqtSignal
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
    QTreeView,
    QInputDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QSizePolicy,
    QStackedWidget, QMenu,
    QFormLayout, QComboBox
)
from PyQt6.QtGui import QStandardItemModel, QStandardItem, QColor, QBrush

ROLE_KEY = int(Qt.ItemDataRole.UserRole) + 1
DISABLED_BRUSH = QBrush(QColor("#9aa0a6"))



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


# ----------------------
# Stable node identity (no QModelIndex storage)
# -----------------------------
@dataclass(frozen=True)
class NodeKey:
    kind: str                 # "ex" | "st" | "grp_news" | "grp_social" | "grp_fin" | "src_news" | "src_social" | "src_fin"
    ex: Optional[str] = None
    ticker: Optional[str] = None
    idx: Optional[int] = None         # only for src_news
    name: Optional[str] = None        # only for social/fin named sources

    def parent_key(self) -> Optional["NodeKey"]:
        if self.kind == "ex":
            return None
        if self.kind == "st":
            return NodeKey("ex", ex=self.ex)
        if self.kind.startswith("grp_"):
            return NodeKey("st", ex=self.ex, ticker=self.ticker)
        if self.kind == "src_news":
            return NodeKey("grp_news", ex=self.ex, ticker=self.ticker)
        if self.kind == "src_social":
            return NodeKey("grp_social", ex=self.ex, ticker=self.ticker)
        if self.kind == "src_fin":
            return NodeKey("grp_fin", ex=self.ex, ticker=self.ticker)
        return None

# -----------------------------
# All config access + shared rules in one place
# -----------------------------
class ExchangeConfigFacade:
    def __init__(self, exchange_config: dict, apis_config: Optional[dict] = None, rss_config: Optional[dict] = None):
        self.exchange_config = exchange_config
        self.apis_config = apis_config or {}
        self.rss_config = rss_config or {}

    # ---- lookup ----
    def ex(self, ex_key: str) -> dict:
        return self.exchange_config[ex_key]

    def stock(self, ex_key: str, ticker_key: str) -> dict:
        return self.exchange_config[ex_key]["stocks"][ticker_key]

    def news_list(self, ex_key: str, ticker_key: str) -> List[dict]:
        return self.stock(ex_key, ticker_key).setdefault("news_sources", []) or []

    def social_map(self, ex_key: str, ticker_key: str) -> dict:
        return self.stock(ex_key, ticker_key).setdefault("social_sources", {}) or {}

    def fin_map(self, ex_key: str, ticker_key: str) -> dict:
        return self.stock(ex_key, ticker_key).setdefault("financial_sources", {}) or {}

    # ---- labels ----
    def ex_label(self, ex_key: str) -> str:
        ex = self.ex(ex_key)
        return f"{ex_key} - {ex.get('name', ex_key)}"

    def stock_label(self, ex_key: str, ticker_key: str) -> str:
        st = self.stock(ex_key, ticker_key)
        return f"{ticker_key} - {st.get('full_name', ticker_key)}"

    def news_label(self, ex_key: str, ticker_key: str, idx: int) -> str:
        lst = self.news_list(ex_key, ticker_key)
        if 0 <= idx < len(lst):
            return lst[idx].get("name") or f"news_{idx}"
        return f"news_{idx}"

    # ---- enable logic ----
    def ex_enabled(self, ex_key: str) -> bool:
        return bool(self.ex(ex_key).get("enabled", True))

    def stock_enabled(self, ex_key: str, ticker_key: str) -> bool:
        return bool(self.stock(ex_key, ticker_key).get("enabled", True))

    def stock_effective_enabled(self, ex_key: str, ticker_key: str) -> bool:
        return self.ex_enabled(ex_key) and self.stock_enabled(ex_key, ticker_key)

    def node_effective_enabled(self, key: NodeKey) -> bool:
        if key.kind == "ex":
            return self.ex_enabled(key.ex or "")
        if key.kind == "st":
            return self.stock_effective_enabled(key.ex or "", key.ticker or "")
        if key.kind.startswith("grp_"):
            return self.stock_effective_enabled(key.ex or "", key.ticker or "")

        if key.kind == "src_news":
            st_ok = self.stock_effective_enabled(key.ex or "", key.ticker or "")
            lst = self.news_list(key.ex or "", key.ticker or "")
            src = lst[key.idx] if (key.idx is not None and 0 <= key.idx < len(lst)) else {}
            return st_ok and bool(src.get("enabled", True))

        if key.kind == "src_social":
            st_ok = self.stock_effective_enabled(key.ex or "", key.ticker or "")
            src = self.social_map(key.ex or "", key.ticker or "").get(key.name or "", {})
            return st_ok and bool(src.get("enabled", True))

        if key.kind == "src_fin":
            st_ok = self.stock_effective_enabled(key.ex or "", key.ticker or "")
            src = self.fin_map(key.ex or "", key.ticker or "").get(key.name or "", {})
            return st_ok and bool(src.get("enabled", True))

        return True

    # ---- mutations: delete ----
    def delete_news_source(self, ex_key: str, ticker_key: str, idx: int) -> bool:
        lst = self.news_list(ex_key, ticker_key)
        if 0 <= idx < len(lst):
            lst.pop(idx)
            return True
        return False

    def delete_social_source(self, ex_key: str, ticker_key: str, name: str) -> bool:
        m = self.social_map(ex_key, ticker_key)
        if name in m:
            del m[name]
            return True
        return False

    def delete_fin_source(self, ex_key: str, ticker_key: str, name: str) -> bool:
        m = self.fin_map(ex_key, ticker_key)
        if name in m:
            del m[name]
            return True
        return False

    # ---- mutations: add ----
    def add_stock(self, ex_key: str, ticker_key: str, full_name: str = "") -> None:
        ex = self.ex(ex_key)
        stocks = ex.setdefault("stocks", {}) or {}
        if ticker_key in stocks:
            raise KeyError(f"Stock '{ticker_key}' already exists")

        stocks[ticker_key] = {
            "ticker": ticker_key,
            "full_name": full_name,
            "enabled": True,
            "social_sources": {},
            "news_sources": [],
            "financial_sources": {},
        }

    def add_news_source(self, ex_key: str, ticker_key: str) -> int:
        stock = self.stock(ex_key, ticker_key)
        # Ensure news_sources exists as a list
        if "news_sources" not in stock:
            stock["news_sources"] = []
        lst = stock["news_sources"]
        if not isinstance(lst, list):
            stock["news_sources"] = []
            lst = stock["news_sources"]
        
        idx = len(lst)
        lst.append({
            "name": f"news_{idx}",
            "type": "rss",
            "enabled": True,
            "url": "",
            "query": "",
            "api_name": "",
        })
        return idx

    def add_social_source(self, ex_key: str, ticker_key: str, name: str) -> None:
        stock = self.stock(ex_key, ticker_key)
        # Ensure social_sources exists as a dict
        if "social_sources" not in stock:
            stock["social_sources"] = {}
        m = stock["social_sources"]
        if not isinstance(m, dict):
            stock["social_sources"] = {}
            m = stock["social_sources"]
        
        if name in m:
            raise KeyError(f"Social source '{name}' already exists")
        m[name] = {"enabled": True}

    def add_fin_source(self, ex_key: str, ticker_key: str, name: str) -> None:
        stock = self.stock(ex_key, ticker_key)
        # Ensure financial_sources exists as a dict
        if "financial_sources" not in stock:
            stock["financial_sources"] = {}
        m = stock["financial_sources"]
        if not isinstance(m, dict):
            stock["financial_sources"] = {}
            m = stock["financial_sources"]
        
        if name in m:
            raise KeyError(f"Financial source '{name}' already exists")
        m[name] = {"enabled": True}

# -----------------------------
# Model builder (centralized styling + item creation)
# Always render the group nodes even when empty.
# -----------------------------
class ExchangeTreeModelBuilder:
    def __init__(self, facade: ExchangeConfigFacade):
        self.f = facade

    def build(self) -> QStandardItemModel:
        model = QStandardItemModel()
        model.setHorizontalHeaderLabels(["Exchanges"])

        root = model.invisibleRootItem()
        exchanges = self.f.exchange_config or {}

        for ex_key in sorted(exchanges.keys()):
            ex_item = self._mk_item(self.f.ex_label(ex_key), NodeKey("ex", ex=ex_key))
            root.appendRow(ex_item)

            stocks = (self.f.ex(ex_key).get("stocks", {}) or {})
            for ticker_key in sorted(stocks.keys()):
                st_item = self._mk_item(self.f.stock_label(ex_key, ticker_key), NodeKey("st", ex=ex_key, ticker=ticker_key))
                ex_item.appendRow(st_item)

                # Always create all groups (even if empty)
                grp_social = self._mk_item("Social sources", NodeKey("grp_social", ex=ex_key, ticker=ticker_key))
                st_item.appendRow(grp_social)

                grp_news = self._mk_item("News sources", NodeKey("grp_news", ex=ex_key, ticker=ticker_key))
                st_item.appendRow(grp_news)

                grp_fin = self._mk_item("Financial sources", NodeKey("grp_fin", ex=ex_key, ticker=ticker_key))
                st_item.appendRow(grp_fin)

                # Fill group children (if any)
                social = self.f.social_map(ex_key, ticker_key)
                for src_name in sorted(social.keys()):
                    grp_social.appendRow(self._mk_item(src_name, NodeKey("src_social", ex=ex_key, ticker=ticker_key, name=src_name)))

                news = self.f.news_list(ex_key, ticker_key)
                for idx in range(len(news)):
                    grp_news.appendRow(self._mk_item(self.f.news_label(ex_key, ticker_key, idx), NodeKey("src_news", ex=ex_key, ticker=ticker_key, idx=idx)))

                fin = self.f.fin_map(ex_key, ticker_key)
                for src_name in sorted(fin.keys()):
                    grp_fin.appendRow(self._mk_item(src_name, NodeKey("src_fin", ex=ex_key, ticker=ticker_key, name=src_name)))

        return model

    def _mk_item(self, text: str, key: NodeKey) -> QStandardItem:
        it = QStandardItem(text)
        it.setEditable(False)
        it.setData(key, ROLE_KEY)
        enabled = self.f.node_effective_enabled(key)
        it.setData(None if enabled else DISABLED_BRUSH, int(Qt.ItemDataRole.ForegroundRole))
        return it

# -----------------------------
# Left panel: QTreeView + model + selection signal + context menu
# -----------------------------
class ExchangeTreePanel(QWidget):
    nodeSelected = pyqtSignal(object)          # NodeKey
    actionRequested = pyqtSignal(str, object)  # action: str, key: NodeKey

    def __init__(self, parent: QWidget, facade: ExchangeConfigFacade):
        super().__init__(parent)
        self.f = facade
        self.view = QTreeView(self)
        self.view.setHeaderHidden(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.view, 1)

        self._builder = ExchangeTreeModelBuilder(self.f)
        self.model: Optional[QStandardItemModel] = None

        # context menu on QTreeView via CustomContextMenuRequested
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._on_context_menu)

        self.rebuild(select_key=None)

    def rebuild(self, select_key: Optional[NodeKey]):
        self.model = self._builder.build()
        self.view.setModel(self.model)
        self.view.expandToDepth(0)

        # Reconnect because selectionModel changes with the model
        self.view.selectionModel().currentChanged.connect(self._on_current_changed)

        if select_key:
            self.select(select_key)

    def select(self, key: NodeKey) -> bool:
        if not self.model:
            return False

        matches = self.model.match(
            self.model.index(0, 0),
            ROLE_KEY,
            key,
            hits=1,
            flags=Qt.MatchFlag.MatchRecursive | Qt.MatchFlag.MatchExactly,
        )
        if not matches:
            return False

        idx = matches[0]
        self.view.setCurrentIndex(idx)
        self.view.scrollTo(idx)
        return True

    def _on_current_changed(self, current, _previous):
        if not current.isValid() or not self.model:
            return
        key = self.model.data(current, ROLE_KEY)
        if isinstance(key, NodeKey):
            self.nodeSelected.emit(key)

    def _on_context_menu(self, pos):
        if not self.model:
            return

        idx = self.view.indexAt(pos)
        if not idx.isValid():
            return

        # keep selection consistent with what was right-clicked
        self.view.setCurrentIndex(idx)

        key = self.model.data(idx, ROLE_KEY)
        if not isinstance(key, NodeKey):
            return

        # Requirement: no menu on stock node
        if key.kind == "st":
            return

        menu = QMenu(self.view)

        if key.kind == "ex":
            act = menu.addAction("Add stock")
            act.triggered.connect(lambda _=False, k=key: self.actionRequested.emit("add_stock", k))

        elif key.kind in ("grp_news", "src_news"):
            act = menu.addAction("Add news source")
            act.triggered.connect(lambda _=False, k=key: self.actionRequested.emit("add_news", k))

        elif key.kind in ("grp_social", "src_social"):
            act = menu.addAction("Add social source")
            act.triggered.connect(lambda _=False, k=key: self.actionRequested.emit("add_social", k))

        elif key.kind in ("grp_fin", "src_fin"):
            act = menu.addAction("Add financial source")
            act.triggered.connect(lambda _=False, k=key: self.actionRequested.emit("add_fin", k))

        else:
            return

        menu.exec(self.view.viewport().mapToGlobal(pos))

# -----------------------------
# Editor base: shared UI pieces
# -----------------------------
class BaseEditor(QWidget):
    saved = pyqtSignal(object)    # NodeKey (or another key to reselect)
    deleted = pyqtSignal(object)  # NodeKey (usually parent to reselect)

    def __init__(self, parent: QWidget, facade: ExchangeConfigFacade):
        super().__init__(parent)
        self.f = facade
        self._key: Optional[NodeKey] = None

        self._v = QVBoxLayout(self)
        self._v.setContentsMargins(10, 10, 10, 10)
        self._v.setSpacing(12)

        self.title = QLabel("", self)
        fnt = self.title.font()
        fnt.setPointSize(13)
        fnt.setBold(True)
        self.title.setFont(fnt)
        self._v.addWidget(self.title)

        self.form = QFormLayout()
        self._v.addLayout(self.form)

        self._btn_row = QHBoxLayout()
        self._v.addLayout(self._btn_row)
        self._btn_row.addStretch(1)

        self._v.addStretch(1)

    def set_title(self, text: str):
        self.title.setText(text)

    def clear_buttons(self):
        while self._btn_row.count():
            it = self._btn_row.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        self._btn_row.addStretch(1)

    @staticmethod
    def word_limit_ok(text: str, max_words: int) -> bool:
        return (not text) or (len(text.split()) <= max_words)

# -----------------------------
# Exchange editor
# -----------------------------
class ExchangeEditor(BaseEditor):
    def __init__(self, parent: QWidget, facade: ExchangeConfigFacade, save_config_cb):
        super().__init__(parent, facade)
        self._save_config_cb = save_config_cb

        self.name_in = QLineEdit(self)
        self.symbol_in = QLineEdit(self)
        self.enabled_in = QCheckBox("Enabled", self)

        self.tz_in = QComboBox(self)
        tz_ids = [bytes(z).decode("utf-8", "ignore") for z in QTimeZone.availableTimeZoneIds()]
        tz_ids.sort()
        self.tz_in.addItems(tz_ids)

        self.form.addRow("Name", self.name_in)
        self.form.addRow("Symbol", self.symbol_in)
        self.form.addRow("Timezone", self.tz_in)
        self.form.addRow("", self.enabled_in)

        self.save_btn = QPushButton("Save exchange", self)
        self._btn_row.addWidget(self.save_btn)
        self.save_btn.clicked.connect(self._on_save)

    def load(self, key: NodeKey):
        self._key = key
        ex = self.f.ex(key.ex or "")

        self.set_title(f"Exchange: {key.ex}")
        self.name_in.setText(ex.get("name", ""))
        self.symbol_in.setText(ex.get("symbol", ""))
        self.enabled_in.setChecked(bool(ex.get("enabled", True)))

        cur_tz = ex.get("timezone", "UTC")
        if self.tz_in.findText(cur_tz) >= 0:
            self.tz_in.setCurrentText(cur_tz)
        else:
            self.tz_in.insertItem(0, cur_tz)
            self.tz_in.setCurrentIndex(0)

    def _on_save(self):
        if not self._key:
            return
        ex = self.f.ex(self._key.ex or "")
        ex["name"] = self.name_in.text().strip()
        ex["symbol"] = self.symbol_in.text().strip()
        ex["timezone"] = self.tz_in.currentText().strip()
        ex["enabled"] = bool(self.enabled_in.isChecked())

        self._save_config_cb()
        QMessageBox.information(self, "Saved", "Exchange updated.")
        self.saved.emit(self._key)

# -----------------------------
# Stock editor
# -----------------------------
class StockEditor(BaseEditor):
    def __init__(self, parent: QWidget, facade: ExchangeConfigFacade, save_config_cb):
        super().__init__(parent, facade)
        self._save_config_cb = save_config_cb

        self.ticker_in = QLineEdit(self)
        self.full_name_in = QLineEdit(self)
        self.enabled_in = QCheckBox("Enabled", self)

        self.form.addRow("Ticker", self.ticker_in)
        self.form.addRow("Full name", self.full_name_in)
        self.form.addRow("", self.enabled_in)

        self.save_btn = QPushButton("Save stock", self)
        self._btn_row.addWidget(self.save_btn)
        self.save_btn.clicked.connect(self._on_save)

    def load(self, key: NodeKey):
        self._key = key
        st = self.f.stock(key.ex or "", key.ticker or "")

        self.set_title(f"Stock: {key.ex} / {key.ticker}")
        self.ticker_in.setText(st.get("ticker", key.ticker))
        self.full_name_in.setText(st.get("full_name", ""))
        self.enabled_in.setChecked(bool(st.get("enabled", True)))

    def _on_save(self):
        if not self._key:
            return
        st = self.f.stock(self._key.ex or "", self._key.ticker or "")
        st["ticker"] = self.ticker_in.text().strip()
        st["full_name"] = self.full_name_in.text().strip()
        st["enabled"] = bool(self.enabled_in.isChecked())

        self._save_config_cb()
        QMessageBox.information(self, "Saved", "Stock updated.")
        self.saved.emit(self._key)

# -----------------------------
# News source editor (list-based)
# -----------------------------
# -----------------------------
# News source editor (list-based) - hide URL field when type is "api"
# -----------------------------
class NewsSourceEditor(BaseEditor):
    def __init__(self, parent: QWidget, facade: ExchangeConfigFacade, save_config_cb):
        super().__init__(parent, facade)
        self._save_config_cb = save_config_cb

        self.enabled_in = QCheckBox("Enabled", self)

        self.type_in = QComboBox(self)
        self.type_in.setEditable(False)
        self.type_in.addItems(["rss", "api"])

        # Make editable so empty rss_config/apis_config doesn't block user input
        self.name_in = QComboBox(self)
        self.name_in.setEditable(True)

        # URL row (label + field) - will be hidden when type is "api"
        self.url_label = QLabel("URL (rss)", self)
        self.url_in = QLineEdit(self)
        self.url_in.setMaxLength(800)

        self.query_in = QLineEdit(self)
        self.query_in.setMaxLength(800)

        self.form.addRow("", self.enabled_in)
        self.form.addRow("Type", self.type_in)
        self.form.addRow("Name (RSS/API_NAME)", self.name_in)
        self.form.addRow(self.url_label, self.url_in)
        self.form.addRow("Query (<=100 words)", self.query_in)

        self.delete_btn = QPushButton("Delete news source", self)
        self.save_btn = QPushButton("Save news source", self)
        self._btn_row.insertWidget(0, self.delete_btn)  # before stretch
        self._btn_row.addWidget(self.save_btn)

        self.type_in.currentTextChanged.connect(self._on_type_changed)
        self.save_btn.clicked.connect(self._on_save)
        self.delete_btn.clicked.connect(self._on_delete)

    def load(self, key: NodeKey):
        self._key = key
        self.set_title(f"News source: {key.ex} / {key.ticker} / #{key.idx}")

        lst = self.f.news_list(key.ex or "", key.ticker or "")
        if key.idx is None or not (0 <= key.idx < len(lst)):
            # show empty state (keep editor usable)
            self.enabled_in.setChecked(False)
            self.type_in.setCurrentText("rss")
            self.name_in.clear()
            self.url_in.setText("")
            self.query_in.setText("")
            self._update_url_visibility()
            return

        src = lst[key.idx]
        self.enabled_in.setChecked(bool(src.get("enabled", True)))

        cur_type = (src.get("type", "rss") or "rss").strip()
        self.type_in.setCurrentText(cur_type if cur_type in ("rss", "api") else "rss")

        self.url_in.setText(src.get("url", ""))
        self.query_in.setText(src.get("query", ""))

        self._repopulate_name_dropdown()

        # name: for "api", try api_name fallback; otherwise src["name"]
        cur_name = (src.get("api_name") if self.type_in.currentText() == "api" else src.get("name")) or src.get("name", "")
        cur_name = (cur_name or "").strip()
        if cur_name:
            if self.name_in.findText(cur_name) >= 0:
                self.name_in.setCurrentText(cur_name)
            else:
                # editable combo: just set text
                self.name_in.setCurrentText(cur_name)

        self._update_url_visibility()

    def _on_type_changed(self):
        self._repopulate_name_dropdown()
        self._update_url_visibility()

    def _update_url_visibility(self):
        """Hide URL field when type is 'api', show when 'rss'."""
        is_rss = self.type_in.currentText().strip() == "rss"
        self.url_label.setVisible(is_rss)
        self.url_in.setVisible(is_rss)

    def _repopulate_name_dropdown(self):
        self.name_in.blockSignals(True)
        current = self.name_in.currentText()
        self.name_in.clear()

        t = self.type_in.currentText().strip()
        if t == "api":
            names = sorted(list((self.f.apis_config or {}).keys()))
        else:
            names = sorted(list((self.f.rss_config or {}).keys()))

        if names:
            self.name_in.addItems(names)

        # restore typed text in editable combo
        if current:
            self.name_in.setCurrentText(current)

        self.name_in.blockSignals(False)

    def _on_save(self):
        if not self._key:
            return
        q = self.query_in.text().strip()
        if not self.word_limit_ok(q, 100):
            QMessageBox.warning(self, "Invalid query", "Query too long (max 100 words).")
            return

        lst = self.f.news_list(self._key.ex or "", self._key.ticker or "")
        if self._key.idx is None or not (0 <= self._key.idx < len(lst)):
            QMessageBox.warning(self, "Invalid", "This news source no longer exists.")
            return

        src = lst[self._key.idx]
        src["enabled"] = bool(self.enabled_in.isChecked())
        src["type"] = self.type_in.currentText().strip()

        name_txt = self.name_in.currentText().strip()
        if src["type"] == "api":
            src["api_name"] = name_txt
            # keep "name" as display label if user previously set it; otherwise mirror api_name
            src["name"] = (src.get("name") or name_txt).strip()
        else:
            src["name"] = name_txt
            src["url"] = self.url_in.text().strip()

        src["query"] = q

        self._save_config_cb()
        QMessageBox.information(self, "Saved", "News source updated.")
        self.saved.emit(self._key)

    def _on_delete(self):
        if not self._key:
            return
        reply = QMessageBox.question(self, "Confirm delete", f"Delete this news source (#{self._key.idx})?")
        if reply != QMessageBox.StandardButton.Yes:
            return

        ok = self.f.delete_news_source(self._key.ex or "", self._key.ticker or "", int(self._key.idx or -1))
        parent = self._key.parent_key() or NodeKey("grp_news", ex=self._key.ex, ticker=self._key.ticker)

        self._save_config_cb()
        QMessageBox.information(self, "Deleted", "News source deleted." if ok else "This news source no longer exists.")
        # Re-select parent group; rebuild will re-index remaining items safely.
        self.deleted.emit(parent)

# -----------------------------
# Dict source editor (social / financial)
# -----------------------------
class DictSourceEditor(BaseEditor):
    """
    Generic editor for src_social and src_fin (dict-based).
    Keeps it simple: enabled + JSON body for the remaining fields.
    """
    def __init__(self, parent: QWidget, facade: ExchangeConfigFacade, save_config_cb, kind: str):
        super().__init__(parent, facade)
        self._save_config_cb = save_config_cb
        self._kind = kind  # "social" or "fin"

        self.enabled_in = QCheckBox("Enabled", self)
        self.form.addRow("", self.enabled_in)

        self.form.addRow("Config JSON (excluding 'enabled')", QLabel("", self))
        self.json_in = QPlainTextEdit(self)
        self.json_in.setMinimumHeight(160)
        self._v.insertWidget(3, self.json_in)  # after form; before button row

        self.delete_btn = QPushButton("Delete source", self)
        self.save_btn = QPushButton("Save source", self)
        self._btn_row.insertWidget(0, self.delete_btn)
        self._btn_row.addWidget(self.save_btn)

        self.save_btn.clicked.connect(self._on_save)
        self.delete_btn.clicked.connect(self._on_delete)

    def _map(self, ex_key: str, ticker_key: str) -> dict:
        return self.f.social_map(ex_key, ticker_key) if self._kind == "social" else self.f.fin_map(ex_key, ticker_key)

    def load(self, key: NodeKey):
        self._key = key
        ex_key, ticker_key, name = key.ex or "", key.ticker or "", key.name or ""

        m = self._map(ex_key, ticker_key)
        src = m.get(name)
        if not isinstance(src, dict):
            self.set_title("Source not found")
            self.enabled_in.setChecked(False)
            self.json_in.setPlainText("{}")
            return

        title_kind = "Social" if self._kind == "social" else "Financial"
        self.set_title(f"{title_kind} source: {ex_key} / {ticker_key} / {name}")

        self.enabled_in.setChecked(bool(src.get("enabled", True)))
        raw = {k: v for k, v in src.items() if k != "enabled"}
        self.json_in.setPlainText(json.dumps(raw, indent=2))

    def _on_save(self):
        if not self._key:
            return
        ex_key, ticker_key, name = self._key.ex or "", self._key.ticker or "", self._key.name or ""

        txt = self.json_in.toPlainText().strip()
        try:
            data = json.loads(txt) if txt else {}
            if not isinstance(data, dict):
                raise ValueError("JSON must be an object.")
        except Exception as e:
            QMessageBox.warning(self, "Invalid JSON", f"Could not parse JSON: {e}")
            return

        m = self._map(ex_key, ticker_key)
        if name not in m:
            QMessageBox.warning(self, "Invalid", "This source no longer exists.")
            self.deleted.emit(self._key.parent_key() or NodeKey("st", ex=ex_key, ticker=ticker_key))
            return

        new_src = dict(data)
        new_src["enabled"] = bool(self.enabled_in.isChecked())
        m[name] = new_src

        self._save_config_cb()
        QMessageBox.information(self, "Saved", "Source updated.")
        self.saved.emit(self._key)

    def _on_delete(self):
        if not self._key:
            return
        ex_key, ticker_key, name = self._key.ex or "", self._key.ticker or "", self._key.name or ""

        reply = QMessageBox.question(self, "Confirm delete", f"Delete source '{name}'?")
        if reply != QMessageBox.StandardButton.Yes:
            return

        ok = self.f.delete_social_source(ex_key, ticker_key, name) if self._kind == "social" else self.f.delete_fin_source(ex_key, ticker_key, name)

        self._save_config_cb()
        QMessageBox.information(self, "Deleted", "Source deleted." if ok else "This source no longer exists.")
        self.deleted.emit(self._key.parent_key() or NodeKey("st", ex=ex_key, ticker=ticker_key))

# -----------------------------
# Screen/controller: wiring only + add actions
# -----------------------------
class ExchangesScreen(Screen):
    def __init__(self, parent: QWidget, _save_config, exchange_config=None, apis_config=None, rss_config=None):
        super().__init__(parent)

        self.exchange_config = exchange_config or {}
        self.apis_config = apis_config or {}
        self.rss_config = rss_config or {}

        self._save_config = _save_config
        self.f = ExchangeConfigFacade(self.exchange_config, apis_config=self.apis_config, rss_config=self.rss_config)

        self._ui_built = False

        # created in _build_ui_once()
        self.tree_panel: Optional[ExchangeTreePanel] = None
        self.stack: Optional[QStackedWidget] = None
        self.blank: Optional[QLabel] = None
        self.ex_editor: Optional[ExchangeEditor] = None
        self.st_editor: Optional[StockEditor] = None
        self.news_editor: Optional[NewsSourceEditor] = None
        self.social_editor: Optional[DictSourceEditor] = None
        self.fin_editor: Optional[DictSourceEditor] = None

    def setup(self, title, subtitle):
        super().setup(title, subtitle)

        if self.exchange_config is None:
            QMessageBox.warning(self.frame, "Warning", "exchange_config is missing.")
            return

        if not self._ui_built:
            self._build_ui_once()
            self._ui_built = True

        # ensure model reflects latest config
        assert self.tree_panel is not None
        assert self.stack is not None
        assert self.blank is not None

        self.tree_panel.rebuild(select_key=None)
        self.stack.setCurrentWidget(self.blank)

    def _build_ui_once(self):
        lay = QHBoxLayout(self.body)
        lay.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal, self.body)
        lay.addWidget(splitter, 1)

        # left
        self.tree_panel = ExchangeTreePanel(splitter, self.f)

        # right
        right = QWidget(splitter)
        right_l = QVBoxLayout(right)
        right_l.setContentsMargins(0, 0, 0, 0)

        self.stack = QStackedWidget(right)
        right_l.addWidget(self.stack, 1)

        self.blank = QLabel("Select an item on the left", right)
        self.blank.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.ex_editor = ExchangeEditor(right, self.f, self._save_config)
        self.st_editor = StockEditor(right, self.f, self._save_config)
        self.news_editor = NewsSourceEditor(right, self.f, self._save_config)
        self.social_editor = DictSourceEditor(right, self.f, self._save_config, kind="social")
        self.fin_editor = DictSourceEditor(right, self.f, self._save_config, kind="fin")

        self.stack.addWidget(self.blank)
        self.stack.addWidget(self.ex_editor)
        self.stack.addWidget(self.st_editor)
        self.stack.addWidget(self.news_editor)
        self.stack.addWidget(self.social_editor)
        self.stack.addWidget(self.fin_editor)
        self.stack.setCurrentWidget(self.blank)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        # wiring (only once)
        self.tree_panel.nodeSelected.connect(self._on_node_selected)
        self.tree_panel.actionRequested.connect(self._on_tree_action)

        for ed in (self.ex_editor, self.st_editor, self.news_editor, self.social_editor, self.fin_editor):
            ed.saved.connect(self._on_editor_saved)
            ed.deleted.connect(self._on_editor_deleted)

    def _on_node_selected(self, key: NodeKey):
        assert self.stack is not None
        assert self.blank is not None
        assert self.ex_editor is not None
        assert self.st_editor is not None
        assert self.news_editor is not None
        assert self.social_editor is not None
        assert self.fin_editor is not None

        if key.kind == "ex":
            self.ex_editor.load(key)
            self.stack.setCurrentWidget(self.ex_editor)
        elif key.kind == "st":
            self.st_editor.load(key)
            self.stack.setCurrentWidget(self.st_editor)
        elif key.kind == "src_news":
            self.news_editor.load(key)
            self.stack.setCurrentWidget(self.news_editor)
        elif key.kind == "src_social":
            self.social_editor.load(key)
            self.stack.setCurrentWidget(self.social_editor)
        elif key.kind == "src_fin":
            self.fin_editor.load(key)
            self.stack.setCurrentWidget(self.fin_editor)
        else:
            # groups or unknown nodes
            self.stack.setCurrentWidget(self.blank)

    def _on_editor_saved(self, reselect_key: NodeKey):
        assert self.tree_panel is not None
        self.tree_panel.rebuild(select_key=reselect_key)

    def _on_editor_deleted(self, reselect_key: NodeKey):
        assert self.tree_panel is not None
        assert self.stack is not None
        assert self.blank is not None

        self.tree_panel.rebuild(select_key=reselect_key)
        if not self.tree_panel.select(reselect_key):
            self.stack.setCurrentWidget(self.blank)

    # ---------- context menu actions ----------
    def _on_tree_action(self, action: str, key: NodeKey):
        assert self.tree_panel is not None

        if action == "add_stock" and key.kind == "ex":
            ticker, ok = QInputDialog.getText(self.frame, "Add stock", "Stock key (e.g. RELIANCE):")
            if not ok:
                return
            ticker = (ticker or "").strip().upper()
            if not ticker:
                return

            full, ok2 = QInputDialog.getText(self.frame, "Add stock", "Full name (optional):")
            if not ok2:
                return
            full = (full or "").strip()

            try:
                self.f.add_stock(key.ex or "", ticker, full)
            except KeyError as e:
                QMessageBox.warning(self.frame, "Already exists", str(e))
                return

            self._save_config()
            self.tree_panel.rebuild(select_key=NodeKey("st", ex=key.ex, ticker=ticker))
            return

        # For sources: handle both group nodes (grp_news, grp_social, grp_fin) 
        # and existing source nodes (src_news, src_social, src_fin)
        if action in ("add_news", "add_social", "add_fin"):
            ex_key = key.ex
            ticker_key = key.ticker
            
            # Validate we have the required parent references
            if not ex_key or not ticker_key:
                QMessageBox.warning(self.frame, "Error", "Cannot determine parent stock for this action.")
                return

            # Verify the stock actually exists in config
            try:
                stock = self.f.stock(ex_key, ticker_key)
            except (KeyError, AttributeError):
                QMessageBox.warning(self.frame, "Error", f"Stock {ticker_key} not found in {ex_key}.")
                return

            if action == "add_news":
                try:
                    idx = self.f.add_news_source(ex_key, ticker_key)
                    self._save_config()
                    self.tree_panel.rebuild(select_key=NodeKey("src_news", ex=ex_key, ticker=ticker_key, idx=idx))
                except Exception as e:
                    QMessageBox.warning(self.frame, "Error", f"Failed to add news source: {e}")
                return

            if action == "add_social":
                name, ok = QInputDialog.getText(self.frame, "Add social source", "Source name (e.g. twitter, reddit):")
                if not ok:
                    return
                name = (name or "").strip()
                if not name:
                    return
                try:
                    self.f.add_social_source(ex_key, ticker_key, name)
                    self._save_config()
                    self.tree_panel.rebuild(select_key=NodeKey("src_social", ex=ex_key, ticker=ticker_key, name=name))
                except KeyError as e:
                    QMessageBox.warning(self.frame, "Already exists", str(e))
                except Exception as e:
                    QMessageBox.warning(self.frame, "Error", f"Failed to add social source: {e}")
                return

            if action == "add_fin":
                name, ok = QInputDialog.getText(self.frame, "Add financial source", "Source name (e.g. yfinance):")
                if not ok:
                    return
                name = (name or "").strip()
                if not name:
                    return
                try:
                    self.f.add_fin_source(ex_key, ticker_key, name)
                    self._save_config()
                    self.tree_panel.rebuild(select_key=NodeKey("src_fin", ex=ex_key, ticker=ticker_key, name=name))
                except KeyError as e:
                    QMessageBox.warning(self.frame, "Already exists", str(e))
                except Exception as e:
                    QMessageBox.warning(self.frame, "Error", f"Failed to add financial source: {e}")
                return


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



