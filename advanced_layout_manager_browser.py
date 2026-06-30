# -*- coding: utf-8 -*-
"""
Advanced Layout Manager Browser
----------------------

A local QGIS plugin that adds a right dock panel for organising print layouts
into custom groups and subgroups.

"""

import json
import os
import re

try:
    from qgis.PyQt.QtGui import QAction, QIcon, QColor, QBrush
except Exception:  # pragma: no cover - kept for unusual Qt bindings
    from qgis.PyQt.QtWidgets import QAction
    from qgis.PyQt.QtGui import QIcon, QColor, QBrush

from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from qgis.core import (
    QgsLayoutExporter,
    QgsPrintLayout,
    QgsProject,
)


PLUGIN_MENU_NAME = "&Advanced Layout Manager Browser"
PLUGIN_PROJECT_KEY = "AdvancedLayoutManagerBrowser"
ENTRY_LAYOUT_GROUPS = "layout_to_group_json"
ENTRY_FAVOURITES = "favourite_layouts_json"
ENTRY_GROUP_COLOURS = "group_colours_json"

UNGROUPED_NAME = "Ungrouped"
FAVOURITES_NAME = "Favourites"
GROUP_SEPARATOR = "/"

ITEM_GROUP = "group"
ITEM_LAYOUT = "layout"
ITEM_SPECIAL = "special"

GROUP_COLOURS = {
    "None": None,
    "Green": "#6fad83",
    "Blue": "#7fa7c7",
    "Orange": "#d6a15f",
    "Purple": "#a98bc7",
    "Grey": "#9ba3a0",
}


# ---------------------------------------------------------------------
# Qt compatibility helpers
# ---------------------------------------------------------------------

def _exec_dialog(dialog):
    """Run a dialog in a Qt5/Qt6-compatible way."""
    if hasattr(dialog, "exec"):
        return dialog.exec()
    return dialog.exec_()


def _exec_menu(menu, global_pos):
    """Run a menu in a Qt5/Qt6-compatible way."""
    if hasattr(menu, "exec"):
        return menu.exec(global_pos)
    return menu.exec_(global_pos)


def _qt_enum(scope_name, enum_name):
    """Return a Qt enum value compatible with both Qt5 and Qt6."""
    scope = getattr(Qt, scope_name, None)
    if scope is not None and hasattr(scope, enum_name):
        return getattr(scope, enum_name)
    if hasattr(Qt, enum_name):
        return getattr(Qt, enum_name)
    raise AttributeError(f"Qt enum not found: {scope_name}.{enum_name}")


def _class_enum(cls, scope_name, enum_name):
    """Return a class enum value compatible with both Qt5 and Qt6."""
    scope = getattr(cls, scope_name, None)
    if scope is not None and hasattr(scope, enum_name):
        return getattr(scope, enum_name)
    if hasattr(cls, enum_name):
        return getattr(cls, enum_name)
    raise AttributeError(f"Enum not found: {cls.__name__}.{scope_name}.{enum_name}")


def _enum_to_int(value):
    """Convert Qt enum values to int when an integer role is required."""
    if hasattr(value, "value"):
        return int(value.value)
    return int(value)


def _item_role(offset=0):
    """Return ROLE_TYPE + offset in a Qt5/Qt6-compatible way."""
    return _enum_to_int(_qt_enum("ItemDataRole", "UserRole")) + offset


def _qt_flag(*flags):
    """Combine Qt flags safely for Qt5 and Qt6."""
    result = flags[0]
    for flag in flags[1:]:
        result |= flag
    return result


def _dialog_accepted():
    return _class_enum(QDialog, "DialogCode", "Accepted")


def _messagebox_button(name):
    return _class_enum(QMessageBox, "StandardButton", name)


def _dialog_buttonbox_button(name):
    return _class_enum(QDialogButtonBox, "StandardButton", name)


QT_CUSTOM_CONTEXT_MENU = _qt_enum("ContextMenuPolicy", "CustomContextMenu")
QT_MOVE_ACTION = _qt_enum("DropAction", "MoveAction")
QT_LEFT_DOCK_AREA = _qt_enum("DockWidgetArea", "LeftDockWidgetArea")

QT_ITEM_ENABLED = _qt_enum("ItemFlag", "ItemIsEnabled")
QT_ITEM_SELECTABLE = _qt_enum("ItemFlag", "ItemIsSelectable")
QT_ITEM_DROP_ENABLED = _qt_enum("ItemFlag", "ItemIsDropEnabled")
QT_ITEM_EDITABLE = _qt_enum("ItemFlag", "ItemIsEditable")
QT_ITEM_DRAG_ENABLED = _qt_enum("ItemFlag", "ItemIsDragEnabled")

TREE_EXTENDED_SELECTION = _class_enum(QAbstractItemView, "SelectionMode", "ExtendedSelection")
TREE_INTERNAL_MOVE = _class_enum(QAbstractItemView, "DragDropMode", "InternalMove")

ROLE_TYPE = _item_role(0)
ROLE_VALUE = _item_role(1)


# ---------------------------------------------------------------------
# Plugin entry point
# ---------------------------------------------------------------------

class AdvancedLayoutManagerBrowserPlugin:
    """Main QGIS plugin class."""

    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.dock = None

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(__file__), "icon.svg")

        self.action = QAction("Advanced Layout Manager Browser", self.iface.mainWindow())
        self.action.setObjectName("AdvancedLayoutManagerBrowserAction")

        if os.path.exists(icon_path):
            self.action.setIcon(QIcon(icon_path))

        self.action.triggered.connect(self.show_dock)

        self.iface.addPluginToMenu(PLUGIN_MENU_NAME, self.action)
        self.iface.addToolBarIcon(self.action)

    def unload(self):
        if self.action:
            self.iface.removePluginMenu(PLUGIN_MENU_NAME, self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action = None

        if self.dock:
            self.iface.removeDockWidget(self.dock)
            self.dock.deleteLater()
            self.dock = None

    def _tabify_with_available_dock(self):
        main_window = self.iface.mainWindow()

        preferred_titles = [
            "browser",
            "layers",
            "layer styling",
        ]

        docks = main_window.findChildren(QDockWidget)

        # First try common visible panels
        for preferred in preferred_titles:
            for dock in docks:
                if dock is self.dock:
                    continue

                title = dock.windowTitle().lower()
                name = dock.objectName().lower()

                if dock.isVisible() and (preferred in title or preferred in name):
                    main_window.tabifyDockWidget(dock, self.dock)
                    self.dock.raise_()
                    return True

        # Fallback: tabify with any visible dock
        for dock in docks:
            if dock is self.dock:
                continue

            if dock.isVisible():
                main_window.tabifyDockWidget(dock, self.dock)
                self.dock.raise_()
                return True

        return False
    
    def show_dock(self):
        if self.dock is None:
            self.dock = AdvancedLayoutManagerBrowserDock(self.iface)
            self.iface.addDockWidget(QT_LEFT_DOCK_AREA, self.dock)
            self._tabify_with_available_dock()

        self.dock.show()
        self.dock.raise_()


# ---------------------------------------------------------------------
# Custom tree widget
# ---------------------------------------------------------------------

class LayoutTreeWidget(QTreeWidget):
    """Tree widget that only allows layouts to be dropped into real groups."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.drop_finished_callback = None

    def _event_pos(self, event):
        if hasattr(event, "position"):
            return event.position().toPoint()
        return event.pos()

    def _selected_items_are_layouts(self):
        return bool(self.selectedItems()) and all(
            item.data(0, ROLE_TYPE) == ITEM_LAYOUT
            for item in self.selectedItems()
        )

    def _drop_target_is_valid_group(self, event):
        target_item = self.itemAt(self._event_pos(event))
        if target_item is None:
            return False

        return target_item.data(0, ROLE_TYPE) == ITEM_GROUP

    def dragMoveEvent(self, event):
        if self._selected_items_are_layouts() and self._drop_target_is_valid_group(event):
            event.accept()
            super().dragMoveEvent(event)
            return

        event.ignore()

    def dropEvent(self, event):
        if not self._selected_items_are_layouts() or not self._drop_target_is_valid_group(event):
            event.ignore()
            return

        super().dropEvent(event)

        if callable(self.drop_finished_callback):
            QTimer.singleShot(0, self.drop_finished_callback)
            
# ---------------------------------------------------------------------
# Dock widget
# ---------------------------------------------------------------------


class AdvancedLayoutManagerBrowserDock(QDockWidget):
    """Right dock panel for grouped QGIS print layouts."""

    def __init__(self, iface):
        super().__init__("Advanced Layout Manager Browser", iface.mainWindow())

        self.iface = iface
        self.project = QgsProject.instance()
        self.layout_manager = self.project.layoutManager()
        self._refreshing = False

        self.setObjectName("AdvancedLayoutManagerBrowserDock")

        self._build_ui()
        self._connect_signals()
        self.refresh_tree()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        wrapper = QWidget()
        wrapper.setObjectName("AdvancedLayoutManagerBrowserWrapper")

        main_layout = QVBoxLayout(wrapper)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(7)

        title = QLabel("Advanced Layout Manager Browser")
        title.setObjectName("AdvancedLayoutManagerBrowserTitle")
        main_layout.addWidget(title)

        self.info_label = QLabel("Groups are saved inside the QGIS project. Save the project to keep changes.")
        self.info_label.setWordWrap(True)
        self.info_label.setObjectName("AdvancedLayoutManagerBrowserInfo")
        main_layout.addWidget(self.info_label)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search layouts or groups...")
        self.search_box.setClearButtonEnabled(True)
        main_layout.addWidget(self.search_box)

        self.tree = LayoutTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(18)
        self.tree.setContextMenuPolicy(QT_CUSTOM_CONTEXT_MENU)
        self.tree.setSelectionMode(TREE_EXTENDED_SELECTION)
        self.tree.setDragDropMode(TREE_INTERNAL_MOVE)
        self.tree.setDefaultDropAction(QT_MOVE_ACTION)
        self.tree.setAlternatingRowColors(True)
        self.tree.drop_finished_callback = self._handle_tree_drag_drop_finished
        main_layout.addWidget(self.tree)

        button_row_1 = QHBoxLayout()
        self.btn_new_group = QPushButton("New Group")
        self.btn_new_subgroup = QPushButton("New Subgroup")
        button_row_1.addWidget(self.btn_new_group)
        button_row_1.addWidget(self.btn_new_subgroup)
        main_layout.addLayout(button_row_1)

        button_row_2 = QHBoxLayout()
        self.btn_new_layout = QPushButton("New Empty Layout")
        self.btn_open = QPushButton("Open")
        button_row_2.addWidget(self.btn_new_layout)
        button_row_2.addWidget(self.btn_open)
        main_layout.addLayout(button_row_2)

        button_row_3 = QHBoxLayout()
        self.btn_export_group = QPushButton("Export Group")
        self.btn_refresh = QPushButton("Refresh")
        button_row_3.addWidget(self.btn_export_group)
        button_row_3.addWidget(self.btn_refresh)
        main_layout.addLayout(button_row_3)

        button_row_4 = QHBoxLayout()
        self.btn_help = QPushButton("Help")
        button_row_4.addStretch()
        button_row_4.addWidget(self.btn_help)
        main_layout.addLayout(button_row_4)

        self.setWidget(wrapper)
        self._apply_style()

        self.search_box.textChanged.connect(self._apply_filter)
        self.btn_new_group.clicked.connect(self.create_group)
        self.btn_new_subgroup.clicked.connect(self.create_subgroup)
        self.btn_new_layout.clicked.connect(self.create_layout)
        self.btn_open.clicked.connect(self.open_selected_layout)
        self.btn_export_group.clicked.connect(self.export_selected_group_to_pdf)
        self.btn_refresh.clicked.connect(self.refresh_tree)
        self.btn_help.clicked.connect(self.show_help)

        self.tree.itemDoubleClicked.connect(self._handle_double_click)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)

    def _apply_style(self):
        self.setStyleSheet("""
            QDockWidget#AdvancedLayoutManagerBrowserDock {
                font-size: 9.5pt;
            }
            QWidget#AdvancedLayoutManagerBrowserWrapper {
                background: palette(window);
            }
            QLabel#AdvancedLayoutManagerBrowserTitle {
                font-size: 13pt;
                font-weight: 600;
                padding: 4px 2px 2px 2px;
            }
            QLabel#AdvancedLayoutManagerBrowserInfo {
                color: palette(mid);
                padding: 2px 2px 6px 2px;
            }
            QLineEdit {
                padding: 6px 8px;
                border: 1px solid palette(mid);
                border-radius: 6px;
                background: palette(base);
            }
            QTreeWidget {
                border: 1px solid palette(mid);
                border-radius: 7px;
                padding: 4px;
                background: palette(base);
                alternate-background-color: palette(alternate-base);
            }
            QTreeWidget::item {
                min-height: 24px;
                padding: 2px 4px;
                border-radius: 4px;
            }
            QTreeWidget::item:selected {
                background: palette(highlight);
                color: palette(highlighted-text);
            }
            QPushButton {
                padding: 6px 8px;
                border-radius: 6px;
                border: 1px solid palette(mid);
                background: palette(button);
            }
            QPushButton:hover {
                background: palette(light);
            }
        """)

    def _connect_signals(self):
        """Connect QGIS project/layout signals where available.

        Refreshes are scheduled rather than run immediately because project
        and layout signals can fire while QGIS is still loading or saving.
        """

        for signal_name in ("layoutAdded", "layoutRemoved", "layoutRenamed"):
            try:
                getattr(self.layout_manager, signal_name).connect(self._schedule_refresh)
            except Exception:
                pass

        for signal_name in ("readProject", "cleared", "projectSaved", "writeProject"):
            try:
                getattr(self.project, signal_name).connect(self._schedule_project_event_refresh)
            except Exception:
                pass

        try:
            self.iface.projectRead.connect(self._schedule_project_loaded_refresh)
        except Exception:
            pass

    def _schedule_project_event_refresh(self, *args):
        """Refresh after project read/write/save/clear events."""
        QTimer.singleShot(0, self.refresh_tree)
        QTimer.singleShot(500, self.refresh_tree)

    def _schedule_refresh(self, *args):
        """Refresh after the current Qt event has completed."""
        QTimer.singleShot(0, self.refresh_tree)

    def _schedule_project_loaded_refresh(self, *args):
        """Refresh twice after project load to avoid partial layout-manager state."""
        QTimer.singleShot(0, self.refresh_tree)
        QTimer.singleShot(500, self.refresh_tree)

    # ------------------------------------------------------------------
    # Project storage
    # ------------------------------------------------------------------

    def _read_json_entry(self, entry_name, default):
        raw_value, ok = self.project.readEntry(PLUGIN_PROJECT_KEY, entry_name, json.dumps(default))
        if not ok or not raw_value:
            return default
        try:
            value = json.loads(raw_value)
        except Exception:
            return default
        return value if isinstance(value, type(default)) else default

    def _write_json_entry(self, entry_name, value):
        self.project.writeEntry(
            PLUGIN_PROJECT_KEY,
            entry_name,
            json.dumps(value, indent=2, sort_keys=True)
        )
        self.project.setDirty(True)

    def _read_layout_to_group(self):
        """Read layout -> group mapping without modifying project storage.

        Do not remove entries here. During project loading QGIS may emit signals
        before all layouts are available in QgsLayoutManager. Cleaning missing
        layout names during a read can therefore delete valid saved grouping data
        and make layouts appear as ungrouped after reopening the project.
        """
        data = self._read_json_entry(ENTRY_LAYOUT_GROUPS, {})
        clean = {}

        for layout_name, group_path in data.items():
            layout_name = str(layout_name).strip()
            group_path = self._clean_group_path(group_path)
            if layout_name and group_path:
                clean[layout_name] = group_path

        return clean

    def _write_layout_to_group(self, data):
        """Write layout -> group mapping.

        Existing layout validation is intentionally conservative. If the layout
        manager is temporarily empty, we do not treat that as proof that all
        saved layout names are stale.
        """
        clean = {}
        existing_layouts = set(self._layout_names())

        for layout_name, group_path in data.items():
            layout_name = str(layout_name).strip()
            group_path = self._clean_group_path(group_path)
            if layout_name and group_path and (not existing_layouts or layout_name in existing_layouts):
                clean[layout_name] = group_path

        self._write_json_entry(ENTRY_LAYOUT_GROUPS, clean)

    def _read_favourites(self):
        data = self._read_json_entry(ENTRY_FAVOURITES, [])
        existing_layouts = set(self._layout_names())
        return [str(name) for name in data if str(name) in existing_layouts]

    def _write_favourites(self, favourites):
        existing_layouts = set(self._layout_names())
        clean = []
        for name in favourites:
            if name in existing_layouts and name not in clean:
                clean.append(name)
        self._write_json_entry(ENTRY_FAVOURITES, clean)

    def _read_group_colours(self):
        data = self._read_json_entry(ENTRY_GROUP_COLOURS, {})
        clean = {}
        for group_path, colour_name in data.items():
            group_path = self._clean_group_path(group_path)
            if group_path and colour_name in GROUP_COLOURS:
                clean[group_path] = colour_name
        return clean

    def _write_group_colours(self, colours):
        self._write_json_entry(ENTRY_GROUP_COLOURS, colours)

    # ------------------------------------------------------------------
    # Tree building
    # ------------------------------------------------------------------

    def refresh_tree(self, *args):
        """Rebuild the browser from QGIS layouts and saved project entries."""
        self._refreshing = True
        self.tree.blockSignals(True)
        self.tree.clear()

        layout_names = self._layout_names()
        layout_to_group = self._read_layout_to_group()
        favourites = self._read_favourites()
        group_colours = self._read_group_colours()

        if favourites:
            fav_root = self._create_special_item(FAVOURITES_NAME, expanded=True)
            self.tree.addTopLevelItem(fav_root)
            for layout_name in favourites:
                fav_root.addChild(self._create_layout_item(layout_name, favourite=True))
            self._set_count_label(fav_root)

        group_roots = {}

        for layout_name in layout_names:
            group_path = layout_to_group.get(layout_name, "")
            if group_path:
                group_item = self._ensure_group_path(group_path, group_roots, group_colours)
                group_item.addChild(self._create_layout_item(layout_name, favourite=layout_name in favourites))

        # Add empty saved groups from colour entries, useful when a user creates a group first.
        for group_path in sorted(group_colours.keys()):
            self._ensure_group_path(group_path, group_roots, group_colours)

        ungrouped = [name for name in layout_names if name not in layout_to_group]
        if ungrouped:
            ungrouped_item = self._create_group_item(UNGROUPED_NAME, UNGROUPED_NAME, editable=False)
            self.tree.addTopLevelItem(ungrouped_item)
            for layout_name in ungrouped:
                ungrouped_item.addChild(self._create_layout_item(layout_name, favourite=layout_name in favourites))
            self._set_count_label(ungrouped_item)
            ungrouped_item.setExpanded(True)

        self._update_all_group_counts()
        self.tree.blockSignals(False)
        self._refreshing = False
        self._apply_filter(self.search_box.text())

    def _ensure_group_path(self, group_path, group_roots, group_colours):
        parts = [p for p in group_path.split(GROUP_SEPARATOR) if p]
        current_parent = None
        current_path = ""

        for part in parts:
            current_path = part if not current_path else f"{current_path}{GROUP_SEPARATOR}{part}"

            if current_path in group_roots:
                current_parent = group_roots[current_path]
                continue

            item = self._create_group_item(part, current_path, editable=True)
            self._apply_group_colour(item, group_colours.get(current_path))

            if current_parent is None:
                self.tree.addTopLevelItem(item)
            else:
                current_parent.addChild(item)

            item.setExpanded(True)
            group_roots[current_path] = item
            current_parent = item

        return current_parent

    def _create_special_item(self, name, expanded=False):
        item = QTreeWidgetItem([name])
        item.setData(0, ROLE_TYPE, ITEM_SPECIAL)
        item.setData(0, ROLE_VALUE, name)
        item.setFlags(_qt_flag(QT_ITEM_ENABLED, QT_ITEM_SELECTABLE))
        item.setExpanded(expanded)
        return item

    def _create_group_item(self, label, group_path, editable=True):
        item = QTreeWidgetItem([label])
        item.setData(0, ROLE_TYPE, ITEM_GROUP)
        item.setData(0, ROLE_VALUE, group_path)

        flags = _qt_flag(QT_ITEM_ENABLED, QT_ITEM_SELECTABLE, QT_ITEM_DROP_ENABLED)

        item.setFlags(flags)
        return item

    def _create_layout_item(self, layout_name, favourite=False):
        label = f"★ {layout_name}" if favourite else layout_name
        item = QTreeWidgetItem([label])
        item.setData(0, ROLE_TYPE, ITEM_LAYOUT)
        item.setData(0, ROLE_VALUE, layout_name)
        item.setFlags(_qt_flag(QT_ITEM_ENABLED, QT_ITEM_SELECTABLE, QT_ITEM_DRAG_ENABLED))
        return item

    def _apply_group_colour(self, item, colour_name):
        hex_colour = GROUP_COLOURS.get(colour_name)
        if not hex_colour:
            return
        try:
            item.setForeground(0, QBrush(QColor(hex_colour)))
        except Exception:
            pass

    def _update_all_group_counts(self):
        def walk(item):
            if item.data(0, ROLE_TYPE) in (ITEM_GROUP, ITEM_SPECIAL):
                self._set_count_label(item)
            for i in range(item.childCount()):
                walk(item.child(i))

        for i in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(i))

    def _set_count_label(self, item):
        item_type = item.data(0, ROLE_TYPE)
        raw_label = item.data(0, ROLE_VALUE)

        if item_type == ITEM_LAYOUT:
            return

        count = self._count_layout_children(item)
        base = raw_label.split(GROUP_SEPARATOR)[-1] if item_type == ITEM_GROUP else raw_label
        item.setText(0, f"{base} ({count})")

    def _count_layout_children(self, item):
        total = 0
        for i in range(item.childCount()):
            child = item.child(i)
            if child.data(0, ROLE_TYPE) == ITEM_LAYOUT:
                total += 1
            else:
                total += self._count_layout_children(child)
        return total

    # ------------------------------------------------------------------
    # Selection helpers
    # ------------------------------------------------------------------

    def _layout_names(self):
        return sorted(layout.name() for layout in self.layout_manager.layouts())

    def _selected_item(self):
        items = self.tree.selectedItems()
        return items[0] if items else None

    def _selected_layout_name(self):
        item = self._selected_item()
        if not item or item.data(0, ROLE_TYPE) != ITEM_LAYOUT:
            return None
        return item.data(0, ROLE_VALUE)
    
    def _selected_layout_names(self):
        """Return all selected layout names, preserving tree selection order."""
        layout_names = []

        for item in self.tree.selectedItems():
            if item.data(0, ROLE_TYPE) == ITEM_LAYOUT:
                layout_name = item.data(0, ROLE_VALUE)
                if layout_name and layout_name not in layout_names:
                    layout_names.append(layout_name)

        return layout_names

    def _selected_group_path(self):
        item = self._selected_item()
        if not item:
            return None

        if item.data(0, ROLE_TYPE) == ITEM_GROUP:
            return item.data(0, ROLE_VALUE)

        parent = item.parent()
        while parent:
            if parent.data(0, ROLE_TYPE) == ITEM_GROUP:
                return parent.data(0, ROLE_VALUE)
            parent = parent.parent()

        return None

    def _find_layout_by_name(self, layout_name):
        for layout in self.layout_manager.layouts():
            if layout.name() == layout_name:
                return layout
        return None

    def _clean_group_path(self, value):
        text = str(value or "").strip()
        text = re.sub(r"/+", GROUP_SEPARATOR, text)
        text = GROUP_SEPARATOR.join(part.strip() for part in text.split(GROUP_SEPARATOR) if part.strip())
        if text == UNGROUPED_NAME:
            return ""
        return text

    # ------------------------------------------------------------------
    # Main actions
    # ------------------------------------------------------------------

    def create_group(self):
        name, ok = QInputDialog.getText(self, "New Layout Group", "Group name:")
        group_path = self._clean_group_path(name)
        if not ok or not group_path:
            return

        colours = self._read_group_colours()
        colours.setdefault(group_path, "None")
        self._write_group_colours(colours)
        self.refresh_tree()

    def create_subgroup(self):
        parent_path = self._selected_group_path()
        if not parent_path or parent_path == UNGROUPED_NAME:
            QMessageBox.information(self, "New Subgroup", "Select a normal group first.")
            return

        name, ok = QInputDialog.getText(self, "New Subgroup", "Subgroup name:")
        child_name = self._clean_group_path(name)
        if not ok or not child_name:
            return

        group_path = self._clean_group_path(f"{parent_path}{GROUP_SEPARATOR}{child_name}")
        colours = self._read_group_colours()
        colours.setdefault(group_path, "None")
        self._write_group_colours(colours)
        self.refresh_tree()

    def create_layout(self):
        name, ok = QInputDialog.getText(self, "New Empty Layout", "Layout name:")
        name = name.strip()
        if not ok or not name:
            return

        if self._find_layout_by_name(name):
            QMessageBox.warning(self, "Layout Exists", f"A layout named '{name}' already exists.")
            return

        layout = QgsPrintLayout(self.project)
        layout.initializeDefaults()
        layout.setName(name)

        if not self.layout_manager.addLayout(layout):
            QMessageBox.critical(self, "Create Layout Failed", f"Could not create layout '{name}'.")
            return

        group_path = self._selected_group_path()
        if group_path and group_path != UNGROUPED_NAME:
            self._assign_layout_to_group(name, group_path, refresh=False)

        self.refresh_tree()
        self.open_layout(name)

    def open_selected_layout(self):
        layout_name = self._selected_layout_name()
        if not layout_name:
            QMessageBox.information(self, "Open Layout", "Select a layout to open.")
            return
        self.open_layout(layout_name)

    def open_layout(self, layout_name):
        layout = self._find_layout_by_name(layout_name)
        if not layout:
            QMessageBox.warning(self, "Layout Not Found", f"Layout '{layout_name}' could not be found.")
            self.refresh_tree()
            return
        self.iface.openLayoutDesigner(layout)

    def duplicate_selected_layout(self):
        layout_name = self._selected_layout_name()
        if not layout_name:
            return

        source_layout = self._find_layout_by_name(layout_name)
        if not source_layout:
            self.refresh_tree()
            return

        new_name, ok = QInputDialog.getText(
            self,
            "Duplicate Layout",
            "New layout name:",
            text=f"{layout_name} copy"
        )
        new_name = new_name.strip()
        if not ok or not new_name:
            return

        if self._find_layout_by_name(new_name):
            QMessageBox.warning(self, "Layout Exists", f"A layout named '{new_name}' already exists.")
            return

        try:
            duplicated_layout = source_layout.clone()
            duplicated_layout.setName(new_name)
        except Exception as exc:
            QMessageBox.critical(self, "Duplicate Failed", f"Could not duplicate layout.\n\n{exc}")
            return

        if not self.layout_manager.addLayout(duplicated_layout):
            QMessageBox.critical(self, "Duplicate Failed", f"Could not add duplicated layout '{new_name}'.")
            return

        group_path = self._selected_group_path()
        if group_path and group_path != UNGROUPED_NAME:
            self._assign_layout_to_group(new_name, group_path, refresh=False)

        self.refresh_tree()

    def rename_selected_layout(self):
        old_name = self._selected_layout_name()
        if not old_name:
            return

        layout = self._find_layout_by_name(old_name)
        if not layout:
            self.refresh_tree()
            return

        new_name, ok = QInputDialog.getText(self, "Rename Layout", "New layout name:", text=old_name)
        new_name = new_name.strip()
        if not ok or not new_name or new_name == old_name:
            return

        if self._find_layout_by_name(new_name):
            QMessageBox.warning(self, "Layout Exists", f"A layout named '{new_name}' already exists.")
            return

        group_data = self._read_layout_to_group()
        favs = self._read_favourites()

        layout.setName(new_name)

        if old_name in group_data:
            group_data[new_name] = group_data.pop(old_name)
            self._write_layout_to_group(group_data)

        favs = [new_name if name == old_name else name for name in favs]
        self._write_favourites(favs)
        self.refresh_tree()

    def delete_selected_layout(self):
        layout_names = self._selected_layout_names()
        if not layout_names:
            return

        existing_layouts = [
            name for name in layout_names
            if self._find_layout_by_name(name)
        ]

        if not existing_layouts:
            self.refresh_tree()
            return

        if len(existing_layouts) == 1:
            message = (
                f"Delete layout '{existing_layouts[0]}'?\n\n"
                "This removes the real QGIS layout from the project."
            )
        else:
            message = (
                f"Delete {len(existing_layouts)} selected layouts?\n\n"
                "This removes the real QGIS layouts from the project."
            )

        answer = QMessageBox.question(
            self,
            "Delete Layouts",
            message,
            _messagebox_button("Yes") | _messagebox_button("No"),
            _messagebox_button("No")
        )
        if answer != _messagebox_button("Yes"):
            return

        for layout_name in existing_layouts:
            layout = self._find_layout_by_name(layout_name)
            if layout:
                self.layout_manager.removeLayout(layout)

        group_data = self._read_layout_to_group()
        for layout_name in existing_layouts:
            group_data.pop(layout_name, None)
        self._write_layout_to_group(group_data)

        favs = [
            name for name in self._read_favourites()
            if name not in existing_layouts
        ]
        self._write_favourites(favs)

        self.refresh_tree()

    def move_selected_layout_to_group(self):
            layout_names = self._selected_layout_names()
            if not layout_names:
                return

            group_paths = self._all_group_paths(include_ungrouped=True)
            dialog = MoveToGroupDialog(self, group_paths)
            if _exec_dialog(dialog) != _dialog_accepted():
                return

            target = dialog.selected_group_path()

            for layout_name in layout_names:
                self._assign_layout_to_group(layout_name, target, refresh=False)

            self.refresh_tree()

    def toggle_selected_favourite(self):
        layout_names = self._selected_layout_names()
        if not layout_names:
            return

        favs = self._read_favourites()

        for layout_name in layout_names:
            if layout_name in favs:
                favs.remove(layout_name)
            else:
                favs.append(layout_name)

        self._write_favourites(favs)
        self.refresh_tree()

    def set_selected_group_colour(self):
        group_path = self._selected_group_path()
        if not group_path or group_path == UNGROUPED_NAME:
            QMessageBox.information(self, "Group Colour", "Select a normal group first.")
            return

        colour_name, ok = QInputDialog.getItem(
            self,
            "Group Colour",
            "Colour:",
            list(GROUP_COLOURS.keys()),
            0,
            False
        )
        if not ok:
            return

        colours = self._read_group_colours()
        if colour_name == "None":
            colours.pop(group_path, None)
        else:
            colours[group_path] = colour_name
        self._write_group_colours(colours)
        self.refresh_tree()

    def delete_selected_group(self):
        group_path = self._selected_group_path()
        if not group_path or group_path == UNGROUPED_NAME:
            QMessageBox.information(self, "Delete Group", f"'{UNGROUPED_NAME}' cannot be deleted.")
            return

        answer = QMessageBox.question(
            self,
            "Delete Group",
            f"Delete group '{group_path}'?\n\nLayouts inside it will not be deleted. They will become ungrouped.",
            _messagebox_button("Yes") | _messagebox_button("No"),
            _messagebox_button("No")
        )
        if answer != _messagebox_button("Yes"):
            return

        group_data = self._read_layout_to_group()
        prefix = f"{group_path}{GROUP_SEPARATOR}"
        group_data = {
            layout_name: path
            for layout_name, path in group_data.items()
            if path != group_path and not path.startswith(prefix)
        }
        self._write_layout_to_group(group_data)

        colours = self._read_group_colours()
        colours = {
            path: colour
            for path, colour in colours.items()
            if path != group_path and not path.startswith(prefix)
        }
        self._write_group_colours(colours)
        self.refresh_tree()

    # ------------------------------------------------------------------
    # Assignment and drag/drop
    # ------------------------------------------------------------------

    def _assign_layout_to_group(self, layout_name, group_path, refresh=True):
        group_path = self._clean_group_path(group_path)
        data = self._read_layout_to_group()

        if group_path:
            data[layout_name] = group_path
        else:
            data.pop(layout_name, None)

        self._write_layout_to_group(data)

        if refresh:
            self.refresh_tree()

    def _handle_tree_drag_drop_finished(self):
        """Persist layout moves after drag/drop using the same storage model as Move to Group."""
        if self._refreshing:
            return

        data = self._read_layout_to_group()

        def walk(parent_item):
            parent_type = parent_item.data(0, ROLE_TYPE)
            parent_path = parent_item.data(0, ROLE_VALUE)

            for i in range(parent_item.childCount()):
                child = parent_item.child(i)
                child_type = child.data(0, ROLE_TYPE)

                if child_type == ITEM_LAYOUT and parent_type == ITEM_GROUP:
                    layout_name = child.data(0, ROLE_VALUE)
                    if parent_path == UNGROUPED_NAME:
                        data.pop(layout_name, None)
                    else:
                        data[layout_name] = parent_path

                elif child_type == ITEM_GROUP:
                    walk(child)

        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            top_type = top.data(0, ROLE_TYPE)

            if top_type == ITEM_GROUP:
                walk(top)

            # If a layout is dropped at the tree root, treat it as ungrouped.
            elif top_type == ITEM_LAYOUT:
                layout_name = top.data(0, ROLE_VALUE)
                data.pop(layout_name, None)

        self._write_layout_to_group(data)
        QTimer.singleShot(0, self.refresh_tree)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_selected_group_to_pdf(self):
        group_path = self._selected_group_path()
        if not group_path:
            QMessageBox.information(self, "Export Group", "Select a group to export.")
            return

        layout_names = self._layouts_in_group(group_path)
        if not layout_names:
            QMessageBox.information(self, "Export Group", "The selected group does not contain any layouts.")
            return

        folder = QFileDialog.getExistingDirectory(self, "Select Export Folder")
        if not folder:
            return

        errors = []
        settings = QgsLayoutExporter.PdfExportSettings()

        for layout_name in layout_names:
            layout = self._find_layout_by_name(layout_name)
            if not layout:
                continue

            safe_name = self._safe_filename(layout_name)
            output_path = os.path.join(folder, f"{safe_name}.pdf")
            result = QgsLayoutExporter(layout).exportToPdf(output_path, settings)

            if result != QgsLayoutExporter.Success:
                errors.append(layout_name)

        if errors:
            QMessageBox.warning(
                self,
                "Export Finished With Errors",
                "Some layouts could not be exported:\n\n" + "\n".join(errors)
            )
        else:
            QMessageBox.information(
                self,
                "Export Complete",
                f"Exported {len(layout_names)} layout(s) to PDF."
            )

    # ------------------------------------------------------------------
    # Context menu and events
    # ------------------------------------------------------------------

    def _handle_double_click(self, item, column):
        if item.data(0, ROLE_TYPE) == ITEM_LAYOUT:
            self.open_layout(item.data(0, ROLE_VALUE))

    def _show_context_menu(self, point):
        item = self.tree.itemAt(point)
        if item is None:
            return

        if not item.isSelected():
            self.tree.clearSelection()
            self.tree.setCurrentItem(item)
            item.setSelected(True)
        item_type = item.data(0, ROLE_TYPE)
        menu = QMenu(self)

        if item_type == ITEM_LAYOUT:
            open_action = menu.addAction("Open Layout")
            duplicate_action = menu.addAction("Duplicate Layout")
            rename_action = menu.addAction("Rename Layout")
            move_action = menu.addAction("Move to Group...")
            fav_action = menu.addAction("Add/Remove Favourite")
            delete_action = menu.addAction("Delete Layout")

            action = _exec_menu(menu, self.tree.viewport().mapToGlobal(point))

            if action == open_action:
                self.open_selected_layout()
            elif action == duplicate_action:
                self.duplicate_selected_layout()
            elif action == rename_action:
                self.rename_selected_layout()
            elif action == move_action:
                self.move_selected_layout_to_group()
            elif action == fav_action:
                self.toggle_selected_favourite()
            elif action == delete_action:
                self.delete_selected_layout()

        elif item_type == ITEM_GROUP:
            new_layout_action = menu.addAction("New Layout in Group")
            new_subgroup_action = menu.addAction("New Subgroup")
            move_all_action = menu.addAction("Export Group to PDF")
            colour_action = menu.addAction("Set Group Colour")
            delete_group_action = menu.addAction("Delete Group")

            if item.data(0, ROLE_VALUE) == UNGROUPED_NAME:
                new_subgroup_action.setEnabled(False)
                colour_action.setEnabled(False)
                delete_group_action.setEnabled(False)

            action = _exec_menu(menu, self.tree.viewport().mapToGlobal(point))

            if action == new_layout_action:
                self.create_layout()
            elif action == new_subgroup_action:
                self.create_subgroup()
            elif action == move_all_action:
                self.export_selected_group_to_pdf()
            elif action == colour_action:
                self.set_selected_group_colour()
            elif action == delete_group_action:
                self.delete_selected_group()

    # ------------------------------------------------------------------
    # Search/filter
    # ------------------------------------------------------------------

    def _apply_filter(self, text):
        text = (text or "").strip().lower()

        def filter_item(item):
            own_match = text in item.text(0).lower() if text else True
            child_match = False

            for i in range(item.childCount()):
                child = item.child(i)
                if filter_item(child):
                    child_match = True

            visible = own_match or child_match
            item.setHidden(not visible)

            if text and child_match:
                item.setExpanded(True)

            return visible

        for i in range(self.tree.topLevelItemCount()):
            filter_item(self.tree.topLevelItem(i))

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def _all_group_paths(self, include_ungrouped=False):
        paths = set()
        for path in self._read_layout_to_group().values():
            if path:
                paths.add(path)
                parts = path.split(GROUP_SEPARATOR)
                for i in range(1, len(parts)):
                    paths.add(GROUP_SEPARATOR.join(parts[:i]))
        for path in self._read_group_colours().keys():
            paths.add(path)

        result = sorted(paths)
        if include_ungrouped:
            result.insert(0, UNGROUPED_NAME)
        return result

    def _layouts_in_group(self, group_path):
        group_path = self._clean_group_path(group_path)
        data = self._read_layout_to_group()

        if group_path == UNGROUPED_NAME or not group_path:
            return [name for name in self._layout_names() if name not in data]

        prefix = f"{group_path}{GROUP_SEPARATOR}"
        return sorted(
            layout_name
            for layout_name, path in data.items()
            if path == group_path or path.startswith(prefix)
        )

    def _safe_filename(self, text):
        text = re.sub(r"[^A-Za-z0-9_.-]+", "_", text.strip())
        return text.strip("_") or "layout"

    # ------------------------------------------------------------------
    # Show Help
    # ------------------------------------------------------------------

    def show_help(self):
        """Show a short user guide for the plugin."""
        QMessageBox.information(
            self,
            "Advanced Layout Manager Browser - Help",
            (
                "<b>Advanced Layout Manager Browser</b><br><br>"
                "This plugin helps you organise QGIS print layouts into custom groups and subgroups.<br><br>"
                "<b>Main actions</b><br>"
                "• <b>New Group</b>: create a new layout group.<br>"
                "• <b>New Subgroup</b>: create a subgroup inside the selected group.<br>"
                "• <b>New Empty Layout</b>: create a new QGIS print layout.<br>"
                "• <b>Open</b>: open the selected layout in the QGIS Layout Designer.<br>"
                "• <b>Export Group</b>: export all layouts in the selected group to PDF.<br>"
                "• <b>Refresh</b>: reload the layout browser from the current QGIS project.<br><br>"
                "<b>Drag and drop</b><br>"
                "Layouts can be dragged into groups to reorganise them.<br><br>"
                "<b>Storage</b><br>"
                "Groups are saved inside the QGIS project file. Save the project to keep your changes.<br><br>"
                "QGIS layouts remain normal QGIS layouts. The plugin only stores their group organisation."
            )
        )

# ---------------------------------------------------------------------
# Dialogs
# ---------------------------------------------------------------------

class MoveToGroupDialog(QDialog):
    """Simple dialog for moving a layout to a selected group."""

    def __init__(self, parent, group_paths):
        super().__init__(parent)
        self.setWindowTitle("Move to Group")

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Select destination group:"))

        self.combo = QComboBox()
        self.combo.addItems(group_paths)
        layout.addWidget(self.combo)

        buttons = QDialogButtonBox(_dialog_buttonbox_button("Ok") | _dialog_buttonbox_button("Cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_group_path(self):
        value = self.combo.currentText().strip()
        return "" if value == UNGROUPED_NAME else value
