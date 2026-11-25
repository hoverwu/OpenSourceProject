# -*- coding: utf-8 -*-
"""EBX 分层工具目录：少量常驻入口、中文检索与原工具代理（hoverwu / 0.1.0）。"""
from collections import Counter
from collections.abc import Sequence
import re
from typing import Annotated, Any

from fastmcp.server.context import Context
from fastmcp.server.transforms.search.base import BaseSearchTransform, _schema_type
from fastmcp.tools.base import Tool

DOMAIN_TAG = "domain:"
PINNED_TOOLS = ["ebx_status"]
SYNTHETIC_TOOLS = ["ebx_catalog", "ebx_find_tools", "ebx_call_tool"]
BOOTSTRAP_TOOLS = PINNED_TOOLS + SYNTHETIC_TOOLS

TOOL_ALIASES = {
    "ebx_native_generate": ["原生生成", "生成画面", "代码生成", "native generate"],
    "ebx_native_import": ["原生导入", "导入画面", "安全导入", "native import"],
    "ebx_native_patch_capture": ["补丁快照", "捕获补丁", "patch capture"],
    "ebx_native_patch_apply": ["增量补丁", "应用补丁", "修改既有画面", "patch apply"],
    "ebx_native_clone_screen": ["克隆画面", "复制画面", "clone screen"],
    "ebx_native_query_objects": ["查询对象", "对象列表", "query objects"],
    "ebx_native_snapshot": ["画面快照", "PNG", "snapshot"],
    "ebx_screen_open": ["打开画面", "切换画面", "screen open"],
    "ebx_screen_list": ["画面列表", "枚举画面", "screen list"],
    "ebx_screenshot": ["截图", "屏幕截图", "screenshot"],
    "ebx_compile": ["编译工程", "编译", "compile"],
    "ebx_offline_simulate": ["离线模拟", "启动模拟", "simulate"],
    "ebx_open": ["打开工程", "open project"],
    "ebx_save_as": ["另存为", "保存工程", "save as"],
}

DOMAINS = {
    "project": {
        "title": "工程与进程",
        "summary": "启动、新建、打开、保存和产物核验；先看运行状态。",
        "aliases": ["project", "launch", "save", "open", "工程", "启动", "保存", "打开"],
    },
    "observe": {
        "title": "观察与诊断",
        "summary": "窗口、UIA 树、控件查找、结构导出、截图和 Ribbon 坐标图。",
        "aliases": ["observe", "window", "uia", "screenshot", "观察", "窗口", "截图", "诊断"],
    },
    "screen": {
        "title": "画面导航",
        "summary": "枚举、切换画面和读取当前画面的元件列表。",
        "aliases": ["screen", "navigation", "画面", "导航", "元件列表"],
    },
    "native": {
        "title": "原生 JSON 与补丁",
        "summary": "快速生成/导入画面、dry-run、增量补丁、克隆、查询和快照。",
        "aliases": ["native", "json", "patch", "clone", "snapshot", "原生", "导入", "补丁", "克隆"],
    },
    "uia": {
        "title": "UIA 输入操作",
        "summary": "语义点击、窗口内坐标点击、Ribbon 点击和真实按键。",
        "aliases": ["input", "click", "ribbon", "keys", "点击", "按键", " ribbon"],
    },
    "legacy_json": {
        "title": "慢速整页重建",
        "summary": "无原生预览时通过 UIA 逐元件重建 ebx-screen/1.0 页面。",
        "aliases": ["legacy", "importer", "rebuild", "旧版", "慢速", "重建"],
    },
    "build": {
        "title": "编译与模拟",
        "summary": "编译工程、启动/停止离线模拟并检查运行产物。",
        "aliases": ["build", "compile", "simulate", "编译", "模拟", "下载"],
    },
    "other": {
        "title": "未分类工具",
        "summary": "尚未加入领域标签的底层工具。",
        "aliases": ["other", "misc", "其他"],
    },
}


def domain_of(tool: Tool) -> str:
    for tag in sorted(tool.tags):
        if tag.startswith(DOMAIN_TAG):
            domain = tag[len(DOMAIN_TAG):]
            return domain if domain in DOMAINS else "other"
    return "other"


def _summary(tool: Tool) -> str:
    if not tool.description:
        return ""
    lines = [line.strip() for line in tool.description.splitlines() if line.strip()]
    text = lines[0] if lines else ""
    return text if len(text) <= 220 else text[:217] + "..."


def _parameter_names(tool: Tool) -> list[str]:
    return list((tool.parameters or {}).get("properties", {}))


def _compact_tool(tool: Tool) -> dict[str, Any]:
    schema = tool.parameters or {}
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    return {
        "name": tool.name,
        "domain": domain_of(tool),
        "summary": _summary(tool),
        "aliases": TOOL_ALIASES.get(tool.name, []),
        "parameters": [
            {
                "name": name,
                "type": _schema_type(field),
                "required": name in required,
            }
            for name, field in properties.items()
        ],
    }


def render_search(tools: Sequence[Tool]) -> str:
    if not tools:
        return "没有匹配工具。可缩短关键词、改用中文领域词，或调用 ebx_catalog 查看全部领域。"
    blocks = []
    for tool in tools:
        item = _compact_tool(tool)
        parameters = item["parameters"]
        parameter_text = "; ".join(
            "%s:%s%s" % (param["name"], param["type"], "!" if param["required"] else "")
            for param in parameters
        ) or "无参数"
        blocks.append(
            "### %s\n领域: %s | %s\n参数(!=必填): %s\n完整 Schema: ebx_catalog(tool=%r)"
            % (tool.name, item["domain"], item["summary"], parameter_text, tool.name)
        )
    return "\n\n".join(blocks)


def _domain_filter(tools: Sequence[Tool], domain: str) -> list[Tool]:
    return [tool for tool in tools if domain_of(tool) == domain]


def _terms(query: str) -> list[str]:
    return [part.casefold() for part in re.split(r"[\s,，/]+", query.strip()) if part]


def search_score(tool: Tool, terms: Sequence[str]) -> int:
    name = tool.name.casefold()
    description = (tool.description or "").casefold()
    parameters = " ".join(_parameter_names(tool)).casefold()
    domain = domain_of(tool)
    metadata = DOMAINS[domain]
    domain_text = " ".join([domain, metadata["title"], metadata["summary"], *metadata["aliases"]]).casefold()
    aliases = " ".join(TOOL_ALIASES.get(tool.name, [])).casefold()
    total = 0
    for term in terms:
        if term == name:
            score = 1000
        elif name.startswith(term):
            score = 700
        elif term in name:
            score = 500
        elif term in description:
            score = 250
        elif term in parameters:
            score = 200
        elif term in aliases:
            score = 400
        elif term in domain_text:
            score = 120
        else:
            return 0
        total += score
    return total


class EBXCatalogTransform(BaseSearchTransform):
    def __init__(self, max_results: int = 6):
        super().__init__(
            max_results=max_results,
            always_visible=PINNED_TOOLS,
            search_tool_name="ebx_find_tools",
            call_tool_name="ebx_call_tool",
            search_result_serializer=render_search,
        )

    async def transform_tools(self, tools: Sequence[Tool]) -> Sequence[Tool]:
        visible = list(await super().transform_tools(tools))
        visible.insert(len(PINNED_TOOLS), self._make_catalog_tool())
        return visible

    async def get_tool(self, name, call_next, *, version=None):
        if name == "ebx_catalog":
            return self._make_catalog_tool()
        return await super().get_tool(name, call_next, version=version)

    def _make_catalog_tool(self) -> Tool:
        transform = self

        async def ebx_catalog(
            domain: Annotated[str, "领域 ID；空字符串返回领域总览"] = "",
            tool: Annotated[str, "精确工具名；指定后返回完整参数 Schema"] = "",
            ctx: Context = None,
        ) -> dict:
            """按需查看 EBX 工具领域或单个工具的完整参数 Schema。"""
            tools = await transform.get_tool_catalog(ctx)
            if tool:
                matches = [item for item in tools if item.name == tool]
                if domain and domain not in DOMAINS:
                    return {"ok": False, "code": "UNKNOWN_DOMAIN", "domain": domain}
                if not matches:
                    return {"ok": False, "code": "UNKNOWN_TOOL", "tool": tool}
                selected = matches[0]
                if domain and domain_of(selected) != domain:
                    return {"ok": False, "code": "DOMAIN_MISMATCH", "tool": tool, "domain": domain}
                return {
                    "ok": True,
                    "tool": {
                        "name": selected.name,
                        "domain": domain_of(selected),
                        "summary": _summary(selected),
                        "description": selected.description,
                        "input_schema": selected.parameters,
                        "output_schema": selected.output_schema,
                    },
                }
            if domain:
                if domain not in DOMAINS:
                    return {"ok": False, "code": "UNKNOWN_DOMAIN", "valid": list(DOMAINS)}
                return {
                    "ok": True,
                    "domain": domain,
                    "title": DOMAINS[domain]["title"],
                    "summary": DOMAINS[domain]["summary"],
                    "tools": [_compact_tool(item) for item in _domain_filter(tools, domain)],
                }
            counts = Counter(domain_of(item) for item in tools)
            return {
                "ok": True,
                "bootstrap_tools": BOOTSTRAP_TOOLS,
                "registered_tools": len(tools),
                "domains": [
                    {
                        "id": key,
                        "title": value["title"],
                        "summary": value["summary"],
                        "count": counts[key],
                        "aliases": value["aliases"],
                    }
                    for key, value in DOMAINS.items()
                    if counts[key]
                ],
            }

        return Tool.from_function(fn=ebx_catalog, name="ebx_catalog")

    def _make_search_tool(self) -> Tool:
        transform = self

        async def ebx_find_tools(
            query: Annotated[str, "中文、英文或精确工具名关键词"],
            domain: Annotated[str, "可选领域 ID"] = "",
            limit: Annotated[int, "返回数量，1–10"] = 6,
            ctx: Context = None,
        ) -> str:
            """按中文子串、英文别名或工具名检索；不返回完整 Schema，按需再用目录查询。"""
            if domain and domain not in DOMAINS:
                return "未知领域 %r；可选: %s" % (domain, ", ".join(DOMAINS))
            terms = _terms(query)
            if not terms:
                return "query 不能为空。"
            tools = await transform._get_visible_tools(ctx)
            if domain:
                tools = _domain_filter(tools, domain)
            scored = [(search_score(tool, terms), tool) for tool in tools]
            matched = [(score, tool) for score, tool in scored if score > 0]
            matched.sort(key=lambda pair: (-pair[0], pair[1].name))
            return render_search([tool for _, tool in matched[:max(1, min(limit, 10))]])

        return Tool.from_function(fn=ebx_find_tools, name="ebx_find_tools")

    async def _search(self, tools: Sequence[Tool], query: str) -> Sequence[Tool]:
        terms = _terms(query)
        scored = [(search_score(tool, terms), tool) for tool in tools]
        matched = [(score, tool) for score, tool in scored if score > 0]
        matched.sort(key=lambda pair: (-pair[0], pair[1].name))
        return [tool for _, tool in matched[:self._max_results]]
