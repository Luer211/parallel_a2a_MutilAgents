import os
from typing import Any, Dict, List, Literal, TypedDict
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
Prompt1 = ("""""")

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

    # 财报解析
    report: str
    # 公司新闻
    company_news: str
    # 行业新闻
    industry_news: str

    # 用户确认键
    user_confirm: bool

    # 投研讨论
    final_summary: str

    # 最终报告输出
    final_output: Dict[str, Any]


# ======= Node =======
"""获取数据，解析成三个任务"""
def get_data(state: MainState):

    original_report = state.get("original_report")
    if not original_report:
        original_report = input("请输入原始财报文本：\n")

    # 这里先粗暴生成三条任务描述，后面你可以改成 LLM 帮你拆任务
    report_task = f"请对以下财报做结构化分析和要点提炼：\n{original_report}"
    company_news_task = "请根据公司名称，抓取并总结最近 1-3 个月的重要公司新闻。"
    industry_news_task = "请根据公司所在行业，抓取并总结最近 1-3 个月的重要行业新闻。"

    return {
        "report_task": report_task,
        "company_news_task": company_news_task,
        "industry_news_task": industry_news_task,
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

    # 子图只会返回三种键中的一种，我们判断一下是哪种
    if "report" in sub_result:
        return {"report": sub_result["report"]}
    elif "company_news" in sub_result:
        return {"company_news": sub_result["company_news"]}
    elif "industry_news" in sub_result:
        return {"industry_news": sub_result["industry_news"]}
    else:
        # 理论上不会走到这里，留个兜底
        return {}


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
        "dialogue_history": state["dialogue_history"],
        "round": state["round"],
        "max_round": state["max_round"],
    })
    return {"final_summary": response["final_summary"]}

"""汇总所有结论，输出结构化报告"""
def summary_and_output(state: MainState):
    output = Output(
        report_summary=state.get("report", ""),
        company_news_summary=state.get("company_news", ""),
        industry_news_summary=state.get("industry_news", ""),
        investment_conclusion=state.get("final_summary", ""),
    )
    # LangGraph State 里放 dict，避免直接塞 Pydantic 对象
    return {"final_output": output.dict()}

# ====== 建图 ======
"""关联State"""
main_builder = StateGraph(MainState)

"""注册Node"""
main_builder.add_node("get_data", get_data)
main_builder.add_node("parse_and_process", parse_and_process)
main_builder.add_node("fanout_PipelineSubgraph", fanout_PipelineSubgraph)
main_builder.add_node("run_PipelineSubgraph", run_PipelineSubgraph)
main_builder.add_node("HITL", HITL)
main_builder.add_node("fanout_A2ASubgraph", fanout_A2ASubgraph)
main_builder.add_node("run_A2ASubgraph", run_A2ASubgraph)
main_builder.add_node("summary_and_output", summary_and_output)

"""连接Edge"""
main_builder.add_edge(START, get_data)
main_builder.add_edge(get_data, parse_and_process)
main_builder.add_edge(parse_and_process, fanout_PipelineSubgraph)
main_builder.add_edge(fanout_PipelineSubgraph, run_PipelineSubgraph)
main_builder.add_edge(run_PipelineSubgraph, HITL)

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
        "yes": "fanout_A2ASubgraph",           # 用户同意 → 下一步
        "no": "parse_and_process",             # 用户不同意 → 重新收集信息
    }
)

main_builder.add_edge(fanout_A2ASubgraph, run_A2ASubgraph)
main_builder.add_edge(run_A2ASubgraph, summary_and_output)

main_builder.add_edge(summary_and_output, END)

"""创建图"""
# 创建两个子图
pipeline_subgraph = create_pipeline_subgraph()
a2a_subgraph = create_a2a_subgraph()
main_graph = main_builder.compile()

"""开始使用"""
def run_invest_pipeline(original_report: str):
    return main_graph.invoke({"original_report": original_report})