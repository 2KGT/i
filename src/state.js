// Thay thế dict `users = {}` trong RAM (bản Python) bằng Cloudflare KV - lưu bền vững giữa các lần
// Worker được gọi, vì mỗi request là 1 lần "sống" độc lập, không có RAM dùng chung xuyên suốt.
//
// Cấu trúc mỗi user lưu dưới key `user:<chat_id>`:
// {
//   lastReplyTime: number (epoch ms),
//   reminderStage: number,
//   running: boolean,
//   history: [{role: "user"|"model", text: string}, ...]  (tối đa MAX_HISTORY_TURNS)
// }

const MAX_HISTORY_TURNS = 20;

function userKey(chatId) {
  return `user:${chatId}`;
}

export async function getUserState(kv, chatId) {
  const raw = await kv.get(userKey(chatId));
  if (raw) {
    try {
      return JSON.parse(raw);
    } catch (e) {
      console.log(`⚠️ [State] Lỗi parse state của ${chatId}, tạo state mới.`);
    }
  }
  return {
    lastReplyTime: Date.now(),
    reminderStage: 0,
    running: true,
    history: [],
  };
}

export async function saveUserState(kv, chatId, state) {
  await kv.put(userKey(chatId), JSON.stringify(state));
}

export function appendHistory(state, role, text) {
  state.history.push({ role, text });
  if (state.history.length > MAX_HISTORY_TURNS) {
    state.history = state.history.slice(-MAX_HISTORY_TURNS);
  }
}

/** Liệt kê toàn bộ chat_id đang được theo dõi (running=true) - dùng trong cron để quét nhắc nhở. */
export async function listActiveUserIds(kv) {
  const ids = [];
  let cursor;
  do {
    const res = await kv.list({ prefix: "user:", cursor });
    for (const key of res.keys) {
      ids.push(key.name.slice("user:".length));
    }
    cursor = res.cursor;
  } while (cursor);
  return ids;
}
