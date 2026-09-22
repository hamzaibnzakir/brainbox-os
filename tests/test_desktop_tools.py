import platform

from brainbox_os.desktop_tools import register_desktop_tools
from brainbox_os.execution import ToolRegistry


def test_desktop_registry_is_platform_safe():
    registry = ToolRegistry()
    register_desktop_tools(registry)
    if platform.system() == "Windows":
        assert any(t["name"] == "open_application" for t in registry.schemas())
    else:
        assert registry.schemas() == []


def test_app_name_normalization_and_fuzzy_matching():
    from brainbox_os.windows_tools import _choose_start_menu_app

    apps = [
        {"Name": "Calculator", "AppID": "calc"},
        {"Name": "Notepad", "AppID": "note"},
    ]
    chosen, kind, score = _choose_start_menu_app("calculato", apps)
    assert chosen["Name"] == "Calculator"
    assert kind == "fuzzy"
    assert score >= 0.86

    chosen, kind, score = _choose_start_menu_app("notes pad", apps)
    assert chosen["Name"] == "Notepad"
    assert kind == "fuzzy"
    assert score >= 0.86


def test_low_confidence_app_match_is_not_selected():
    from brainbox_os.windows_tools import _choose_start_menu_app

    chosen, kind, score = _choose_start_menu_app("kakuleto", [{"Name": "Calculator", "AppID": "calc"}])
    assert chosen is None
    assert kind == "ambiguous"
    assert score < 0.86
