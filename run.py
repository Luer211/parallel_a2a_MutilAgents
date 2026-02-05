# run.py
import uvicorn
from dotenv import load_dotenv

def main():
    load_dotenv()

    # 2. 启动 FastAPI
    uvicorn.run(
        "main:app",     # main.py 中的 app 实例
        host="0.0.0.0",
        port=8000,
        reload=True
    )

if __name__ == "__main__":
    main()
