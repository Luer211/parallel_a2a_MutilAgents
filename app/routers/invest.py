# api/routers/invest.py
from fastapi import APIRouter, UploadFile, File
from app.main_graph.graph import run_invest_pipeline

router = APIRouter(prefix="/invest", tags=["Investment Analysis"])

# ---- 文件 → 文本解析工具（初版） ----
def read_text_from_file(file: UploadFile) -> str:
    filename = file.filename.lower()
    data = file.file.read().decode("utf-8")

    if filename.endswith(".md") or filename.endswith(".txt"):
        return data
    else:
        raise ValueError("暂时只支持 md/txt，其它格式稍后扩展 PDF/DOCX")

# ---- API ----
@router.post("/analysis")
async def analyze_report(file: UploadFile = File(...)):
    # 1. 读取文本
    original_report = read_text_from_file(file)

    # 2. 调用主图
    result = run_invest_pipeline(original_report)

    # 3. 返回结果
    return {
        "status": "success",
        "data": result["final_output"]
    }
