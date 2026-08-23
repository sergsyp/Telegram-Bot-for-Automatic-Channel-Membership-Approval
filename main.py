import logging
from html import escape
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import Application, CallbackQueryHandler, ChatJoinRequestHandler, CommandHandler, ContextTypes, MessageHandler, filters
from config import ADMIN_CHAT_ID, DATABASE_PATH, TOKEN
from database import Database
from podcasts import PODCASTS, search_text, season_text
from publication_links import PUBLICATION_LINKS
from view_stats import schedule_collection

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

Основу моей экспертизы составляет уникальное сочетание глубоких технических знаний и сильных управленческих компетенций, отточенных за четверть века практики в ИТ.

Мой путь начался в 1999 году с написания кода, что заложило фундаментальное понимание всех процессов разработки. Я прошел все ключевые этапы эволюции отрасли: от сопровождения и разработки проектов на 1С и Java до создания мобильных приложений и организации сложных системных интеграций.

Со временем моя роль трансформировалась из технического специалиста в архитектора решений и лидера команд. Я приобрел бесценный опыт не только в создании продуктов (как собственных, так и на базе типовых конфигураций), но и в формировании высокоэффективных команд: я нанимал, развивал и руководил штатными разработчиками, а также выстраивал продуктивную работу с внешними подрядчиками.

Этот многогранный опыт позволяет мне видеть проект целостно — от архитектурной концепции и линии кода до бизнес-результата и эффективной работы команды."""
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
• Почта: <a href="mailto:s@sypachev.ru">s@sypachev.ru</a>"""
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
    rows.append([InlineKeyboardButton("🔎 Поиск",callback_data="podcast_search")])
    rows.append([InlineKeyboardButton("🏠 Главное меню",callback_data="menu")])
    return InlineKeyboardMarkup(rows)

async def start(update,context):
    context.user_data.pop("awaiting_proposal",None)
    context.user_data.pop("awaiting_podcast_search",None)
    db.upsert_user(update.effective_user)
    db.log_action(update.effective_user.id,"command_start",{"command":update.message.text.split()[0]})
    await update.message.reply_text(WELCOME_TEXT,reply_markup=main_menu())

async def on_callback(update,context):
    query=update.callback_query; await query.answer(); action=query.data
    db.upsert_user(update.effective_user); db.log_action(update.effective_user.id,action)
    context.user_data.pop("awaiting_proposal",None)
    context.user_data.pop("awaiting_podcast_search",None)
    if action=="menu": await query.edit_message_text(WELCOME_TEXT,reply_markup=main_menu())
    elif action=="podcasts": await query.edit_message_text("🎙 <b>Подкасты «Мир 1С»</b>\n\nВыбери сезон или открой весь каталог:",parse_mode=ParseMode.HTML,reply_markup=podcasts_menu())
    elif action=="all_seasons":
        await query.edit_message_text("📚 <b>Все сезоны подкаста «Мир 1С»</b>\n\nНиже — все выпуски, разделённые по сезонам.",parse_mode=ParseMode.HTML)
        episode_stats=db.latest_episode_view_stats()
        for season in PODCASTS:
            await query.message.reply_text(season_text(season,episode_stats),parse_mode=ParseMode.HTML,disable_web_page_preview=True,reply_markup=navigation("podcasts") if season==len(PODCASTS) else None)
    elif action.startswith("season:"):
        season=int(action.split(":",1)[1])
        await query.edit_message_text(season_text(season,db.latest_episode_view_stats()),parse_mode=ParseMode.HTML,disable_web_page_preview=True,reply_markup=navigation("podcasts"))
    elif action=="podcast_search":
        context.user_data["awaiting_podcast_search"]=True
        await query.edit_message_text("🔎 <b>Поиск по подкастам</b>\n\nВведи часть названия, темы или имени гостя.",parse_mode=ParseMode.HTML,reply_markup=navigation("podcasts"))
    elif action=="club": await query.edit_message_text(CLUB_TEXT,parse_mode=ParseMode.HTML,reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Вступить в клуб",url="https://t.me/+y1om0bSvon1iODIy")],[InlineKeyboardButton("🏠 Главное меню",callback_data="menu")]]))
    elif action=="about": await query.edit_message_text("👤 <b>Обо мне</b>",parse_mode=ParseMode.HTML,reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Кратко обо мне",callback_data="about_short")],[InlineKeyboardButton("🌐 Социальные сети",callback_data="social")],[InlineKeyboardButton("🏠 Главное меню",callback_data="menu")]]))
    elif action=="about_short": await query.edit_message_text(ABOUT_TEXT,parse_mode=ParseMode.HTML,reply_markup=navigation("about"))
    elif action=="social": await query.edit_message_text(SOCIAL_TEXT,parse_mode=ParseMode.HTML,disable_web_page_preview=True,reply_markup=navigation("about"))
    elif action=="contacts": await query.edit_message_text(CONTACTS_TEXT,parse_mode=ParseMode.HTML,disable_web_page_preview=True,reply_markup=navigation())
    elif action=="proposal":
        context.user_data["awaiting_proposal"]=True
        await query.edit_message_text(PROPOSAL_TEXT,parse_mode=ParseMode.HTML,reply_markup=navigation())

async def receive_proposal(update,context):
    if context.user_data.pop("awaiting_podcast_search",None):
        query=update.message.text.strip()
        if len(query)<2:
            db.log_action(update.effective_user.id,"podcast_search_invalid",{"query_length":len(query)},False)
            context.user_data["awaiting_podcast_search"]=True
            await update.message.reply_text("Введи не менее двух символов."); return
        results=search_text(query,db.latest_episode_view_stats())
        db.log_action(update.effective_user.id,"podcast_search",{"query":query,"results":len(results)})
        for index, result in enumerate(results):
            await update.message.reply_text(result,parse_mode=ParseMode.HTML,disable_web_page_preview=True,reply_markup=navigation("podcasts") if index==len(results)-1 else None)
        return
    if not context.user_data.get("awaiting_proposal"): return
    text=update.message.text.strip()
    if len(text)<20:
        db.log_action(update.effective_user.id,"podcast_proposal_invalid",{"text_length":len(text)},False)
        await update.message.reply_text("Расскажи чуть подробнее — сообщение должно содержать хотя бы 20 символов."); return
    user=update.effective_user; proposal_id=db.save_proposal(user,text)
    username=f"@{user.username}" if user.username else "не указан"
    admin_text=f"🎤 <b>Новое предложение для подкаста №{proposal_id}</b>\n\nОт: {escape(user.full_name)}\nUsername: {escape(username)}\nTelegram ID: <code>{user.id}</code>\n\n{escape(text)}"
    try: await context.bot.send_message(ADMIN_CHAT_ID,admin_text,parse_mode=ParseMode.HTML)
    except Exception:
        db.log_action(user.id,"podcast_proposal_delivery",{"proposal_id":proposal_id},False)
        logger.exception("Не удалось переслать предложение %s",proposal_id)
        await update.message.reply_text("Не удалось передать предложение. Попробуй ещё раз немного позже.",reply_markup=main_menu()); return
    db.log_action(user.id,"podcast_proposal_delivery",{"proposal_id":proposal_id},True)
    context.user_data.pop("awaiting_proposal",None)
    await update.message.reply_text("✅ Спасибо! Предложение передано Сергею.",reply_markup=main_menu())

async def auto_approve(update,context):
    request=update.chat_join_request
    try:
        await request.approve(); db.log_action(request.from_user.id,"join_request_approved",{"chat_id":request.chat.id})
    except Exception:
        db.log_action(request.from_user.id,"join_request_approved",{"chat_id":request.chat.id},False)
        logger.exception("Не удалось принять заявку пользователя %s",request.from_user.id)

async def stats(update,context):
    if update.effective_user.id != ADMIN_CHAT_ID:
        db.log_action(update.effective_user.id,"command_stats_denied",success=False)
        return
    labels=((1,"24 часа"),(7,"7 дней"),(30,"30 дней"))
    blocks=[]
    for days,label in labels:
        report=db.stats(days)
        top=", ".join(f"{escape(action)} — {amount}" for action,amount in report["actions"][:5]) or "нет данных"
        blocks.append(
            f"<b>{label}</b>: событий {report['events']}, пользователей {report['users']}, "
            f"ошибок {report['errors']}\nПопулярные действия: {top}"
        )
    db.log_action(update.effective_user.id,"command_stats")
    await update.message.reply_text("📊 <b>Статистика бота</b>\n\n"+"\n\n".join(blocks),parse_mode=ParseMode.HTML)

async def error_handler(update,context):
    user_id=update.effective_user.id if update and update.effective_user else None
    db.log_action(user_id,"unhandled_error",{"type":type(context.error).__name__},False)
    logger.exception("Необработанная ошибка",exc_info=context.error)

def build_application():
    db.initialize(); db.sync_podcast_catalog(PODCASTS); db.sync_publication_links(PUBLICATION_LINKS)
    application=Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start",start)); application.add_handler(CommandHandler("menu",start)); application.add_handler(CommandHandler("stats",stats))
    application.add_handler(CallbackQueryHandler(on_callback)); application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,receive_proposal)); application.add_handler(ChatJoinRequestHandler(auto_approve)); application.add_error_handler(error_handler)
    schedule_collection(application,db,ADMIN_CHAT_ID)
    return application

def main(): build_application().run_polling(allowed_updates=Update.ALL_TYPES)
if __name__=="__main__": main()
