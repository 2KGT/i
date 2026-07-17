import os
import sys
import time
import yaml
import logging
import threading

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)

# Thêm thư mục hiện tại vào hệ thống đường dẫn để Python tìm thấy các module bên cạnh
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from send_message import TelegramSender
from gemini import GeminiGenerator

# Chế độ chạy bot (REMINDER_MODE):
# - 'off'    = CHẾ ĐỘ GỬI THỦ CÔNG CHO 1 NGƯỜI CỤ THỂ. Chỉ gửi 1 tin tới đúng target_chat_id
#              (nhập ở input target_chat_id, hoặc mặc định DEFAULT_CHAT_ID nếu để trống) rồi thoát ngay.
#              KHÔNG bật polling, KHÔNG phục vụ multi-user, không ai khác nhắn vào sẽ được trả lời.
#              Dùng khi bạn chỉ cần gửi 1 tin chỉ định thủ công tới 1 cá nhân, không cần chat qua lại.
# - 'auto'   = CHẾ ĐỘ CHẠY NỀN PHỤC VỤ MỌI NGƯỜI (multi-user). Giữ polling, bất kỳ ai nhắn vào Telegram
#              đều được nhận/trả lời, mỗi người có đồng hồ nhắc nhở + lịch sử hội thoại riêng.
#              Nếu 1 người im lặng đủ 10' -> nhắc 1; đủ 30' -> nhắc cuối rồi dừng theo dõi
#              riêng người đó (người khác không bị ảnh hưởng). Họ nhắn lại thì tự khởi động lại từ đầu.
# - 'custom' = giống 'auto' (multi-user, giữ polling) nhưng mỗi người chỉ có 1 mốc chờ duy nhất do người
#              dùng tự nhập (phút) thay vì 3 mốc 15'/30'/1h. Hết mốc mà im lặng -> nhắc 1 lần rồi dừng.
REMINDER_MODE = (os.environ.get("REMINDER_MODE") or "auto").strip().lower()
CUSTOM_MINUTES_RAW = (os.environ.get("CUSTOM_MINUTES") or "").strip()

if REMINDER_MODE not in ("off", "auto", "custom"):
    print(f"⚠️ [Main] REMINDER_MODE '{REMINDER_MODE}' không hợp lệ, dùng mặc định 'auto'.")
    REMINDER_MODE = "auto"

CUSTOM_MINUTES = None
if REMINDER_MODE == "custom":
    try:
        # Chỉ chấp nhận số thuần (đơn vị luôn là PHÚT) - vd "20" nghĩa là 20 phút.
        # Không hỗ trợ kèm chữ như "20 phút", "1h", "90s".
        CUSTOM_MINUTES = float(CUSTOM_MINUTES_RAW)
        if CUSTOM_MINUTES <= 0:
            raise ValueError
    except ValueError:
        print(f"⚠️ [Main] CUSTOM_MINUTES '{CUSTOM_MINUTES_RAW}' không hợp lệ - chỉ nhập số thuần (đơn vị phút, vd '20'), không kèm chữ hay đơn vị khác. Chuyển về chế độ 'auto'.")
        REMINDER_MODE = "auto"

# Chế độ tương tác trong nhóm/kênh (GROUP_MODE):
# - 'mention_only' (mặc định, an toàn) = trong nhóm, bot CHỈ trả lời khi bị tag (@tên_bot) hoặc bị reply trực tiếp.
# - 'smart'                            = ngoài việc luôn trả lời khi bị tag/reply, bot còn tự đánh giá (bằng chính
#                                         Gemini) các tin nhắn khác trong nhóm xem có đáng góp lời không, giống một
#                                         thành viên thật đang theo dõi nhóm - không trả lời máy móc mọi tin nhắn.
GROUP_MODE = (os.environ.get("GROUP_MODE") or "mention_only").strip().lower()
if GROUP_MODE not in ("mention_only", "smart"):
    print(f"⚠️ [Main] GROUP_MODE '{GROUP_MODE}' không hợp lệ, dùng mặc định 'mention_only'.")
    GROUP_MODE = "mention_only"

# --- 1. ĐỌC CẤU HÌNH (ƯU TIÊN BIẾN MÔI TRƯỜNG TRƯỚC, YAML SAU) ---
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
DEFAULT_CHAT_ID = os.environ.get("DEFAULT_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Ưu tiên lấy nhân vật được chọn từ nút bấm GitHub Actions
PERSONALITY_MODE = os.environ.get("SELECTED_PERSONALITY")

# Nếu không chạy trên GitHub Actions (không có biến môi trường), đọc từ file config.yml
if not BOT_TOKEN or not GEMINI_API_KEY:
    CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yml")
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
            BOT_TOKEN = config["telegram"]["bot_token"]
            DEFAULT_CHAT_ID = config["telegram"]["chat_id"]
            GEMINI_API_KEY = config["gemini"]["api_key"]
            # Nếu chạy local và không có SELECTED_PERSONALITY, lấy từ config.yml
            if not PERSONALITY_MODE:
                PERSONALITY_MODE = config["gemini"].get("personality_mode", "angel")
    else:
        print("✗ [Main] Lỗi nghiêm trọng: Không tìm thấy Token cấu hình!")
        sys.exit(1)

# Nếu vì lý do nào đó vẫn trống, đặt mặc định là dynamic (bot tự linh hoạt theo ngữ cảnh)
if not PERSONALITY_MODE:
    PERSONALITY_MODE = "dynamic"

PERSONALITY_MODE = PERSONALITY_MODE.strip().lower()
if PERSONALITY_MODE not in ("angel", "devil", "dynamic"):
    print(f"⚠️ [Main] PERSONALITY_MODE '{PERSONALITY_MODE}' không hợp lệ, dùng mặc định 'dynamic'.")
    PERSONALITY_MODE = "dynamic"

# Quyết định Chat ID mục tiêu
INPUT_CHAT_ID = os.environ.get("INPUT_CHAT_ID")
TARGET_CHAT_ID = INPUT_CHAT_ID.strip() if (INPUT_CHAT_ID and INPUT_CHAT_ID.strip()) else DEFAULT_CHAT_ID

if not TARGET_CHAT_ID or "THAY_THE_BANG" in str(TARGET_CHAT_ID):
    print("✗ [Main] Lỗi: Chưa cấu hình Chat ID mục tiêu!")
    print("   -> Nếu chạy trên GitHub Actions: kiểm tra đã tạo Secret 'CHAT_ID' chưa (Settings > Secrets and variables > Actions).")
    print("   -> Nếu chạy local: kiểm tra đã điền chat_id thật vào config.yml chưa (không để nguyên placeholder).")
    sys.exit(1)

try:
    TARGET_CHAT_ID = int(str(TARGET_CHAT_ID).strip())
except ValueError:
    print(f"✗ [Main] Lỗi: Chat ID '{TARGET_CHAT_ID}' không phải là số hợp lệ.")
    sys.exit(1)

if not BOT_TOKEN or "THAY_THE_BANG" in str(BOT_TOKEN):
    print("✗ [Main] Lỗi: Chưa cấu hình BOT_TOKEN hợp lệ (kiểm tra Secret 'BOT_TOKEN' hoặc config.yml).")
    sys.exit(1)

if not GEMINI_API_KEY or "THAY_THE_BANG" in str(GEMINI_API_KEY):
    print("✗ [Main] Lỗi: Chưa cấu hình GEMINI_API_KEY hợp lệ (kiểm tra Secret 'GEMINI_API_KEY' hoặc config.yml).")
    sys.exit(1)

# --- 2. KHỞI TẠO CÁC MODULE ---
sender = TelegramSender(BOT_TOKEN, TARGET_CHAT_ID)
ai = GeminiGenerator(GEMINI_API_KEY, PERSONALITY_MODE)

# --- 3. STATE RIÊNG CHO TỪNG NGƯỜI DÙNG (MULTI-USER) ---
# Bot mở cho bất kỳ ai nhắn vào, mỗi chat_id có: đồng hồ im lặng riêng, mốc nhắc nhở riêng,
# lịch sử hội thoại riêng (để trả lời có mạch), và cờ bật/tắt luồng nhắc nhở riêng.
MOC_10_PHUT = 600
MOC_30_PHUT = 1800

# Bật dòng dưới đây nếu bạn muốn test nhanh trên máy cá nhân (giây thay vì phút)
# MOC_10_PHUT, MOC_30_PHUT = 10, 25

MAX_HISTORY_TURNS = 20  # số lượt (user+model) tối đa giữ lại mỗi người, tránh phình bộ nhớ vô hạn

users_lock = threading.Lock()  # bảo vệ dict users khỏi truy cập đồng thời giữa các thread
users = {}
# Cấu trúc mỗi user: {
#   "last_reply_time": float, "reminder_stage": int, "running": bool, "history": [{"role","text"}, ...]
# }


def _get_user_state(chat_id):
    with users_lock:
        if chat_id not in users:
            users[chat_id] = {
                "last_reply_time": time.time(),
                "reminder_stage": 0,
                "running": True,
                "history": [],
            }
        return users[chat_id]


def _append_history(chat_id, role, text):
    with users_lock:
        state = users.get(chat_id)
        if state is None:
            return
        state["history"].append({"role": role, "text": text})
        if len(state["history"]) > MAX_HISTORY_TURNS:
            state["history"] = state["history"][-MAX_HISTORY_TURNS:]


def reminder_tracker(chat_id):
    """Luồng đếm giờ nhắc nhở riêng cho 1 người dùng (chat_id). Mỗi người dùng có 1 thread độc lập."""
    print(f"⏰ [Main] Bắt đầu theo dõi im lặng cho chat_id={chat_id} (chế độ: {REMINDER_MODE})...")

    while True:
        time.sleep(1)
        with users_lock:
            state = users.get(chat_id)
            if state is None or not state["running"]:
                return
            silent_duration = time.time() - state["last_reply_time"]
            reminder_stage = state["reminder_stage"]
            check_time = state["last_reply_time"]

        def _send_reminder(stage):
            history = list(_get_user_state(chat_id)["history"])
            ai_text, is_fallback = ai.generate_content("", is_reminder=True, reminder_stage=stage, history=history)
            with users_lock:
                state = users.get(chat_id)
                if state is None or state["last_reply_time"] != check_time:
                    # Người dùng vừa nhắn trong lúc soạn nhắc nhở -> huỷ gửi để tránh trùng lặp
                    print(f"↩️ [Main] chat_id={chat_id} vừa nhắn trong lúc soạn nhắc nhở, huỷ gửi để tránh trùng lặp.")
                    return False
                # Gửi NGAY TRONG lock để không có khoảng hở giữa lúc kiểm tra và lúc gửi thật -
                # nếu handle_incoming_messages đang chờ lock này, nó sẽ đợi tới khi gửi xong mới
                # được cập nhật last_reply_time, đảm bảo không có tin nhắn nào "lọt" vào giữa 2 bước.
                sender.send_to(chat_id, ai_text)
                if not is_fallback:
                    # Chỉ lưu vào lịch sử nếu là câu nhắc nhở thật - nếu là fallback (Gemini lỗi tạm
                    # thời), không lưu để lượt sau bot không nghĩ "đã nhắc nhở xong", giữ mạch tự nhiên.
                    state["history"].append({"role": "model", "text": ai_text})
                    if len(state["history"]) > MAX_HISTORY_TURNS:
                        state["history"] = state["history"][-MAX_HISTORY_TURNS:]
            return True

        if REMINDER_MODE == "custom":
            moc_giay = CUSTOM_MINUTES * 60
            if silent_duration >= moc_giay and reminder_stage == 0:
                if _send_reminder(1):
                    with users_lock:
                        users[chat_id]["reminder_stage"] = 1
                        users[chat_id]["running"] = False
                    print(f"📴 [Main] chat_id={chat_id} im lặng quá {CUSTOM_MINUTES} phút (mốc tùy chỉnh). Dừng theo dõi.")
                    return
            continue

        # Chế độ auto: 2 mốc cố định 10' -> 30' (mốc cuối, dừng hẳn)
        if silent_duration >= MOC_10_PHUT and reminder_stage == 0:
            if _send_reminder(1):
                with users_lock:
                    users[chat_id]["reminder_stage"] = 1

        elif silent_duration >= MOC_30_PHUT and reminder_stage == 1:
            if _send_reminder(2):
                with users_lock:
                    users[chat_id]["reminder_stage"] = 2
                    users[chat_id]["running"] = False
                print(f"📴 [Main] chat_id={chat_id} im lặng quá 30 phút. Dừng theo dõi.")
                return


# --- 4. TIẾP NHẬN TƯƠNG TÁC CHAT CHÍNH (MỌI NGƯỜI DÙNG, KỂ CẢ NHÓM/KÊNH) ---

try:
    _BOT_USERNAME = (sender.bot.get_me().username or "").lower()
    print(f"🤖 [Main] Bot username: @{_BOT_USERNAME}")
except Exception as e:
    _BOT_USERNAME = ""
    print(f"⚠️ [Main] Không lấy được username của bot ({e}), việc phát hiện tag @username trong nhóm có thể không hoạt động.")


def _was_bot_addressed(message) -> bool:
    """Kiểm tra tin nhắn trong nhóm có đang nhắm tới bot không: bị @tag trong nội dung, hoặc là reply
    trực tiếp vào 1 tin nhắn trước đó của chính bot."""
    # Trường hợp 1: reply trực tiếp vào tin nhắn của bot
    if message.reply_to_message and getattr(message.reply_to_message, "from_user", None):
        if message.reply_to_message.from_user.is_bot and message.reply_to_message.from_user.username and \
                message.reply_to_message.from_user.username.lower() == _BOT_USERNAME:
            return True

    # Trường hợp 2: bị @tag trong nội dung tin nhắn (dò qua message.entities cho chính xác, không chỉ so text)
    text = message.text or message.caption or ""
    entities = message.entities or message.caption_entities or []
    if _BOT_USERNAME:
        for ent in entities:
            if ent.type == "mention":
                mention_text = text[ent.offset: ent.offset + ent.length]
                if mention_text.lower() == f"@{_BOT_USERNAME}":
                    return True
    return False


def _display_name(user) -> str:
    """Lấy tên hiển thị dễ đọc của 1 thành viên trong nhóm, ưu tiên tên đầy đủ, sau đó username."""
    if not user:
        return "Ai đó"
    full_name = " ".join(part for part in [user.first_name, user.last_name] if part)
    return full_name or (f"@{user.username}" if user.username else f"User{user.id}")


@sender.bot.message_handler(commands=['start'])
def handle_start_command(message):
    """Lệnh /start là lệnh khởi tạo chuẩn của Telegram, không phải câu chat thật -> trả lời chào cố định
    ngay lập tức, không cần gọi Gemini (tránh tốn API call vô ích và độ trễ không cần thiết)."""
    chat_id = message.chat.id
    state = _get_user_state(chat_id)

    with users_lock:
        was_running = state["running"]
        state["last_reply_time"] = time.time()
        state["reminder_stage"] = 0
        state["running"] = True

    if REMINDER_MODE != "off" and not was_running:
        threading.Thread(target=reminder_tracker, args=(chat_id,), daemon=True).start()

    print(f"📥 [Main] chat_id={chat_id} vừa bấm /start.")

    if PERSONALITY_MODE == "devil":
        greeting = "Ơ, xịn đó, bấm /start rồi hả. Mình là trợ lý AI đồng hành thôi nha, không phải người thật đâu. Cứ nhắn gì cũng được, mình nghe hết 😏"
    else:
        greeting = "Chào cậu! ✨ Mình là trợ lý AI đồng hành của cậu đây - một người bạn AI luôn sẵn sàng lắng nghe và trò chuyện. Cậu cứ thoải mái nhắn bất cứ điều gì nha!"

    sender.reply_to_message(message, greeting)
    _append_history(chat_id, "model", greeting)


@sender.bot.message_handler(func=lambda message: True)
def handle_incoming_messages(message):
    chat_id = message.chat.id
    is_group = message.chat.type in ("group", "supergroup", "channel")
    message_text = message.text or message.caption or ""

    if is_group:
        was_addressed = _was_bot_addressed(message)
        if not was_addressed and GROUP_MODE == "mention_only":
            # Chế độ an toàn: trong nhóm/kênh, không bị tag/reply thì im lặng hoàn toàn, không tốn API.
            return
        # Nếu không bị tag/reply nhưng chưa có nội dung để đánh giá (ví dụ tin không phải text) -> bỏ qua
        if not was_addressed and not message_text.strip():
            return

    state = _get_user_state(chat_id)

    with users_lock:
        was_running = state["running"]
        state["last_reply_time"] = time.time()
        state["reminder_stage"] = 0
        state["running"] = True

    # Nếu đây là người dùng/nhóm mới hoặc luồng nhắc nhở trước đó đã dừng -> khởi động lại riêng cho chat_id này
    if REMINDER_MODE != "off" and not was_running:
        threading.Thread(target=reminder_tracker, args=(chat_id,), daemon=True).start()

    with users_lock:
        history = list(state["history"])

    if is_group:
        sender_name = _display_name(message.from_user) if message.from_user else "Ai đó"
        print(f"📥 [Main] (Nhóm {chat_id}) {sender_name}: '{message_text}' | addressed={was_addressed}")

        should_reply, ai_reply, is_fallback = ai.generate_group_reply(
            sender_name=sender_name,
            message_text=message_text,
            was_addressed=was_addressed,
            history=history,
        )
        # Luôn lưu tin nhắn của thành viên vào lịch sử chung của nhóm, kể cả khi bot chọn im lặng,
        # để lần sau bot vẫn có đủ ngữ cảnh nhóm đang nói chuyện gì.
        _append_history(chat_id, "user", f"{sender_name}: {message_text}")

        if not should_reply:
            print(f"🤫 [Main] (Nhóm {chat_id}) Bot chọn không góp lời cho tin nhắn này.")
            return

        # Không lưu câu fallback vào lịch sử như một câu trả lời thật - để lượt kế tiếp Gemini vẫn
        # thấy tin nhắn của thành viên "chưa được trả lời đúng nghĩa" và tự nối đúng mạch cũ.
        if not is_fallback:
            _append_history(chat_id, "model", ai_reply)
        sender.reply_to_message(message, ai_reply)
        return

    # Chat riêng (private): giữ nguyên hành vi cũ - luôn trả lời, có lịch sử hội thoại riêng.
    print(f"📥 [Main] Nhận tin nhắn từ chat_id={chat_id}: '{message_text}'")
    ai_reply, is_fallback = ai.generate_content(message_text, is_reminder=False, history=history)
    _append_history(chat_id, "user", message_text)
    if not is_fallback:
        _append_history(chat_id, "model", ai_reply)
    sender.reply_to_message(message, ai_reply)

# --- 5. CHẠY CHƯƠNG TRÌNH ---
if __name__ == "__main__":
    # Gửi tin chào hỏi đầu tiên tới người dùng mặc định, giới thiệu rõ đây là trợ lý AI đồng hành
    starting_text = ai.generate_content("Hãy soạn một lời chào mở đầu, giới thiệu bạn là trợ lý AI đồng hành (nói rõ mình là AI), thân thiện và tự nhiên theo đúng phong cách của bạn.", is_reminder=False)
    sender.send(starting_text)
    default_state = _get_user_state(TARGET_CHAT_ID)
    with users_lock:
        default_state["last_reply_time"] = time.time()
    _append_history(TARGET_CHAT_ID, "model", starting_text)

    if REMINDER_MODE == "off":
        # off: chế độ gửi thủ công cho 1 người cụ thể (TARGET_CHAT_ID) -> đã gửi xong, thoát ngay,
        # không giữ polling, không phục vụ multi-user.
        print(f"🔌 [Main] REMINDER_MODE=off -> đã gửi tin thủ công tới chat_id={TARGET_CHAT_ID}, thoát ngay (không phục vụ người khác).")
        sys.exit(0)

    # auto / custom: giữ polling để luôn sẵn sàng nhận và trả lời tin nhắn thật từ BẤT KỲ ai nhắn vào
    # (mỗi người có luồng đếm giờ + lịch sử hội thoại riêng, độc lập với nhau).
    threading.Thread(target=reminder_tracker, args=(TARGET_CHAT_ID,), daemon=True).start()

    mode_desc = f"custom ({CUSTOM_MINUTES} phút)" if REMINDER_MODE == "custom" else "auto (10' → 30')"
    print(f"🤖 [Main] Hệ thống đã sẵn sàng kết nối! Chế độ: {PERSONALITY_MODE.upper()} | Nhắc nhở: {mode_desc} | Multi-user: bật")

    try:
        sender.bot.infinity_polling(timeout=20, long_polling_timeout=20)
    except KeyboardInterrupt:
        print("⏹️ [Main] Nhận tín hiệu dừng, thoát sạch.")
        sys.exit(0)
