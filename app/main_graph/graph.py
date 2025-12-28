import operator
import os
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Dict, List, Literal, TypedDict
from langgraph.types import Send
from fastapi import APIRouter, Depends
from langchain.chat_models import init_chat_model
from langgraph.constants import START, END
from langgraph.graph import MessagesState, StateGraph
from langgraph.checkpoint.memory import InMemorySaver  
from langgraph.prebuilt import ToolNode, tools_condition
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.a2a_graph.subgraph import create_a2a_subgraph
from app.pipeline_graph.subgraph import create_pipeline_subgraph

# ======= Tools =======

# ======= Pydantic =======
class Output(BaseModel):
    """最终对外输出结构"""
    report_summary: str = Field(..., description="财报解析结果")
    company_news_summary: str = Field(..., description="公司新闻摘要")
    industry_news_summary: str = Field(..., description="行业新闻摘要")
    investment_conclusion: str = Field(..., description="多智能体投研结论")

# ======= Models =======
model = init_chat_model(
        model="gpt-4o-mini",
        api_key=os.getenv("API_KEY"),
        base_url=os.getenv("BASE_URL"),
    )

# ======= Prompt =======

# ======= State =======
class MainState(TypedDict):
    # 财报本身
    original_report: str

    # 财报解析任务
    report_task: str
    # 获取公司新闻任务
    company_news_task: str
    # 获取行业新闻任务
    industry_news_task: str

    # 给管道的输入
    pipeline_inputs: List[Dict[str, Any]]

    # 【关键修改】使用 Reducer 确保并行任务的结果是“累加”或“收集”
    # 如果子图返回的是 str，这里会把字符串拼起来；建议用 List 存储
    report: Annotated[str, operator.add] 
    company_news: Annotated[str, operator.add]
    industry_news: Annotated[str, operator.add]

    # 用户确认键
    user_confirm: bool

    # 投研讨论
    final_summary: str

    # 最终报告输出
    final_output: Dict[str, Any]


# ======= Node =======
"""获取数据，解析成三个任务"""
def get_data(state: MainState):
    return {
        "report_task": f"分析财报：{state['original_report']}",
        "company_news_task": "获取公司新闻",
        "industry_news_task": "获取行业新闻",
        "report": "", "company_news": "", "industry_news": "" 
    }
    
"""解析数据、加键"""
def parse_and_process(state: MainState):
    # 解析成三条记录，每一个是一个字典，有任务类型+任务描述
    tasks: List[Dict[str, Any]] = [
        {
            "route": "choices_a",          # → 财报解析
            "task_description": state["report_task"],
        },
        {
            "route": "choices_b",          # → 公司新闻
            "task_description": state["company_news_task"],
        },
        {
            "route": "choices_c",          # → 行业新闻
            "task_description": state["industry_news_task"],
        },
    ]
    return {"pipeline_inputs": tasks}

"""fan-out分发路由：Send到并行处理子图"""
def fanout_PipelineSubgraph(state: MainState):
    # 把三条记录Send到三个子图
    sends = []
    for task in state["pipeline_inputs"]:
        # Send 到主图里的节点名 "run_PipelineSubgraph"
        # task 里已经有 route + task_description 了
        sends.append(Send("run_PipelineSubgraph", {"task": task}))
    return sends


"""定义并行处理子图数据收回方式"""
def run_PipelineSubgraph(state):
    task = state["task"]

    sub_result = pipeline_subgraph.invoke(
        {
            "route": task["route"],
            "task_description": task["task_description"],
        }
    )

    # 只返回命中的键，Reducer 会处理合并
    return {k: v for k, v in sub_result.items() if k in ["report", "company_news", "industry_news"]}


"""HITL,用户拿到汇总的信息，判断是继续往下执行还是重新收集"""
def HITL(state: MainState):
    
    report = state["report"]
    company_news = state["company_news"]
    industry_news = state["industry_news"]

    print(f"已收集信息：{report}\n {company_news}\n {industry_news}\n")
    user_input = input("是否确认继续？(true/false) ：")

    confirm = (user_input.lower() == "true")

    return {"user_confirm": confirm}

"""fan-out分发路由：Send到a2a子图"""
def fanout_A2ASubgraph(state: MainState):
    # Send到a2a子图
    return [
        Send("run_A2ASubgraph", {
            "dialogue_history": [],
            "round": 1,
            "max_round": 5,
        })
    ]

"""定义a2a子图数据收回方式"""
def run_A2ASubgraph(state):
    response = a2a_subgraph.invoke({
        "report": state["report"],
        "company_news": state["company_news"],
        "industry_news": state["industry_news"],
        "dialogue_history": [],
        "round": 1,
        "max_round": 5,
    })
    return {"final_summary": response["final_summary"]}

"""汇总所有结论，输出结构化报告"""
def summary_and_output(state: MainState):
    structured_model = model.with_structured_output(Output)
    prompt = f"""
        你是投资研究分析师。请基于以下已收集信息，生成一份结构化报告。
        要求：
        1) 按字段输出：report_summary、company_news_summary、industry_news_summary、investment_conclusion
        2) 必须覆盖输入信息中的关键事实，避免臆测
        3) 用中文，条理清晰，尽量精炼

        【财报解析】
        {state.get("report", "")}

        【公司新闻】
        {state.get("company_news", "")}

        【行业新闻】
        {state.get("industry_news", "")}

        【多智能体讨论结论】
        {state.get("final_summary", "")}
    """.strip()
    output = structured_model.invoke(prompt)
    # LangGraph State 里放 dict，避免直接塞 Pydantic 对象
    return {"final_output": output.dict()}

# ====== 建图 ======
"""关联State"""
main_builder = StateGraph(MainState)

"""注册Node"""
main_builder.add_node("get_data", get_data)
main_builder.add_node("parse_and_process", parse_and_process)
main_builder.add_node("run_PipelineSubgraph", run_PipelineSubgraph)
main_builder.add_node("HITL", HITL)
main_builder.add_node("fanout_A2ASubgraph", fanout_A2ASubgraph)
main_builder.add_node("run_A2ASubgraph", run_A2ASubgraph)
main_builder.add_node("summary_and_output", summary_and_output)

"""连接Edge"""
main_builder.add_edge(START, "get_data")
main_builder.add_edge("get_data", "parse_and_process")
main_builder.add_conditional_edges(
    "parse_and_process",
    fanout_PipelineSubgraph,
    ["run_PipelineSubgraph"]
)
main_builder.add_edge("run_PipelineSubgraph", "HITL")

# 定义条件边
def HITL_condition(state: MainState):
    if state["user_confirm"] is True:
        return "yes"
    else:
        return "no"
# 使用条件边
main_builder.add_conditional_edges(
    "HITL",
    HITL_condition,
    {
        "yes": "run_A2ASubgraph",           # 用户同意 → 下一步
        "no": "get_data",             # 用户不同意 → 重新收集信息
    }
)

main_builder.add_edge("fanout_A2ASubgraph", "run_A2ASubgraph")
main_builder.add_edge("run_A2ASubgraph", "summary_and_output")
main_builder.add_edge("summary_and_output", END)

"""创建图"""
# 创建两个子图
pipeline_subgraph = create_pipeline_subgraph()
a2a_subgraph = create_a2a_subgraph()
main_graph = main_builder.compile()

"""开始使用"""
def run_invest_pipeline(original_report: str):
    result = main_graph.invoke({"original_report": original_report})

    final_output = result.get("final_output")
    if final_output:
        md_path = save_report_to_md(final_output)
        print(f"📄 投研报告已保存为 Markdown 文件：{md_path}")

    return result

"""将最终投研结果保存为 Markdown 文件"""
def save_report_to_md(final_output: dict, output_dir: str = "reports") -> str:
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"investment_report_{timestamp}.md"
    filepath = Path(output_dir) / filename

    md_content = f"""# 投研分析报告

        ## 一、财报解析摘要
        {final_output.get("report_summary", "")}

        ---

        ## 二、公司新闻摘要
        {final_output.get("company_news_summary", "")}

        ---

        ## 三、行业新闻摘要
        {final_output.get("industry_news_summary", "")}

        ---

        ## 四、投资结论（多智能体讨论）
        {final_output.get("investment_conclusion", "")}

        ---

        *生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}*
    """

    filepath.write_text(md_content, encoding="utf-8")
    return str(filepath)
