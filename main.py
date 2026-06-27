from telegram.ext import Application, CommandHandler
from config import TOKEN, CHANNEL_USERNAME

# Обработчик команды /start
async def start(update, context):
    user = update.message.from_user
    await update.message.reply_text(f'Привет, {user.first_name}!\nВот ссылка на закрытый канал.\nhttps://t.me/+y1om0bSvon1iODIy')

# Обработчик команды для заявки на вступление
async def join_channel(update, context):
    user = update.message.from_user

    try:
        # Добавляем пользователя в канал
        await context.bot.add_chat_member(chat_id=CHANNEL_USERNAME,
                                    user_id=user.id,
                                    can_send_messages=False)  # пользователь может отправлять сообщения
        await update.message.reply_text(f'Добро пожаловать в канал, {user.first_name}!')
    except Exception as e:
        await update.message.reply_text('Что-то пошло не так. Попробуйте позже.')

def main():
    # Создаем экземпляр Application и передаем ему токен вашего бота
    application = Application.builder().token(TOKEN).build()

    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("join", join_channel))

    # Начинаем поиск обновлений
    application.run_polling()

if __name__ == '__main__':
    main()
