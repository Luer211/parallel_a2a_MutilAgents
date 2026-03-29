import operator
import os
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Dict, List, TypedDict

from langchain.chat_models import init_chat_model
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.types import Send
from pydantic import BaseModel, Field

from app.analyze_graph.analyze_subgraph import create_analyze_subgraph
from app.pipeline_graph.subgraph import create_pipeline_subgraph


class Output(BaseModel):
    """输出的结构"""
    report_summary: str = Field(..., description="财报解析结果")
    company_news_summary: str = Field(..., description="公司新闻摘要")
    industry_news_summary: str = Field(..., description="行业新闻摘要")
    investment_conclusion: str = Field(..., description="投研结论")


model = init_chat_model(
    model="gpt-4o-mini",
    api_key=os.getenv("API_KEY"),
    base_url=os.getenv("BASE_URL"),
)


class MainState(TypedDict):
    """主State"""
    # 原始财报
    original_report: str
    report_task: str
    company_news_task: str
    industry_news_task: str
    pipeline_inputs: List[Dict[str, Any]]
    report: Annotated[str, operator.add]
    company_news: Annotated[str, operator.add]
    industry_news: Annotated[str, operator.add]
    user_confirm: bool
    final_summary: str
    structured_memo: Dict[str, Any]
    final_output: Dict[str, Any]

class TargetInfo(BaseModel):
    company_name: str = Field(..., description="公司名称")
    industry_name: str = Field(..., description="行业名称")

def get_data(state: MainState):
    extract_prompt = f"""

    从下面财报文本中提取：
    1) 公司名称
    2) 所属行业
    只返回结构化结果。

    文本：
    {state['original_report']}

    """.strip()

    info = model.with_structured_output(TargetInfo).invoke(
        [{"role": "user", "content": extract_prompt}]
    )

    company = (info.company_name or "").strip() or "目标公司"
    industry = (info.industry_name or "").strip() or "所属行业"

    return {
        "report_task": f"分析财报：{state['original_report']}",
        "company_news_task": f"获取公司新闻：{company}",
        "industry_news_task": f"获取行业新闻：{industry}",
        "report": "",
        "company_news": "",
        "industry_news": "",
    }


def parse_and_process(state: MainState):
    """把三类任务整理成列表"""
    tasks: List[Dict[str, Any]] = [
        {
            "route": "choices_a",
            "task_description": state["report_task"],
        },
        {
            "route": "choices_b",
            "task_description": state["company_news_task"],
        },
        {
            "route": "choices_c",
            "task_description": state["industry_news_task"],
        },
    ]
    return {"pipeline_inputs": tasks}


def fanout_PipelineSubgraph(state: MainState):
    """将三个任务扇出"""
    sends = []
    for task in state["pipeline_inputs"]:
        sends.append(Send("run_PipelineSubgraph", {"task": task}))
    return sends


def run_PipelineSubgraph(state):
    """调用 pipeline_subgraph.invoke(...) 真正执行单条任务，并合并"""
    task = state["task"]

    sub_result = pipeline_subgraph.invoke(
        {
            "route": task["route"],
            "task_description": task["task_description"],
        }
    )

    return {
        k: v
        for k, v in sub_result.items()
        if k in ["report", "company_news", "industry_news"]
    }


def HITL(state: MainState):
    """人机确认节点"""
    report = state["report"]
    company_news = state["company_news"]
    industry_news = state["industry_news"]

    print(f"已收集信息：{report}\n{company_news}\n{industry_news}\n")
    user_input = input("是否确认继续？(true/false): ")

    confirm = user_input.lower() == "true"

    return {"user_confirm": confirm}


def fanout_AnalyzeSubgraph(state: MainState):
    """发送信息到分析子图"""
    return [
        Send(
            "run_AnalyzeSubgraph",
            {},
        )
    ]


def run_AnalyzeSubgraph(state):
    """调用 analyze_subgraph，输入三类信息，拿回分析结果中的 final_summary。"""
    response = analyze_subgraph.invoke(
        {
            "report": state["report"],
            "company_news": state["company_news"],
            "industry_news": state["industry_news"],
        }
    )
    return {
        "final_summary": response["final_summary"],
        "structured_memo": response.get("structured_memo", {}),
    }


def summary_and_output(state: MainState):
    memo = state.get("structured_memo") or {}
    if not memo:
        memo = {
            "one_line_summary": state.get("final_summary", ""),
            "merged_evidence": [],
            "conflicts": [],
            "conclusion": {
                "stance": "neutral",
                "action": "watch",
                "conviction": 0.3,
                "thesis": state.get("final_summary", ""),
                "key_risks": [],
                "catalysts": [],
            },
            "monitoring_checklist": [],
        }
    return {"final_output": memo}



main_builder = StateGraph(MainState)

main_builder.add_node("get_data", get_data)
main_builder.add_node("parse_and_process", parse_and_process)
main_builder.add_node("run_PipelineSubgraph", run_PipelineSubgraph)
main_builder.add_node("HITL", HITL)
main_builder.add_node("fanout_AnalyzeSubgraph", fanout_AnalyzeSubgraph)
main_builder.add_node("run_AnalyzeSubgraph", run_AnalyzeSubgraph)
main_builder.add_node("summary_and_output", summary_and_output)

main_builder.add_edge(START, "get_data")
main_builder.add_edge("get_data", "parse_and_process")
main_builder.add_conditional_edges(
    "parse_and_process",
    fanout_PipelineSubgraph,
    ["run_PipelineSubgraph"],
)
main_builder.add_edge("run_PipelineSubgraph", "HITL")


def HITL_condition(state: MainState):
    if state["user_confirm"] is True:
        return "yes"
    return "no"


main_builder.add_conditional_edges(
    "HITL",
    HITL_condition,
    {
        "yes": "run_AnalyzeSubgraph",
        "no": "get_data",
    },
)

main_builder.add_edge("fanout_AnalyzeSubgraph", "run_AnalyzeSubgraph")
main_builder.add_edge("run_AnalyzeSubgraph", "summary_and_output")
main_builder.add_edge("summary_and_output", END)

pipeline_subgraph = create_pipeline_subgraph()
analyze_subgraph = create_analyze_subgraph()
main_graph = main_builder.compile()


def run_invest_pipeline(original_report: str):
    result = main_graph.invoke({"original_report": original_report})

    final_output = result.get("final_output")
    if final_output:
        md_path = save_report_to_md(final_output)
        print(f"投研报告已保存为 Markdown 文件：{md_path}")

    return result


def save_report_to_md(final_output: dict, output_dir: str = "reports") -> str:
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"investment_report_{timestamp}.md"
    filepath = Path(output_dir) / filename

    evidence = final_output.get("merged_evidence", [])
    conflicts = final_output.get("conflicts", [])
    conclusion = final_output.get("conclusion", {})
    checklist = final_output.get("monitoring_checklist", [])

    evidence_md = "\n".join(
        [
            f"- [{i.get('source', 'unknown')}] {i.get('claim', '')} "
            f"(impact={i.get('impact', 'neutral')}, confidence={i.get('confidence', 0)})"
            for i in evidence
        ]
    ) or "- 无"

    conflicts_md = "\n".join(
        [
            f"- {c.get('topic', '')} | severity={c.get('severity', 'low')} | "
            f"hint={c.get('resolution_hint', '')}"
            for c in conflicts
        ]
    ) or "- 无"

    risks_md = "\n".join([f"- {x}" for x in conclusion.get("key_risks", [])]) or "- 无"
    catalysts_md = "\n".join([f"- {x}" for x in conclusion.get("catalysts", [])]) or "- 无"
    checklist_md = "\n".join([f"- {x}" for x in checklist]) or "- 无"

    md_content = f"""
# 投研分析报告

## 一句话总结
{final_output.get("one_line_summary", "")}

## 证据合并
{evidence_md}

## 关键冲突
{conflicts_md}

## 投资结论
- stance: {conclusion.get("stance", "neutral")}
- action: {conclusion.get("action", "watch")}
- conviction: {conclusion.get("conviction", 0)}
- thesis: {conclusion.get("thesis", "")}

### 主要风险
{risks_md}

### 潜在催化剂
{catalysts_md}

## 跟踪清单
{checklist_md}

---
*生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}*
    """

    filepath.write_text(md_content, encoding="utf-8")
    return str(filepath)

