# search_service.py
from mcp.server.fastmcp import FastMCP
from tavily import TavilyClient
import os

# 1. 初始化框架
mcp = FastMCP("SearchService")

# 注意：生产环境下建议使用 os.getenv("TAVILY_API_KEY")
tavily_client = TavilyClient(api_key="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")

# --- Resource (资源) ---
@mcp.resource("config://search_policy")
def get_search_policy() -> str:
    """获取搜索服务的限制和合规性政策"""
    return (
        "1. 搜索限制：严禁搜索任何涉及个人隐私、色情或暴力违规的内容。\n"
        "2. 优先级：如果用户问题可以通过本地资源解决，则无需调用互联网搜索。\n"
        "3. 数据引用：在返回结果时，必须保留原文的来源链接 (URL)。"
    )

# --- Prompt (提示词模板) ---
@mcp.prompt("structured_search")
def create_search_prompt(topic: str) -> str:
    """这是一个引导 AI 进行高质量结构化搜索的模板"""
    return (
        f"用户想要了解关于 '{topic}' 的信息。\n"
        "请你按照以下步骤操作：\n"
        "1. 首先阅读 config://search_policy 获取搜索合规要求。\n"
        "2. 使用 internet_search 工具获取最新信息。\n"
        "3. 总结结果，并以‘根据最新搜索结果...’开头进行回答。"
    )

# 2. 封装动作：工具 (Tool)
@mcp.tool()
def internet_search(query: str) -> str:
    """这是一个功能强大的互联网搜索工具。
    当用户询问实时新闻、近期发生的事件或需要从互联网获取知识时，必须调用此工具。
    """
    try:
        response = tavily_client.search(query=query, search_depth="basic", max_results=3)
        results = []
        for res in response.get("results", []):
            content = res.get("content", "")
            url = res.get("url", "")
            results.append(f"内容: {content}\n来源: {url}")
        
        return "\n\n---\n\n".join(results) if results else "未找到相关结果。"
        
    except Exception as e:
        return f"搜索过程中发生错误: {str(e)}"

if __name__ == "__main__":
    mcp.run()

# npx @modelcontextprotocol/inspector@0.15.0 uv run python MCP/searsh_mcp.py