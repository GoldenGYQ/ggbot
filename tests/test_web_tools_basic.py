"""Basic tests for web tools (web_search, web_fetch)."""

import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from ggbot.tools.web import make_web_tools
from ggbot.tools.registry import ToolRegistry


def test_tool_creation():
    """Test that web tools can be created."""
    web_search, web_fetch = make_web_tools()

    assert web_search is not None
    assert web_fetch is not None

    print("Tool creation test passed")


def test_tool_registration():
    """Test that tools can be registered in ToolRegistry."""
    web_search, web_fetch = make_web_tools()

    reg = ToolRegistry()

    # Register all web tools
    reg.register_tool(web_search)
    reg.register_tool(web_fetch)

    # Check specs
    specs = reg.specs()
    spec_names = [spec.name for spec in specs]

    assert "web_search" in spec_names
    assert "web_fetch" in spec_names

    print(" Tool registration test passed")


def test_tool_specs():
    """Test tool specifications."""
    web_search, web_fetch = make_web_tools()

    # Check web_search spec
    web_search_spec = web_search.__ggbot_tool__.spec
    assert web_search_spec.name == "web_search"
    assert "Search the web" in web_search_spec.description
    assert "query" in web_search_spec.parameters["properties"]
    assert "count" in web_search_spec.parameters["properties"]
    assert "provider" in web_search_spec.parameters["properties"]

    # Check web_fetch spec
    web_fetch_spec = web_fetch.__ggbot_tool__.spec
    assert web_fetch_spec.name == "web_fetch"
    assert "Fetch URL" in web_fetch_spec.description
    assert "url" in web_fetch_spec.parameters["properties"]
    assert "extractMode" in web_fetch_spec.parameters["properties"]
    assert "maxChars" in web_fetch_spec.parameters["properties"]

    print(" Tool specs test passed")


def test_web_tool_functions():
    """Test web tool helper functions."""
    from ggbot.tools.web import _strip_tags, _normalize, _validate_url

    # Test _strip_tags
    html = "<p>Hello <b>World</b>!</p>"
    stripped = _strip_tags(html)
    assert stripped == "Hello World!"

    # Test _normalize
    text = "  Hello   World\n\n\nTest  "
    normalized = _normalize(text)
    assert normalized == "Hello World\n\nTest"

    # Test _validate_url
    valid, msg = _validate_url("https://example.com")
    assert valid is True
    assert msg == ""

    valid, msg = _validate_url("ftp://example.com")
    assert valid is False
    assert "Only http/https allowed" in msg

    valid, msg = _validate_url("http://")
    assert valid is False
    assert "Missing domain" in msg

    print(" Web tool helper functions test passed")


def test_make_web_tools_function():
    """Test make_web_tools function returns correct number of tools."""
    tools = make_web_tools()
    assert len(tools) == 2
    assert callable(tools[0])
    assert callable(tools[1])

    print(" make_web_tools function test passed")


if __name__ == "__main__":
    print("Running basic web tools tests...")
    print("-" * 50)

    test_tool_creation()
    test_tool_registration()
    test_tool_specs()
    test_web_tool_functions()
    test_make_web_tools_function()

    print("-" * 50)
    print("All basic tests passed!")
