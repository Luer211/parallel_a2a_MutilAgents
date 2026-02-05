"""基础搜索工具：使用serpAPI"""
"""进阶搜索工具：使用jinaAPI"""
"""加上无头浏览器的搜索工具：使用browser-use"""

"""专用社区搜索工具"""
"""抖音搜索工具"""
"""小红书搜索工具"""
"""知乎搜索工具"""

class SearchTools:
    def __init__(self):
        self.serp_api_key = os.getenv("SERP_API_KEY")
        self.jina_reader_url = "https://r.jina.ai/"

    async def web_search(self, query: str):
        """
        使用 SerpApi 获取搜索结果列表。
        """
        params = {
            "q": query,
            "api_key": self.serp_api_key,
            "engine": "google"
        }
        async with httpx.AsyncClient() as client:
            response = await client.get("https://serpapi.com/search", params=params)
            results = response.json()
            return results.get("organic_results", [])[:5] # 返回前5条

    async def jina_reader(self, url: str):
        """
        利用 Jina Reader 将网页转为适合 LLM 阅读的 Markdown。
        """
        async with httpx.AsyncClient() as client:
            # Jina Reader 简单到只需要在 URL 前加前缀
            response = await client.get(f"{self.jina_reader_url}{url}")
            return response.text