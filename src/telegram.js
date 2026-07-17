// Tương đương src/send_message.py. Cloudflare Workers dùng fetch() gọi thẳng Telegram Bot API,
// không cần thư viện pyTelegramBotAPI vì đây là môi trường webhook (không polling).

export class TelegramClient {
  constructor(botToken) {
    this.botToken = botToken;
    this.apiBase = `https://api.telegram.org/bot${botToken}`;
  }

  async getMe() {
    const res = await fetch(`${this.apiBase}/getMe`);
    const data = await res.json();
    return data?.result;
  }

  /** Gửi tin nhắn chủ động tới 1 chat_id bất kỳ (dùng cho nhắc nhở tự động, tin chào...) */
  async sendMessage(chatId, text) {
    try {
      const res = await fetch(`${this.apiBase}/sendMessage`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chat_id: chatId, text }),
      });
      const data = await res.json();
      if (!data.ok) {
        console.log(`✗ [Telegram] Gửi tin thất bại tới ${chatId}: ${JSON.stringify(data)}`);
        return false;
      }
      console.log(`📡 [Telegram] -> Đã gửi thành công tới ID: ${chatId}`);
      return true;
    } catch (e) {
      console.log(`✗ [Telegram] Lỗi gửi tin tới ${chatId}: ${e.message}`);
      return false;
    }
  }

  /** Trả lời trực tiếp 1 tin nhắn cụ thể (reply_to_message_id) */
  async replyToMessage(chatId, messageId, text) {
    try {
      const res = await fetch(`${this.apiBase}/sendMessage`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chat_id: chatId, text, reply_to_message_id: messageId }),
      });
      const data = await res.json();
      if (!data.ok) {
        console.log(`✗ [Telegram] Reply thất bại tới ${chatId}: ${JSON.stringify(data)}`);
        return false;
      }
      console.log(`📡 [Telegram] -> Đã phản hồi tin nhắn của ID: ${chatId}`);
      return true;
    } catch (e) {
      console.log(`✗ [Telegram] Lỗi reply tới ${chatId}: ${e.message}`);
      return false;
    }
  }

  /** Đăng ký webhook URL với Telegram - gọi 1 lần khi setup, không cần gọi mỗi request */
  async setWebhook(webhookUrl) {
    const res = await fetch(`${this.apiBase}/setWebhook`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: webhookUrl }),
    });
    return res.json();
  }
}
