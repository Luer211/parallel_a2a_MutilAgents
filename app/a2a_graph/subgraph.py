import os
from typing import TypedDict, List, Optional
from langchain.chat_models import init_chat_model
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from pydantic import BaseModel, Field

# ======= Tools =======

# ======= Pydantic =======
"""约束按键被正确按下"""
class InvestorOutput(BaseModel):
    opinion: str = Field(..., description="投资者对当前信息的分析判断")
    agree: bool = Field(..., description="该投资者认为是否可以结束讨论")


# ======= Models =======
model = init_chat_model(
        model="gpt-4o-mini",
        api_key=os.getenv("API_KEY"),
        base_url=os.getenv("BASE_URL"),
    )

# ======= Prompt =======
Prompt1 = ("""""")

# ======= State =======
class A2AState(TypedDict):
    report: str                     # 财报
    company_news: str               # 公司新闻
    industry_news: str              # 行业新闻

    dialogue_history: List[str]     # 存放每一轮压缩后的对话
    round: int                      # 当前轮数
    max_round: int                  # 最大轮数（建议 3-5）

    buffett_opinion: str            # 当轮巴菲特观点
    munger_opinion: str             # 当轮芒格观点

    buffett_agree: bool             # 巴菲特认为是否可以结束
    munger_agree: bool              # 芒格认为是否可以结束

    judgment_confirm: bool          # judgment 节点的判断：是否需要结束
    final_summary: Optional[str]    # 最终压缩总结

# ======= Node =======
"""对话压缩"""
def dialogue_compression(state: A2AState):
    # 压缩每一轮上下文
    # 假如是第一轮，不压缩
    # 假如是后面，开始对上一轮的两条意见进行压缩
    round = state["round"]
    history = state["dialogue_history"]

    # 第一轮不压缩
    if round == 1:
        return {}

    # 压缩上一轮 Buffett + Munger 观点
    text = (
        f"请将以下两位投资者的意见压缩浓缩一下：\n"
        f"巴菲特观点：{state['buffett_opinion']}\n"
        f"芒格观点：{state['munger_opinion']}\n"
    )

    responseonseonse = model.invoke([{"role": "user", "content": text}]).content
    history.append(responseonseonse)

    return {"dialogue_history": history}


"""巴菲特llm"""
def Buffett(state: A2AState):
    # 假如是第一轮，输入信息，先输出自己的想法
    # 假如是后面，输入信息、对话记录，输出自己的想法+判断按钮
    round = state["round"]
    history = state["dialogue_history"]

    if round == 1:
        prompt = (
            "你是巴菲特，请根据以下信息给出你的投资观点，并判断是否可以结束讨论：\n"
            f"财报：{state['report']}\n"
            f"公司新闻：{state['company_news']}\n"
            f"行业新闻：{state['industry_news']}\n"
        )
    else:
        prompt = (
            "你是巴菲特，请继续进行投资讨论：\n"
            f"历史压缩观点：{history}\n"
            f"上一轮芒格观点：{state['munger_opinion']}\n"
        )

    response = (
        model
        .with_structured_output(InvestorOutput)
        .invoke([{"role": "user", "content": prompt}])
    )

    return {
        "buffett_opinion": response.opinion,
        "buffett_agree": response.agree,
    }

"""芒格llm"""
def Munger(state: A2AState):
    # 假如是第一轮，输入信息，先输出自己的想法
    # 假如是后面，输入信息、对话记录，输出自己的想法+判断按钮
    round = state["round"]
    history = state["dialogue_history"]

    if round == 1:
        prompt = (
            "你是芒格，请根据以下信息给出你的第一轮投资观点，并判断是否可以结束讨论：\n"
            f"财报：{state['report']}\n"
            f"公司新闻：{state['company_news']}\n"
            f"行业新闻：{state['industry_news']}\n"
        )
    else:
        prompt = (
            "你是芒格，请基于以下内容继续进行投资讨论，并给出你的看法与是否结束讨论的判断：\n"
            f"历史压缩观点：{history}\n"
            f"上一轮巴菲特观点：{state['buffett_opinion']}\n"
        )

    response = (
        model
        .with_structured_output(InvestorOutput)
        .invoke([{"role": "user", "content": prompt}])
    )

    return {
        "munger_opinion": response.opinion,
        "munger_agree": response.agree,
    }


"""判断是否需要下一轮"""
def judgment(state: A2AState):
    # 检查轮询次数
    # 检查一致按钮
    round = state["round"]
    max_round = state["max_round"]

    # 两个投资者是否都同意
    agree = state["buffett_agree"] and state["munger_agree"]

    # 达成一致 or 达到最大轮数
    need_stop = agree or (round >= max_round)

    return {
        "judgment_confirm": need_stop,
        "round": round + 1,  # 下一轮计数
    }

"""最后的对话压缩"""
def final_dialogue_compression(state: A2AState):
    # 对最后一轮对话进行压缩
    prompt = (
        "请将整个对话过程写成最终投资决策总结（50-100 字）：\n"
        f"历史记录：{state['dialogue_history']}\n"
        f"最后一轮巴菲特：{state['buffett_opinion']}\n"
        f"最后一轮芒格：{state['munger_opinion']}"
    )

    summary = model.invoke([{"role": "user", "content": prompt}]).content
    return {"final_summary": summary}

# ====== 建图 ======
def create_a2a_subgraph():
    """关联State"""
    a2a_builder = StateGraph(A2AState)

    """注册Node"""
    a2a_builder.add_node("dialogue_compression", dialogue_compression)
    a2a_builder.add_node("Buffett", Buffett)
    a2a_builder.add_node("Munger", Munger)
    a2a_builder.add_node("judgment", judgment)
    a2a_builder.add_node("final_dialogue_compression", final_dialogue_compression)

    """连接Edge"""
    a2a_builder.add_edge(START, "dialogue_compression")
    a2a_builder.add_edge("dialogue_compression", "Buffett")
    a2a_builder.add_edge("Buffett", "Munger")
    a2a_builder.add_edge("Munger", "judgment")


    # 动态选择
    def judgment_condition(state: A2AState):
        if state["judgment_confirm"] is True:
            return "yes"
        else:
            return "no"
    a2a_builder.add_conditional_edges(
        "judgment",
        judgment_condition,
        {
            "yes": "final_dialogue_compression",      # 达成一致/到达最大轮数 → 最后的压缩
            "no": "dialogue_compression",             # 未达到 → 继续对话
        }
    )

    a2a_builder.add_edge("final_dialogue_compression", END)

    """创建图"""
    return a2a_builder.compile()