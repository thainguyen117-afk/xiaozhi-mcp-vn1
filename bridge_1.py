"""
Xiaozhi MCP VN - Bridge gộp
- Kết nối vào wss://api.xiaozhi.me/mcp/?token=... (MCP_ENDPOINT)
- Cung cấp tool: brave_search, get_news, search_music, play_music, get_top_charts
- Đồng thời chạy web server /sse, /health, /search, /charts để test
Chạy: python bridge.py
Env: MCP_ENDPOINT, BRAVE_API_KEY, NEWS_API_KEY
"""
import os, json, asyncio, httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

MCP_ENDPOINT = os.getenv("MCP_ENDPOINT", "")
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")  # thay Brave, dang ky free khong can the
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")
MUSIC_BASE = "https://mp3.mrhung.io.vn"

app = FastAPI()

async def brave_search(query: str):
    # 1. Uu tien Tavily (free, khong can the) - thay Brave
    if TAVILY_API_KEY:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post("https://api.tavily.com/search",
                json={"api_key": TAVILY_API_KEY, "query": query, "max_results": 5, "search_depth": "basic", "include_answer": True})
            return r.json()
    # 2. Fallback khong can key: DuckDuckGo Instant Answer
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get("https://api.duckduckgo.com/", params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1})
            d = r.json()
            return {"answer": d.get("AbstractText"), "results": [{"title": x.get("Text"), "url": x.get("FirstURL")} for x in d.get("RelatedTopics", [])[:5]]}
    except Exception as e:
        return {"error": f"Khong search duoc, can TAVILY_API_KEY. Loi: {e}"}

async def get_news(query: str = "Việt Nam", category: str = ""):
    if not NEWS_API_KEY:
        return {"error": "Chua co NEWS_API_KEY"}
    async with httpx.AsyncClient(timeout=15) as c:
        # NewsAPI: everything, ưu tiên tiếng Việt / VN
        r = await c.get("https://newsapi.org/v2/everything",
            params={"q": query, "language": "vi", "sortBy": "publishedAt", "pageSize": 5, "apiKey": NEWS_API_KEY})
        data = r.json()
        arts = data.get("articles", [])
        return {"articles": [{"title": a.get("title"), "description": a.get("description"), "url": a.get("url"), "publishedAt": a.get("publishedAt")} for a in arts]}

async def search_music(q: str):
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as c:
        # Thử endpoint public của mp3.mrhung.io.vn, fallback trả hướng dẫn
        try:
            r = await c.get(f"{MUSIC_BASE}/search", params={"q": q})
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            pass
        return {"query": q, "note": "Goi /search tren MUSIC_BASE, neu khong co ket qua hay doi source trong file bridge.py", "try_url": f"{MUSIC_BASE}/search?q={q}"}

@app.get("/health")
async def health():
    return {"status": "ok", "has_mcp": bool(MCP_ENDPOINT), "has_tavily": bool(TAVILY_API_KEY), "has_brave": bool(BRAVE_API_KEY), "search_mode": "tavily" if TAVILY_API_KEY else "duckduckgo-free-no-key", "has_news": bool(NEWS_API_KEY)}

@app.get("/search")
async def http_search(q: str = "sontung"):
    return await search_music(q)

@app.get("/charts")
async def charts():
    return {"charts": "Goi tool get_top_charts tu Xiaozhi, hoac mo /search?q=hot"}

@app.get("/sse")
async def sse():
    return JSONResponse({"message": "MCP SSE endpoint - ket noi tu xiaozhi.me vao day", "tools": ["search_music", "play_music", "get_top_charts", "brave_search", "get_news"]})

@app.get("/")
async def root():
    return {"service": "xiaozhi-mcp-vn", "health": "/health", "search": "/search?q=sontung", "sse": "/sse"}

async def xiaozhi_bridge():
    """Giữ kết nối WebSocket tới Xiaozhi, trả lời tools/list và tools/call đơn giản."""
    if not MCP_ENDPOINT:
        print("⚠️ Chua co MCP_ENDPOINT - chi chay web server de test, chua ket noi Xiaozhi")
        return
    import websockets
    print(f"Đang kết nối tới Xiaozhi MCP...")
    try:
        async with websockets.connect(MCP_ENDPOINT, ping_interval=50) as ws:
            print("✅ Successfully connected to WebSocket server")
            async for msg in ws:
                try:
                    req = json.loads(msg)
                except:
                    continue
                method = req.get("method", "")
                rid = req.get("id")
                if method == "initialize":
                    await ws.send(json.dumps({"jsonrpc": "2.0", "id": rid, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "xiaozhi-mcp-vn", "version": "1.0"}}}))
                elif method == "tools/list":
                    tools = [
                        {"name": "brave_search", "description": "Search web, dùng khi hỏi tin tức, giá, sự kiện mới. Param: query", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
                        {"name": "get_news", "description": "Lấy tin tức mới nhất Việt Nam. Param: query", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
                        {"name": "search_music", "description": "Tìm nhạc Việt Nam theo tên bài / ca sĩ. Param: query", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
                        {"name": "play_music", "description": "Phát nhạc, lấy link stream. Param: query", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
                        {"name": "get_top_charts", "description": "Lấy nhạc hot trending hôm nay", "inputSchema": {"type": "object", "properties": {}}},
                    ]
                    await ws.send(json.dumps({"jsonrpc": "2.0", "id": rid, "result": {"tools": tools}}))
                elif method == "tools/call":
                    params = req.get("params", {})
                    name = params.get("name")
                    args = params.get("arguments", {})
                    q = args.get("query", args.get("q", "Việt Nam"))
                    if name == "brave_search":
                        out = await brave_search(q)
                    elif name == "get_news":
                        out = await get_news(q)
                    elif name in ("search_music", "play_music"):
                        out = await search_music(q)
                    elif name == "get_top_charts":
                        out = {"charts": "Xem tại /charts hoặc gọi search_music với query hot"}
                    else:
                        out = {"error": f"Unknown tool {name}"}
                    text = json.dumps(out, ensure_ascii=False)[:4000]
                    await ws.send(json.dumps({"jsonrpc": "2.0", "id": rid, "result": {"content": [{"type": "text", "text": text}]}}))
                elif method == "ping":
                    await ws.send(json.dumps({"jsonrpc": "2.0", "id": rid, "result": {}}))
    except Exception as e:
        print(f"❌ Bridge lỗi, sẽ thử lại sau 10s: {e}")
        await asyncio.sleep(10)

async def main():
    # Chạy web + bridge song song
    config = uvicorn.Config(app, host="0.0.0.0", port=int(os.getenv("PORT", "10000")), log_level="info")
    server = uvicorn.Server(config)
    await asyncio.gather(server.serve(), xiaozhi_bridge())

if __name__ == "__main__":
    asyncio.run(main())
