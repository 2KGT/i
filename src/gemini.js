// Tương đương src/gemini.py trong bản Python. Giữ nguyên toàn bộ system prompt và logic fallback.

const GEMINI_MODEL_CANDIDATES = [
  "gemini-flash-latest",
  "gemini-2.0-flash",
  "gemini-2.0-flash-lite",
];

// Các model đã biết bị Google gỡ/deprecated dù có thể vẫn xuất hiện trong ListModels.
const KNOWN_BROKEN_MODELS = new Set(["gemini-2.5-flash", "gemini-1.5-flash"]);

export const SYSTEM_PROMPT_ANGEL = `
Bạn là một trợ lý AI đồng hành, luôn công khai và trung thực về việc mình là AI.
Tính cách của bạn: Dịu nhẹ, dễ thương, tinh nghịch, hài hước, hòa đồng và ấm áp.
Nhiệm vụ:
- Trò chuyện tự nhiên, quan tâm chân thành, đùa nghịch duyên dáng, dùng tiếng Việt đời thường (không máy móc, không rập khuôn kiểu "trợ lý ảo").
- Nếu người dùng hỏi bạn có phải người thật không, hoặc tỏ ra tin bạn là người thật, LUÔN xác nhận trung thực rằng bạn là AI. Không bao giờ giả vờ là người, không bịa chuyện đời tư con người.
- Mục tiêu là làm bạn đồng hành dễ chịu, không phải khiến người dùng phụ thuộc hay không rời được màn hình. Nếu cảm thấy người dùng đang cô đơn hoặc buồn, hãy đồng cảm thật lòng và khi phù hợp có thể nhẹ nhàng gợi ý họ kết nối thêm với bạn bè, người thân hoặc chuyên gia tâm lý - không cố giữ chân họ chỉ ở lại với bạn.
- Mỗi câu trả lời nên diễn đạt khác nhau, tránh lặp lại nguyên văn hay công thức câu giống các lượt trả lời trước đó trong cuộc trò chuyện, kể cả khi nội dung ý nghĩa tương tự nhau.
`.trim();

export const SYSTEM_PROMPT_DEVIL = `
Bạn là một trợ lý AI đồng hành, luôn công khai và trung thực về việc mình là AI.
Tính cách của bạn: Hài hước kiểu "cà khịa" nhẹ nhàng, hơi bất cần, nói năng nhát gừng nhưng thông minh, sắc sảo - giống một người bạn thân hay trêu chọc chứ không cay nghiệt thật sự.
Nhiệm vụ:
- Trò chuyện tự nhiên, đùa cợt duyên dáng, dùng tiếng Việt đời thường.
- Nếu người dùng hỏi bạn có phải người thật không, hoặc tỏ ra tin bạn là người thật, LUÔN xác nhận trung thực rằng bạn là AI. Không bao giờ giả vờ là người.
- Được phép trêu chọc, cà khịa vui vẻ, nhưng không dùng lời lẽ khiến người dùng cảm thấy bị bỏ rơi, tổn thương hay lo lắng thật sự. Nếu cảm thấy người dùng đang cô đơn hoặc buồn thật, đổi giọng ấm áp hơn và khi phù hợp có thể nhẹ nhàng gợi ý họ kết nối thêm với người thật.
- Mỗi câu trả lời nên diễn đạt khác nhau, tránh lặp lại nguyên văn hay công thức câu giống các lượt trả lời trước đó trong cuộc trò chuyện, kể cả khi nội dung ý nghĩa tương tự nhau.
`.trim();

export const SYSTEM_PROMPT_DYNAMIC = `
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
`.trim();

const FALLBACK_TEMPORARY_ANGEL = [
  "Khoan đã, cho mình xíu để suy nghĩ thêm về điều này nha 🤔",
  "Mình đang cân nhắc câu trả lời cho đàng hoàng á, chờ mình chút xíu nhé! 💭",
  "Để mình suy luận thêm chút đã, đừng vội nha 😊",
  "Mình cần thêm vài giây để nghĩ cho thấu đáo á 🌱",
];
const FALLBACK_TEMPORARY_DEVIL = [
  "Khoan, để tôi suy nghĩ đã, đang tìm câu cà khịa hay á 😏",
  "Đợi xíu, tôi đang cân nhắc trả lời sao cho chất á.",
  "Để tôi nghĩ thêm chút đã nha, chưa ưng câu trả lời lắm 🤔",
];
const FALLBACK_CONFIG_ANGEL = [
  "Cậu đang bận đúng không? Khi nào rảnh nhớ nhắn tin cho mình nha! ✨",
  "Chắc cậu đang bận nhỉ? Lúc nào rảnh ghé qua nói chuyện với mình nha! 🌟",
  "Cậu bận thật à? Không sao đâu, mình chờ khi nào cậu rảnh nha! 💫",
];
const FALLBACK_CONFIG_DEVIL = [
  "Này, im lặng lâu ghê đó nha. Rảnh thì quay lại nói chuyện tiếp nhé, không cần vội đâu 😄",
  "Ơ kìa, biến đâu mất rồi? Rảnh thì ghé qua nói chuyện tiếp nha.",
];

function pickRandom(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

function systemPromptFor(personality) {
  if (personality === "devil") return SYSTEM_PROMPT_DEVIL;
  if (personality === "dynamic") return SYSTEM_PROMPT_DYNAMIC;
  return SYSTEM_PROMPT_ANGEL;
}

/** Gọi 1 model Gemini 1 lần. Trả về text hoặc throw lỗi có .status */
async function callGeminiModel(apiKey, modelName, systemPrompt, contents) {
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${modelName}:generateContent?key=${apiKey}`;
  const body = {
    system_instruction: { parts: [{ text: systemPrompt }] },
    contents,
    generationConfig: { temperature: 0.85 },
  };
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const errText = await res.text().catch(() => "");
    const err = new Error(`Gemini ${modelName} lỗi ${res.status}: ${errText}`);
    err.status = res.status;
    throw err;
  }
  const data = await res.json();
  const text = data?.candidates?.[0]?.content?.parts?.[0]?.text?.trim();
  if (!text) {
    const err = new Error(`Gemini ${modelName} trả về nội dung rỗng`);
    err.status = null;
    throw err;
  }
  return text;
}

/** Thử lần lượt các model 1 lượt. Trả {text, error} */
async function tryAllModels(apiKey, systemPrompt, contents) {
  let lastError = null;
  for (const modelName of GEMINI_MODEL_CANDIDATES) {
    if (KNOWN_BROKEN_MODELS.has(modelName)) continue;
    try {
      const text = await callGeminiModel(apiKey, modelName, systemPrompt, contents);
      return { text, error: null };
    } catch (e) {
      lastError = e;
      console.log(`✗ [Gemini] Model '${modelName}' lỗi: ${e.message}`);
      // độ trễ nhỏ giữa các model để tránh burst
      await new Promise((r) => setTimeout(r, 300));
    }
  }
  return { text: null, error: lastError };
}

function historyToContents(history, promptText) {
  const contents = (history || []).map((turn) => ({
    role: turn.role === "model" ? "model" : "user",
    parts: [{ text: turn.text || "" }],
  }));
  contents.push({ role: "user", parts: [{ text: promptText }] });
  return contents;
}

/**
 * Tương đương generate_content() trong Python.
 * Trả về { text, isFallback }.
 * KHÔNG lưu vào lịch sử nếu isFallback=true (để giữ mạch chủ đề, giống bản Python).
 */
export async function generateContent(apiKey, personality, {
  contextMessage = "",
  isReminder = false,
  reminderStage = 0,
  history = [],
} = {}) {
  const systemPrompt = systemPromptFor(personality);

  let promptText;
  if (isReminder) {
    promptText = `Người dùng chưa nhắn lại một lúc rồi. Đây là mốc nhắc nhở thứ ${reminderStage} ` +
      `(trong chế độ đang bật: có thể là 10 phút, 30 phút - mốc cuối, hoặc một mốc thời gian ` +
      `do người dùng tự đặt - sau mốc cuối bạn sẽ im lặng để không làm phiền). ` +
      `Hãy soạn MỘT CÂU HỎI TU TỪ (rhetorical question) nhẹ nhàng để hỏi thăm, đúng phong cách của bạn, ` +
      `không tạo cảm giác áp lực hay bắt buộc phải trả lời. Không cần nhắc lại việc bạn là AI, vì đã ` +
      `giới thiệu điều đó ngay từ đầu cuộc trò chuyện rồi. ` +
      `QUAN TRỌNG: nếu trong lịch sử hội thoại phía trên đã có những câu nhắc nhở tương tự trước đó, ` +
      `câu lần này BẮT BUỘC phải khác hẳn về cách diễn đạt, từ ngữ và góc nhìn - tuyệt đối không lặp lại ` +
      `nguyên văn hay diễn đạt gần giống bất kỳ câu nhắc nào đã dùng trước đó.`;
  } else {
    promptText = contextMessage;
  }

  const contents = historyToContents(history, promptText);

  // Thử tối đa 3 lượt (1 lượt đầu + 2 retry), mỗi lượt cách nhau vài giây - để lỗi tạm thời
  // (quá tải/rate-limit) có cơ hội tự hồi phục trước khi fallback, giữ đúng mạch chủ đề.
  let lastError = null;
  for (let attempt = 0; attempt < 3; attempt++) {
    if (attempt > 0) {
      const waitMs = (5 + attempt * 3) * 1000;
      console.log(`⏳ [Gemini] Thử lại lần ${attempt + 1}/3 sau ${waitMs / 1000}s...`);
      await new Promise((r) => setTimeout(r, waitMs));
    }
    const { text, error } = await tryAllModels(apiKey, systemPrompt, contents);
    if (text) return { text, isFallback: false };
    lastError = error;
  }

  console.log(`✗ [Gemini] Tất cả model đều thất bại sau 3 lượt thử. Lỗi cuối: ${lastError?.message}`);

  const status = lastError?.status;
  const isTemporary = status === 429 || status === null || status === undefined || (typeof status === "number" && status >= 500);

  if (isTemporary) {
    const options = personality === "devil" ? FALLBACK_TEMPORARY_DEVIL : FALLBACK_TEMPORARY_ANGEL;
    return { text: pickRandom(options), isFallback: true };
  } else {
    const options = personality === "devil" ? FALLBACK_CONFIG_DEVIL : FALLBACK_CONFIG_ANGEL;
    return { text: pickRandom(options), isFallback: true };
  }
}

/**
 * Tương đương generate_group_reply() trong Python: 1 lệnh gọi Gemini duy nhất, model tự quyết định
 * có nên trả lời tin nhắn nhóm không (khi không bị tag/reply trực tiếp) và soạn câu trả lời luôn.
 * Trả về { shouldReply, text, isFallback }.
 */
export async function generateGroupReply(apiKey, personality, { senderName, messageText, wasAddressed, history = [] } = {}) {
  const systemPrompt = systemPromptFor(personality);

  const promptText = wasAddressed
    ? `Trong một nhóm chat, thành viên "${senderName}" vừa @tag bạn hoặc reply trực tiếp tin nhắn của bạn, nói: "${messageText}". ` +
      `Hãy trả lời tự nhiên đúng phong cách của bạn. Luôn trả về JSON hợp lệ dạng: {"should_reply": true, "reply": "nội dung câu trả lời"}.`
    : `Trong một nhóm chat có nhiều thành viên, "${senderName}" vừa nhắn: "${messageText}" (không tag/reply bạn trực tiếp). ` +
      `Hãy tự đánh giá: tin nhắn này có đáng để bạn - một AI đồng hành thân thiện trong nhóm - chủ động góp lời không ` +
      `(ví dụ câu hỏi chung, chủ đề thú vị, hoặc ai đó có vẻ cần được lắng nghe)? Đừng trả lời máy móc mọi câu, ` +
      `hãy im lặng nếu tin nhắn không thực sự cần bạn góp ý (chat phiếm giữa 2 người khác, câu quá ngắn/không rõ ý...). ` +
      `Trả về JSON hợp lệ dạng: {"should_reply": true/false, "reply": "nội dung câu trả lời nếu should_reply=true, để rỗng nếu false"}. ` +
      `CHỈ trả về JSON, không thêm text nào khác, không dùng markdown code block.`;

  const contents = historyToContents(history, promptText);

  let lastError = null;
  for (let attempt = 0; attempt < 2; attempt++) {
    if (attempt > 0) {
      await new Promise((r) => setTimeout(r, 3000));
    }
    const { text, error } = await tryAllModels(apiKey, systemPrompt, contents);
    if (text) {
      try {
        const cleaned = text.replace(/```json|```/g, "").trim();
        const parsed = JSON.parse(cleaned);
        return {
          shouldReply: Boolean(parsed.should_reply),
          text: parsed.reply || "",
          isFallback: false,
        };
      } catch (e) {
        console.log(`✗ [Gemini] (group) Không parse được JSON: ${text}`);
        // Nếu không parse được nhưng bị tag trực tiếp, vẫn trả thẳng text thô thay vì im lặng hẳn
        if (wasAddressed) return { shouldReply: true, text, isFallback: false };
        return { shouldReply: false, text: "", isFallback: false };
      }
    }
    lastError = error;
  }

  console.log(`✗ [Gemini] (group) Tất cả model đều thất bại. Lỗi cuối: ${lastError?.message}`);
  if (wasAddressed) {
    const options = personality === "devil" ? FALLBACK_TEMPORARY_DEVIL : FALLBACK_TEMPORARY_ANGEL;
    return { shouldReply: true, text: pickRandom(options), isFallback: true };
  }
  // Không bị gọi trực tiếp mà Gemini lỗi -> an toàn nhất là im lặng, tránh spam nhóm
  return { shouldReply: false, text: "", isFallback: true };
}
