import os
import asyncio
from typing import Dict, Any
from dotenv import load_dotenv

# 加载环境变量 (必须在导入 app 模块之前)
load_dotenv()

from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field

# 假设我们在项目根目录运行
# 引入 graph (需要确保 app 在 python path 中)
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from app.main_graph.graph import run_invest_pipeline

# ======= Eval Models =======
class EvaluationResult(BaseModel):
    score: int = Field(..., description="评分 0-100")
    reasoning: str = Field(..., description="评分理由")
    missing_points: list[str] = Field(..., description="遗漏的关键点")

# ======= Evaluator =======
class Evaluator:
    def __init__(self):
        self.model = init_chat_model(
            model="gpt-4o-mini",
            api_key=os.getenv("API_KEY"),
            base_url=os.getenv("BASE_URL"),
        )

    def evaluate_report(self, generated_report: Dict[str, Any], ground_truth: str) -> EvaluationResult:
        """
        使用 LLM-as-a-Judge 评估生成的报告
        """
        # 拼接生成的报告内容
        report_content = f"""
        【财报摘要】{generated_report.get('report_summary')}
        【公司新闻】{generated_report.get('company_news_summary')}
        【行业新闻】{generated_report.get('industry_news_summary')}
        【投资结论】{generated_report.get('investment_conclusion')}
        """

        prompt = f"""
        你是专业的投研报告评审员。请对比“生成的报告”与“参考标准(Ground Truth)”，进行打分。

        【参考标准 (Ground Truth)】
        {ground_truth}

        【生成的报告】
        {report_content}

        请评估：
        1. 准确性：生成报告是否包含了参考标准中的关键事实？
        2. 完整性：是否有重大遗漏？
        3. 幻觉：是否有捏造的数据？

        请输出 JSON 格式的评分结果。
        """

        result = self.model.with_structured_output(EvaluationResult).invoke(prompt)
        return result

# ======= Test Case =======
def run_eval():
    print("🚀 开始评测...")
    
    # 1. 模拟输入数据 (这里用简单的文本代替文件上传)
    mock_report_text = """
    【模拟财报】
    公司：TechCorp
    年份：2024
    营收：100亿 (同比增长 20%)
    净利润：15亿 (同比增长 5%)
    风险：面临反垄断调查。
    """

    # 2. 定义 Ground Truth (期望 AI 提取出的核心信息)
    ground_truth = """
    1. TechCorp 2024年营收100亿，增长20%。
    2. 净利润15亿，增长5%。
    3. 存在反垄断调查风险。
    4. 需要结合新闻分析反垄断的影响。
    """

    print(f"📊 输入财报长度: {len(mock_report_text)} chars")
    
    # 3. 运行 Pipeline
    # 注意：run_invest_pipeline 内部调用了 main_graph.invoke
    # 我们需要 patch 一下，或者直接调用 graph。
    # 这里直接调用 run_invest_pipeline，它接受 str
    try:
        result = run_invest_pipeline(mock_report_text)
        final_output = result["final_output"]
        
        print("✅ Pipeline 运行成功")
        
        # 4. 评估
        evaluator = Evaluator()
        eval_result = evaluator.evaluate_report(final_output, ground_truth)
        
        print("\n🏆 评测结果:")
        print(f"分数: {eval_result.score}/100")
        print(f"理由: {eval_result.reasoning}")
        print(f"遗漏点: {eval_result.missing_points}")
        
    except Exception as e:
        print(f"❌ 运行失败: {e}")

if __name__ == "__main__":
    run_eval()
