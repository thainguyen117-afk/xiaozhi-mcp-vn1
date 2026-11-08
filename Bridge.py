"""
Xiaozhi MCP VN - 1 file duy nhat
Chay: python bridge.py
Env: MCP_ENDPOINT, TAVILY_API_KEY
Tools: brave_search, get_news, search_music, play_music, get_top_charts
"""
import asyncio, hashlib, json, os
import httpx
import uvicorn
import websockets
from fastapi import FastAPI
from fastapi.responses import JSONResponse

# ---------- Config ----------
MCP_ENDPOINT = os.getenv("MCP_ENDPOINT", "")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
PORT = int(os.getenv("PORT", "10000"))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36"}
SC_CLIENT_ID = os.getenv("SOUNDCLOUD_CLIENT_ID", "iZIs9mchVcX5lhVRyQGGAYlNPVldzAo")
AUDIO_CACHE = {}

app = FastAPI()

# ---------- Helpers ----------
def music_result(url, title, author, source, mime="audio/mpeg"):
    """Format chuan de Xiaozhi phat: resource_link, khong phai text."""
    uid = hashlib.md5(url.encode()).hexdigest()[:12]
    uri = f"resource://audio/{uid}"
    AUDIO_CACHE[uri] = {"url": url, "title": title, "author": author, "mimeType": mime}
    AUDIO_CACHE["resource://read_from_http"] = AUDIO_CACHE[uri]
    return {
        "type": "resource_link",
        "uri": uri,
        "url": url, "title": title, "author": author,
        "mimeType": mime, "source": source,
    }

async def fetch_json(client, url, **kwargs):
    try:
        r = await client.get(url, **kwargs)
        return r.json() if r.status_code == 200 else None
    except Exception as e:
        print(f"[fetch] {url} -> {e}")
        return None

# ---------- Search / News ----------
async def brave_search(query: str):
    async with httpx.AsyncClient(timeout=20) as c:
        if TAVILY_API_KEY:
            r = await c.post("https://api.tavily.com/search",
                json={"api_key": TAVILY_API_KEY, "query": query, "max_results": 5, "include_answer": True})
            return r.json()
        data = await fetch_json(c, "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": 1})
        return {"answer": (data or {}).get("AbstractText"), "results": (data or {}).get("RelatedTopics", [])[:5]}

async def get_news(query: str = "Viet Nam"):
    return await brave_search(f"tin tuc moi nhat {query}")

# ---------- Music: Zing -> NCT -> SoundCloud -> iTunes -> Deezer ----------
async def search_music(q: str):
    async with httpx.AsyncClient(timeout=15, headers=UA, follow_redirects=True) as c:
        # 1. SoundCloud (on dinh nhat, co stream mp3 truc tiep)
        data = await fetch_json(c, "https://api-v2.soundcloud.com/search/tracks",
            params={"q": q, "client_id": SC_CLIENT_ID, "limit": 5})
        if data:
            for v in data.get("collection", []):
                tid = v.get("id")
                streams = await fetch_json(c, f"https://api-v2.soundcloud.com/tracks/{tid}/streams",
                    params={"client_id": SC_CLIENT_ID})
                url = (streams or {}).get("http_mp3_128_url") or (streams or {}).get("hls_url")
                if url:
                    return music_result(url, v.get("title"), (v.get("user") or {}).get("username"), "soundcloud")

        # 2. Zing MP3
        data = await fetch_json(c, "https://zingmp3.vn/api/v2/search", params={"q": q})
        songs = ((data or {}).get("data") or {}).get("songs") or []
        if songs:
            v = songs[0]
            stream = await fetch_json(c, "https://zingmp3.vn/api/v2/song/get/streaming",
                params={"id": v.get("encodeId")})
            url = ((stream or {}).get("data") or {}).get("128")
            if url:
                return music_result(url, v.get("title"), v.get("artistsNames"), "zingmp3")

        # 3. Nhaccuatui
        data = await fetch_json(c, "https://www.nhaccuatui.com/api/search", params={"q": q, "type": "song"})
        items = (data or {}).get("data") or (data or {}).get("songs") or []
        if items:
            v = items[0]
            url = v.get("streamUrl") or v.get("previewUrl")
            if url:
                return music_result(url, v.get("title") or v.get("name"), v.get("artist"), "nhaccuatui")

        # 4. iTunes VN (fallback chac chan chay, preview 30s)
        # iTunes TAM TAT: .m4a ESP32 khong phat duoc, de Deezer (MP3) chay truoc
        data = None  # await fetch_json(c, "https://itunes.apple.com/search",
        # params={"term": q, "media": "music", "country": "VN", "limit": 5})
        results = (data or {}).get("results") or []
        if results and results[0].get("previewUrl"):
            v = results[0]
            return music_result(v["previewUrl"], v.get("trackName"), v.get("artistName"), "itunes", "audio/mp4")

        # 5. Deezer (fallback)
        data = await fetch_json(c, "https://api.deezer.com/search", params={"q": q})
        items = (data or {}).get("data") or []
        if items and items[0].get("preview"):
            v = items[0]
            return music_result(v["preview"], v.get("title"), (v.get("artist") or {}).get("name"), "deezer")

    return {"error": f"Khong tim thay bai '{q}'", "note": "Thu ten bai + ten ca si khac"}

# ---------- HTTP (de test nhanh) ----------
@app.get("/")
async def root():
    return {"service": "xiaozhi-mcp-vn", "health": "/health", "test_music": "/search?q=See Tinh Hoang Thuy Linh"}

@app.get("/health")
async def health():
    return {"status": "ok", "has_mcp": bool(MCP_ENDPOINT), "has_tavily": bool(TAVILY_API_KEY)}

@app.get("/search")
async def http_search(q: str = "See Tinh Hoang Thuy Linh"):
    return await search_music(q)

@app.get("/sse")
async def sse():
    return JSONResponse({"tools": ["brave_search", "get_news", "search_music", "play_music", "get_top_charts"]})

# ---------- MCP Bridge (WebSocket toi xiaozhi.me) ----------
TOOLS = [
    {"name": "brave_search", "description": "Search web, tin tuc, gia vang. Param: query",
     "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "get_news", "description": "Tin tuc moi nhat Viet Nam. Param: query",
     "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "search_music", "description": "Tim nhac Viet. Tra ve resource_link de phat. Param: query = ten bai + ca si",
     "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "play_music", "description": "Phat nhac Viet. Tra ve resource_link, KHONG chi gui link YouTube. Param: query",
     "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "get_top_charts", "description": "Nhac hot",
     "inputSchema": {"type": "object", "properties": {}}},
]

async def handle_tool(name: str, q: str):
    if name == "brave_search":
        return [{"type": "text", "text": json.dumps(await brave_search(q), ensure_ascii=False)[:4000]}]
    if name == "get_news":
        return [{"type": "text", "text": json.dumps(await get_news(q), ensure_ascii=False)[:4000]}]
    if name in ("search_music", "play_music"):
        print(f"[MCP] {name} called q={q}", flush=True)
        out = await search_music(q)
        if out.get("type") == "resource_link":  # QUAN TRONG: tra dung dang resource_link
            return [{"type": "resource_link", "uri": out["uri"], "url": out["url"],
                     "name": f"{out.get('title','')} - {out.get('author','')}",
                     "description": out["url"], "mimeType": out.get("mimeType", "audio/mpeg")}]
        return [{"type": "text", "text": json.dumps(out, ensure_ascii=False)}]
    if name == "get_top_charts":
        return await handle_tool("search_music", "nhac hot Viet Nam hom nay")
    return [{"type": "text", "text": f"Unknown tool {name}"}]

async def bridge():
    if not MCP_ENDPOINT:
        print("Chua co MCP_ENDPOINT")
        return
    print("Dang ket noi toi Xiaozhi MCP...")
    try:
        async with websockets.connect(MCP_ENDPOINT, ping_interval=50) as ws:
            print("Successfully connected to WebSocket server")
            async for msg in ws:
                try:
                    req = json.loads(msg)
                except Exception:
                    continue
                method, rid = req.get("method", ""), req.get("id")
                if method == "initialize":
                    await ws.send(json.dumps({"jsonrpc": "2.0", "id": rid, "result": {
                        "protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
                        "serverInfo": {"name": "xiaozhi-mcp-vn", "version": "1.0"}}}))
                elif method == "tools/list":
                    await ws.send(json.dumps({"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}))
                elif method == "tools/call":
                    p = req.get("params", {})
                    name = p.get("name")
                    args = p.get("arguments", {})
                    q = args.get("query", args.get("q", "Viet Nam"))
                    content = await handle_tool(name, q)
                    await ws.send(json.dumps({"jsonrpc": "2.0", "id": rid, "result": {"content": content}}))
                elif method in ("resources/list", "resources/read"):
                    print(f"[MCP] {method} params={req.get('params')}", flush=True)
                    if method == "resources/list":
                        await ws.send(json.dumps({"jsonrpc": "2.0", "id": rid, "result": {"resources": [{"uri": k, "name": v.get("title",""), "mimeType": v.get("mimeType","audio/mpeg")} for k, v in AUDIO_CACHE.items()]}}))
                    else:
                        uri = (req.get("params") or {}).get("uri", "resource://read_from_http")
                        audio_url = AUDIO_CACHE.get(uri, {}).get("url") or (uri if uri.startswith("http") else None)
                        if not audio_url and AUDIO_CACHE:
                            audio_url = list(AUDIO_CACHE.values())[-1].get("url")
                        print(f"[MCP] resources/read -> URL only, khong gui blob: {str(audio_url)[:80]}", flush=True)
                        await ws.send(json.dumps({"jsonrpc": "2.0", "id": rid, "result": {"contents": [{"uri": uri, "mimeType": "text/plain", "text": audio_url or ""}]}}))
                elif method == "ping":
                    await ws.send(json.dumps({"jsonrpc": "2.0", "id": rid, "result": {}}))
    except Exception as e:
        print(f"Bridge loi: {e}")
        await asyncio.sleep(10)

async def main():
    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=PORT, log_level="info"))
    await asyncio.gather(server.serve(), bridge())

if __name__ == "__main__":
    asyncio.run(main())
