import os
import json
import asyncio
import logging
import re
import calendar
import gspread
import google.auth.transport.requests
from google.oauth2.credentials import Credentials
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

# Автоматическое создание конфиг-файлов на сервере Render из переменных окружения
if os.getenv("CREDENTIALS_JSON") and not os.path.exists("credentials.json"):
    with open("credentials.json", "w", encoding="utf-8") as f:
        f.write(os.getenv("CREDENTIALS_JSON"))

if os.getenv("TOKEN_JSON") and not os.path.exists("token.json"):
    with open("token.json", "w", encoding="utf-8") as f:
        f.write(os.getenv("TOKEN_JSON"))

# НАСТРОЙКИ: ваш токен бота
TOKEN = "8808526635:AAH-4n7icXhM0efIzJPr9wHB2tTgMpLxmco"
SPREADSHEET_NAME = "Kaspi & ИП Танкеев"
WORKSHEET_NAME = "Courier List"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class RegState(StatesGroup):
    waiting_for_iin = State()
    waiting_for_first_name = State()
    waiting_for_last_name = State()
    waiting_for_middle_name = State()
    waiting_for_phone = State()
    waiting_for_confirmation = State()

def get_sheet():
    creds = Credentials.from_authorized_user_file('token.json', [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ])
    
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(google.auth.transport.requests.Request())
        
    gc = gspread.authorize(creds)
    return gc.open(SPREADSHEET_NAME).worksheet(WORKSHEET_NAME)

def is_valid_name_string(text: str) -> bool:
    """Тихая проверка имени/фамилии/отчества: возвращает True/False без деталей."""
    text = text.strip()
    
    # Только кириллица (русские + казахские ә, і, ң, ғ, ү, ұ, қ, ө, һ) и дефис
    pattern = r'^[а-яА-ЯёЁӘәІіҢңҒғҮүҰұҚқӨөҺһ\-]+$'
    if not re.match(pattern, text):
        return False
    
    if len(text) < 2:
        return False
        
    # Защита от спама (повторяющиеся подряд символы)
    if re.search(r'(.)\1{2,}', text.lower()):
        return False
        
    return True

def validate_iin_structure(iin: str) -> bool:
    """Тихая проверка ИИН: возвращает True/False."""
    if not iin.isdigit() or len(iin) != 12:
        return False
        
    yy = int(iin[0:2])
    mm = int(iin[2:4])
    dd = int(iin[4:6])
    century_digit = int(iin[6])
    
    if century_digit in (3, 4):
        year = 1900 + yy
    elif century_digit in (5, 6):
        year = 2000 + yy
    else:
        year = 2000 + yy if yy <= 8 else 1900 + yy

    # Диапазон года курьеров (1960 - 2008)
    if not (1960 <= year <= 2008):
        return False
        
    if not (1 <= mm <= 12):
        return False
        
    try:
        max_days = calendar.monthrange(year, mm)[1]
    except Exception:
        return False
        
    if not (1 <= dd <= max_days):
        return False
        
    return True

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 Здравствуйте! Это бот регистрации курьеров.\n\n"
        "Пожалуйста, введите **ИИН** курьера (12 цифр):",
        reply_markup=types.ReplyKeyboardRemove()
    )
    await state.set_state(RegState.waiting_for_iin)

@dp.message(RegState.waiting_for_iin)
async def process_iin(message: types.Message, state: FSMContext):
    iin = message.text.strip()
    
    if not validate_iin_structure(iin):
        await message.answer("❌ Неверный формат или данные ИИН. Пожалуйста, проверьте и введите корректный ИИН:")
        return

    try:
        sheet = get_sheet()
        iins = sheet.col_values(1)
        if iin in iins:
            await message.answer(f"⚠️ Ошибка: Курьер с таким ИИН уже зарегистрирован в базе!")
            await state.clear()
            return
    except Exception as e:
        logging.error(f"Ошибка проверки дубликатов ИИН: {e}")

    await state.update_data(iin=iin)
    await message.answer("✅ ИИН принят.\n\nТеперь введите **Имя** курьера:")
    await state.set_state(RegState.waiting_for_first_name)

@dp.message(RegState.waiting_for_first_name)
async def process_first_name(message: types.Message, state: FSMContext):
    raw_name = message.text.strip()
    
    if not is_valid_name_string(raw_name):
        await message.answer("❌ Неверный формат имени. Введите настоящее имя кириллицей:")
        return

    first_name = raw_name.capitalize()
    await state.update_data(first_name=first_name)
    await message.answer("✅ Имя принято.\n\nТеперь введите **Фамилию** курьера:")
    await state.set_state(RegState.waiting_for_last_name)

@dp.message(RegState.waiting_for_last_name)
async def process_last_name(message: types.Message, state: FSMContext):
    raw_name = message.text.strip()
    
    if not is_valid_name_string(raw_name):
        await message.answer("❌ Неверный формат фамилии. Введите настоящую фамилию кириллицей:")
        return

    last_name = raw_name.capitalize()
    await state.update_data(last_name=last_name)
    await message.answer("✅ Фамилия принята.\n\nТеперь введите **Отчество** курьера (если нет, отправьте «Нет»):")
    await state.set_state(RegState.waiting_for_middle_name)

@dp.message(RegState.waiting_for_middle_name)
async def process_middle_name(message: types.Message, state: FSMContext):
    raw_name = message.text.strip()
    
    if raw_name.lower() in ("нет", "-", "отсутствует"):
        middle_name = ""
    else:
        if not is_valid_name_string(raw_name):
            await message.answer("❌ Неверный формат отчества. Попробуйте снова или напишите «Нет»:")
            return
        middle_name = raw_name.capitalize()

    data = await state.get_data()
    first_name = data.get('first_name')
    last_name = data.get('last_name')

    try:
        sheet = get_sheet()
        rows = sheet.get_all_values()
        for row in rows[1:]:
            if len(row) >= 3:
                row_first = row[1].strip().lower()
                row_last = row[2].strip().lower()
                if row_first == first_name.lower() and row_last == last_name.lower():
                    await message.answer(f"⚠️ Ошибка: Курьер с такими ФИО уже зарегистрирован в базе!")
                    await state.clear()
                    return
    except Exception as e:
        logging.error(f"Ошибка проверки дубликатов ФИО: {e}")

    await state.update_data(middle_name=middle_name)
    
    builder = ReplyKeyboardBuilder()
    builder.button(text="📱 Поделиться номером телефона", request_contact=True)
    
    full_name_str = f"{last_name} {first_name} {middle_name}".strip()
    await message.answer(
        f"✅ ФИО зафиксировано: **{full_name_str}**\n\n"
        "Теперь нажмите на кнопку ниже, чтобы передать номер телефона:",
        reply_markup=builder.as_markup(resize_keyboard=True, one_time_keyboard=True)
    )
    await state.set_state(RegState.waiting_for_phone)

@dp.message(RegState.waiting_for_phone, lambda message: message.contact is not None)
async def process_phone(message: types.Message, state: FSMContext):
    raw_phone = message.contact.phone_number
    phone = re.sub(r'\D', '', raw_phone)
    
    if phone.startswith('8') and len(phone) == 11:
        phone = '7' + phone[1:]

    try:
        sheet = get_sheet()
        phones = sheet.col_values(4)
        if phone in phones:
            await message.answer(
                f"⚠️ Ошибка: Данный номер телефона уже зарегистрирован в базе!",
                reply_markup=types.ReplyKeyboardRemove()
            )
            await state.clear()
            return
    except Exception as e:
        logging.error(f"Ошибка проверки телефона: {e}")

    await state.update_data(phone=phone)

    data = await state.get_data()
    iin = data.get('iin')
    first_name = data.get('first_name')
    last_name = data.get('last_name')
    middle_name = data.get('middle_name', '')
    
    full_name_display = f"{last_name} {first_name} {middle_name}".strip()

    confirm_builder = InlineKeyboardBuilder()
    confirm_builder.button(text="✅ Всё верно, отправить", callback_data="confirm_yes")
    confirm_builder.button(text="🔄 Заполнить заново", callback_data="confirm_no")
    confirm_builder.adjust(1)

    await message.answer(
        "📋 **Пожалуйста, проверьте ваши данные:**\n\n"
        f"👤 **ФИО:** {full_name_display}\n"
        f"🆔 **ИИН:** {iin}\n"
        f"📞 **Телефон:** +{phone}\n"
        f"🛵 **Транспорт:** Мото\n\n"
        "Всё указано верно?",
        reply_markup=confirm_builder.as_markup()
    )
    await state.set_state(RegState.waiting_for_confirmation)

@dp.message(RegState.waiting_for_phone)
async def process_phone_incorrect(message: types.Message):
    await message.answer("⚠️ Пожалуйста, нажмите на кнопку **«📱 Поделиться номером телефона»**, чтобы передать контакт.")

@dp.callback_query(RegState.waiting_for_confirmation)
async def process_confirmation(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    if callback.data == "confirm_no":
        await callback.message.edit_text("🔄 Регистрация отменена. Давайте начнем заново. Отправьте команду /start")
        await state.clear()
        return

    if callback.data == "confirm_yes":
        data = await state.get_data()
        iin = data.get('iin')
        first_name = data.get('first_name')
        last_name = data.get('last_name')
        middle_name = data.get('middle_name', '')
        phone = data.get('phone')

        full_name_col = f"{last_name} {first_name} {middle_name}".strip()

        try:
            sheet = get_sheet()
            next_row = len(sheet.col_values(1)) + 1
            sheet.update(f'A{next_row}:E{next_row}', [[iin, first_name, last_name, phone, "Мото"]])
            
            await callback.message.edit_text(
                "🎉 **Регистрация успешно завершена!**\n\n"
                f"👤 ФИО: {full_name_col}\n"
                f"🆔 ИИН: {iin}\n"
                f"📞 Телефон: +{phone}\n"
                f"🛵 Транспорт: Мото\n\n"
                "Данные успешно сохранены в таблицу."
            )
        except Exception as e:
            logging.error(f"Ошибка записи в таблицу: {e}")
            await callback.message.edit_text("❌ Произошла ошибка при сохранении данных в таблицу. Обратитесь к администратору.")

        await state.clear()

async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())