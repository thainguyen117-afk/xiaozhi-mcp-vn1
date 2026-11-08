"""
Bridge MCP am nhac cho Xiaozhi.me
Danh cho robot Xiaozhi co san, cau hinh MCP tren xiaozhi.me.
Chay: python Bridge.py

Bien moi truong:
  MCP_ENDPOINT=wss://api.xiaozhi.me/mcp/?token=...
  TAVILY_API_KEY=... (tuy chon)
  SOUNDCLOUD_CLIENT_ID=... (tuy chon)
  PORT=10000

Ghi chu: nguon nhac ben thu ba co the thay doi/het han/gioi han ban quyen.
"""
import asyncio
import base64
import json
import os
from urllib.parse import urlparse

import httpx
import uvicorn
import websockets
from fastapi import FastAPI

MCP_ENDPOINT = os.getenv("MCP_ENDPOINT", "").strip()
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "").strip()
SC_CLIENT_ID = os.getenv("SOUNDCLOUD_CLIENT_ID", "").strip()
PORT = int(os.getenv("PORT", "10000"))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36"}
TIMEOUT = httpx.Timeout(25.0, connect=10.0)
AUDIO_URL = ""  # URL cua bai vua tim; Xiaozhi doc qua resource://read_from_http

app = FastAPI(title="Xiaozhi MCP Music Bridge")


def rpc(rid, result):
    return json.dumps({"jsonrpc": "2.0", "id": rid, "result": result}, ensure_ascii=False)


async def get_json(client, url, **kwargs):
    try:
        r = await client.get(url, **kwargs)
        r.raise_for_status()
        return r.json()
    except (httpx.HTTPError, ValueError) as e:
        print(f"[HTTP JSON] {url}: {e}", flush=True)
        return None


async def web_search(query):
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=UA, follow_redirects=True) as c:
        if TAVILY_API_KEY:
            try:
                r = await c.post(
                    "https://api.tavily.com/search",
                    json={"api_key": TAVILY_API_KEY, "query": query,
                          "max_results": 5, "include_answer": True},
                )
                r.raise_for_status()
                return r.json()
            except (httpx.HTTPError, ValueError) as e:
                print(f"[Tavily] {e}", flush=True)
        data = await get_json(
            c, "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": 1},
        )
        return {"answer": (data or {}).get("AbstractText", ""),
                "results": (data or {}).get("RelatedTopics", [])[:5]}


async def find_music(query):
    """Tim mot URL audio truc tiep; uu tien MP3."""
    global AUDIO_URL
    query = (query or "").strip()
    if not query:
        return {"error": "Chua co ten bai hat."}

    async with httpx.AsyncClient(timeout=TIMEOUT, headers=UA, follow_redirects=True) as c:
        # Deezer cung cap preview MP3 hop le de kiem tra playback.
        data = await get_json(c, "https://api.deezer.com/search", params={"q": query})
        for song in (data or {}).get("data", [])[:5]:
            url = song.get("preview")
            if url and url.startswith("http"):
                AUDIO_URL = url
                return {
                    "ok": True, "url": url,
                    "title": song.get("title", query),
                    "artist": (song.get("artist") or {}).get("name", ""),
                    "source": "Deezer preview",
                }

        # SoundCloud chi hoat dong neu co client ID con hieu luc.
        if SC_CLIENT_ID:
            data = await get_json(
                c, "https://api-v2.soundcloud.com/search/tracks",
                params={"q": query, "client_id": SC_CLIENT_ID, "limit": 5},
            )
            for song in (data or {}).get("collection", []):
                sid = song.get("id")
                if not sid:
                    continue
                streams = await get_json(
                    c, f"https://api-v2.soundcloud.com/tracks/{sid}/streams",
                    params={"client_id": SC_CLIENT_ID},
                )
                url = (streams or {}).get("http_mp3_128_url")
                if url and url.startswith("http"):
                    AUDIO_URL = url
                    return {
                        "ok": True, "url": url, "title": song.get("title", query),
                        "artist": (song.get("user") or {}).get("username", ""),
                        "source": "SoundCloud",
                    }

        # Zing endpoint khong chinh thuc, co the thay doi.
        data = await get_json(c, "https://zingmp3.vn/api/v2/search", params={"q": query})
        songs = ((data or {}).get("data") or {}).get("songs") or []
        for song in songs[:3]:
            eid = song.get("encodeId")
            if not eid:
                continue
            stream = await get_json(
                c, "https://zingmp3.vn/api/v2/song/get/streaming", params={"id": eid}
            )
            url = ((stream or {}).get("data") or {}).get("128")
            if isinstance(url, str) and url.startswith("http"):
                AUDIO_URL = url
                return {
                    "ok": True, "url": url, "title": song.get("title", query),
                    "artist": song.get("artistsNames", ""), "source": "Zing MP3",
                }

        # Nhaccuatui API khong chinh thuc; chi nhan URL HTTP(S).
        data = await get_json(
            c, "https://www.nhaccuatui.com/api/search",
            params={"q": query, "type": "song"},
        )
        items = (data or {}).get("data") or (data or {}).get("songs") or []
        for song in items[:5]:
            url = song.get("streamUrl") or song.get("previewUrl")
            if isinstance(url, str) and url.startswith("http"):
                AUDIO_URL = url
                return {
                    "ok": True, "url": url,
                    "title": song.get("title") or song.get("name") or query,
                    "artist": song.get("artist", ""), "source": "Nhaccuatui",
                }

    return {
        "error": f"Khong tim thay nguon audio truc tiep cho: {query}",
        "note": "Deezer preview/SoundCloud/Zing/NCT co the thay doi API hoac gioi han khu vuc.",
    }


TOOLS = [
    {"name": "brave_search", "description": "Tim kiem web va thong tin. Nhap query.",
     "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}},
                     "required": ["query"]}},
    {"name": "get_news", "description": "Tim tin tuc moi nhat Viet Nam. Nhap query.",
     "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}},
                     "required": ["query"]}},
    {"name": "search_music",
     "description": "Tim bai hat. Nhap ten bai hat va ca si; tra ve tai nguyen audio.",
     "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}},
                     "required": ["query"]}},
    {"name": "play_music",
     "description": "Tim va phat bai hat tren robot. Nhap ten bai hat va ca si. Khong chi tra link YouTube.",
     "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}},
                     "required": ["query"]}},
    {"name": "get_top_charts", "description": "Tim nhac hot Viet Nam.",
     "inputSchema": {"type": "object", "properties": {}}},
]


async def call_tool(name, query=""):
    if name == "brave_search":
        result = await web_search(query)
        return [{"type": "text", "text": json.dumps(result, ensure_ascii=False)[:5000]}]
    if name == "get_news":
        result = await web_search("tin tuc moi nhat Viet Nam " + (query or ""))
        return [{"type": "text", "text": json.dumps(result, ensure_ascii=False)[:5000]}]
    if name == "get_top_charts":
        query = "nhac hot Viet Nam"
        name = "search_music"
    if name in ("search_music", "play_music"):
        result = await find_music(query)
        if not result.get("ok"):
            return [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]
        # Dinh dang ResourceLink dung cho Xiaozhi Go server.
        # URL nam trong description; URI dac biet de server goi resources/read theo tung chunk.
        return [{
            "type": "resource_link",
            "uri": "resource://read_from_http",
            "name": f"{result['title']} - {result['artist']}".strip(" -"),
            "description": result["url"],
            "mimeType": "audio/mpeg",
        }]
    return [{"type": "text", "text": f"Khong co tool: {name}"}]


async def read_audio_chunk(params):
    """
    Xiaozhi goi resources/read voi:
      params.uri = resource://read_from_http
      params.arguments = {url, start, end}
    Tra blob Base64 theo Range; chunk cuoi co text [DONE].
    """
    args = params.get("arguments") or {}
    url = args.get("url") or params.get("url") or AUDIO_URL
    if not url or urlparse(url).scheme not in ("http", "https"):
        return {"contents": [{"uri": "resource://read_from_http",
                              "mimeType": "text/plain",
                              "text": "Khong co URL audio hop le. Hay goi play_music truoc."}]}

    try:
        start = max(0, int(args.get("start", 0)))
        end = max(start, int(args.get("end", start + 102399)))
    except (TypeError, ValueError):
        start, end = 0, 102399

    # Gioi han moi lan doc toi da 100 KiB theo giao thuc Xiaozhi.
    end = min(end, start + 102399)
    headers = dict(UA)
    headers["Range"] = f"bytes={start}-{end}"

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as c:
            r = await c.get(url, headers=headers)
            r.raise_for_status()
            data = r.content
            total = None
            content_range = r.headers.get("content-range", "")
            if "/" in content_range:
                try:
                    total = int(content_range.rsplit("/", 1)[1])
                except ValueError:
                    pass

            # Neu nguon khong ho tro HTTP Range va tra 200, cat phan duoc yeu cau.
            if r.status_code == 200 and start > 0:
                data = data[start:end + 1]
            elif r.status_code == 200:
                data = data[:end + 1]

            if not data:
                return {"contents": [{"uri": "resource://read_from_http",
                                      "mimeType": "text/plain", "text": "[DONE]"}]}

            last_chunk = (
                (total is not None and start + len(data) >= total)
                or (total is None and len(data) < (end - start + 1))
            )
            contents = [{
                "uri": "resource://read_from_http",
                "mimeType": "audio/mpeg",
                "blob": base64.b64encode(data).decode("ascii"),
            }]
            if last_chunk:
                contents.append({
                    "uri": "resource://read_from_http",
                    "mimeType": "text/plain",
                    "text": "[DONE]",
                })
            return {"contents": contents}
    except (httpx.HTTPError, ValueError) as e:
        print(f"[audio read] {e}", flush=True)
        return {"contents": [{"uri": "resource://read_from_http",
                              "mimeType": "text/plain",
                              "text": f"Loi tai audio: {e}"}]}


async def handle_request(ws, req):
    method = req.get("method", "")
    rid = req.get("id")

    if method == "initialize":
        await ws.send(rpc(rid, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}, "resources": {}},
            "serverInfo": {"name": "xiaozhi-mcp-vn", "version": "2.0"},
        }))
    elif method == "notifications/initialized":
        return
    elif method == "tools/list":
        await ws.send(rpc(rid, {"tools": TOOLS}))
    elif method == "tools/call":
        p = req.get("params") or {}
        args = p.get("arguments") or {}
        query = args.get("query", args.get("q", ""))
        try:
            content = await call_tool(p.get("name", ""), str(query))
            await ws.send(rpc(rid, {"content": content}))
        except Exception as e:
            print(f"[tool] {e}", flush=True)
            await ws.send(json.dumps({
                "jsonrpc": "2.0", "id": rid,
                "error": {"code": -32603, "message": str(e)},
            }, ensure_ascii=False))
    elif method == "resources/read":
        result = await read_audio_chunk(req.get("params") or {})
        await ws.send(rpc(rid, result))
    elif method == "resources/list":
        await ws.send(rpc(rid, {"resources": []}))
    elif method == "ping":
        await ws.send(rpc(rid, {}))
    elif rid is not None:
        await ws.send(json.dumps({
            "jsonrpc": "2.0", "id": rid,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }, ensure_ascii=False))


async def bridge():
    if not MCP_ENDPOINT:
        print("[MCP] Chua co MCP_ENDPOINT. HTTP test van chay.", flush=True)
        return
    while True:
        try:
            print("[MCP] Dang ket noi Xiaozhi.me...", flush=True)
            async with websockets.connect(
                MCP_ENDPOINT, ping_interval=30, ping_timeout=30,
                close_timeout=10, max_size=8 * 1024 * 1024,
            ) as ws:
                print("[MCP] Da ket noi Xiaozhi.me.", flush=True)
                async for message in ws:
                    try:
                        req = json.loads(message)
                        if isinstance(req, dict):
                            await handle_request(ws, req)
                    except json.JSONDecodeError:
                        print("[MCP] Bo qua goi tin JSON loi.", flush=True)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[MCP] Mat ket noi: {e}; thu lai sau 5 giay.", flush=True)
            await asyncio.sleep(5)


@app.get("/")
async def root():
    return {"service": "xiaozhi-mcp-music", "health": "/health",
            "test_music": "/search?q=See%20Tinh"}


@app.get("/health")
async def health():
    return {"status": "ok", "has_mcp": bool(MCP_ENDPOINT),
            "has_tavily": bool(TAVILY_API_KEY), "audio_ready": bool(AUDIO_URL)}


@app.get("/search")
async def http_search(q: str = "See Tinh Hoang Thuy Linh"):
    return await find_music(q)


async def main():
    server = uvicorn.Server(
        uvicorn.Config(app, host="0.0.0.0", port=PORT, log_level="info")
    )
    await asyncio.gather(server.serve(), bridge())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Da dung Bridge.")
