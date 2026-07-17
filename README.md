# Trợ lý AI đồng hành (Telegram Bot)

Bot Telegram dùng Gemini AI để trò chuyện đồng hành với người dùng, hướng tới đề tài
đồ án về “những người cô đơn tìm kiếm niềm vui”.

## Nguyên tắc thiết kế quan trọng

Bot này **luôn công khai mình là AI** ngay từ tin nhắn đầu tiên, và không bao giờ giả vờ
là người thật kể cả khi được hỏi trực tiếp. Mục tiêu là làm bạn đồng hành lành mạnh,
không phải khiến người dùng phụ thuộc hoặc nhầm lẫn với một mối quan hệ con người thật.

Nếu người dùng có dấu hiệu buồn/cô đơn thật sự, bot được yêu cầu (qua system prompt)
đồng cảm chân thành và gợi ý kết nối thêm với người thật (bạn bè, người thân, chuyên gia
tâm lý) thay vì cố giữ chân họ ở lại trò chuyện với bot.

## Cấu trúc

- `.github/workflows/aigram-runbot.yml`: cấu hình chạy trên GitHub Actions.
- `src/main.py`: vòng lặp chính, xử lý tin nhắn đến (chat riêng + nhóm/kênh) và hẹn giờ hỏi thăm khi im lặng lâu.
- `src/gemini.py`: sinh nội dung trả lời bằng Gemini API, 3 tính cách (dynamic/angel/devil), và hàm riêng cho ngữ cảnh nhóm.
- `src/send_message.py`: gửi/nhận tin nhắn qua Telegram Bot API (dùng pyTelegramBotAPI).
- `config.yml`: cấu hình token khi chạy local (ưu tiên biến môi trường khi chạy trên GitHub Actions).

## Các lựa chọn khi chạy workflow (Run Workflow)

Form trên GitHub giữ mô tả ngắn gọn cho gọn màn hình; chi tiết đầy đủ ở đây:

**Tính cách bot (`personality_mode`)**

- `dynamic` (khuyên dùng): bot tự linh hoạt chuyển giọng theo ngữ cảnh mỗi tin nhắn - dịu dàng
  khi người dùng buồn/nghiêm túc, cà khịa vui vẻ khi họ đang đùa giỡn/thoải mái. Không cần
  người dùng tự chọn gì, bot tự phán đoán.
- `angel` / `devil`: ép cố định 1 phong cách (dịu dàng / cà khịa) suốt cả phiên chạy, dùng khi
  cần kiểm soát hoặc test riêng 1 giọng điệu.

**Chế độ chạy (`reminder_mode`)**

- `off`: CHỈ gửi 1 tin thủ công tới đúng 1 người (`target_chat_id`, hoặc mặc định), thoát ngay,
  không giữ polling, không phục vụ ai khác nhắn vào.
- `auto`: chạy nền phục vụ MỌI người nhắn vào (multi-user, giữ polling). Mỗi người có đồng hồ
  riêng: im lặng 10’ → nhắc 1 lần; im lặng 30’ → nhắc lần cuối rồi dừng theo dõi riêng người đó.
- `custom`: giống `auto` nhưng chỉ 1 mốc chờ do tự nhập ở ô “Số phút chờ” (`custom_minutes`).
  Chỉ nhập số thuần, đơn vị luôn là **phút** (vd nhập `20` = chờ 20 phút). Không hỗ trợ kèm
  chữ hay đơn vị khác (không nhập “20 phút”, “1h”, “90s”…).

**Tương tác trong nhóm/kênh (`group_mode`)**

- `mention_only` (mặc định, an toàn): bot chỉ trả lời khi bị `@tag` trực tiếp hoặc bị reply vào
  đúng tin nhắn của bot. Các tin nhắn khác trong nhóm bị bỏ qua hoàn toàn, không tốn API.
- `smart`: ngoài việc luôn trả lời khi bị tag/reply, bot còn tự đánh giá (bằng chính Gemini, chỉ
  1 lượt gọi API) các tin nhắn khác xem có đáng góp lời không - giống một thành viên thật đang
  theo dõi nhóm, không trả lời máy móc mọi câu. Cả nhóm dùng chung 1 luồng hội thoại.

**Dọn dẹp repo (`run_clean_logs`)**: xóa sạch lịch sử commit + workflow runs cũ. Chỉ chạy SAU
khi bot đã gửi/nhận tin xong, không ảnh hưởng tới bước chat chính dù thành công hay thất bại.
Cần quyền “Read and write” cho `GITHUB_TOKEN` (Settings → Actions → General → Workflow
permissions), nếu không sẽ tự bỏ qua lỗi.

**Thiết lập bắt buộc để dùng `group_mode = smart`**: mặc định Telegram bật “Privacy Mode” cho
bot, khiến bot chỉ thấy được lệnh (`/command`) hoặc tin nhắn tag/reply trực tiếp tới nó. Để đọc
được mọi tin nhắn trong nhóm, cần tắt Privacy Mode:

1. Chat với [@BotFather](https://t.me/BotFather) → gõ `/mybots` → chọn bot của bạn.
1. Vào `Bot Settings` → `Group Privacy` → `Turn off`.
1. Thêm lại bot vào nhóm (nếu đã có sẵn trong nhóm, có thể cần kick rồi add lại để áp dụng).

## Lưu ý khi làm đồ án

Nên trình bày rõ trong báo cáo đồ án về nguyên tắc minh bạch AI ở trên — đây là điểm
quan trọng về đạo đức AI (AI ethics) khi thiết kế chatbot đồng hành, đặc biệt với đối
tượng người dùng dễ tổn thương (cô đơn, buồn bã).