import os
from typing import Literal, TypedDict
from langchain.chat_models import init_chat_model
from langchain_core.tools import tool
from langgraph.constants import START, END
from langgraph.graph import  StateGraph
from pydantic import BaseModel
from sqlalchemy import text


# ======= Tools =======



# ======= Pydantic =======
class Output(BaseModel):

# ======= Models =======
model = init_chat_model(
        model="gpt-4o-mini",
        api_key=os.getenv("API_KEY"),
        base_url=os.getenv("BASE_URL"),
)

# ======= Prompt =======
Prompt1 = ("""""")

# ======= State =======
class PipelineState(TypedDict):
    # 由主图传进来：
    route: Literal["choices_a", "choices_b", "choices_c"] # 动态路由选择
    task_description: str   # 当前这条任务的描述

    # 子图产出的结果三选一：
    report: str
    company_news: str
    industry_news: str

# ======= Node =======
"""动态路由接收来自主图的信息，动态选择路由"""
# 这里要实现三条动态选择边
def dynamic_router(state: PipelineState):
    # 拿到输入
    # 拿到输入的任务键的值
    # 判断去哪条路
    return {}

"""财报解析"""
def report_analysis():
    # 拿到输入的任务描述
    # 解析财报，去掉冗余的信息。其实是不是可以不去除。
    return {"report": text}

"""公司新闻获取"""
def get_company_news():
    # 拿到输入的任务描述
    # 发起检索
    # 返回三条结果，封装成列表返回
    return {"company_news": text}

"""行业新闻获取"""
def get_industry_news():
    # 拿到输入的任务描述
    # 发起检索
    # 返回三条结果，封装成列表返回
    return {"industry_news": text}


# ====== 建图 ======
def create_pipeline_subgraph():
    """关联State"""
    Pipeline_builder = StateGraph(PipelineState)

    """注册Node"""
    Pipeline_builder.add_node("dynamic_router", dynamic_router)
    Pipeline_builder.add_node("report_analysis", report_analysis)
    Pipeline_builder.add_node("get_company_news", get_company_news)
    Pipeline_builder.add_node("get_industry_news", get_industry_news)

    """连接Edge"""
    Pipeline_builder.add_edge(START, dynamic_router)

    Pipeline_builder.add_conditional_edges(
        "dynamic_router",
        lambda state: state["route"],
        {
            "choices_a": "report_analysis",
            "choices_b": "get_company_news",
            "choices_c": "get_industry_news",
        },
    )

    Pipeline_builder.add_edge(report_analysis, END)
    Pipeline_builder.add_edge(get_company_news, END)
    Pipeline_builder.add_edge(get_industry_news, END)

    """创建图"""
    return Pipeline_builder.compile()