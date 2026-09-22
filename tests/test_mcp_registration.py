from brainbox_os.execution import ToolRegistry
from brainbox_os.policy import Risk


class FakeConfig:
    name = "demo"


class FakeBridge:
    config = FakeConfig()

    def discover(self):
        return [{
            "name": "demo_lookup",
            "description": "Look something up",
            "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
            "risk": "read",
            "mcp_server": "demo",
        }]

    def call(self, name, args):
        return {"tool": name, "args": args}


def test_register_mcp_server_preserves_schema_and_execution():
    registry = ToolRegistry()
    names = registry.register_mcp_server(FakeBridge())
    assert names == ["demo_lookup"]
    schema = registry.schemas()[0]
    assert schema["parameters"]["required"] == ["query"]
    assert registry.risk("demo_lookup") == Risk.READ
    assert registry.execute("demo_lookup", {"query": "Brainbox"}) == {"tool": "demo_lookup", "args": {"query": "Brainbox"}}
