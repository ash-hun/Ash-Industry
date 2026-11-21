"""extension 기능의 ExtensionLoader: 확장 패키지의 register(ctx) 를 이름순으로 부르고 실패한 확장만 건너뛴다."""

from ash_industry.app.extension_loader import ExtensionContext, ExtensionLoader
from ash_industry.core.tools.tools_registry import ToolRegistry
from tests.fixtures.extension_helpers import write_extension


def test_loads_extensions_in_name_order_with_tools_and_commands(tmp_path):
    write_extension(tmp_path, "beta", ("b_tool",), command="beta")
    write_extension(tmp_path, "alpha", ("a_tool",))
    ctx = ExtensionContext(agent_tools=ToolRegistry())

    loaded = ExtensionLoader(str(tmp_path)).load(ctx)

    assert loaded == ["alpha", "beta"]
    assert sorted(t.name for t in ctx.agent_tools.list_all()) == ["a_tool", "b_tool"]
    assert [c.name for c in ctx.commands] == ["beta"]


def test_broken_extension_is_skipped_and_missing_dir_loads_nothing(tmp_path):
    write_extension(tmp_path, "broken", (), source="raise RuntimeError('boom')\n")
    write_extension(tmp_path, "good", ("g_tool",))
    ctx = ExtensionContext(agent_tools=ToolRegistry())

    assert ExtensionLoader(str(tmp_path)).load(ctx) == ["good"]
    assert ExtensionLoader(str(tmp_path / "none")).load(ExtensionContext(agent_tools=ToolRegistry())) == []
