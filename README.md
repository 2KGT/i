# AIGram Bot
# phiên bản Cloudflare Workers (miễn phí, không sleep)

Bản viết lại từ Python (GitHub Actions) sang JavaScript (Cloudflare Workers), dùng kiến trúc
**webhook** thay vì polling - Telegram tự gọi thẳng URL của bạn mỗi khi có tin nhắn mới, nên
không cần tiến trình chạy nền liên tục. Đây là lý do free tier của Cloudflare không bị "sleep"
như Render.

## Khác biệt so với bản Python

| | Bản Python (GitHub Actions) | Bản JS (Cloudflare Workers) |
|---|---|---|
| Cơ chế nhận tin | Polling (`infinity_polling()`) | Webhook (Telegram tự gọi tới) |
| Cần chạy nền? | Có, phải bấm Run Workflow | Không, luôn sẵn sàng 24/7 |
| Lưu trạng thái | Biến trong RAM (`users = {}`) | Cloudflare KV (bền vững) |
| Cơ chế nhắc nhở | `threading` + `time.sleep()` | Cron Trigger (chạy mỗi phút, tự quét) |

## Bước 1: Cài Wrangler CLI

```bash
npm install -g wrangler
wrangler login
```

Lệnh `wrangler login` sẽ mở trình duyệt để bạn đăng nhập tài khoản Cloudflare (miễn phí, không
cần thẻ tín dụng).

## Bước 2: Tạo KV Namespace

```bash
wrangler kv namespace create USERS_KV
```

Lệnh này in ra 1 `id` — copy giá trị đó, mở file `wrangler.toml`, thay vào dòng:

```toml
[[kv_namespaces]]
binding = "USERS_KV"
id = "THAY_BANG_KV_NAMESPACE_ID_THAT"   # <-- dán id thật vào đây
```

## Bước 3: Cấu hình secrets (token, API key)

Không đặt trực tiếp trong `wrangler.toml` (file này có thể bị commit lên Git). Dùng lệnh sau,
mỗi lệnh sẽ hỏi bạn nhập giá trị (không hiện ra màn hình):

```bash
wrangler secret put TELEGRAM_BOT_TOKEN
wrangler secret put GEMINI_API_KEY
```

## Bước 4: Deploy

```bash
npm install
npm run deploy
```

Sau khi deploy xong, Wrangler in ra 1 URL dạng:
`https://aigram-bot.<tên-tài-khoản>.workers.dev`

## Bước 5: Đăng ký Webhook với Telegram

Đây là bước quan trọng nhất — báo cho Telegram biết gửi tin nhắn tới đâu. Mở trình duyệt, truy
cập URL sau (thay `<BOT_TOKEN>` và `<WORKER_URL>` bằng giá trị thật):

```
https://api.telegram.org/bot<BOT_TOKEN>/setWebhook?url=<WORKER_URL>
```

Ví dụ:
```
https://api.telegram.org/bot123456:ABC-DEF/setWebhook?url=https://aigram-bot.myaccount.workers.dev
```

Thấy `{"ok":true,"result":true,...}` là thành công. Từ giờ bot **luôn online 24/7**, không cần
bấm Run Workflow gì nữa — cứ nhắn tin là bot trả lời ngay.

## Kiểm tra hoạt động

```bash
npm run tail
```

Lệnh này xem log thời gian thực (tương đương xem log trong GitHub Actions trước đây). Mở song
song, rồi thử nhắn tin cho bot trên Telegram để xem log hiện ra.

## Thay đổi cấu hình (tính cách, chế độ nhóm)

Sửa trong `wrangler.toml`, mục `[vars]`:

```toml
[vars]
PERSONALITY_MODE = "dynamic"   # dynamic / angel / devil
GROUP_MODE = "mention_only"    # mention_only / smart
```

Sau khi sửa, chạy lại `npm run deploy` để áp dụng.

## Lưu ý về giới hạn free tier

- **100.000 request/ngày** — dư dả cho bot cá nhân/nhóm nhỏ.
- **Cron Trigger tối thiểu 1 phút/lần** — cơ chế nhắc nhở 10'/30' có thể lệch tối đa ~1 phút so
  với mốc chính xác, không đáng kể.
- **CPU time giới hạn mỗi request** (free tier: 10ms CPU thực, nhưng có thể chờ I/O như gọi API
  lâu hơn nhiều) — nếu Gemini phản hồi quá chậm (nhiều lượt retry), có khả năng request bị cắt.
  Nếu gặp lỗi timeout thường xuyên, có thể cần giảm số lượt retry trong `gemini.js`.
- **Không hỗ trợ `off` mode kiểu gửi 1 tin thủ công rồi thoát** như bản Python cũ, vì kiến trúc
  webhook không có khái niệm "chạy 1 lần rồi dừng" — bot luôn ở trạng thái sẵn sàng. Muốn gửi 1
  tin thủ công, gọi trực tiếp Telegram Bot API `sendMessage` từ trình duyệt/Postman, không cần
  qua Worker.

## Cấu trúc file

- `wrangler.toml` — cấu hình Worker, KV namespace, Cron Trigger.
- `src/index.js` — điểm vào chính: `fetch()` xử lý webhook, `scheduled()` xử lý cron nhắc nhở.
- `src/gemini.js` — gọi Gemini API, system prompt 3 tính cách, fallback đa dạng, retry.
- `src/telegram.js` — gửi/nhận qua Telegram Bot API (HTTP thuần, không cần thư viện ngoài).
- `src/state.js` — quản lý trạng thái người dùng qua Cloudflare KV.
