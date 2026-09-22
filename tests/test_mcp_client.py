from brainbox_os.mcp_client import MCPServerConfig


def test_mcp_server_config_requires_a_transport():
    config = MCPServerConfig(name="demo", command="demo-server")
    target = config.target()
    assert target.command == "demo-server"
    assert target.args == []


def test_mcp_server_config_rejects_missing_transport():
    config = MCPServerConfig(name="demo")
    try:
        config.target()
    except ValueError as exc:
        assert "url or command" in str(exc)
    else:
        raise AssertionError("missing MCP transport should fail")
