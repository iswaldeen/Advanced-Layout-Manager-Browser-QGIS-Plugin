# -*- coding: utf-8 -*-


def classFactory(iface):
    from .advanced_layout_manager_browser import AdvancedLayoutManagerBrowserPlugin
    return AdvancedLayoutManagerBrowserPlugin(iface)
