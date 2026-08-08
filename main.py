from telegram.ext import Application, CommandHandler, ChatMemberHandler
from config import TOKEN, CHANNEL_USERNAME

# Обработчик команды /start
async def start(update, context):
    user = update.message.from_user
    await update.message.reply_text(f'Привет, {user.first_name}!\nВот ссылка на закрытую группу.\nhttps://t.me/+y1om0bSvon1iODIy')

# Обработчик изменения статуса участника (автоматическое принятие заявок)
async def auto_approve(update, context):
    # Проверяем, что это запрос на вступление в канал
    if update.chat_member.new_chat_member.status == 'requested':
        user_id = update.chat_member.from_user.id
        chat_id = update.chat_member.chat.id

        try:
            # Принимаем заявку
            await context.bot.approve_chat_join_request(chat_id=chat_id, user_id=user_id)
            print(f'Заявка от пользователя {user_id} принята')
        except Exception as e:
            print(f'Ошибка при принятии заявки: {e}')

def main():
    # Создаем экземпляр Application
    application = Application.builder().token(TOKEN).build()

    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start))

    # Регистрируем обработчик заявок (автоматическое принятие)
    application.add_handler(ChatMemberHandler(auto_approve, ChatMemberHandler.CHAT_MEMBER))

    # Начинаем поиск обновлений
    application.run_polling()

if __name__ == '__main__':
    main()
