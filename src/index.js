// Tương đương src/main.py. Kiến trúc webhook: Telegram tự gọi POST tới URL của Worker mỗi khi có
// tin nhắn mới (thay vì bot tự polling liên tục) -> không cần tiến trình chạy nền, phù hợp free tier.

import { TelegramClient } from "./telegram.js";
import { generateContent, generateGroupReply } from "./gemini.js";
import { getUserState, saveUserState, appendHistory, listActiveUserIds } from "./state.js";

const MOC_10_PHUT_MS = 10 * 60 * 1000;
const MOC_30_PHUT_MS = 30 * 60 * 1000;

function displayName(user) {
  if (!user) return "Ai đó";
  const fullName = [user.first_name, user.last_name].filter(Boolean).join(" ");
  return fullName || (user.username ? `@${user.username}` : `User${user.id}`);
}

/** Kiểm tra tin nhắn nhóm có đang nhắm tới bot không: bị @tag hoặc reply trực tiếp tin của bot. */
function wasBotAddressed(message, botUsername) {
  if (message.reply_to_message?.from?.is_bot && message.reply_to_message.from.username?.toLowerCase() === botUsername) {
    return true;
  }
  const text = message.text || message.caption || "";
  const entities = message.entities || message.caption_entities || [];
  for (const ent of entities) {
    if (ent.type === "mention") {
      const mentionText = text.slice(ent.offset, ent.offset + ent.length);
      if (mentionText.toLowerCase() === `@${botUsername}`) return true;
    }
  }
  return false;
}

async function handleStartCommand(env, tg, chatId, personality) {
  const greeting = personality === "devil"
    ? "Ơ, xịn đó, bấm /start rồi hả. Mình là trợ lý AI đồng hành thôi nha, không phải người thật đâu. Cứ nhắn gì cũng được, mình nghe hết 😏"
    : "Chào cậu! ✨ Mình là trợ lý AI đồng hành của cậu đây - một người bạn AI luôn sẵn sàng lắng nghe và trò chuyện. Cậu cứ thoải mái nhắn bất cứ điều gì nha!";

  const state = await getUserState(env.USERS_KV, chatId);
  state.lastReplyTime = Date.now();
  state.reminderStage = 0;
  state.running = true;
  appendHistory(state, "model", greeting);
  await saveUserState(env.USERS_KV, chatId, state);

  await tg.sendMessage(chatId, greeting);
}

async function handlePrivateMessage(env, tg, message, personality) {
  const chatId = message.chat.id;
  const messageText = message.text || "";

  const state = await getUserState(env.USERS_KV, chatId);
  const history = [...state.history];

  state.lastReplyTime = Date.now();
  state.reminderStage = 0;
  state.running = true;

  const { text: aiReply, isFallback } = await generateContent(env.GEMINI_API_KEY, personality, {
    contextMessage: messageText,
    history,
  });

  appendHistory(state, "user", messageText);
  if (!isFallback) {
    appendHistory(state, "model", aiReply);
  }
  await saveUserState(env.USERS_KV, chatId, state);

  await tg.replyToMessage(chatId, message.message_id, aiReply);
}

async function handleGroupMessage(env, tg, message, personality, groupMode, botUsername) {
  const chatId = message.chat.id;
  const messageText = message.text || message.caption || "";
  const wasAddressed = wasBotAddressed(message, botUsername);

  if (!wasAddressed && groupMode === "mention_only") return; // im lặng hoàn toàn, không tốn API
  if (!wasAddressed && !messageText.trim()) return;

  const state = await getUserState(env.USERS_KV, chatId);
  const history = [...state.history];

  state.lastReplyTime = Date.now();
  state.reminderStage = 0;
  state.running = true;

  const senderName = displayName(message.from);
  console.log(`📥 [Main] (Nhóm ${chatId}) ${senderName}: '${messageText}' | addressed=${wasAddressed}`);

  const { shouldReply, text: aiReply, isFallback } = await generateGroupReply(env.GEMINI_API_KEY, personality, {
    senderName,
    messageText,
    wasAddressed,
    history,
  });

  appendHistory(state, "user", `${senderName}: ${messageText}`);

  if (!shouldReply) {
    await saveUserState(env.USERS_KV, chatId, state);
    console.log(`🤫 [Main] (Nhóm ${chatId}) Bot chọn không góp lời cho tin nhắn này.`);
    return;
  }

  if (!isFallback) {
    appendHistory(state, "model", aiReply);
  }
  await saveUserState(env.USERS_KV, chatId, state);
  await tg.replyToMessage(chatId, message.message_id, aiReply);
}

async function handleUpdate(update, env) {
  const message = update.message;
  if (!message) return; // bỏ qua các loại update khác (edited_message, callback_query...)

  const tg = new TelegramClient(env.TELEGRAM_BOT_TOKEN);
  const personality = env.PERSONALITY_MODE || "dynamic";
  const groupMode = env.GROUP_MODE || "mention_only";
  const isGroup = ["group", "supergroup", "channel"].includes(message.chat.type);

  if (message.text?.startsWith("/start")) {
    await handleStartCommand(env, tg, message.chat.id, personality);
    return;
  }

  if (isGroup) {
    const me = await tg.getMe();
    const botUsername = (me?.username || "").toLowerCase();
    await handleGroupMessage(env, tg, message, personality, groupMode, botUsername);
  } else {
    await handlePrivateMessage(env, tg, message, personality);
  }
}

/** Cron handler: quét toàn bộ user đang active, gửi nhắc nhở nếu im lặng đủ 10'/30'. */
async function handleScheduledReminders(env) {
  const tg = new TelegramClient(env.TELEGRAM_BOT_TOKEN);
  const personality = env.PERSONALITY_MODE || "dynamic";
  const now = Date.now();

  const userIds = await listActiveUserIds(env.USERS_KV);

  for (const chatId of userIds) {
    const state = await getUserState(env.USERS_KV, chatId);
    if (!state.running) continue;

    const silentMs = now - state.lastReplyTime;
    const checkTime = state.lastReplyTime;

    let stageToSend = null;
    let isFinal = false;

    if (silentMs >= MOC_10_PHUT_MS && state.reminderStage === 0) {
      stageToSend = 1;
    } else if (silentMs >= MOC_30_PHUT_MS && state.reminderStage === 1) {
      stageToSend = 2;
      isFinal = true;
    }

    if (stageToSend === null) continue;

    const { text: aiText, isFallback } = await generateContent(env.GEMINI_API_KEY, personality, {
      isReminder: true,
      reminderStage: stageToSend,
      history: state.history,
    });

    // Đọc lại state ngay trước khi gửi để tránh trùng lặp nếu người dùng vừa nhắn trong lúc soạn
    const freshState = await getUserState(env.USERS_KV, chatId);
    if (freshState.lastReplyTime !== checkTime) {
      console.log(`↩️ [Cron] chat_id=${chatId} vừa nhắn trong lúc soạn nhắc nhở, huỷ gửi.`);
      continue;
    }

    await tg.sendMessage(chatId, aiText);
    freshState.reminderStage = stageToSend;
    if (!isFallback) appendHistory(freshState, "model", aiText);
    if (isFinal) {
      freshState.running = false;
      console.log(`📴 [Cron] chat_id=${chatId} im lặng quá 30 phút. Dừng theo dõi.`);
    }
    await saveUserState(env.USERS_KV, chatId, freshState);
  }
}

export default {
  async fetch(request, env, ctx) {
    if (request.method !== "POST") {
      return new Response("AIGram Bot Worker đang chạy. Dùng webhook POST để gửi update.", { status: 200 });
    }
    try {
      const update = await request.json();
      // waitUntil để xử lý xong hoàn toàn trước khi Worker bị Cloudflare tắt, dù response đã trả về
      ctx.waitUntil(handleUpdate(update, env));
      return new Response("OK", { status: 200 });
    } catch (e) {
      console.log(`✗ [Main] Lỗi xử lý update: ${e.message}`);
      return new Response("Error", { status: 500 });
    }
  },

  async scheduled(controller, env, ctx) {
    ctx.waitUntil(handleScheduledReminders(env));
  },
};
