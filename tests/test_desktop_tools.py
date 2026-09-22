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
