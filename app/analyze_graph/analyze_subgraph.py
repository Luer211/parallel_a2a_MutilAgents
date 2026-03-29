import json
import os
from typing import Any, Dict, List, Literal, Optional, TypedDict

from langchain.chat_models import init_chat_model
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from pydantic import BaseModel, Field

# ======= Tools =======

# ======= Pydantic =======
class EvidenceItem(BaseModel):
    source: Literal["report", "company_news", "industry_news"] = Field(..., description="证据来源")
    claim: str = Field(..., description="可验证的事实陈述")
    impact: Literal["positive", "negative", "neutral"] = Field(..., description="对投资判断的方向性影响")
    confidence: float = Field(..., ge=0.0, le=1.0, description="该证据可靠度，0-1")


class ConflictItem(BaseModel):
    topic: str = Field(..., description="冲突主题")
    bullish_evidence: List[str] = Field(default_factory=list, description="支持乐观看法的证据")
    bearish_evidence: List[str] = Field(default_factory=list, description="支持谨慎/悲观看法的证据")
    severity: Literal["low", "medium", "high"] = Field(..., description="冲突严重程度")
    resolution_hint: str = Field(..., description="如何消解该冲突或后续如何验证")


class InvestmentConclusion(BaseModel):
    stance: Literal["bullish", "neutral", "bearish"] = Field(..., description="综合结论倾向")
    action: Literal["buy", "hold", "sell", "watch"] = Field(..., description="建议动作")
    conviction: float = Field(..., ge=0.0, le=1.0, description="结论置信度，0-1")
    thesis: str = Field(..., description="核心投资论点")
    key_risks: List[str] = Field(default_factory=list, description="主要风险")
    catalysts: List[str] = Field(default_factory=list, description="潜在催化剂")


class StructuredInvestmentMemo(BaseModel):
    one_line_summary: str = Field(..., description="一句话结论")
    merged_evidence: List[EvidenceItem] = Field(default_factory=list, description="合并后的关键证据")
    conflicts: List[ConflictItem] = Field(default_factory=list, description="冲突与分歧")
    conclusion: InvestmentConclusion = Field(..., description="最终投资结论")
    monitoring_checklist: List[str] = Field(default_factory=list, description="后续跟踪清单")


# ======= Models =======
model = init_chat_model(
    model="gpt-4o-mini",
    api_key=os.getenv("API_KEY"),
    base_url=os.getenv("BASE_URL"),
)

# ======= Prompt =======
Prompt1 = """
你是 buy-side 投资研究分析师。基于财报、公司新闻、行业新闻完成四件事：
1) 合并证据：抽取去重后的关键事实，注明来源、影响方向与可靠度。
2) 找冲突：识别证据之间与观点之间的矛盾，给出冲突严重度与验证建议。
3) 给结论：形成清晰可执行的投资判断（倾向、动作、置信度、核心论点、风险与催化剂）。
4) 输出 structured investment memo：严格按给定 schema 产出。

要求：
- 不编造输入中不存在的事实；信息不足时明确写出不确定性。
- `merged_evidence` 与 `conflicts` 必须覆盖正反信息，不要只给单边观点。
- 语言简洁，偏投研表达，中文输出。
""".strip()


# ======= State =======
class AnalyzeState(TypedDict, total=False):
    report: str
    company_news: str
    industry_news: str

    # 最终摘要
    final_summary: Optional[str]
    # 结构化投研 memo
    structured_memo: Optional[Dict[str, Any]]


# ======= Node =======
def analyze_and_summary(state: AnalyzeState):
    user_prompt = f"""
    【财报】
    {state.get("report", "")}

    【公司新闻】
    {state.get("company_news", "")}

    【行业新闻】
    {state.get("industry_news", "")}
    """.strip()

    structured_model = model.with_structured_output(StructuredInvestmentMemo)
    response = structured_model.invoke(
        [
            {"role": "system", "content": Prompt1},
            {"role": "user", "content": user_prompt},
        ]
    )

    memo: Dict[str, Any]
    if isinstance(response, BaseModel):
        memo = response.model_dump() if hasattr(response, "model_dump") else response.dict()
    elif isinstance(response, dict):
        memo = response
    else:
        # fallback: 避免上游因异常格式中断
        memo = {
            "one_line_summary": str(response),
            "merged_evidence": [],
            "conflicts": [],
            "conclusion": {
                "stance": "neutral",
                "action": "watch",
                "conviction": 0.3,
                "thesis": str(response),
                "key_risks": ["模型未返回结构化字段"],
                "catalysts": [],
            },
            "monitoring_checklist": ["检查模型结构化输出配置"],
        }

    final_summary = memo.get("one_line_summary") or json.dumps(memo, ensure_ascii=False)
    return {"final_summary": final_summary, "structured_memo": memo}


# ====== Build Graph ======
def create_analyze_subgraph():
    analyze_builder = StateGraph(AnalyzeState)
    analyze_builder.add_node("analyze_and_summary", analyze_and_summary)

    analyze_builder.add_edge(START, "analyze_and_summary")
    analyze_builder.add_edge("analyze_and_summary", END)

    return analyze_builder.compile()
