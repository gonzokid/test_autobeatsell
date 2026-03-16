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
BOT_TOKEN = "8275158092:AAEuv6319LCcpfZzl--mN0CNIvSOpMIzsl8"
SUPER_ADMIN_ID = 6756790622

# ============ СОСТОЯНИЯ ============
(
    MAIN_MENU,
    SUPER_ADMIN_MENU,
    ADD_BEATMAKER,
    BEATMAKER_MENU,
    PRICELIST_MENU,
    BEATS_LIST,
    ADD_BEAT_TITLE,
    ADD_BEAT_BPM,
    ADD_BEAT_KEY,
    ADD_BEAT_COLLAB,
    ADD_BEAT_MP3,
    ADD_BEAT_COVER,
    ADD_BEAT_WAV,
    ADD_BEAT_STEMS,
    ADD_BEAT_PRICES
) = range(15)

# ============ ЛОГИРОВАНИЕ ============
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============ МОДЕЛИ ДАННЫХ ============

@dataclass
class Collab:
    """Участник коллаба"""
    channel: str
    share: int


@dataclass
class Beat:
    """Модель бита с разными версиями"""
    id: str
    title: str
    bpm: Optional[int] = None
    key: Optional[str] = None
    collabs: List[Collab] = field(default_factory=list)
    mp3_file_id: str = ""
    cover_file_id: Optional[str] = None
    wav_file_id: str = ""
    stems_file_id: str = ""
    price_wav: int = 100
    price_trackout: int = 200
    price_exclusive: int = 500
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    is_active: bool = True


@dataclass
class Beatmaker:
    """Битмейкер"""
    user_id: int
    channel_id: str
    beats: List[str] = field(default_factory=list)
    price_wav: int = 100
    price_trackout: int = 200
    price_exclusive: int = 500


@dataclass
class Purchase:
    """Покупка"""
    id: str
    user_id: int
    beat_id: str
    beatmaker_id: int
    type: str
    amount: int
    date: str = field(default_factory=lambda: datetime.now().isoformat())


# ============ БАЗА ДАННЫХ ============

class Database:
    def __init__(self):
        self.data_dir = "data"
        os.makedirs(self.data_dir, exist_ok=True)
        self.beatmakers: Dict[int, Beatmaker] = self._load("beatmakers.json")
        self.beats: Dict[str, Beat] = self._load("beats.json")
        self.purchases: Dict[str, Purchase] = self._load("purchases.json")

    def _load(self, filename):
        path = os.path.join(self.data_dir, filename)
        if not os.path.exists(path):
            return {}
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if filename == "beatmakers.json":
                    return {int(k): Beatmaker(**v) for k, v in data.items()}
                elif filename == "purchases.json":
                    return {k: Purchase(**v) for k, v in data.items()}
                else:
                    result = {}
                    for k, v in data.items():
                        if 'collabs' in v:
                            collabs = [Collab(**c) for c in v['collabs']]
                            v['collabs'] = collabs
                        result[k] = Beat(**v)
                    return result
        except Exception as e:
            logger.error(f"Ошибка загрузки {filename}: {e}")
            return {}

    def _save(self, filename, data):
        path = os.path.join(self.data_dir, filename)
        try:
            serializable = {}
            for k, v in data.items():
                if hasattr(v, '__dict__'):
                    d = v.__dict__.copy()
                    if 'collabs' in d and d['collabs']:
                        d['collabs'] = [c.__dict__ for c in d['collabs']]
                    serializable[str(k)] = d
                else:
                    serializable[str(k)] = v

            with open(path, 'w', encoding='utf-8') as f:
                json.dump(serializable, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения {filename}: {e}")

    def add_beatmaker(self, user_id: int, channel_id: str):
        self.beatmakers[user_id] = Beatmaker(
            user_id=user_id,
            channel_id=channel_id
        )
        self._save("beatmakers.json", self.beatmakers)

    def get_beatmaker(self, user_id: int) -> Optional[Beatmaker]:
        return self.beatmakers.get(user_id)

    def get_all_beatmakers(self) -> List[Beatmaker]:
        return list(self.beatmakers.values())

    def update_beatmaker_prices(self, user_id: int, wav: int, trackout: int, exclusive: int):
        if user_id in self.beatmakers:
            self.beatmakers[user_id].price_wav = wav
            self.beatmakers[user_id].price_trackout = trackout
            self.beatmakers[user_id].price_exclusive = exclusive
            self._save("beatmakers.json", self.beatmakers)

    def add_beat(self, beat: Beat, user_id: int):
        self.beats[beat.id] = beat
        if user_id in self.beatmakers:
            self.beatmakers[user_id].beats.append(beat.id)
        self._save("beats.json", self.beats)
        self._save("beatmakers.json", self.beatmakers)

    def get_beat(self, beat_id: str) -> Optional[Beat]:
        return self.beats.get(beat_id)

    def get_beatmaker_beats(self, user_id: int) -> List[Beat]:
        beatmaker = self.beatmakers.get(user_id)
        if not beatmaker:
            return []
        return [self.beats[bid] for bid in beatmaker.beats if bid in self.beats]

    def get_all_beats(self) -> List[Beat]:
        return list(self.beats.values())

    def add_purchase(self, user_id: int, beat_id: str, beatmaker_id: int, ptype: str, amount: int) -> Purchase:
        purchase_id = str(uuid.uuid4())[:8]
        purchase = Purchase(
            id=purchase_id,
            user_id=user_id,
            beat_id=beat_id,
            beatmaker_id=beatmaker_id,
            type=ptype,
            amount=amount
        )
        self.purchases[purchase_id] = purchase
        self._save("purchases.json", self.purchases)
        return purchase

    def get_beatmaker_purchases(self, beatmaker_id: int) -> List[Purchase]:
        return [p for p in self.purchases.values() if p.beatmaker_id == beatmaker_id]


db = Database()


# ============ ВСПОМОГАТЕЛЬНЫЕ ============

def is_super_admin(user_id: int) -> bool:
    return user_id == SUPER_ADMIN_ID


def get_beat_keyboard(beat_id: str) -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("WAV", callback_data=f"buy_{beat_id}_wav"),
            InlineKeyboardButton("Трэкаут", callback_data=f"buy_{beat_id}_trackout"),
            InlineKeyboardButton("Эксклюзив", callback_data=f"buy_{beat_id}_exclusive"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


# ============ СТАРТ ============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    beatmaker = db.get_beatmaker(user_id)

    if is_super_admin(user_id):
        text = "👑 **Панель суперадмина**"
        keyboard = [
            ["👑 Управление битмейкерами"],
            ["🎵 Моя панель битмейкера"],
            ["📊 Общая статистика"]
        ]
    elif beatmaker:
        text = f"🎵 **Панель битмейкера**\n\nКанал: {beatmaker.channel_id}"
        keyboard = [
            ["➕ Добавить бит", "💰 Прайслист"],
            ["📋 Мои биты", "📊 Продажи"],
            ["❌ Выход"]
        ]
    else:
        text = "👋 Привет! Это бот для битмейкеров."
        keyboard = [["/start"]]

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return MAIN_MENU


# ============ СУПЕРАДМИН ============

async def super_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_super_admin(update.effective_user.id):
        return MAIN_MENU

    text = "👑 **УПРАВЛЕНИЕ БИТМЕЙКЕРАМИ**"
    keyboard = [
        ["➕ Добавить битмейкера"],
        ["📋 Список битмейкеров"],
        ["❌ Назад"]
    ]

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return SUPER_ADMIN_MENU


async def super_admin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    if not is_super_admin(user_id):
        return MAIN_MENU

    if text == "➕ Добавить битмейкера":
        await update.message.reply_text(
            "📝 Отправь ID пользователя и @канал через пробел:\n"
            "Пример: `6756790622 @channel`",
            reply_markup=ReplyKeyboardMarkup([["❌ Назад"]], resize_keyboard=True)
        )
        return ADD_BEATMAKER

    elif text == "📋 Список битмейкеров":
        beatmakers = db.get_all_beatmakers()
        if not beatmakers:
            await update.message.reply_text("📭 Нет битмейкеров")
        else:
            msg = "📋 **БИТМЕЙКЕРЫ**\n\n"
            for bm in beatmakers:
                purchases = db.get_beatmaker_purchases(bm.user_id)
                revenue = sum(p.amount for p in purchases)
                msg += f"• ID: {bm.user_id}\n"
                msg += f"  Канал: {bm.channel_id}\n"
                msg += f"  Битов: {len(bm.beats)}\n"
                msg += f"  Продаж: {len(purchases)} | Выручка: {revenue}⭐\n\n"
            await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

    elif text == "📊 Общая статистика":
        beats = db.get_all_beats()
        purchases = list(db.purchases.values())
        revenue = sum(p.amount for p in purchases)
        await update.message.reply_text(
            f"📊 **ОБЩАЯ СТАТИСТИКА**\n\n"
            f"Битмейкеров: {len(db.beatmakers)}\n"
            f"Битов: {len(beats)}\n"
            f"Продаж: {len(purchases)}\n"
            f"Выручка: {revenue} ⭐",
            parse_mode=ParseMode.MARKDOWN
        )

    elif text == "❌ Назад":
        return await start(update, context)

    return SUPER_ADMIN_MENU


async def add_beatmaker_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Назад":
        return await super_admin_panel(update, context)

    parts = update.message.text.split()
    if len(parts) != 2:
        await update.message.reply_text("❌ Нужно: ID @channel")
        return ADD_BEATMAKER

    try:
        user_id = int(parts[0])
        channel_id = parts[1]
        db.add_beatmaker(user_id, channel_id)

        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🎉 Теперь ты битмейкер!\nКанал: {channel_id}\nНапиши /start"
            )
        except:
            pass

        await update.message.reply_text(f"✅ Битмейкер {user_id} добавлен")

    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом")
        return ADD_BEATMAKER

    return await super_admin_panel(update, context)


# ============ БИТМЕЙКЕР ============

async def beatmaker_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    beatmaker = db.get_beatmaker(user_id) or db.get_beatmaker(SUPER_ADMIN_ID)

    if not beatmaker:
        await update.message.reply_text("❌ Ты не битмейкер")
        return MAIN_MENU

    context.user_data['current_beatmaker'] = beatmaker.user_id

    text = f"🎵 **Панель битмейкера**\n\nКанал: {beatmaker.channel_id}"
    keyboard = [
        ["➕ Добавить бит", "💰 Прайслист"],
        ["📋 Мои биты", "📊 Продажи"],
        ["❌ Выход"]
    ]

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return BEATMAKER_MENU


async def beatmaker_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    beatmaker_id = context.user_data.get('current_beatmaker')
    beatmaker = db.get_beatmaker(beatmaker_id) if beatmaker_id else None

    if not beatmaker:
        return await start(update, context)

    if text == "➕ Добавить бит":
        context.user_data['new_beat'] = {'beatmaker_id': beatmaker.user_id}
        await update.message.reply_text(
            "🎵 **Название бита:**",
            reply_markup=ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True)
        )
        return ADD_BEAT_TITLE

    elif text == "💰 Прайслист":
        await update.message.reply_text(
            f"💰 **ТЕКУЩИЕ ЦЕНЫ**\n\n"
            f"WAV: {beatmaker.price_wav} ⭐\n"
            f"Трэкаут: {beatmaker.price_trackout} ⭐\n"
            f"Эксклюзив: {beatmaker.price_exclusive} ⭐\n\n"
            f"Чтобы изменить, отправь новые цены через пробел:\n"
            f"`WAV Трэкаут Эксклюзив`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True)
        )
        return PRICELIST_MENU

    elif text == "📋 Мои биты":
        beats = db.get_beatmaker_beats(beatmaker.user_id)
        if not beats:
            await update.message.reply_text("📭 У тебя пока нет битов")
        else:
            msg = "📋 **ТВОИ БИТЫ**\n\n"
            for beat in beats[-10:]:
                msg += f"• {beat.title}\n"
                if beat.bpm:
                    msg += f"  {beat.bpm} BPM"
                if beat.key:
                    msg += f" | {beat.key}"
                msg += f"\n  Цены: {beat.price_wav}/{beat.price_trackout}/{beat.price_exclusive}⭐\n\n"
            await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

    elif text == "📊 Продажи":
        purchases = db.get_beatmaker_purchases(beatmaker.user_id)
        if not purchases:
            await update.message.reply_text("📊 Пока нет продаж")
        else:
            revenue = sum(p.amount for p in purchases)
            msg = f"📊 **ПРОДАЖИ**\n\n"
            msg += f"Всего продаж: {len(purchases)}\n"
            msg += f"Выручка: {revenue} ⭐\n\n"
            msg += "**Последние:**\n"
            for p in purchases[-5:]:
                beat = db.get_beat(p.beat_id)
                msg += f"• {beat.title if beat else 'Бит'} — {p.type} — {p.amount}⭐\n"
            await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

    elif text == "❌ Выход":
        context.user_data.pop('current_beatmaker', None)
        return await start(update, context)

    return BEATMAKER_MENU


async def pricelist_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Отмена":
        return await beatmaker_menu(update, context)

    beatmaker_id = context.user_data.get('current_beatmaker')
    beatmaker = db.get_beatmaker(beatmaker_id)

    if not beatmaker:
        return MAIN_MENU

    try:
        prices = update.message.text.split()
        if len(prices) != 3:
            raise ValueError

        wav = int(prices[0])
        trackout = int(prices[1])
        exclusive = int(prices[2])

        db.update_beatmaker_prices(beatmaker.user_id, wav, trackout, exclusive)

        await update.message.reply_text(
            f"✅ Цены обновлены!\n\n"
            f"WAV: {wav} ⭐\n"
            f"Трэкаут: {trackout} ⭐\n"
            f"Эксклюзив: {exclusive} ⭐",
            parse_mode=ParseMode.MARKDOWN
        )

    except:
        await update.message.reply_text("❌ Неверный формат. Нужно: 100 200 500")
        return PRICELIST_MENU

    return await beatmaker_menu(update, context)


# ============ ДОБАВЛЕНИЕ БИТА ============

async def add_beat_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    beatmaker = db.get_beatmaker(user_id)

    if not beatmaker and not is_super_admin(user_id):
        await update.message.reply_text("❌ Ты не битмейкер")
        return MAIN_MENU

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
        except:
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
        "🤝 **Коллабораторы (или пропусти)**\n"
        "Формат: @канал процент\n"
        "Например: @producer 50\n"
        "Можно добавить несколько, каждый с новой строки\n"
        "Когда закончишь, напиши 'готово'",
        reply_markup=ReplyKeyboardMarkup([["⏭️ Пропустить", "❌ Отмена"]], resize_keyboard=True)
    )
    context.user_data['new_beat']['collabs'] = []
    return ADD_BEAT_COLLAB


async def add_beat_collab(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "❌ Отмена":
        context.user_data.pop('new_beat', None)
        return await start(update, context)

    if text == "⏭️ Пропустить" or text.lower() == "готово":
        await update.message.reply_text(
            "🎵 **Отправь MP3 файл (демо для канала):**",
            reply_markup=ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True)
        )
        return ADD_BEAT_MP3

    try:
        parts = text.split()
        if len(parts) != 2:
            await update.message.reply_text("❌ Формат: @канал процент")
            return ADD_BEAT_COLLAB

        channel = parts[0]
        if not channel.startswith('@'):
            channel = '@' + channel

        percent = int(parts[1])

        if percent <= 0 or percent > 100:
            await update.message.reply_text("❌ Процент должен быть от 1 до 100")
            return ADD_BEAT_COLLAB

        context.user_data['new_beat']['collabs'].append({
            'channel': channel,
            'share': percent
        })

        await update.message.reply_text(
            f"✅ Добавлен {channel} с долей {percent}%\n"
            f"Добавь еще или напиши 'готово'",
            reply_markup=ReplyKeyboardMarkup([["готово", "❌ Отмена"]], resize_keyboard=True)
        )
        return ADD_BEAT_COLLAB

    except ValueError:
        await update.message.reply_text("❌ Процент должен быть числом")
        return ADD_BEAT_COLLAB
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")
        return ADD_BEAT_COLLAB


async def add_beat_mp3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Отмена":
        context.user_data.pop('new_beat', None)
        return await start(update, context)

    if not update.message.audio:
        await update.message.reply_text("❌ Отправь аудиофайл")
        return ADD_BEAT_MP3

    context.user_data['new_beat']['mp3_file_id'] = update.message.audio.file_id
    await update.message.reply_text(
        "🖼️ **Отправь обложку для бита (картинку) или нажми 'Пропустить':**",
        reply_markup=ReplyKeyboardMarkup([["⏭️ Пропустить", "❌ Отмена"]], resize_keyboard=True)
    )
    return ADD_BEAT_COVER


async def add_beat_cover(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Отмена":
        context.user_data.pop('new_beat', None)
        return await start(update, context)

    if update.message.text == "⏭️ Пропустить":
        context.user_data['new_beat']['cover_file_id'] = None
    elif update.message.photo:
        context.user_data['new_beat']['cover_file_id'] = update.message.photo[-1].file_id
    else:
        await update.message.reply_text("❌ Отправь картинку или нажми 'Пропустить'")
        return ADD_BEAT_COVER

    await update.message.reply_text(
        "🎵 **Отправь WAV файл (для выдачи):**",
        reply_markup=ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True)
    )
    return ADD_BEAT_WAV


async def add_beat_wav(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Отмена":
        context.user_data.pop('new_beat', None)
        return await start(update, context)

    if update.message.document:
        context.user_data['new_beat']['wav_file_id'] = update.message.document.file_id
    else:
        await update.message.reply_text("❌ Отправь файл")
        return ADD_BEAT_WAV

    await update.message.reply_text(
        "📦 **Отправь ZIP файл со стэмзами:**",
        reply_markup=ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True)
    )
    return ADD_BEAT_STEMS


async def add_beat_stems(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Отмена":
        context.user_data.pop('new_beat', None)
        return await start(update, context)

    if update.message.document:
        context.user_data['new_beat']['stems_file_id'] = update.message.document.file_id
    else:
        await update.message.reply_text("❌ Отправь ZIP файл")
        return ADD_BEAT_STEMS

    beatmaker_id = context.user_data['new_beat']['beatmaker_id']
    beatmaker = db.get_beatmaker(beatmaker_id)

    await update.message.reply_text(
        f"💰 **ЦЕНЫ БИТА**\n\n"
        f"Текущие цены по умолчанию:\n"
        f"WAV: {beatmaker.price_wav} ⭐\n"
        f"Трэкаут: {beatmaker.price_trackout} ⭐\n"
        f"Эксклюзив: {beatmaker.price_exclusive} ⭐\n\n"
        f"Введи новые цены через пробел или нажми 'Пропустить'",
        reply_markup=ReplyKeyboardMarkup([["⏭️ Пропустить", "❌ Отмена"]], resize_keyboard=True)
    )
    return ADD_BEAT_PRICES


async def add_beat_prices(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ Отмена":
        context.user_data.pop('new_beat', None)
        return await start(update, context)

    beatmaker_id = context.user_data['new_beat']['beatmaker_id']
    beatmaker = db.get_beatmaker(beatmaker_id)

    if update.message.text == "⏭️ Пропустить":
        price_wav = beatmaker.price_wav
        price_trackout = beatmaker.price_trackout
        price_exclusive = beatmaker.price_exclusive
    else:
        try:
            prices = update.message.text.split()
            if len(prices) != 3:
                raise ValueError
            price_wav = int(prices[0])
            price_trackout = int(prices[1])
            price_exclusive = int(prices[2])
        except:
            await update.message.reply_text("❌ Неверный формат. Нужно: 100 200 500")
            return ADD_BEAT_PRICES

    beat_data = context.user_data['new_beat']
    beat_id = str(uuid.uuid4())[:8]

    collabs = []
    for c in beat_data.get('collabs', []):
        collabs.append(Collab(
            channel=c['channel'],
            share=c['share']
        ))

    beat = Beat(
        id=beat_id,
        title=beat_data['title'],
        bpm=beat_data.get('bpm'),
        key=beat_data.get('key'),
        collabs=collabs,
        mp3_file_id=beat_data['mp3_file_id'],
        cover_file_id=beat_data.get('cover_file_id'),
        wav_file_id=beat_data['wav_file_id'],
        stems_file_id=beat_data['stems_file_id'],
        price_wav=price_wav,
        price_trackout=price_trackout,
        price_exclusive=price_exclusive
    )

    db.add_beat(beat, beatmaker.user_id)

    caption = f"🔥 **{beat.title}**"
    if beat.bpm:
        caption += f"\n⚡ BPM: {beat.bpm}"
    if beat.key:
        caption += f"\n🎹 {beat.key}"
    if beat.collabs:
        collab_text = ", ".join([f"{c.channel} ({c.share}%)" for c in beat.collabs])
        caption += f"\n🤝 Коллаб: {collab_text}"
    caption += f"\n\n💰 **Цены:**\n"
    caption += f"WAV: {beat.price_wav}⭐\n"
    caption += f"Трэкаут: {beat.price_trackout}⭐\n"
    caption += f"Эксклюзив: {beat.price_exclusive}⭐"

    try:
        if beat.cover_file_id:
            await context.bot.send_photo(
                chat_id=beatmaker.channel_id,
                photo=beat.cover_file_id,
                caption=caption,
                parse_mode=ParseMode.MARKDOWN
            )

        await context.bot.send_audio(
            chat_id=beatmaker.channel_id,
            audio=beat.mp3_file_id,
            caption=caption,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_beat_keyboard(beat.id)
        )
        await update.message.reply_text("✅ Бит выложен в канал!")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}\nПроверь, что бот добавлен в канал админом")

    context.user_data.pop('new_beat', None)
    return await beatmaker_menu(update, context)


# ============ ПОКУПКИ ============

async def buy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, beat_id, ptype = query.data.split('_')
    beat = db.get_beat(beat_id)

    if not beat:
        await query.edit_message_text("❌ Бит не найден")
        return

    prices = {
        'wav': beat.price_wav,
        'trackout': beat.price_trackout,
        'exclusive': beat.price_exclusive
    }
    names = {
        'wav': 'WAV',
        'trackout': 'Трэкаут',
        'exclusive': 'Эксклюзив'
    }

    price = prices.get(ptype)
    if not price:
        return

    await context.bot.send_invoice(
        chat_id=update.effective_chat.id,
        title=f"{beat.title} — {names[ptype]}",
        description=f"Покупка бита {beat.title}",
        payload=f"{beat_id}_{ptype}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=names[ptype], amount=price)]
    )


async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)


async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    beat_id, ptype = payment.invoice_payload.split('_')

    beat = db.get_beat(beat_id)
    if not beat:
        await update.message.reply_text("❌ Ошибка")
        return

    beatmaker = None
    for bm in db.beatmakers.values():
        if beat.id in bm.beats:
            beatmaker = bm
            break

    if not beatmaker:
        await update.message.reply_text("❌ Битмейкер не найден")
        return

    db.add_purchase(
        user_id=update.effective_user.id,
        beat_id=beat_id,
        beatmaker_id=beatmaker.user_id,
        ptype=ptype,
        amount=payment.total_amount
    )

    if ptype == 'wav':
        await update.message.reply_document(
            document=beat.wav_file_id,
            caption=f"✅ {beat.title} (WAV)"
        )
    elif ptype == 'trackout':
        await update.message.reply_document(
            document=beat.wav_file_id,
            caption=f"✅ {beat.title} (WAV)"
        )
        await update.message.reply_document(
            document=beat.stems_file_id,
            caption=f"✅ {beat.title} (Стэмзы)"
        )
    elif ptype == 'exclusive':
        await update.message.reply_document(
            document=beat.wav_file_id,
            caption=f"✅ {beat.title} (WAV)"
        )
        await update.message.reply_document(
            document=beat.stems_file_id,
            caption=f"✅ {beat.title} (Стэмзы)"
        )
        await update.message.reply_text(
            "📄 **Эксклюзивные права**\n\n"
            "Свяжись с битмейкером для оформления договора.\n"
            f"Канал: {beatmaker.channel_id}",
            parse_mode=ParseMode.MARKDOWN
        )

    await update.message.reply_text("✅ Спасибо за покупку!")


# ============ MAIN ============

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(buy_callback, pattern="^buy_"))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))

    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^👑 Управление битмейкерами$"), super_admin_panel),
            MessageHandler(filters.Regex("^🎵 Моя панель битмейкера$"), beatmaker_menu),
            MessageHandler(filters.Regex("^🎵 Панель битмейкера$"), beatmaker_menu),
            MessageHandler(filters.Regex("^➕ Добавить бит$"), add_beat_start),
        ],
        states={
            MAIN_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, start)],
            SUPER_ADMIN_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, super_admin_handler)],
            ADD_BEATMAKER: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_beatmaker_handler)],
            BEATMAKER_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, beatmaker_handler)],
            PRICELIST_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, pricelist_handler)],
            ADD_BEAT_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_beat_title)],
            ADD_BEAT_BPM: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_beat_bpm)],
            ADD_BEAT_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_beat_key)],
            ADD_BEAT_COLLAB: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_beat_collab)],
            ADD_BEAT_MP3: [MessageHandler(filters.AUDIO, add_beat_mp3)],
            ADD_BEAT_COVER: [MessageHandler(filters.PHOTO | filters.TEXT, add_beat_cover)],
            ADD_BEAT_WAV: [MessageHandler(filters.Document.ALL, add_beat_wav)],
            ADD_BEAT_STEMS: [MessageHandler(filters.Document.ALL, add_beat_stems)],
            ADD_BEAT_PRICES: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_beat_prices)],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True
    )
    app.add_handler(conv)

    print("🚀 БОТ ЗАПУЩЕН!")
    print(f"👑 Суперадмин ID: {SUPER_ADMIN_ID}")
    print("✅ Поддерживаются: WAV, Трэкаут, Эксклюзив, Коллабы, Обложки")
    app.run_polling()


if __name__ == '__main__':
    main()