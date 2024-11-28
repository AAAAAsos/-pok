import sys
import asyncio

# Установка политики событийного цикла для Windows
if sys.platform.startswith('win'):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import aiosqlite
import re
import logging
import time
from datetime import datetime, timedelta
from pyrogram import Client, filters, enums, idle
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    CallbackQuery,
    ChatPermissions,
    ChatMemberUpdated,
)
from pyrogram.errors import PeerIdInvalid, UserNotParticipant
from pyrogram.types import User
import random

logging.basicConfig(level=logging.INFO)

# Словарь для отслеживания времени последнего нажатия кнопки пользователем
button_usage_times = {}

async def is_button_click_allowed(user_id):
    current_time = time.time()
    last_time = button_usage_times.get(user_id, 0)
    if current_time - last_time >= 0.5:
        button_usage_times[user_id] = current_time
        return True
    else:
        return False

async def main():
    # Конфигурация бота
    API_ID = '24142370'  
    API_HASH = '5499eef960820d34a871c67024d89819' 
    BOT_TOKEN = '7606576920:AAH1NHux5muyr-kdt0aaMMmZ0sxuAwp06Ec' 
    OWNER_ID = 6927426919  



    db = None  # Переменная для подключения к базе данных

    app = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

    # Словарь с изображениями для каждого типа репутации
    IMAGE_URLS = {
        "Владелец": "https://ibb.co/6DgKqwq",
        "Админ": "https://i.ibb.co/0c7PSpQ",
        "Стажер": "https://i.ibb.co/s9zjWWW",
        "Гарант": "https://i.ibb.co/4FTCJ10",
        "Проверен Гарантом": "https://i.ibb.co/s3kRSnf",
        "Скамер": "https://i.ibb.co/qFKYTg7",
        "Нет в базе": "https://ibb.co/j3xxGdr"
    }

    def is_owner(user_id):
        return user_id == OWNER_ID

    async def is_admin(user_id):
        if is_owner(user_id):
            return True
        if db is None:
            logging.error("База данных не инициализирована.")
            return False
        async with db.execute('SELECT 1 FROM admins WHERE user_id = ?', (user_id,)) as cursor:
            return await cursor.fetchone() is not None

    async def is_trainee(user_id):
        if db is None:
            logging.error("База данных не инициализирована.")
            return False
        async with db.execute('SELECT 1 FROM trainees WHERE user_id = ?', (user_id,)) as cursor:
            return await cursor.fetchone() is not None

    async def is_guarantor(user_id):
        if db is None:
            logging.error("База данных не инициализирована.")
            return False
        async with db.execute('SELECT 1 FROM guarantors WHERE user_id = ?', (user_id,)) as cursor:
            return await cursor.fetchone() is not None

    async def is_premium(user_id):
        if db is None:
            logging.error("База данных не инициализирована.")
            return False
        async with db.execute('SELECT 1 FROM premium_users WHERE user_id = ?', (user_id,)) as cursor:
            return await cursor.fetchone() is not None

    async def init_db():
        nonlocal db
        try:
            db = await aiosqlite.connect('bot_data.db')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS admins (
                    user_id INTEGER PRIMARY KEY
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS scammers (
                    user_id INTEGER PRIMARY KEY,
                    proof_link TEXT
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS guarantors (
                    user_id INTEGER PRIMARY KEY
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS premium_users (
                    user_id INTEGER PRIMARY KEY,
                    channel_link TEXT,
                    photo_link TEXT
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS search_logs (
                    searcher_id INTEGER,
                    target_id INTEGER,
                    PRIMARY KEY (searcher_id, target_id)
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS user_stats (
                    user_id INTEGER PRIMARY KEY,
                    scammers_reported INTEGER DEFAULT 0,
                    balance INTEGER DEFAULT 0
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS trusted_users (
                    user_id INTEGER PRIMARY KEY,
                    guarantor_id INTEGER
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS trainees (
                    user_id INTEGER PRIMARY KEY,
                    admin_id INTEGER
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS pending_scam_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trainee_id INTEGER,
                    target TEXT,
                    proof_link TEXT
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS bot_groups (
                    chat_id INTEGER PRIMARY KEY
                )
            ''')
            await db.commit()
            logging.info("База данных успешно инициализирована.")
        except Exception as e:
            logging.error(f"Ошибка при инициализации базы данных: {e}")
            sys.exit(1)

    async def get_user_info(client, target):
        user_id = None
        user = None
        if target.isdigit():
            user_id = int(target)
            try:
                user = await client.get_users(user_id)
            except PeerIdInvalid:
                user = None
        else:
            if target.startswith('@'):
                target = target[1:]
            user = await client.get_users(target)
            user_id = user.id

        return user, user_id

    async def can_restrict_members(chat):
        member = await app.get_chat_member(chat.id, 'me')
        if member.status == enums.ChatMemberStatus.OWNER:
            return True
        elif member.status == enums.ChatMemberStatus.ADMINISTRATOR:
            return member.privileges.can_restrict_members
        else:
            return False

    # Обработчики команд и функций

    @app.on_message(filters.command("start"))
    async def start_command(client, message: Message):
        logging.info(f"Получена команда /start от пользователя {message.from_user.id}")
        keyboard = ReplyKeyboardMarkup(
            [
                ["❓Мой Профиль", "📊Статистика"],
                ["💓Наши Гаранты", "👀Премиум"],
                ["🤬Слить скамера", "🙌Частые вопросы"],
                ["🎁Новогодние кейсы"]  # Добавлена новая кнопка
            ],
            resize_keyboard=True
        )
        await message.reply(
            "Мы - туалеты, Глобальная АнтиСкам База нового поколения:\n\n"
            "🤓 **Проверим человека на скам**\n"
            "🤠 **Найдём проверенного гаранта**\n"
            "🤕 **Поможем слить скаммера**\n\n"
            "ℹ️ Используйте кнопки ниже для диалога с ботом",
            parse_mode=enums.ParseMode.MARKDOWN,
            reply_markup=keyboard
        )

    # ... (остальной код остается без изменений до функций проверки пользователя)

    @app.on_message(filters.regex(r'^чек(?:\s*(.*))?$', flags=re.IGNORECASE))
    async def check_user(client, message: Message):
        if not await is_button_click_allowed(message.from_user.id):
            temp_msg = await message.reply("Нельзя нажимать так часто!")
            await asyncio.sleep(3)
            await temp_msg.delete()
            return
        logging.info(f"Получена команда чек от пользователя {message.from_user.id}")
        args_match = re.match(r'^чек(?:\s*(.*))?$', message.text.strip(), flags=re.IGNORECASE)
        args = args_match.group(1) if args_match else None

        if args is None or args.lower() in ['ми', 'я']:
            # Проверяем самого пользователя
            user_id = message.from_user.id
            user = message.from_user
        elif message.reply_to_message:
            # Проверяем пользователя, на сообщение которого ответили
            user = message.reply_to_message.from_user
            user_id = user.id
        else:
            target = args.strip()
            # Отправляем сообщение о начале поиска
            searching_msg = await message.reply("🔎 Идет поиск по базе...")

            try:
                user, user_id = await get_user_info(client, target)

                # Проверяем, является ли объект пользователем
                if user and not isinstance(user, User):
                    await message.reply("Вы можете проверять только пользователей.")
                    return

                # Если user_id все еще неизвестен, используем введенный айди
                if user_id is None:
                    await message.reply("Не удалось определить user_id пользователя.")
                    return

            except Exception as e:
                logging.error(f"Ошибка при обработке команды чек: {e}")
                await message.reply(f"Не удалось получить информацию о пользователе: {e}")
                return

            finally:
                # Удаляем сообщение о начале поиска
                await searching_msg.delete()

        # Продолжаем обработку с имеющимися user и user_id
        # Получаем и форматируем имя пользователя
        if user:
            nickname = ' '.join(filter(None, [user.first_name, user.last_name]))
            nickname = nickname.replace('_', '\\_')  # Экранируем подчеркивания для Markdown
        else:
            nickname = "Неизвестно"

        # Обновляем счетчик поисков в базе данных
        if message.from_user.id != user_id:
            async with db.execute('SELECT 1 FROM search_logs WHERE searcher_id = ? AND target_id = ?', (message.from_user.id, user_id)) as cursor:
                exists = await cursor.fetchone()
            if not exists:
                await db.execute('INSERT INTO search_logs (searcher_id, target_id) VALUES (?, ?)', (message.from_user.id, user_id))
                await db.commit()

        # Получаем количество уникальных поисков
        async with db.execute('SELECT COUNT(DISTINCT searcher_id) FROM search_logs WHERE target_id = ?', (user_id,)) as cursor:
            result = await cursor.fetchone()
        if result:
            search_count = result[0]
        else:
            search_count = 0

        # Получаем количество слитых скамеров
        async with db.execute('SELECT scammers_reported FROM user_stats WHERE user_id = ?', (user_id,)) as cursor:
            result = await cursor.fetchone()
        if result:
            scammers_reported = result[0]
        else:
            scammers_reported = 0

        # Проверяем роли пользователя
        is_owner_user = user_id == OWNER_ID
        is_admin_user = await is_admin(user_id)
        is_trainee_user = await is_trainee(user_id)

        additional_info = ""
        reputation_type = "Нет в базе"
        reputation = reputation_type
        image_url = IMAGE_URLS.get(reputation_type)

        if is_owner_user:
            reputation_type = "Владелец"
            reputation = reputation_type
            image_url = IMAGE_URLS.get(reputation_type)
        elif is_admin_user:
            reputation_type = "Админ"
            reputation = reputation_type
            image_url = IMAGE_URLS.get(reputation_type)
        elif is_trainee_user:
            # Получаем admin_id из таблицы trainees
            async with db.execute('SELECT admin_id FROM trainees WHERE user_id = ?', (user_id,)) as cursor:
                result = await cursor.fetchone()
            if result:
                admin_id = result[0]
                # Получаем имя администратора
                admin_user = await client.get_users(admin_id)
                admin_name = ' '.join(filter(None, [admin_user.first_name, admin_user.last_name]))
                reputation_type = "Стажер"
                reputation = f"{reputation_type} {admin_name}"
            else:
                reputation_type = "Стажер"
                reputation = f"{reputation_type} Неизвестен"
            image_url = IMAGE_URLS.get(reputation_type)

        # Дополнительные проверки (гаранты, скамеры, премиум и т.д.)
        async with db.execute('SELECT channel_link, photo_link FROM premium_users WHERE user_id = ?', (user_id,)) as cursor:
            premium_data = await cursor.fetchone()

        async with db.execute('SELECT guarantor_id FROM trusted_users WHERE user_id = ?', (user_id,)) as cursor:
            trusted_data = await cursor.fetchone()

        async with db.execute('SELECT 1 FROM guarantors WHERE user_id = ?', (user_id,)) as cursor:
            guarantor_data = await cursor.fetchone()

        async with db.execute('SELECT proof_link FROM scammers WHERE user_id = ?', (user_id,)) as cursor:
            scammer_data = await cursor.fetchone()

        if guarantor_data:
            reputation_type = "Гарант"
            reputation = reputation_type
            image_url = IMAGE_URLS.get(reputation_type)
        elif trusted_data:
            guarantor_id = trusted_data[0]
            guarantor = await client.get_users(guarantor_id)
            guarantor_nickname = ' '.join(filter(None, [guarantor.first_name, guarantor.last_name]))
            reputation_type = "Проверен Гарантом"
            reputation = f"{reputation_type} {guarantor_nickname}"
            image_url = IMAGE_URLS.get(reputation_type)
        elif scammer_data:
            proof_link = scammer_data[0]
            reputation_type = "Скамер"
            reputation = reputation_type
            image_url = IMAGE_URLS.get(reputation_type)
            additional_info += f"""
📒 **Пруфы:** [Ссылка]({proof_link})
"""

        # Если пользователь премиум, добавляем информацию
        if premium_data:
            channel_link, photo_link = premium_data
            if channel_link:
                additional_info += f"""
🎭 **Канал:** {channel_link}
"""
            if photo_link:
                image_url = photo_link  # Используем пользовательское фото

        # Создаем клавиатуру с кнопкой ПРОФИЛЬ
        if user:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("ПРОФИЛЬ", url=f"tg://user?id={user_id}")]
            ])
        else:
            keyboard = None  # Не можем дать ссылку на профиль

        # Отправляем сообщение с результатами поиска
        await client.send_photo(
            chat_id=message.chat.id,
            photo=image_url,
            caption=f"""🕵️ **Результаты по поиску:** {nickname}

🆔 Айди : `{user_id}`

🔁 **Репутация:** {reputation}

🚮 **Слито скамеров:** {scammers_reported}

🔎 **Искали в базе:** {search_count} раз
{additional_info}
""",
            reply_markup=keyboard,
            parse_mode=enums.ParseMode.MARKDOWN
        )

    @app.on_message(filters.text & filters.regex(r'^❓Мой Профиль$'))
    async def my_profile(client, message: Message):
        if not await is_button_click_allowed(message.from_user.id):
            temp_msg = await message.reply("Нельзя нажимать так часто!")
            await asyncio.sleep(3)
            await temp_msg.delete()
            return
        logging.info(f"Пользователь {message.from_user.id} запросил свой профиль")
        user = message.from_user

        nickname = ' '.join(filter(None, [user.first_name, user.last_name]))
        nickname = nickname.replace('_', '\\_')  # Экранируем подчеркивания для Markdown
        user_id = user.id

        # Получаем количество уникальных поисков
        async with db.execute('SELECT COUNT(DISTINCT searcher_id) FROM search_logs WHERE target_id = ?', (user_id,)) as cursor:
            result = await cursor.fetchone()
        if result:
            search_count = result[0]
        else:
            search_count = 0

        # Получаем количество слитых скамеров
        async with db.execute('SELECT scammers_reported FROM user_stats WHERE user_id = ?', (user_id,)) as cursor:
            result = await cursor.fetchone()
        if result:
            scammers_reported = result[0]
        else:
            scammers_reported = 0

        # Проверяем роли пользователя
        is_owner_user = user_id == OWNER_ID
        is_admin_user = await is_admin(user_id)
        is_trainee_user = await is_trainee(user_id)

        additional_info = ""
        reputation_type = "Нет в базе"
        reputation = reputation_type
        image_url = IMAGE_URLS.get(reputation_type)

        if is_owner_user:
            reputation_type = "Владелец"
            reputation = reputation_type
            image_url = IMAGE_URLS.get(reputation_type)
        elif is_admin_user:
            reputation_type = "Админ"
            reputation = reputation_type
            image_url = IMAGE_URLS.get(reputation_type)
        elif is_trainee_user:
            # Получаем admin_id из таблицы trainees
            async with db.execute('SELECT admin_id FROM trainees WHERE user_id = ?', (user_id,)) as cursor:
                result = await cursor.fetchone()
            if result:
                admin_id = result[0]
                # Получаем имя администратора
                admin_user = await client.get_users(admin_id)
                admin_name = ' '.join(filter(None, [admin_user.first_name, admin_user.last_name]))
                reputation_type = "Стажер"
                reputation = f"{reputation_type} {admin_name}"
            else:
                reputation_type = "Стажер"
                reputation = f"{reputation_type} Неизвестен"
            image_url = IMAGE_URLS.get(reputation_type)

        # Дополнительные проверки (гаранты, скамеры, премиум и т.д.)
        async with db.execute('SELECT channel_link, photo_link FROM premium_users WHERE user_id = ?', (user_id,)) as cursor:
            premium_data = await cursor.fetchone()

        async with db.execute('SELECT guarantor_id FROM trusted_users WHERE user_id = ?', (user_id,)) as cursor:
            trusted_data = await cursor.fetchone()

        async with db.execute('SELECT 1 FROM guarantors WHERE user_id = ?', (user_id,)) as cursor:
            guarantor_data = await cursor.fetchone()

        async with db.execute('SELECT proof_link FROM scammers WHERE user_id = ?', (user_id,)) as cursor:
            scammer_data = await cursor.fetchone()

        if guarantor_data:
            reputation_type = "Гарант"
            reputation = reputation_type
            image_url = IMAGE_URLS.get(reputation_type)
        elif trusted_data:
            guarantor_id = trusted_data[0]
            guarantor = await client.get_users(guarantor_id)
            guarantor_nickname = ' '.join(filter(None, [guarantor.first_name, guarantor.last_name]))
            reputation_type = "Проверен Гарантом"
            reputation = f"{reputation_type} {guarantor_nickname}"
            image_url = IMAGE_URLS.get(reputation_type)
        elif scammer_data:
            proof_link = scammer_data[0]
            reputation_type = "Скамер"
            reputation = reputation_type
            image_url = IMAGE_URLS.get(reputation_type)
            additional_info += f"""
📒 **Пруфы:** [Ссылка]({proof_link})
"""

        # Если пользователь премиум, добавляем информацию
        if premium_data:
            channel_link, photo_link = premium_data
            if channel_link:
                additional_info += f"""
🎭 **Канал:** {channel_link}
"""
            if photo_link:
                image_url = photo_link  # Используем пользовательское фото

        # Создаем клавиатуру с кнопкой ПРОФИЛЬ
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("ПРОФИЛЬ", url=f"tg://user?id={user_id}")]
        ])

        # Отправляем сообщение с результатами
        await client.send_photo(
            chat_id=message.chat.id,
            photo=image_url,
            caption=f"""🕵️ **Результаты по поиску:** {nickname}

🆔 Айди: `{user_id}`

🔁 **Репутация:** {reputation}

🚮 **Слито скамеров:** {scammers_reported}

🔎 **Искали в базе:** {search_count} раз
{additional_info}
""",
            reply_markup=keyboard,
            parse_mode=enums.ParseMode.MARKDOWN
        )
    

    @app.on_message(filters.text & filters.regex(r'^🎁Новогодние кейсы$'))
    async def new_year_cases_handler(client, message: Message):
        if not await is_button_click_allowed(message.from_user.id):
            temp_msg = await message.reply("Нельзя нажимать так часто!")
            await asyncio.sleep(3)
            await temp_msg.delete()
            return
        logging.info(f"Пользователь {message.from_user.id} запросил Новогодние кейсы")

        text = (
            "🎁 **Новогодние кейсы** 🎁\n\n"
            "Мы добавили новогодние кейсы, вы можете купить за них кейсы, из которых может выпасть:\n\n"
            "• 🎉 **Премиум** - 8%\n"
            "• 🛡️ **Траст** - 4% (от гаранта AquaSeledka)\n"
            "• ❌ **Ничего** - 75%\n"
            "• 🕵️‍♂️ **Ручение от @Aqua_Seledka (на 500₽)** - шанс 1%\n"
            "• 🕵️‍♂️ **Ручение от @Aqua_Seledka (на 1000₽)** - шанс 0.09%\n\n"
            "Вы можете их купить за новогодние сладости, а их получить за слив скамеров. Напишите `/balance`, чтобы узнать, сколько у вас в балансе."
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎗Купить за сладости", callback_data="buy_candy_case")]
        ])

        await message.reply(
            text,
            reply_markup=keyboard,
            parse_mode=enums.ParseMode.MARKDOWN
        )

    # Обработчик кнопки "🎗Купить за сладости"
    @app.on_callback_query(filters.regex(r'^buy_candy_case$'))
    async def buy_candy_case_callback(client, callback_query: CallbackQuery):
        user_id = callback_query.from_user.id

        # Получаем баланс пользователя
        async with db.execute('SELECT balance FROM user_stats WHERE user_id = ?', (user_id,)) as cursor:
            result = await cursor.fetchone()
        balance = result[0] if result else 0

        if balance < 25:
            await callback_query.answer("У вас недостаточно сладостей для покупки кейса. Вам нужно минимум 25 сладостей.", show_alert=True)
            return

        # Вычитаем 25 сладостей
        await db.execute('UPDATE user_stats SET balance = balance - 25 WHERE user_id = ?', (user_id,))
        await db.commit()

        # Отправляем сообщение о начале открытия кейса
        opening_msg = await callback_query.message.reply("🔄 **Идет открытие кейса...**\n🟩🟩🟩🟩🟩🟩🟩🟩 0%")
        await callback_query.answer()

        # Симулируем прогресс открытия кейса
        for progress in range(10, 110, 10):
            await asyncio.sleep(1)  # Каждая секунда увеличивает прогресс на 10%
            progress_bar = "🟩" * (progress // 10) + "🟦" * (10 - progress // 10)
            await opening_msg.edit(f"🔄 **Идет открытие кейса...**\n{progress_bar} {progress}%")

        # Определяем результат выпадения
        outcome = random.choices(
            population=[
                "Премиум",
                "Траст",
                "Ничего",
                "Ручение_500",
                "Ручение_1000"
            ],
            weights=[8, 4, 75, 1, 0.09],
            k=1
        )[0]

        # Обработка результата
        if outcome == "Премиум":
            await db.execute('INSERT OR IGNORE INTO premium_users (user_id) VALUES (?)', (user_id,))
            await db.commit()
            result_text = "🎉 Поздравляем! Вам выпал **Премиум** статус! Теперь у вас есть доступ к эксклюзивным функциям."
        elif outcome == "Траст":
            # Предполагается, что у вас есть механизм добавления траста
            # Замените 'AquaSeledka_user_id' на реальный user_id
            AQUASELEDKA_USER_ID = 123456789  # Замените на реальный ID
            await db.execute('INSERT OR IGNORE INTO trusted_users (user_id, guarantor_id) VALUES (?, ?)', (user_id, AQUASELEDKA_USER_ID))
            await db.commit()
            result_text = "🛡️ Поздравляем! Вам выпал **Траст** статус от гаранта AquaSeledka."
        elif outcome == "Ничего":
            result_text = "❌ К сожалению, вам ничего не выпало. Попробуйте снова!"
        elif outcome == "Ручение_500":
            result_text = "🕵️‍♂️ **Ручение от @Aqua_Seledka на 500₽**. AquaSeledka ручается за вас!"
            # Дополнительная логика при необходимости
        elif outcome == "Ручение_1000":
            result_text = "🕵️‍♂️ **Ручение от @Aqua_Seledka на 1000₽**. AquaSeledka ручается за вас!"
            # Дополнительная логика при необходимости

        await opening_msg.edit(f"✅ **Кейс открыт!**\n\n{result_text}")

    # Обработчик команды /balance
    @app.on_message(filters.command("balance"))
    async def balance_command(client, message: Message):
        user_id = message.from_user.id

        # Получаем баланс пользователя
        async with db.execute('SELECT balance FROM user_stats WHERE user_id = ?', (user_id,)) as cursor:
            result = await cursor.fetchone()
        balance = result[0] if result else 0

        await message.reply(f"💰 **Ваш баланс:** {balance} 🍬")

    @app.on_message(filters.command('addcon'))
    async def add_con_command(client, message: Message):
        if message.from_user.id != OWNER_ID:
            return await message.reply("Эта команда доступна только владельцу бота.")

        # Извлекаем количество монет и user_id или username
        try:
            parts = message.text.split()
            coins = int(parts[1])
            target = parts[2]
        except (IndexError, ValueError):
            return await message.reply("Неверный формат команды. Используйте: /addcon <количество монет> <user_id или @username>")

        user, user_id = await get_user_info(client, target)
        if user is None:
            return await message.reply("Пользователь не найден.")

        # Выдаем монеты пользователю
        await db.execute('INSERT OR IGNORE INTO user_stats (user_id) VALUES (?)', (user_id,))
        await db.execute('UPDATE user_stats SET balance = balance + ? WHERE user_id = ?', (coins, user_id))
        await db.commit()

        await client.send_message(user_id, f"Тебе выданы {coins} монет! Теперь у тебя {coins} на балансе.")
        await message.reply(f"Выдали {coins} монет пользователю {user.username if user.username else user.first_name}.")

    @app.on_message(filters.text & filters.regex(r'^🙌Частые вопросы$'))
    async def faq_handler(client, message: Message):
        if not await is_button_click_allowed(message.from_user.id):
            temp_msg = await message.reply("Нельзя нажимать так часто!")
            await asyncio.sleep(3)
            await temp_msg.delete()
            return
        logging.info(f"Пользователь {message.from_user.id} запросил Частые вопросы")

        text = "Ответы на Частые Вопросы"

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Кто такой гарант", url="https://telegra.ph/Kto-takoj-Garant-09-20")],
            [InlineKeyboardButton("Как найти гаранта", url="https://telegra.ph/kak-najti-garanta-11-23")],
            [InlineKeyboardButton("Как стать гарантом", url="https://telegra.ph/kak-stat-garantom-11-23")],
            [InlineKeyboardButton("Можно ли купить снятие с базы", url="https://telegra.ph/snyatie-za-dengi-11-23")]
        ])

        await message.reply(text, reply_markup=keyboard)

    @app.on_message(filters.regex(r'^\+спасибо') & filters.reply)
    async def thank_you_command(client, message: Message):
        logging.info(f"Получена команда +спасибо от пользователя {message.from_user.id}")

        if not message.reply_to_message:
            await message.reply("Эта команда должна быть ответом на сообщение пользователя.")
            return

        target_user = message.reply_to_message.from_user
        target_user_id = target_user.id

        # Обновляем счетчик слитых скамеров и баланс для пользователя
        await db.execute('''
            INSERT INTO user_stats (user_id, scammers_reported, balance)
            VALUES (?, 1, 1)
            ON CONFLICT(user_id)
            DO UPDATE SET scammers_reported = scammers_reported + 1,
                          balance = balance + 1
        ''', (target_user_id,))
        await db.commit()

        await message.reply(f"Пользователю {target_user.mention} добавлено 1 к счетчику слитых скамеров и 1 🍬 в баланс.")

    @app.on_message(filters.command("unadmin"))
    async def unadmin_command(client, message: Message):
        logging.info(f"Получена команда /unadmin от пользователя {message.from_user.id}")
        if not is_owner(message.from_user.id):
            await message.reply("У вас нет прав для использования этой команды.")
            return

        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.reply("Использование: /unadmin <айди или юзернейм>")
            return

        target = args[1]

        try:
            user, user_id = await get_user_info(client, target)

            if user_id is None:
                await message.reply("Не удалось определить user_id пользователя.")
                return

            # Удаляем пользователя из администраторов
            await db.execute('DELETE FROM admins WHERE user_id = ?', (user_id,))
            await db.commit()

            await message.reply(f"Администраторские права пользователя {user_id} удалены.")

        except Exception as e:
            logging.error(f"Ошибка при обработке команды /unadmin: {e}")
            await message.reply(f"Не удалось удалить администратора: {e}")

    # Команда /untrust
    @app.on_message(filters.command("untrust"))
    async def untrust_command(client, message: Message):
        logging.info(f"Получена команда /untrust от пользователя {message.from_user.id}")
        if not is_owner(message.from_user.id):
            await message.reply("У вас нет прав для использования этой команды.")
            return

        if not message.reply_to_message:
            await message.reply("Команда должна быть ответом на сообщение пользователя.")
            return

        target_user = message.reply_to_message.from_user
        target_user_id = target_user.id

        # Удаляем пользователя из trusted_users
        await db.execute('DELETE FROM trusted_users WHERE user_id = ?', (target_user_id,))
        await db.commit()

        await message.reply(f"Статус 'Проверен гарантом' у пользователя {target_user_id} удален.")

    # Команда /ungarant
    @app.on_message(filters.command("ungarant"))
    async def unguarantor_command(client, message: Message):
        logging.info(f"Получена команда /ungarant от пользователя {message.from_user.id}")
        if not is_owner(message.from_user.id):
            await message.reply("У вас нет прав для использования этой команды.")
            return

        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.reply("Использование: /ungarant <айди или юзернейм>")
            return

        target = args[1]

        try:
            user, user_id = await get_user_info(client, target)

            if user_id is None:
                await message.reply("Не удалось определить user_id пользователя.")
                return

            # Удаляем пользователя из гарантов
            await db.execute('DELETE FROM guarantors WHERE user_id = ?', (user_id,))
            await db.commit()

            await message.reply(f"Статус гаранта у пользователя {user_id} удален.")

        except Exception as e:
            logging.error(f"Ошибка при обработке команды /ungarant: {e}")
            await message.reply(f"Не удалось удалить гаранта: {e}")

    # Команда /unscam
    @app.on_message(filters.command("unscam"))
    async def unscam_command(client, message: Message):
        logging.info(f"Получена команда /unscam от пользователя {message.from_user.id}")
        if not is_owner(message.from_user.id):
            await message.reply("У вас нет прав для использования этой команды.")
            return

        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.reply("Использование: /unscam <айди или юзернейм>")
            return

        target = args[1]

        try:
            user, user_id = await get_user_info(client, target)

            if user_id is None:
                await message.reply("Не удалось определить user_id пользователя.")
                return

            # Удаляем пользователя из скамеров
            await db.execute('DELETE FROM scammers WHERE user_id = ?', (user_id,))
            await db.commit()

            await message.reply(f"Статус скамер у пользователя {user_id} удален.")

        except Exception as e:
            logging.error(f"Ошибка при обработке команды /unscam: {e}")
            await message.reply(f"Не удалось удалить скамера: {e}")

    # Команда /анстажер
    @app.on_message(filters.command("анстажер"))
    async def untrainee_command(client, message: Message):
        logging.info(f"Получена команда /анстажер от пользователя {message.from_user.id}")
        if not is_owner(message.from_user.id):
            await message.reply("У вас нет прав для использования этой команды.")
            return

        if not message.reply_to_message:
            await message.reply("Команда должна быть ответом на сообщение пользователя.")
            return

        target_user = message.reply_to_message.from_user
        target_user_id = target_user.id

        # Удаляем пользователя из стажеров
        await db.execute('DELETE FROM trainees WHERE user_id = ?', (target_user_id,))
        await db.commit()

        await message.reply(f"Статус стажера у пользователя {target_user_id} удален.")

    @app.on_message(filters.text & filters.regex(r'^👀Премиум$'))
    async def premium_info(client, message: Message):
        if not await is_button_click_allowed(message.from_user.id):
            temp_msg = await message.reply("Нельзя нажимать так часто!")
            await asyncio.sleep(3)
            await temp_msg.delete()
            return
        logging.info(f"Пользователь {message.from_user.id} запросил информацию о премиуме")

        text = """Откройте уникальные возможности:

• Менять фото в профиле (/setphoto)
• Поставить ссылку на свой канал в профиле (/setchannel)
• 100 доступных проверок в день

Все эти фишки входят в ELITE Premium."""

        photo_url = 'https://ibb.co/mXySPM2'  # Прямая ссылка на изображение

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Как купить премиум", callback_data="buy_premium")]
        ])

        await client.send_photo(
            chat_id=message.chat.id,
            photo=photo_url,
            caption=text,
            reply_markup=keyboard,
            parse_mode=enums.ParseMode.MARKDOWN
        )

    @app.on_callback_query(filters.regex(r'^buy_premium$'))
    async def buy_premium_handler(client, callback_query: CallbackQuery):
        logging.info(f"Пользователь {callback_query.from_user.id} запросил информацию о покупке премиума")

        text = """Все Тарифы на покупку:

1. 200 рублей - 1 месяц!

2. 500 рублей - 3 месяца.

3. 800₽ - 6 месяцев.

4. 1200₽ - год

Реквизиты:

блуп не сказал

За другими банками или в других валютах таких как - Тенге, Гривны, Рубли, Сомы, Лиры, И еще многие валюты. В лс - @bluptop

После оплаты скиньте в лс чека где отчётливо видно перевод средств на карту продавца. Если чек подтвердиться, то в течении часа модераторы выдадут вам премиум.

Поддержка - @bluptop"""

        await callback_query.message.reply(text)
        await callback_query.answer()

   

    @app.on_message(filters.text & filters.regex(r'^❓Мой Профиль$'))
    async def my_profile(client, message: Message):
        if not await is_button_click_allowed(message.from_user.id):
            temp_msg = await message.reply("Нельзя нажимать так часто!")
            await asyncio.sleep(3)
            await temp_msg.delete()
            return
        logging.info(f"Пользователь {message.from_user.id} запросил свой профиль")
        user = message.from_user

        nickname = ' '.join(filter(None, [user.first_name, user.last_name]))
        nickname = nickname.replace('_', '\\_')  # Экранируем подчеркивания для Markdown
        user_id = user.id

        # Получаем количество уникальных поисков
        async with db.execute('SELECT COUNT(DISTINCT searcher_id) FROM search_logs WHERE target_id = ?', (user_id,)) as cursor:
            result = await cursor.fetchone()
        if result:
            search_count = result[0]
        else:
            search_count = 0

        # Получаем количество слитых скамеров
        async with db.execute('SELECT scammers_reported FROM user_stats WHERE user_id = ?', (user_id,)) as cursor:
            result = await cursor.fetchone()
        if result:
            scammers_reported = result[0]
        else:
            scammers_reported = 0

        # Проверяем роли пользователя
        is_owner_user = user_id == OWNER_ID
        is_admin_user = await is_admin(user_id)
        is_trainee_user = await is_trainee(user_id)

        additional_info = ""
        reputation = "Нет в базе"
        image_url = "https://ibb.co/mXySPM2"

        if is_owner_user:
            reputation = "Владелец"
            image_url = "https://ibb.co/mXySPM2"
        elif is_admin_user:
            reputation = "Админ"
            image_url = "https://ibb.co/mXySPM2"
        elif is_trainee_user:
            # Получаем admin_id из таблицы trainees
            async with db.execute('SELECT admin_id FROM trainees WHERE user_id = ?', (user_id,)) as cursor:
                result = await cursor.fetchone()
            if result:
                admin_id = result[0]
                # Получаем имя администратора
                admin_user = await client.get_users(admin_id)
                admin_name = ' '.join(filter(None, [admin_user.first_name, admin_user.last_name]))
                reputation = f"Стажер {admin_name}"
            else:
                reputation = "Стажер Неизвестен"
            image_url = "https://ibb.co/s9zjWWW"

        # Дополнительные проверки (гаранты, скамеры, премиум и т.д.)
        async with db.execute('SELECT channel_link, photo_link FROM premium_users WHERE user_id = ?', (user_id,)) as cursor:
            premium_data = await cursor.fetchone()

        async with db.execute('SELECT guarantor_id FROM trusted_users WHERE user_id = ?', (user_id,)) as cursor:
            trusted_data = await cursor.fetchone()

        async with db.execute('SELECT 1 FROM guarantors WHERE user_id = ?', (user_id,)) as cursor:
            guarantor_data = await cursor.fetchone()

        async with db.execute('SELECT proof_link FROM scammers WHERE user_id = ?', (user_id,)) as cursor:
            scammer_data = await cursor.fetchone()

        if guarantor_data:
            reputation = "Гарант"
        elif trusted_data:
            guarantor_id = trusted_data[0]
            guarantor = await client.get_users(guarantor_id)
            guarantor_nickname = ' '.join(filter(None, [guarantor.first_name, guarantor.last_name]))
            reputation = f"Проверен Гарантом {guarantor_nickname}"
        elif scammer_data:
            proof_link = scammer_data[0]
            reputation = "Скамер"
            additional_info += f"""
📒 **Пруфы:** [Ссылка]({proof_link})
"""

        # Если пользователь премиум, добавляем информацию
        if premium_data:
            channel_link, photo_link = premium_data
            if channel_link:
                additional_info += f"""
🎭 **Канал:** {channel_link}
"""
            if photo_link:
                image_url = photo_link  # Используем пользовательское фото

        # Создаем клавиатуру с кнопкой ПРОФИЛЬ
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("ПРОФИЛЬ", url=f"tg://user?id={user_id}")]
        ])

        # Отправляем сообщение с результатами
        await client.send_photo(
            chat_id=message.chat.id,
            photo=image_url,
            caption=f"""🕵️ **Результаты по поиску:** {nickname}

🆔 _Айди:_ {user_id}

🔁 **Репутация:** {reputation}

🚮 **Слито скамеров:** {scammers_reported}

🔎 **Искали в базе:** {search_count} раз
{additional_info}
""",
            reply_markup=keyboard,
            parse_mode=enums.ParseMode.MARKDOWN
        )

    @app.on_message(filters.text & filters.regex(r'^📊Статистика$') | filters.command("stats"))
    async def bot_stats(client, message: Message):
        if not await is_button_click_allowed(message.from_user.id):
            temp_msg = await message.reply("Нельзя нажимать так часто!")
            await asyncio.sleep(3)
            await temp_msg.delete()
            return
        logging.info(f"Пользователь {message.from_user.id} запросил статистику бота")

        user = message.from_user
        nickname = ' '.join(filter(None, [user.first_name, user.last_name]))
        nickname = nickname.replace('_', '\\_')  # Экранируем подчеркивания

        # Получаем количество скамеров в базе
        async with db.execute('SELECT COUNT(*) FROM scammers') as cursor:
            scammers_count = (await cursor.fetchone())[0]

        # Получаем количество пользователей бота
        async with db.execute('SELECT COUNT(DISTINCT user_id) FROM user_stats') as cursor:
            users_count = (await cursor.fetchone())[0]

        # Получаем количество админов
        async with db.execute('SELECT COUNT(*) FROM admins') as cursor:
            admins_count = (await cursor.fetchone())[0]

        # Получаем количество гарантов
        async with db.execute('SELECT COUNT(*) FROM guarantors') as cursor:
            guarantors_count = (await cursor.fetchone())[0]

        # Получаем количество проверенных пользователей
        async with db.execute('SELECT COUNT(*) FROM trusted_users') as cursor:
            trusted_users_count = (await cursor.fetchone())[0]

        # Получаем количество групп из базы данных
        async with db.execute('SELECT COUNT(*) FROM bot_groups') as cursor:
            group_count = (await cursor.fetchone())[0]

        # Формируем и отправляем сообщение с статистикой
        await message.reply(
            f"""{nickname}

🚫 **Скаммеров в базе:** {scammers_count}
👁️ **Пользователей бота:** {users_count}

⚖️ **Админов:** {admins_count}
💸 **Гарантов:** {guarantors_count}
🏆️ **Проверенных:** {trusted_users_count}

🎉 **Бот уже в {group_count} группах**
""",
            parse_mode=enums.ParseMode.MARKDOWN
        )

    @app.on_message(filters.text & filters.regex(r'^💓Наши Гаранты$'))
    async def our_guarantors(client, message: Message):
        if not await is_button_click_allowed(message.from_user.id):
            temp_msg = await message.reply("Нельзя нажимать так часто!")
            await asyncio.sleep(3)
            await temp_msg.delete()
            return
        logging.info(f"Пользователь {message.from_user.id} запросил список гарантов")

        # Получаем список гарантов
        async with db.execute('SELECT user_id FROM guarantors') as cursor:
            guarantors = await cursor.fetchall()

        if not guarantors:
            await message.reply("Список гарантов пуст.")
            return

        buttons = []
        for (guarantor_id,) in guarantors:
            try:
                guarantor = await client.get_users(guarantor_id)
                nickname = ' '.join(filter(None, [guarantor.first_name, guarantor.last_name]))
                buttons.append([InlineKeyboardButton(nickname, url=f"tg://user?id={guarantor_id}")])
            except Exception as e:
                logging.error(f"Не удалось получить информацию о гаранте {guarantor_id}: {e}")

        keyboard = InlineKeyboardMarkup(buttons)

        await message.reply("Наши Гаранты:", reply_markup=keyboard)

    @app.on_message(filters.text & filters.regex(r'^🤬Слить скамера$'))
    async def report_scammer(client, message: Message):
        if not await is_button_click_allowed(message.from_user.id):
            temp_msg = await message.reply("Нельзя нажимать так часто!")
            await asyncio.sleep(3)
            await temp_msg.delete()
            return
        logging.info(f"Пользователь {message.from_user.id} нажал на кнопку '🤬Слить скамера'")

        text = """😮‍💨 Если вы стали жертвой мошенников - жмите кнопку 'Написать жалобу'

👩‍💻 Вы будете направлены в чат с нашими волонтёрами, они разберутся в ситуации и занесут мошенника в базу. Это бесплатно"""

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Написать жалобу", url="https://t.me/Forgotbase")]
        ])

        await message.reply(text, reply_markup=keyboard)

    @app.on_message(filters.command("trust") & filters.reply)
    async def trust_command(client, message: Message):
        logging.info(f"Получена команда /trust от пользователя {message.from_user.id}")

        if not await is_guarantor(message.from_user.id):
            await message.reply("Эта команда доступна только гарантам.")
            return

        if not message.reply_to_message:
            await message.reply("Команда должна быть ответом на сообщение пользователя.")
            return

        target_user = message.reply_to_message.from_user
        target_user_id = target_user.id

        # Сохраняем проверенного пользователя в базе данных
        await db.execute('INSERT OR REPLACE INTO trusted_users (user_id, guarantor_id) VALUES (?, ?)', (target_user_id, message.from_user.id))
        await db.commit()

        guarantor_nickname = ' '.join(filter(None, [message.from_user.first_name, message.from_user.last_name]))

        await message.reply(f"Пользователь {target_user_id} помечен как 'Проверен Гарантом {guarantor_nickname}'.")

        # Уведомляем владельца
        await client.send_message(
            chat_id=OWNER_ID,
            text=f"Гарант {guarantor_nickname} ({message.from_user.id}) выдал /trust пользователю {target_user_id}."
        )

    # ------------------ Команда /стажер ------------------

    @app.on_message(filters.command("стажер") & filters.reply)
    async def trainee_command(client, message: Message):
        if not await is_admin(message.from_user.id):
            await message.reply("У вас нет прав для использования этой команды.")
            return

        if not message.reply_to_message:
            await message.reply("Команда должна быть ответом на сообщение пользователя.")
            return

        target_user = message.reply_to_message.from_user
        target_user_id = target_user.id

        # Проверяем, не является ли пользователь уже стажером
        if await is_trainee(target_user_id):
            await message.reply("Этот пользователь уже является стажером.")
            return

        # Сохраняем администратора, который назначает стажера
        admin_id = message.from_user.id
        await db.execute('INSERT OR IGNORE INTO trainees (user_id, admin_id) VALUES (?, ?)', (target_user_id, admin_id))
        await db.commit()

        await message.reply(f"Пользователь {target_user.mention} назначен стажером.")

        # Уведомляем стажера
        await client.send_message(
            chat_id=target_user_id,
            text=f"Вы назначены стажером администратором {message.from_user.mention}. Теперь вы можете использовать команду /скам для предложения добавления пользователей в базу скамеров."
        )

    # ------------------ Команда /скам ------------------

    @app.on_message(filters.command("скам"))
    async def scam_command(client, message: Message):
        logging.info(f"Получена команда /скам от пользователя {message.from_user.id}")

        if await is_admin(message.from_user.id):
            # Код для администраторов
            args = message.text.split(maxsplit=2)
            if len(args) < 3:
                await message.reply("Использование: /скам <айди или юзернейм> <ссылка на доказательства>")
                return

            target = args[1]
            proof_link = args[2]

            user, user_id = await get_user_info(client, target)

            # Проверяем, является ли объект пользователем
            if user and not isinstance(user, User):
                await message.reply("Вы можете добавлять в скамеры только пользователей.")
                return

            if user_id is None:
                await message.reply("Не удалось определить user_id пользователя.")
                return

            # Добавляем пользователя в список скамеров в базе данных
            await db.execute('INSERT OR REPLACE INTO scammers (user_id, proof_link) VALUES (?, ?)',
                             (user_id, proof_link))
            await db.commit()

            await message.reply(f"Пользователь {user_id} помечен как скамер.")

        elif await is_trainee(message.from_user.id):
            # Код для стажеров
            async with db.execute('SELECT admin_id FROM trainees WHERE user_id = ?', (message.from_user.id,)) as cursor:
                result = await cursor.fetchone()
            if result:
                admin_id = result[0]
                args = message.text.split(maxsplit=2)
                if len(args) < 3:
                    await message.reply("Использование: /скам <айди или юзернейм> <ссылка на доказательства>")
                    return
                target = args[1]
                proof_link = args[2]

                # Сохраняем запрос в таблицу pending_scam_requests
                await db.execute('INSERT INTO pending_scam_requests (trainee_id, target, proof_link) VALUES (?, ?, ?)',
                                 (message.from_user.id, target, proof_link))
                await db.commit()
                async with db.execute('SELECT last_insert_rowid()') as cursor:
                    request_id = (await cursor.fetchone())[0]

                # Отправляем сообщение админу
                trainee_nickname = message.from_user.mention
                await client.send_message(
                    chat_id=admin_id,
                    text=f"Стажер {trainee_nickname} хочет занести в базу пользователя {target}\nСсылка на пруф: {proof_link}",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("Одобрить", callback_data=f"approve_scam_{request_id}")],
                        [InlineKeyboardButton("Отказать", callback_data=f"reject_scam_{request_id}")]
                    ])
                )
                await message.reply("Ваш запрос отправлен администратору на рассмотрение.")
            else:
                await message.reply("Не удалось найти администратора, который вас назначил.")
        else:
            await message.reply("У вас нет прав для использования этой команды.")

    # Обработчик нажатия кнопки "Одобрить" для запроса стажера
    @app.on_callback_query(filters.regex(r'^approve_scam_(\d+)$'))
    async def approve_scam_callback(client, callback_query: CallbackQuery):
        request_id = int(callback_query.data.split('_')[-1])

        # Получаем данные запроса
        async with db.execute('SELECT trainee_id, target, proof_link FROM pending_scam_requests WHERE id = ?', (request_id,)) as cursor:
            result = await cursor.fetchone()
        if result:
            trainee_id, target, proof_link = result
            try:
                user, user_id = await get_user_info(client, target)

                if user and not isinstance(user, User):
                    await callback_query.message.reply("Вы можете добавлять в скамеры только пользователей.")
                    return

                if user_id is None:
                    await callback_query.message.reply("Не удалось определить user_id пользователя.")
                    return

                # Добавляем пользователя в базу скамеров
                await db.execute('INSERT OR REPLACE INTO scammers (user_id, proof_link) VALUES (?, ?)',
                                 (user_id, proof_link))
                await db.commit()

                await callback_query.answer("Пользователь добавлен в базу скамеров.")
                await callback_query.message.edit_text(f"Запрос от стажера одобрен. Пользователь {user_id} добавлен в базу скамеров.")

                # Уведомляем стажера
                await client.send_message(
                    chat_id=trainee_id,
                    text=f"Ваш запрос на добавление пользователя {target} в базу скамеров был одобрен."
                )

                # Удаляем запрос из pending_scam_requests
                await db.execute('DELETE FROM pending_scam_requests WHERE id = ?', (request_id,))
                await db.commit()

            except Exception as e:
                logging.error(f"Ошибка при обработке approve_scam_callback: {e}")
                await callback_query.answer(f"Ошибка: {e}")
        else:
            await callback_query.answer("Запрос не найден или уже обработан.")

    # Обработчик нажатия кнопки "Отклонить" для запроса стажера
    @app.on_callback_query(filters.regex(r'^reject_scam_(\d+)$'))
    async def reject_scam_callback(client, callback_query: CallbackQuery):
        request_id = int(callback_query.data.split('_')[-1])

        # Получаем данные запроса
        async with db.execute('SELECT trainee_id, target FROM pending_scam_requests WHERE id = ?', (request_id,)) as cursor:
            result = await cursor.fetchone()
        if result:
            trainee_id, target = result
            await callback_query.answer("Запрос отклонен.")
            await callback_query.message.edit_text(f"Запрос от стажера отклонен.")

            # Уведомляем стажера
            await client.send_message(
                chat_id=trainee_id,
                text=f"Ваш запрос на добавление пользователя {target} в базу скамеров был отклонен."
            )

            # Удаляем запрос из pending_scam_requests
            await db.execute('DELETE FROM pending_scam_requests WHERE id = ?', (request_id,))
            await db.commit()
        else:
            await callback_query.answer("Запрос не найден или уже обработан.")

    # ------------------ Команда /admin ------------------

    @app.on_message(filters.command("admin"))
    async def admin_command(client, message: Message):
        logging.info(f"Получена команда /admin от пользователя {message.from_user.id}")
        if not is_owner(message.from_user.id):
            await message.reply("У вас нет прав для использования этой команды.")
            return

        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.reply("Использование: /admin <айди или юзернейм>")
            return

        target = args[1]

        try:
            user_id = None
            user = None
            if target.isdigit():
                user_id = int(target)
                try:
                    user = await client.get_users(user_id)
                except PeerIdInvalid:
                    user = None
            else:
                if target.startswith('@'):
                    target = target[1:]
                user = await client.get_users(target)
                user_id = user.id

            # Проверяем, является ли объект пользователем
            if user and not isinstance(user, User):
                await message.reply("Вы можете добавлять в администраторы только пользователей.")
                return

            if user_id is None:
                await message.reply("Не удалось определить user_id пользователя.")
                return

            # Добавляем пользователя в список администраторов в базе данных
            await db.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (user_id,))
            await db.commit()

            await message.reply(f"Пользователь {user_id} добавлен в администраторы.")

        except Exception as e:
            logging.error(f"Ошибка при обработке команды /admin: {e}")
            await message.reply(f"Не удалось добавить администратора: {e}")

    # ------------------ Команда /premium ------------------

    @app.on_message(filters.command("premium"))
    async def premium_command(client, message: Message):
        logging.info(f"Получена команда /premium от пользователя {message.from_user.id}")
        if not is_owner(message.from_user.id):
            await message.reply("У вас нет прав для использования этой команды.")
            return

        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.reply("Использование: /premium <айди или юзернейм>")
            return

        target = args[1]

        try:
            user_id = None
            user = None
            if target.isdigit():
                user_id = int(target)
                try:
                    user = await client.get_users(user_id)
                except PeerIdInvalid:
                    user = None
            else:
                if target.startswith('@'):
                    target = target[1:]
                user = await client.get_users(target)
                user_id = user.id

            # Проверяем, является ли объект пользователем
            if user and not isinstance(user, User):
                await message.reply("Вы можете выдавать премиум только пользователям.")
                return

            if user_id is None:
                await message.reply("Не удалось определить user_id пользователя.")
                return

            # Добавляем пользователя в список премиум-пользователей в базе данных
            await db.execute('INSERT OR IGNORE INTO premium_users (user_id) VALUES (?)', (user_id,))
            await db.commit()

            await message.reply(f"Пользователю {user_id} выдан премиум-статус.")

        except Exception as e:
            logging.error(f"Ошибка при обработке команды /premium: {e}")
            await message.reply(f"Не удалось выдать премиум: {e}")

    # ------------------ Команда /setchannel ------------------

    @app.on_message(filters.command("setchannel"))
    async def set_channel(client, message: Message):
        logging.info(f"Получена команда /setchannel от пользователя {message.from_user.id}")

        if not await is_premium(message.from_user.id):
            await message.reply("Эта команда доступна только премиум-пользователям.")
            return

        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.reply("Использование: /setchannel <ссылка на канал>")
            return

        channel_link = args[1].strip()

        # Сохраняем ссылку на канал в базе данных
        await db.execute('UPDATE premium_users SET channel_link = ? WHERE user_id = ?', (channel_link, message.from_user.id))
        await db.commit()

        await message.reply("Ссылка на ваш канал успешно сохранена.")

    # ------------------ Команда /setphoto ------------------

    @app.on_message(filters.command("setphoto"))
    async def set_photo(client, message: Message):
        logging.info(f"Получена команда /setphoto от пользователя {message.from_user.id}")

        if not await is_premium(message.from_user.id):
            await message.reply("Эта команда доступна только премиум-пользователям.")
            return

        # Проверяем, не отправил ли пользователь фото вместо ссылки
        if message.photo:
            await message.reply("Нужно указать ссылку на картинку, а не отправлять фото. Туториал - https://telegra.ph/tutor-11-22-3")
            return

        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.reply("Использование: /setphoto <ссылка на фото>")
            return

        photo_link = args[1].strip()

        # Проверяем, что ссылка начинается с https://ibb.co/
        if not photo_link.startswith('https://ibb.co/'):
            await message.reply("Ссылка должна начинаться с https://ibb.co/. Туториал - https://telegra.ph/tutor-11-22-3")
            return

        # Сохраняем ссылку на фото в базе данных
        await db.execute('UPDATE premium_users SET photo_link = ? WHERE user_id = ?', (photo_link, message.from_user.id))
        await db.commit()

        await message.reply("Ссылка на ваше фото успешно сохранена.")

    # ------------------ Команда /гарант ------------------

    @app.on_message(filters.command("гарант"))
    async def guarantor_command(client, message: Message):
        logging.info(f"Получена команда /гарант от пользователя {message.from_user.id}")
        if not is_owner(message.from_user.id):
            await message.reply("У вас нет прав для использования этой команды.")
            return

        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.reply("Использование: /гарант <айди или юзернейм>")
            return

        target = args[1]

        try:
            user_id = None
            user = None
            if target.isdigit():
                user_id = int(target)
                try:
                    user = await client.get_users(user_id)
                except PeerIdInvalid:
                    user = None
            else:
                if target.startswith('@'):
                    target = target[1:]
                user = await client.get_users(target)
                user_id = user.id

            # Проверяем, является ли объект пользователем
            if user and not isinstance(user, User):
                await message.reply("Вы можете добавлять в гаранты только пользователей.")
                return

            if user_id is None:
                await message.reply("Не удалось определить user_id пользователя.")
                return

            # Добавляем пользователя в список гарантов в базе данных
            await db.execute('INSERT OR IGNORE INTO guarantors (user_id) VALUES (?)', (user_id,))
            await db.commit()

            await message.reply(f"Пользователь {user_id} добавлен в гаранты.")

        except Exception as e:
            logging.error(f"Ошибка при обработке команды /гарант: {e}")
            await message.reply(f"Не удалось добавить гаранта: {e}")

    # ------------------ Команды модерации ------------------

    @app.on_message(filters.command("оффтоп") & filters.reply)
    async def offtop_command(client, message: Message):
        if not await is_admin(message.from_user.id):
            await message.reply("У вас нет прав для использования этой команды.")
            return

        if not message.reply_to_message:
            await message.reply("Команда должна быть ответом на сообщение пользователя.")
            return

        if not await can_restrict_members(message.chat):
            await message.reply("У меня нет прав для ограничения пользователей.")
            return

        target_user = message.reply_to_message.from_user
        await message.chat.restrict_member(
            target_user.id,
            ChatPermissions(),
            until_date=message.date + timedelta(minutes=30)
        )
        await message.reply_to_message.delete()
        await message.reply(f"{target_user.first_name} выдан мут на 30 минут\nПричина: Оффтоп\n\nОбщайтесь в группе для оффтопа @It_s_bloop")

    @app.on_message(filters.command("мут") & filters.reply)
    async def mute_command(client, message: Message):
        if not await is_admin(message.from_user.id):
            await message.reply("У вас нет прав для использования этой команды.")
            return

        if not message.reply_to_message:
            await message.reply("Команда должна быть ответом на сообщение пользователя.")
            return

        if not await can_restrict_members(message.chat):
            await message.reply("У меня нет прав для ограничения пользователей.")
            return

        target_user = message.reply_to_message.from_user
        await message.chat.restrict_member(
            target_user.id,
            ChatPermissions(),
            until_date=message.date + timedelta(minutes=30)
        )
        await message.reply_to_message.delete()
        await message.reply(f"{target_user.first_name} выдан мут на 30 минут")

    @app.on_message(filters.command("анмут") & filters.reply)
    async def unmute_command(client, message: Message):
        if not await is_admin(message.from_user.id):
            await message.reply("У вас нет прав для использования этой команды.")
            return

        if not await can_restrict_members(message.chat):
            await message.reply("У меня нет прав для ограничения пользователей.")
            return

        target_user = message.reply_to_message.from_user
        await message.chat.unban_member(target_user.id)
        await message.reply(f"{target_user.first_name} размучен.")

    @app.on_message(filters.command("бан") & filters.reply)
    async def ban_command(client, message: Message):
        if not await is_admin(message.from_user.id):
            await message.reply("У вас нет прав для использования этой команды.")
            return

        if not await can_restrict_members(message.chat):
            await message.reply("У меня нет прав для ограничения пользователей.")
            return

        target_user = message.reply_to_message.from_user
        await message.chat.ban_member(target_user.id)
        await message.reply(f"{target_user.first_name} забанен.")

    @app.on_message(filters.command("анбан") & filters.reply)
    async def unban_command(client, message: Message):
        if not await is_admin(message.from_user.id):
            await message.reply("У вас нет прав для использования этой команды.")
            return

        if not await can_restrict_members(message.chat):
            await message.reply("У меня нет прав для ограничения пользователей.")
            return

        target_user = message.reply_to_message.from_user
        await message.chat.unban_member(target_user.id)
        await message.reply(f"{target_user.first_name} разбанен.")

    # ------------------ Обработчик новых участников ------------------

    @app.on_message(filters.new_chat_members)
    async def welcome_new_member(client, message: Message):
        for new_member in message.new_chat_members:
            user_id = new_member.id
            user = new_member

            nickname = ' '.join(filter(None, [user.first_name, user.last_name]))
            nickname = nickname.replace('_', '\\_')  # Экранируем подчеркивания

            # Определяем репутацию пользователя
            is_owner_user = user_id == OWNER_ID
            is_admin_user = await is_admin(user_id)
            is_trainee_user = await is_trainee(user_id)

            reputation = "Нет в базе"

            if is_owner_user:
                reputation = "Владелец"
            elif is_admin_user:
                reputation = "Админ"
            elif is_trainee_user:
                reputation = "Стажер"

            # Дополнительные проверки (гаранты, проверенные, скамеры)
            async with db.execute('SELECT guarantor_id FROM trusted_users WHERE user_id = ?', (user_id,)) as cursor:
                trusted_data = await cursor.fetchone()

            async with db.execute('SELECT 1 FROM guarantors WHERE user_id = ?', (user_id,)) as cursor:
                guarantor_data = await cursor.fetchone()

            async with db.execute('SELECT proof_link FROM scammers WHERE user_id = ?', (user_id,)) as cursor:
                scammer_data = await cursor.fetchone()

            if guarantor_data:
                reputation = "Гарант"
            elif trusted_data:
                guarantor_id = trusted_data[0]
                guarantor = await client.get_users(guarantor_id)
                guarantor_nickname = ' '.join(filter(None, [guarantor.first_name, guarantor.last_name]))
                reputation = f"Проверен Гарантом {guarantor_nickname}"
            elif scammer_data:
                reputation = "Скамер"

            await message.reply(f"В группу зашел **{reputation}** под ником {nickname}", parse_mode=enums.ParseMode.MARKDOWN)

            # Если бот сам зашел в группу, сохраняем её ID
            if new_member.is_self:
                await db.execute('INSERT OR IGNORE INTO bot_groups (chat_id) VALUES (?)', (message.chat.id,))
                await db.commit()

    # ------------------ Обработчик обновлений статуса бота в группе ------------------

    @app.on_chat_member_updated()
    async def bot_added_to_group(client, chat_member_updated: ChatMemberUpdated):
        if chat_member_updated.new_chat_member.user.is_self:
            if chat_member_updated.new_chat_member.status in (enums.ChatMemberStatus.MEMBER, enums.ChatMemberStatus.ADMINISTRATOR):
                # Бот был добавлен в группу
                await db.execute('INSERT OR IGNORE INTO bot_groups (chat_id) VALUES (?)', (chat_member_updated.chat.id,))
                await db.commit()
            elif chat_member_updated.new_chat_member.status == enums.ChatMemberStatus.LEFT:
                # Бот был удален из группы
                await db.execute('DELETE FROM bot_groups WHERE chat_id = ?', (chat_member_updated.chat.id,))
                await db.commit()

    # Инициализация базы данных и запуск бота
    logging.info("Инициализация базы данных...")
    await init_db()
    logging.info("Запуск бота...")
    await app.start()
    logging.info("Бот запущен и ожидает сообщений...")
    await idle()
    await app.stop()
    logging.info("Бот остановлен.")

if __name__ == "__main__":
    asyncio.run(main())
