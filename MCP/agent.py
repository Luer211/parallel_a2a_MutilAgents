# agent_client.py
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

# 1. 配置如何连接到刚才写的 Service
# 这就像告诉电脑：“USB 设备（Service）的路径在这里，用 python 运行它”
server_params = StdioServerParameters(
    command="python",
    args=["search_service.py"] 
)

async def run_my_agent():
    # 2. 建立通信管道 (stdio 方式)
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # 3. 初始化并握手（SDK 自动处理协议细节）
            await session.initialize()
            
            # 4. 【关键】将 MCP 工具动态封装为 LangGraph 工具
            # 我们从 MCP Server 动态获取工具信息
            @tool
            async def call_mcp_search(query: str):
                """调用此工具进行互联网搜索。"""
                # 通过 MCP 协议远程调用 Service 里的函数
                result = await session.call_tool("internet_search", arguments={"query": query})
                return result.content[0].text

            # 5. 构建 LangGraph Agent
            model = ChatOpenAI(model="gpt-4o")
            tools = [call_mcp_search]
            
            # 使用 LangGraph 的内置框架创建 Agent
            agent = create_react_agent(model, tools)

            # 6. 测试
            print("Agent 已就绪，正在准备提问...")
            inputs = {"messages": [("user", "现在最新的奥斯卡最佳影片是谁？")]}
            
            # 运行并打印过程
            async for event in agent.astream(inputs, stream_mode="values"):
                last_message = event["messages"][-1]
                if last_message.type == "assistant" and last_message.content:
                    print(f"\nAI 回答: {last_message.content}")

if __name__ == "__main__":
    # 设置 OpenAI 环境变量（或直接在代码里设置）
    # os.environ["OPENAI_API_KEY"] = "sk-..."
    asyncio.run(run_my_agent())