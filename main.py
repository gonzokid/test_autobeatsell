import os
import json
import uuid
import logging
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, LabeledPrice
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    PreCheckoutQueryHandler, filters, ContextTypes, ConversationHandler
)

# ============ НАСТРОЙКИ ============
BOT_TOKEN = "8690704744:AAGTGrQYoE0Su3gbK1BOOxLCk8U6TqB1dnA"
SUPER_ADMIN_ID = 6756790622

# ============ СОСТОЯНИЯ ============
(
    MAIN_MENU,
    ADD_BEAT_TITLE,
    ADD_BEAT_BPM,
    ADD_BEAT_KEY,
    ADD_BEAT_MP3,
    ADD_BEAT_PRICE
) = range(6)

# ============ ЛОГИРОВАНИЕ ============
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============ МОДЕЛИ ДАННЫХ ============

@dataclass
class Beat:
    id: str
    title: str
    bpm: Optional[int] = None
    key: Optional[str] = None
    price: int = 100
    file_id: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class Beatmaker:
    user_id: int
    channel_id: str
    beats: List[str] = field(default_factory=list)


# ============ БАЗА ДАННЫХ ============

class Database:
    def __init__(self):
        self.data_dir = "data"
        os.makedirs(self.data_dir, exist_ok=True)
        self.beatmakers: Dict[int, Beatmaker] = self._load("beatmakers.json")
        self.beats: Dict[str, Beat] = self._load("beats.json")

    def _load(self, filename):
        path = os.path.join(self.data_dir, filename)
        if not os.path.exists(path):
            return {}
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if filename == "beatmakers.json":
                    return {int(k): Beatmaker(**v) for k, v in data.items()}
                return {k: Beat(**v) for k, v in data.items()}
        except:
            return {}

    def _save(self, filename, data):
        path = os.path.join(self.data_dir, filename)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({str(k): v.__dict__ for k, v in data.items()},
                      f, ensure_ascii=False, indent=2)

    def add_beatmaker(self, user_id: int, channel_id: str):
        self.beatmakers[user_id] = Beatmaker(user_id=user_id, channel_id=channel_id)
        self._save("beatmakers.json", self.beatmakers)

    def get_beatmaker(self, user_id: int) -> Optional[Beatmaker]:
        return self.beatmakers.get(user_id)

    def add_beat(self, beat: Beat, user_id: int):
        self.beats[beat.id] = beat
        if user_id in self.beatmakers:
            self.beatmakers[user_id].beats.append(beat.id)
        self._save("beats.json", self.beats)
        self._save("beatmakers.json", self.beatmakers)

    def get_beat(self, beat_id: str) -> Optional[Beat]:
        return self.beats.get(beat_id)


db = Database()


# ============ КОМАНДЫ ============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    beatmaker = db.get_beatmaker(user_id)

    if user_id == SUPER_ADMIN_ID or beatmaker:
        text = "🎵 **Панель битмейкера**\n\n➕ Добавить бит — выложить новый бит в канал"
        keyboard = [["➕ Добавить бит"]]
    else:
        text = "👋 Привет! Этот бот для битмейкеров."
        keyboard = [["/start"]]

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return MAIN_MENU


async def add_beat_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['new_beat'] = {}
    await update.message.reply_text(
        "🎵 **Название бита:**",
        reply_markup=ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True)
    )
    return ADD_BEAT_TITLE


async def add_beat_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Отмена":
        context.user_data.pop('new_beat', None)
        return await start(update, context)

    context.user_data['new_beat']['title'] = update.message.text
    await update.message.reply_text(
        "⚡ **BPM (или пропусти):**",
        reply_markup=ReplyKeyboardMarkup([["⏭️ Пропустить", "❌ Отмена"]], resize_keyboard=True)
    )
    return ADD_BEAT_BPM


async def add_beat_bpm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Отмена":
        context.user_data.pop('new_beat', None)
        return await start(update, context)

    if update.message.text == "⏭️ Пропустить":
        context.user_data['new_beat']['bpm'] = None
    else:
        try:
            context.user_data['new_beat']['bpm'] = int(update.message.text)
        except ValueError:
            await update.message.reply_text("❌ Введи число или нажми 'Пропустить'")
            return ADD_BEAT_BPM

    await update.message.reply_text(
        "🎹 **Тональность (или пропусти):**",
        reply_markup=ReplyKeyboardMarkup([["⏭️ Пропустить", "❌ Отмена"]], resize_keyboard=True)
    )
    return ADD_BEAT_KEY


async def add_beat_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Отмена":
        context.user_data.pop('new_beat', None)
        return await start(update, context)

    if update.message.text == "⏭️ Пропустить":
        context.user_data['new_beat']['key'] = None
    else:
        context.user_data['new_beat']['key'] = update.message.text

    await update.message.reply_text(
        "🎵 **Отправь MP3 файл (демо для канала):**",
        reply_markup=ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True)
    )
    return ADD_BEAT_MP3


async def add_beat_mp3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Отмена":
        context.user_data.pop('new_beat', None)
        return await start(update, context)

    if not update.message.audio:
        await update.message.reply_text("❌ Отправь аудиофайл")
        return ADD_BEAT_MP3

    context.user_data['new_beat']['mp3_file_id'] = update.message.audio.file_id
    await update.message.reply_text(
        "💰 **Цена бита в ⭐ (по умолчанию 100):**",
        reply_markup=ReplyKeyboardMarkup([["100", "200", "500"], ["❌ Отмена"]], resize_keyboard=True)
    )
    return ADD_BEAT_PRICE


async def add_beat_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Отмена":
        context.user_data.pop('new_beat', None)
        return await start(update, context)

    try:
        price = int(update.message.text) if update.message.text.isdigit() else 100
    except:
        price = 100

    # Сохраняем бит
    beat_data = context.user_data['new_beat']
    beat_id = str(uuid.uuid4())[:8]

    beat = Beat(
        id=beat_id,
        title=beat_data['title'],
        bpm=beat_data.get('bpm'),
        key=beat_data.get('key'),
        price=price,
        file_id=beat_data['mp3_file_id']
    )

    user_id = update.effective_user.id
    beatmaker = db.get_beatmaker(user_id) or db.get_beatmaker(SUPER_ADMIN_ID)

    if not beatmaker:
        await update.message.reply_text("❌ Ты не битмейкер")
        return MAIN_MENU

    db.add_beat(beat, user_id)

    # Публикуем в канал
    caption = f"🔥 **{beat.title}**"
    if beat.bpm:
        caption += f"\n⚡ BPM: {beat.bpm}"
    if beat.key:
        caption += f"\n🎹 {beat.key}"
    caption += f"\n\n💰 Цена: {beat.price} ⭐"

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(f"Купить за {beat.price} ⭐", callback_data=f"buy_{beat_id}")
    ]])

    try:
        await context.bot.send_audio(
            chat_id=beatmaker.channel_id,
            audio=beat.file_id,
            caption=caption,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )
        await update.message.reply_text("✅ Бит выложен в канал!")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}\nПроверь, что бот добавлен в канал админом")

    context.user_data.pop('new_beat', None)
    return MAIN_MENU


# ============ ПОКУПКА ============

async def buy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    beat_id = query.data.split('_')[1]
    beat = db.get_beat(beat_id)

    if not beat:
        await query.edit_message_text("❌ Бит не найден")
        return

    await context.bot.send_invoice(
        chat_id=update.effective_chat.id,
        title=beat.title,
        description=f"Покупка бита {beat.title}",
        payload=beat_id,
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label="Бит", amount=beat.price)]
    )


async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)


async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    beat_id = payment.invoice_payload
    beat = db.get_beat(beat_id)

    if beat:
        await update.message.reply_document(
            document=beat.file_id,
            caption=f"✅ {beat.title}\nСпасибо за покупку!"
        )
    else:
        await update.message.reply_text("❌ Ошибка")


# ============ ДОБАВЛЕНИЕ БИТМЕЙКЕРА ============

async def add_beatmaker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != SUPER_ADMIN_ID:
        return

    args = context.args
    if len(args) != 2:
        await update.message.reply_text("Использование: /add ID @channel")
        return

    try:
        user_id = int(args[0])
        channel_id = args[1]
        db.add_beatmaker(user_id, channel_id)
        await update.message.reply_text(f"✅ Битмейкер {user_id} добавлен с каналом {channel_id}")
    except:
        await update.message.reply_text("❌ Ошибка")


# ============ MAIN ============

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_beatmaker))

    # Кнопки
    app.add_handler(CallbackQueryHandler(buy_callback, pattern="^buy_"))

    # Платежи
    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))

    # Добавление бита (с разными состояниями)
    conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^➕ Добавить бит$"), add_beat_start)],
        states={
            ADD_BEAT_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_beat_title)],
            ADD_BEAT_BPM: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_beat_bpm)],
            ADD_BEAT_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_beat_key)],
            ADD_BEAT_MP3: [MessageHandler(filters.AUDIO, add_beat_mp3)],
            ADD_BEAT_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_beat_price)],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True
    )
    app.add_handler(conv)

    print("🚀 БОТ ЗАПУЩЕН!")
    app.run_polling()


if __name__ == '__main__':
    main()