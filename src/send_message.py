import telebot

class TelegramSender:
    def __init__(self, bot_token: str, target_chat_id: int):
        self.bot = telebot.TeleBot(bot_token)
        self.chat_id = target_chat_id

    def send(self, text: str) -> bool:
        """Nhận văn bản cuối cùng và đẩy thẳng lên Telegram Chat ID mặc định (dùng cho tin chào hỏi lúc khởi động)"""
        return self.send_to(self.chat_id, text)

    def send_to(self, chat_id, text: str) -> bool:
        """Gửi chủ động một tin nhắn tới một chat_id cụ thể bất kỳ (dùng cho nhắc nhở đa người dùng)"""
        try:
            self.bot.send_message(chat_id, text, parse_mode="Markdown")
            print(f"📡 [Telegram] -> Đã gửi thành công tới ID: {chat_id}")
            return True
        except Exception as e:
            print(f"✗ [Telegram] Gửi tin nhắn thất bại tới ID {chat_id}: {e}")
            return False

    def reply_to_message(self, message_obj, text: str):
        """Phản hồi lại một bong bóng tin nhắn cụ thể của người dùng"""
        try:
            self.bot.reply_to(message_obj, text, parse_mode="Markdown")
            print(f"📡 [Telegram] -> Đã phản hồi tin nhắn của ID: {message_obj.chat.id}")
        except Exception as e:
            print(f"✗ [Telegram] Phản hồi tin nhắn thất bại: {e}")
