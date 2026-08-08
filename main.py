import logging
from html import escape
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import Application, CallbackQueryHandler, ChatJoinRequestHandler, CommandHandler, ContextTypes, MessageHandler, filters
from config import ADMIN_CHAT_ID, DATABASE_PATH, TOKEN
from database import Database
from podcasts import PODCASTS, season_text

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
db = Database(DATABASE_PATH)

WELCOME_TEXT = """Привет! Я бот проекта «Мир 1С» 👋

Здесь ты можешь:
• посмотреть выпуски подкаста;
• узнать о клубе «Мир 1С» и вступить в него;
• познакомиться со мной и найти мои социальные сети;
• предложить интересную тему для подкаста;
• найти контакты для связи.

Выбери нужный раздел 👇"""
CLUB_TEXT = """👥 <b>Клуб «Мир 1С»</b>

Закрытое сообщество специалистов 1С для общения, обмена опытом и совместного разбора реальных рабочих кейсов.

В клубе проходят встречи с докладами и открытыми обсуждениями. Участники получают видеозаписи, транскрипции, краткие резюме и презентации спикеров.

Общаемся на «ты», без осуждения, менторского тона и обесценивания — с фокусом на поддержку и практическую пользу."""
ABOUT_TEXT = """👤 <b>Кратко обо мне</b>

Меня зовут Сергей Сыпачев. В 1С с 1999 года — прошёл путь от разработчика до руководителя проектов. Сейчас руковожу внедрением «1С:ERP.УХ»."""
SOCIAL_TEXT = """🌐 <b>Социальные сети</b>

• <a href="https://t.me/sergsyp">Канал «Мир 1С»</a>
• <a href="https://sergsyp.ru/">Сайт</a>
• <a href="https://www.youtube.com/@sergsyp">YouTube</a>
• <a href="https://vkvideo.ru/@sergsyp/">VK Видео</a>
• <a href="https://dzen.ru/sergsyp">Дзен</a>
• <a href="https://rutube.ru/channel/25725705/">Rutube</a>"""
CONTACTS_TEXT = """✉️ <b>Контакты</b>

Связаться со мной можно удобным способом:

• <a href="https://max.ru/u/f9LHodD0cOJu2apFmd-4ceDEioEv5nebgJpi4Irb8KSJzNHO8MtcxfKf628">MAX</a>
• <a href="https://t.me/ssypachev">Telegram</a>
• <a href="mailto:s@sypachev.ru">Почта</a>"""
PROPOSAL_TEXT = """🎤 <b>Попасть на подкаст</b>

Есть интересная тема или полезный опыт?

Напиши одним сообщением, о чём хочешь рассказать и почему это будет интересно слушателям. Я передам твоё предложение Сергею 👇"""

def main_menu():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🎙 Подкасты",callback_data="podcasts")],[InlineKeyboardButton("👥 Клуб «Мир 1С»",callback_data="club")],[InlineKeyboardButton("👤 Обо мне",callback_data="about")],[InlineKeyboardButton("🎤 Попасть на подкаст",callback_data="proposal")],[InlineKeyboardButton("✉️ Контакты",callback_data="contacts")]])

def navigation(back=None):
    buttons=[]
    if back: buttons.append(InlineKeyboardButton("⬅️ Назад",callback_data=back))
    buttons.append(InlineKeyboardButton("🏠 Главное меню",callback_data="menu"))
    return InlineKeyboardMarkup([buttons])

def podcasts_menu():
    rows=[[InlineKeyboardButton("📚 Все сезоны",callback_data="all_seasons")]]
    for start in range(1,len(PODCASTS)+1,3):
        rows.append([InlineKeyboardButton(f"Сезон {s}",callback_data=f"season:{s}") for s in range(start,min(start+3,len(PODCASTS)+1))])
    rows.append([InlineKeyboardButton("🏠 Главное меню",callback_data="menu")])
    return InlineKeyboardMarkup(rows)

async def start(update,context):
    context.user_data.pop("awaiting_proposal",None)
    db.upsert_user(update.effective_user); db.log_action(update.effective_user.id,"start")
    await update.message.reply_text(WELCOME_TEXT,reply_markup=main_menu())

async def on_callback(update,context):
    query=update.callback_query; await query.answer(); action=query.data
    db.upsert_user(update.effective_user); db.log_action(update.effective_user.id,action)
    context.user_data.pop("awaiting_proposal",None)
    if action=="menu": await query.edit_message_text(WELCOME_TEXT,reply_markup=main_menu())
    elif action=="podcasts": await query.edit_message_text("🎙 <b>Подкасты «Мир 1С»</b>\n\nВыбери сезон или открой весь каталог:",parse_mode=ParseMode.HTML,reply_markup=podcasts_menu())
    elif action=="all_seasons":
        await query.edit_message_text("📚 <b>Все сезоны подкаста «Мир 1С»</b>\n\nНиже — все выпуски, разделённые по сезонам.",parse_mode=ParseMode.HTML)
        for season in PODCASTS:
            await query.message.reply_text(season_text(season),parse_mode=ParseMode.HTML,disable_web_page_preview=True,reply_markup=navigation("podcasts") if season==len(PODCASTS) else None)
    elif action.startswith("season:"):
        season=int(action.split(":",1)[1])
        await query.edit_message_text(season_text(season),parse_mode=ParseMode.HTML,disable_web_page_preview=True,reply_markup=navigation("podcasts"))
    elif action=="club": await query.edit_message_text(CLUB_TEXT,parse_mode=ParseMode.HTML,reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Вступить в клуб",url="https://t.me/+y1om0bSvon1iODIy")],[InlineKeyboardButton("🏠 Главное меню",callback_data="menu")]]))
    elif action=="about": await query.edit_message_text("👤 <b>Обо мне</b>",parse_mode=ParseMode.HTML,reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Кратко обо мне",callback_data="about_short")],[InlineKeyboardButton("🌐 Социальные сети",callback_data="social")],[InlineKeyboardButton("🏠 Главное меню",callback_data="menu")]]))
    elif action=="about_short": await query.edit_message_text(ABOUT_TEXT,parse_mode=ParseMode.HTML,reply_markup=navigation("about"))
    elif action=="social": await query.edit_message_text(SOCIAL_TEXT,parse_mode=ParseMode.HTML,disable_web_page_preview=True,reply_markup=navigation("about"))
    elif action=="contacts": await query.edit_message_text(CONTACTS_TEXT,parse_mode=ParseMode.HTML,disable_web_page_preview=True,reply_markup=navigation())
    elif action=="proposal":
        context.user_data["awaiting_proposal"]=True
        await query.edit_message_text(PROPOSAL_TEXT,parse_mode=ParseMode.HTML,reply_markup=navigation())

async def receive_proposal(update,context):
    if not context.user_data.get("awaiting_proposal"): return
    text=update.message.text.strip()
    if len(text)<20:
        await update.message.reply_text("Расскажи чуть подробнее — сообщение должно содержать хотя бы 20 символов."); return
    user=update.effective_user; proposal_id=db.save_proposal(user,text)
    username=f"@{user.username}" if user.username else "не указан"
    admin_text=f"🎤 <b>Новое предложение для подкаста №{proposal_id}</b>\n\nОт: {escape(user.full_name)}\nUsername: {escape(username)}\nTelegram ID: <code>{user.id}</code>\n\n{escape(text)}"
    try: await context.bot.send_message(ADMIN_CHAT_ID,admin_text,parse_mode=ParseMode.HTML)
    except Exception:
        logger.exception("Не удалось переслать предложение %s",proposal_id)
        await update.message.reply_text("Не удалось передать предложение. Попробуй ещё раз немного позже.",reply_markup=main_menu()); return
    context.user_data.pop("awaiting_proposal",None)
    await update.message.reply_text("✅ Спасибо! Предложение передано Сергею.",reply_markup=main_menu())

async def auto_approve(update,context):
    request=update.chat_join_request
    try:
        await request.approve(); db.log_action(request.from_user.id,f"join_request_approved:{request.chat.id}")
    except Exception: logger.exception("Не удалось принять заявку пользователя %s",request.from_user.id)

async def error_handler(update,context): logger.exception("Необработанная ошибка",exc_info=context.error)

def build_application():
    db.initialize(); application=Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start",start)); application.add_handler(CommandHandler("menu",start))
    application.add_handler(CallbackQueryHandler(on_callback)); application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,receive_proposal)); application.add_handler(ChatJoinRequestHandler(auto_approve)); application.add_error_handler(error_handler)
    return application

def main(): build_application().run_polling(allowed_updates=Update.ALL_TYPES)
if __name__=="__main__": main()
