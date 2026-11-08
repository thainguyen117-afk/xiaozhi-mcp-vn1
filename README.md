# Xiaozhi MCP VN - Nhạc Việt + Search + Tin tức - Deploy Render 1 lần

## Bạn cần chuẩn bị 3 thứ (mất 5 phút, không code)
1. Vào xiaozhi.me > Agent của bạn > MCP Endpoint > Regenerate Token mới
    - Copy token mới dạng: wss://api.xiaozhi.me/mcp/?token=...
2. Vào https://brave.com/search/api/ đăng ký Free -> lấy BRAVE_API_KEY
3. Vào https://newsapi.org/ đăng ký Free -> lấy NEWS_API_KEY

## Deploy lên Render (không cần PC)
1. Lên https://render.com > New + > Web Service > Upload repo này / hoặc Deploy từ GitHub sau khi push code này lên
2. Build Command: pip install -r requirements.txt
   Start Command: python bridge.py
3. Vào mục Environment, thêm đúng 3 biến:
   MCP_ENDPOINT = wss://api.xiaozhi.me/mcp/?token=TOKEN_MOI_CUA_BAN
   BRAVE_API_KEY = key_brave_cua_ban
   NEWS_API_KEY = key_newsapi_cua_ban
4. Create -> Vào Logs, thấy dòng "Successfully connected" là xong.

## Cách kết nối thêm MCP Nhạc Việt qua SSE
Service này chạy luôn bridge cho Search/News.
Riêng Nhạc Việt, trong xiaozhi.me > Agent > Mở rộng > Điểm cuối MCP, thêm:
  https://<ten-service-cua-ban>.onrender.com/sse

## Test với robot
- "Tìm bài See Tình của Hoàng Thùy Linh và phát đi"
- "Tìm tin tức mới nhất hôm nay ở Việt Nam rồi tóm tắt"
- "Search trên web xem giá vàng hôm nay bao nhiêu"

## Role Prompt dán vào xiaozhi.me
Bạn là trợ lý robot tiếng Việt.
Khi người dùng yêu cầu nghe nhạc, BẮT BUỘC gọi tool search_music / play_song, không được tự bịa link nhạc.
Khi người dùng hỏi tin tức, thời sự, giá vàng, thời tiết, sự kiện hôm nay, BẮT BUỘC gọi tool brave_search / get_news trước rồi mới trả lời, không được bịa tin.
Luôn trả lời bằng tiếng Việt, ngắn gọn, dễ nghe qua loa.
