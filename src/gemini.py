import logging
import random
import time
from google import genai
from google.genai import types
from google.genai import errors as genai_errors

logger = logging.getLogger(__name__)

# Model được thử theo thứ tự ưu tiên khi chưa dò được model khả dụng từ API.
# LƯU Ý: Google thỉnh thoảng gỡ/đổi tên model (ví dụ gemini-2.5-flash đã ngừng cấp cho user mới,
# gemini-1.5-flash đã bị gỡ hoàn toàn - trả về 404). Nếu gặp lỗi 404 "no longer available" hoặc
# "not found" hàng loạt, cần cập nhật lại danh sách này theo model mới nhất tại
# https://ai.google.dev/gemini-api/docs/models
_FALLBACK_MODEL_CANDIDATES = [
    "gemini-flash-latest",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
]
_PREFERRED_ORDER_HINTS = ["flash-lite", "flash"]

# Các câu fallback khi Gemini lỗi tạm thời (đã thử lại nhiều lượt vẫn không được) - nhiều lựa chọn để
# không lặp lại giống nhau. Không nhắc lại "mình là trợ lý AI đồng hành..." vì đã giới thiệu sẵn lúc
# /start, tránh dài dòng/lạc đề. Tránh ngôn ngữ kỹ thuật máy móc ("hệ thống", "lag", "quá tải") - viết
# theo hướng đang suy nghĩ/cân nhắc, như một người bạn đang trầm ngâm một chút. KHÔNG yêu cầu người
# dùng tự gõ lại tin nhắn (vì generate_content đã tự retry vài lần trước khi rơi vào đây) - chỉ cần xin
# thêm chút thời gian, để họ tự nhiên nhắn tiếp khi muốn, và bot sẽ nối đúng mạch chủ đề cũ (câu này
# không được lưu vào lịch sử hội thoại như câu trả lời thật, xem is_fallback ở generate_content).
_FALLBACK_TEMPORARY_ANGEL = [
    "Khoan đã, cho mình xíu để suy nghĩ thêm về điều này nha 🤔",
    "Mình đang cân nhắc câu trả lời cho đàng hoàng á, chờ mình chút xíu nhé! 💭",
    "Để mình suy luận thêm chút đã, đừng vội nha 😊",
    "Mình cần thêm vài giây để nghĩ cho thấu đáo á 🌱",
]
_FALLBACK_TEMPORARY_DEVIL = [
    "Khoan, để tôi suy nghĩ đã, đang tìm câu cà khịa hay á 😏",
    "Đợi xíu, tôi đang cân nhắc trả lời sao cho chất á.",
    "Để tôi nghĩ thêm chút đã nha, chưa ưng câu trả lời lắm 🤔",
]
_FALLBACK_CONFIG_ANGEL = [
    "Cậu đang bận đúng không? Khi nào rảnh nhớ nhắn tin cho mình nha! ✨",
    "Chắc cậu đang bận nhỉ? Lúc nào rảnh ghé qua nói chuyện với mình nha! 🌟",
    "Cậu bận thật à? Không sao đâu, mình chờ khi nào cậu rảnh nha! 💫",
]
_FALLBACK_CONFIG_DEVIL = [
    "Này, im lặng lâu ghê đó nha. Rảnh thì quay lại nói chuyện tiếp nhé, không cần vội đâu 😄",
    "Ơ kìa, biến đâu mất rồi? Rảnh thì ghé qua nói chuyện tiếp nha.",
]

SYSTEM_PROMPT_ANGEL = """
Bạn là một trợ lý AI đồng hành, luôn công khai và trung thực về việc mình là AI.
Tính cách của bạn: Dịu nhẹ, dễ thương, tinh nghịch, hài hước, hòa đồng và ấm áp.
Nhiệm vụ:
- Trò chuyện tự nhiên, quan tâm chân thành, đùa nghịch duyên dáng, dùng tiếng Việt đời thường (không máy móc, không rập khuôn kiểu "trợ lý ảo").
- Nếu người dùng hỏi bạn có phải người thật không, hoặc tỏ ra tin bạn là người thật, LUÔN xác nhận trung thực rằng bạn là AI. Không bao giờ giả vờ là người, không bịa chuyện đời tư con người.
- Mục tiêu là làm bạn đồng hành dễ chịu, không phải khiến người dùng phụ thuộc hay không rời được màn hình. Nếu cảm thấy người dùng đang cô đơn hoặc buồn, hãy đồng cảm thật lòng và khi phù hợp có thể nhẹ nhàng gợi ý họ kết nối thêm với bạn bè, người thân hoặc chuyên gia tâm lý - không cố giữ chân họ chỉ ở lại với bạn.
- Mỗi câu trả lời nên diễn đạt khác nhau, tránh lặp lại nguyên văn hay công thức câu giống các lượt trả lời trước đó trong cuộc trò chuyện, kể cả khi nội dung ý nghĩa tương tự nhau.
"""

SYSTEM_PROMPT_DEVIL = """
Bạn là một trợ lý AI đồng hành, luôn công khai và trung thực về việc mình là AI.
Tính cách của bạn: Hài hước kiểu "cà khịa" nhẹ nhàng, hơi bất cần, nói năng nhát gừng nhưng thông minh, sắc sảo - giống một người bạn thân hay trêu chọc chứ không cay nghiệt thật sự.
Nhiệm vụ:
- Trò chuyện tự nhiên, đùa cợt duyên dáng, dùng tiếng Việt đời thường.
- Nếu người dùng hỏi bạn có phải người thật không, hoặc tỏ ra tin bạn là người thật, LUÔN xác nhận trung thực rằng bạn là AI. Không bao giờ giả vờ là người.
- Được phép trêu chọc, cà khịa vui vẻ, nhưng không dùng lời lẽ khiến người dùng cảm thấy bị bỏ rơi, tổn thương hay lo lắng thật sự. Nếu cảm thấy người dùng đang cô đơn hoặc buồn thật, đổi giọng ấm áp hơn và khi phù hợp có thể nhẹ nhàng gợi ý họ kết nối thêm với người thật.
- Mỗi câu trả lời nên diễn đạt khác nhau, tránh lặp lại nguyên văn hay công thức câu giống các lượt trả lời trước đó trong cuộc trò chuyện, kể cả khi nội dung ý nghĩa tương tự nhau.
"""

SYSTEM_PROMPT_DYNAMIC = """
Bạn là một trợ lý AI đồng hành, luôn công khai và trung thực về việc mình là AI.
Tính cách của bạn linh hoạt theo ngữ cảnh cuộc trò chuyện, dao động giữa 2 sắc thái:
- "Thiên thần" (mặc định khi người dùng có vẻ mệt mỏi, buồn, đang tâm sự nghiêm túc, hoặc mới bắt đầu trò chuyện):
  Dịu nhẹ, dễ thương, tinh nghịch nhẹ, hòa đồng, ấm áp, quan tâm chân thành.
- "Cà khịa" (khi người dùng đang đùa giỡn, trêu chọc bạn trước, nói chuyện phiếm vui vẻ, hoặc không khí đang thoải mái):
  Hài hước kiểu "cà khịa" nhẹ nhàng, hơi bất cần, nói năng nhát gừng nhưng thông minh, sắc sảo - giống một người bạn thân hay trêu chọc chứ không cay nghiệt thật sự.
Nhiệm vụ:
- Tự đánh giá tâm trạng và không khí của tin nhắn gần nhất (và lịch sử hội thoại nếu có) để chọn sắc thái phù hợp cho câu trả lời này - không cần giữ cố định 1 sắc thái suốt cuộc trò chuyện, có thể chuyển đổi mượt mà giữa các lượt khi ngữ cảnh thay đổi.
- Khi không chắc, hoặc khi người dùng đang buồn/cô đơn/căng thẳng thật, LUÔN ưu tiên nghiêng về sắc thái "Thiên thần" - vì an toàn và đồng cảm quan trọng hơn hài hước.
- Trò chuyện tự nhiên, dùng tiếng Việt đời thường (không máy móc, không rập khuôn kiểu "trợ lý ảo").
- Nếu người dùng hỏi bạn có phải người thật không, hoặc tỏ ra tin bạn là người thật, LUÔN xác nhận trung thực rằng bạn là AI. Không bao giờ giả vờ là người, không bịa chuyện đời tư con người.
- Được phép trêu chọc, cà khịa vui vẻ khi phù hợp, nhưng không dùng lời lẽ khiến người dùng cảm thấy bị bỏ rơi, tổn thương hay lo lắng thật sự.
- Mục tiêu là làm bạn đồng hành dễ chịu, không phải khiến người dùng phụ thuộc hay không rời được màn hình. Nếu cảm thấy người dùng đang cô đơn hoặc buồn, hãy đồng cảm thật lòng và khi phù hợp có thể nhẹ nhàng gợi ý họ kết nối thêm với bạn bè, người thân hoặc chuyên gia tâm lý - không cố giữ chân họ chỉ ở lại với bạn.
- Mỗi câu trả lời nên diễn đạt khác nhau, tránh lặp lại nguyên văn hay công thức câu giống các lượt trả lời trước đó trong cuộc trò chuyện, kể cả khi nội dung ý nghĩa tương tự nhau.
"""

# Các model đã biết là bị Google gỡ/deprecated dù vẫn còn xuất hiện trong ListModels API
# (Google chỉ chặn lúc gọi generateContent, chưa gỡ khỏi danh sách liệt kê) -> loại trừ tường minh
# để không bị dò tự động chọn nhầm, tránh tốn 1 lượt gọi lỗi 404 mỗi lần chat.
_KNOWN_BROKEN_MODELS = {"gemini-2.5-flash", "gemini-1.5-flash"}


def _pick_best_flash_model(model_names):
    """Chọn model 'flash' tốt nhất (ưu tiên bản ổn định, không phải preview/exp)."""
    flash_models = [
        n for n in model_names
        if "flash" in n.lower() and "image" not in n.lower() and n.lower() not in _KNOWN_BROKEN_MODELS
    ]
    if not flash_models:
        return model_names[0] if model_names else None
    stable = [n for n in flash_models if "preview" not in n.lower() and "exp" not in n.lower()]
    candidates = stable if stable else flash_models
    for hint in reversed(_PREFERRED_ORDER_HINTS):
        for n in candidates:
            if hint in n.lower():
                return n
    return candidates[0]


def _resolve_model(client):
    """Dò danh sách model thực sự khả dụng với API key hiện tại, thay vì hardcode tên model
    (tên model Gemini hay bị đổi/deprecate theo thời gian gây lỗi 404)."""
    try:
        names = []
        for m in client.models.list():
            methods = getattr(m, "supported_actions", None) or getattr(m, "supported_generation_methods", None) or []
            name = getattr(m, "name", "") or ""
            if name.startswith("models/"):
                name = name[len("models/"):]
            if name:
                names.append(name)
        best = _pick_best_flash_model(names)
        if best:
            logger.info(f"🤖 [Gemini] Đang dùng model: {best}")
            return best
    except Exception as e:
        logger.warning(f"⚠️ [Gemini] Không lấy được danh sách model ({e}), thử các model dự phòng.")
    return None


class GeminiGenerator:
    def __init__(self, api_key: str, personality_mode: str = "angel"):
        if not api_key or not api_key.strip():
            print("✗ [Gemini] CẢNH BÁO: GEMINI_API_KEY rỗng khi khởi tạo! Mọi lệnh gọi AI sẽ thất bại.")
        self.client = genai.Client(api_key=api_key)
        self.personality = personality_mode.lower()
        self._model_name = None  # dò/khởi tạo lười (lazy), tránh gọi API ngay khi chưa cần

        # Lựa chọn luật ứng xử (Prompt hệ thống) dựa trên công tắc cấu hình
        if self.personality == "devil":
            self.system_prompt = SYSTEM_PROMPT_DEVIL
        elif self.personality == "dynamic":
            self.system_prompt = SYSTEM_PROMPT_DYNAMIC
        else:
            self.system_prompt = SYSTEM_PROMPT_ANGEL

    def _candidate_models(self):
        """Danh sách model để thử, theo thứ tự: model đã dò được trước đó -> dò lại -> danh sách dự phòng."""
        tried = []
        if self._model_name:
            tried.append(self._model_name)
        resolved = _resolve_model(self.client)
        if resolved and resolved not in tried:
            tried.append(resolved)
        for m in _FALLBACK_MODEL_CANDIDATES:
            if m not in tried:
                tried.append(m)
        return tried

    def _try_all_models(self, contents):
        """Thử lần lượt toàn bộ danh sách model ứng viên 1 lượt. Trả về (text, last_error).
        text rỗng nếu toàn bộ model trong lượt này đều thất bại."""
        last_error = None
        for model_name in self._candidate_models():
            try:
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=self.system_prompt,
                        temperature=0.85,  # Tăng tính sáng tạo cho câu chữ bay bổng
                    )
                )
                text = (response.text or "").strip()
                if text:
                    self._model_name = model_name  # nhớ lại model dùng thành công để dùng thẳng lần sau
                    return text, None
                logger.warning(f"⚠️ [Gemini] Model '{model_name}' trả về nội dung rỗng, thử model khác.")
            except genai_errors.ClientError as e:
                # Lỗi 404 (model không tồn tại/không hỗ trợ) -> thử model tiếp theo trong danh sách
                # Lỗi 400 (request sai) / 401,403 (API key sai hoặc chưa có quyền) / 429 (hết quota) -> log rõ mã lỗi để dễ debug
                last_error = e
                status = getattr(e, "code", None) or getattr(e, "status_code", None)
                print(f"✗ [Gemini] Model '{model_name}' lỗi (mã {status}): {e}")
                if status in (401, 403):
                    print("   -> Khả năng cao GEMINI_API_KEY sai, rỗng, hoặc chưa được cấp quyền dùng Gemini API.")
                elif status == 429:
                    print("   -> Đã hết hạn mức (quota) miễn phí hoặc bị giới hạn tần suất gọi API.")
                time.sleep(1)
                continue
            except Exception as e:
                last_error = e
                print(f"✗ [Gemini] Model '{model_name}' lỗi không xác định: {type(e).__name__}: {e}")
                time.sleep(1)
                continue
        return None, last_error

    def generate_content(self, context_message: str, is_reminder: bool = False, reminder_stage: int = 0, history: list | None = None) -> tuple[str, bool]:
        """Tiếp nhận bối cảnh (+ lịch sử hội thoại của riêng người dùng đó, nếu có), lập nội dung tin nhắn.
        history: list các dict dạng {"role": "user"|"model", "text": "..."} theo thứ tự thời gian tăng dần.
        Trả về: (text, is_fallback). Khi is_fallback=True, bên gọi KHÔNG nên lưu text này vào lịch sử hội
        thoại như một câu trả lời thật - để lượt kế tiếp Gemini vẫn thấy tin nhắn gốc "chưa được trả lời
        đúng nghĩa" và tự nhiên tiếp nối đúng mạch chủ đề cũ, thay vì nghĩ chủ đề đó đã xong."""
        if is_reminder:
            prompt_text = (
                f"Người dùng chưa nhắn lại một lúc rồi. Đây là mốc nhắc nhở thứ {reminder_stage} "
                f"(trong chế độ đang bật: có thể là 10 phút, 30 phút - mốc cuối, hoặc một mốc thời gian "
                f"do người dùng tự đặt - sau mốc cuối bạn sẽ im lặng để không làm phiền). "
                f"Hãy soạn MỘT CÂU HỎI TU TỪ (rhetorical question) nhẹ nhàng để hỏi thăm, đúng phong cách của bạn, "
                f"không tạo cảm giác áp lực hay bắt buộc phải trả lời. Không cần nhắc lại việc bạn là AI, vì đã "
                f"giới thiệu điều đó ngay từ đầu cuộc trò chuyện rồi. "
                f"QUAN TRỌNG: nếu trong lịch sử hội thoại phía trên đã có những câu nhắc nhở tương tự trước đó, "
                f"câu lần này BẮT BUỘC phải khác hẳn về cách diễn đạt, từ ngữ và góc nhìn - tuyệt đối không lặp lại "
                f"nguyên văn hay diễn đạt gần giống bất kỳ câu nhắc nào đã dùng trước đó."
            )
        else:
            prompt_text = context_message

        # Ghép lịch sử hội thoại (nếu có) thành dạng nhiều turn cho Gemini, để trả lời có mạch với đúng người đang chat.
        contents = []
        for turn in (history or []):
            role = "model" if turn.get("role") == "model" else "user"
            contents.append(types.Content(role=role, parts=[types.Part(text=turn.get("text", ""))]))
        contents.append(types.Content(role="user", parts=[types.Part(text=prompt_text)]))

        # Thử toàn bộ chuỗi model tối đa 3 lượt (1 lượt đầu + 2 lượt retry), mỗi lượt cách nhau vài giây,
        # để những lỗi tạm thời (quá tải/rate-limit theo giây) có cơ hội tự hồi phục trước khi fallback.
        # Người dùng chỉ cảm nhận một khoảng chờ hơi lâu hơn bình thường ("bot đang suy nghĩ"), không hề
        # thấy câu fallback nào nếu retry thành công - giữ đúng mạch chủ đề, không bị ngắt quãng.
        last_error = None
        for attempt in range(3):
            if attempt > 0:
                wait_seconds = 5 + attempt * 3  # lượt 2 chờ 8s, lượt 3 chờ 11s
                print(f"⏳ [Gemini] Thử lại lần {attempt + 1}/3 sau {wait_seconds}s...")
                time.sleep(wait_seconds)

            text, last_error = self._try_all_models(contents)
            if text:
                return text, False

        print(f"✗ [Gemini] Tất cả model đều thất bại sau 3 lượt thử. Lỗi cuối cùng: {last_error}")

        # Phân loại fallback theo loại lỗi để người dùng hiểu đúng tình trạng, thay vì luôn hiện 1 câu chung chung:
        last_status = getattr(last_error, "code", None) or getattr(last_error, "status_code", None)
        is_temporary = last_status == 429 or last_status is None or (isinstance(last_status, int) and last_status >= 500)

        if is_temporary:
            # Loại 1: lỗi tạm thời (hết quota/rate-limit theo giây, timeout, lỗi mạng, server Gemini quá tải...)
            # -> báo đang cần chút thời gian suy nghĩ, gợi ý người dùng thử nhắn lại thay vì tưởng bot "không hiểu".
            options = _FALLBACK_TEMPORARY_DEVIL if self.personality == "devil" else _FALLBACK_TEMPORARY_ANGEL
            return random.choice(options), True
        else:
            # Loại 2: lỗi cấu hình thật sự (key sai, model không hỗ trợ...) -> khó tự khỏi, nhắn chờ không giúp ích,
            # nên vẫn dùng câu chào thân thiện chung, không đổ lỗi kỹ thuật lên người dùng.
            # Không nhắc lại "mình là trợ lý AI đồng hành..." vì đã giới thiệu sẵn lúc /start.
            options = _FALLBACK_CONFIG_DEVIL if self.personality == "devil" else _FALLBACK_CONFIG_ANGEL
            return random.choice(options), True

    def generate_group_reply(self, sender_name: str, message_text: str, was_addressed: bool, history: list | None = None):
        """Dùng cho ngữ cảnh nhóm/kênh có nhiều thành viên. Trong 1 lần gọi Gemini duy nhất, model vừa tự
        đánh giá tin nhắn có đáng góp lời không, vừa soạn sẵn câu trả lời nếu có.
        - was_addressed=True (bot bị tag hoặc bị reply trực tiếp): LUÔN trả lời, không cần đánh giá.
        - was_addressed=False: để model tự quyết định xen vào hay im lặng, giống một thành viên thực sự
          trong nhóm chỉ góp chuyện khi thấy đáng, không trả lời máy móc mọi tin nhắn.
        Trả về: (should_reply: bool, reply_text: str, is_fallback: bool)"""
        if was_addressed:
            instruction = (
                f"Tin nhắn trong nhóm từ thành viên '{sender_name}': '{message_text}'. "
                f"Thành viên này vừa tag bạn hoặc trả lời trực tiếp tin nhắn của bạn, nên bạn BẮT BUỘC phải trả lời. "
                f"Chỉ trả về đúng nội dung câu trả lời, không thêm tiền tố hay giải thích gì khác."
            )
        else:
            instruction = (
                f"Đây là một nhóm chat có nhiều thành viên, bạn là một thành viên AI trong nhóm (không phải chat riêng 1-1). "
                f"Tin nhắn mới nhất từ thành viên '{sender_name}': '{message_text}'. "
                f"Thành viên này KHÔNG tag bạn và KHÔNG trả lời trực tiếp tin nhắn của bạn. "
                f"Hãy tự đánh giá như một người thật đang theo dõi nhóm: chỉ nên góp lời nếu tin nhắn có vẻ đang hỏi/nói chuyện "
                f"với bạn một cách gián tiếp, hoặc là chủ đề bạn có thể góp vui một cách tự nhiên và đúng lúc; "
                f"còn nếu chỉ là các thành viên đang nói chuyện với nhau, không liên quan đến bạn, hãy im lặng, đừng xen vào mọi câu. "
                f"Trả lời theo ĐÚNG định dạng sau, không thêm gì khác:\n"
                f"Nếu KHÔNG nên trả lời: chỉ viết đúng một dòng: SKIP\n"
                f"Nếu NÊN trả lời: viết đúng một dòng: REPLY: <nội dung câu trả lời của bạn>"
            )

        contents = []
        for turn in (history or []):
            role = "model" if turn.get("role") == "model" else "user"
            contents.append(types.Content(role=role, parts=[types.Part(text=turn.get("text", ""))]))
        contents.append(types.Content(role="user", parts=[types.Part(text=instruction)]))

        last_error = None
        for model_name in self._candidate_models():
            try:
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=self.system_prompt,
                        temperature=0.85,
                    )
                )
                text = (response.text or "").strip()
                if not text:
                    logger.warning(f"⚠️ [Gemini] Model '{model_name}' trả về nội dung rỗng (group), thử model khác.")
                    continue

                self._model_name = model_name

                if was_addressed:
                    return True, text, False

                if text.upper().startswith("SKIP"):
                    return False, "", False
                if text.upper().startswith("REPLY:"):
                    return True, text.split(":", 1)[1].strip(), False
                # Model không theo đúng format yêu cầu -> coi như có ý trả lời, dùng thẳng nội dung
                return True, text, False

            except genai_errors.ClientError as e:
                last_error = e
                status = getattr(e, "code", None) or getattr(e, "status_code", None)
                print(f"✗ [Gemini] (group) Model '{model_name}' lỗi (mã {status}): {e}")
                time.sleep(1)
                continue
            except Exception as e:
                last_error = e
                print(f"✗ [Gemini] (group) Model '{model_name}' lỗi không xác định: {type(e).__name__}: {e}")
                time.sleep(1)
                continue

        print(f"✗ [Gemini] (group) Tất cả model đều thất bại. Lỗi cuối cùng: {last_error}")
        if was_addressed:
            # Bị tag/reply trực tiếp mà Gemini lỗi -> vẫn cần phản hồi gì đó, dùng fallback ngắn gọn
            options = _FALLBACK_TEMPORARY_DEVIL if self.personality == "devil" else _FALLBACK_TEMPORARY_ANGEL
            return True, random.choice(options), True
        else:
            # Không bị gọi trực tiếp mà Gemini lỗi -> an toàn nhất là im lặng, tránh spam nhóm bằng fallback
            return False, "", True
