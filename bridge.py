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
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")
MUSIC_BASE = "https://mp3.mrhung.io.vn"

app = FastAPI()

async def brave_search(query: str):
    if not BRAVE_API_KEY:
        return {"error": "Chua co BRAVE_API_KEY"}
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get("https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": 5},
            headers={"Accept": "application/json", "X-Subscription-Token": BRAVE_API_KEY})
        return r.json()

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

async def get_audio_url(video_id: str):
    """Lay link audio truc tiep tu Piped / Invidious - de ESP32 phat duoc."""
    piped_instances = ["https://piped.video", "https://piped.privacyredirect.com", "https://piped.adminforge.de"]
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as c:
        for inst in piped_instances:
            try:
                r = await c.get(f"{inst}/api/v1/streams/{video_id}")
                if r.status_code == 200:
                    d = r.json()
                    audios = d.get("audioStreams") or []
                    if audios:
                        # Uu tien opus/m4a, bitrate cao
                        audios = sorted(audios, key=lambda x: x.get("bitrate", 0), reverse=True)
                        return audios[0].get("url"), d.get("title"), d.get("uploader")
            except Exception:
                continue
        # Fallback Invidious latest_version
        for inst in ["https://invidious.0011.lt", "https://inv.nadeko.net"]:
            try:
                url = f"{inst}/latest_version?id={video_id}&itag=140&local=true"
                return url, "", ""
            except Exception:
                continue
    return None, "", ""

async def search_music(q: str):
    """Tim nhac Viet tren YouTube, tra ve DANG XIAOZHI HIEU DE PHAT."""
    instances = ["https://invidious.0011.lt", "https://inv.nadeko.net", "https://invidious.privacyredirect.com"]
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as c:
        for inst in instances:
            try:
                r = await c.get(f"{inst}/api/v1/search", params={"q": q, "type": "video"})
                if r.status_code == 200 and r.json():
                    v = r.json()[0]
                    vid = v.get("videoId")
                    title = v.get("title")
                    author = v.get("author")
                    audio_url, _, _ = await get_audio_url(vid)
                    if audio_url:
                        # DAY LA FORMAT CHUAN DE XIAOZHI PHAT, KHONG PHAI LINK YOUTUBE WATCH
                        return {
                            "type": "resource_link",
                            "uri": "resource://read_from_http",
                            "url": audio_url,
                            "title": title,
                            "author": author,
                            "videoId": vid,
                            "play_url": audio_url,
                            "note": f"Dang phat: {title} - {author}. Day la link audio truc tiep, hay phat ngay."
                        }
                    return {"title": title, "author": author, "videoId": vid, "note": "Tim thay bai roi nhung chua lay duoc audio, hay goi play_music voi videoId nay"}
            except Exception:
                continue
    return {"query": q, "note": "Khong tim thay, hay thu lai voi ten bai + ten ca si"}

async def play_music(videoId: str = "", q: str = "", url: str = ""):
    """Tool rieng de phat - Xiaozhi goi tool nay thi no se phat duoc."""
    vid = videoId or ""
    if not vid and url and "v=" in url:
        vid = url.split("v=")[-1].split("&")[0]
    if not vid and q:
        # Tim roi lay audio
        res = await search_music(q)
        return res
    if vid:
        audio_url, title, author = await get_audio_url(vid)
        if audio_url:
            return {"type": "resource_link", "uri": "resource://read_from_http", "url": audio_url, "title": title, "author": author, "note": "Dang phat nhac, hay phat url nay ngay"}
    return {"error": "Khong lay duoc audio, hay thu bai khac"}

@app.get("/health")
async def health():
    return {"status": "ok", "has_mcp": bool(MCP_ENDPOINT), "has_brave": bool(BRAVE_API_KEY), "has_news": bool(NEWS_API_KEY)}

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
