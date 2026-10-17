import os
import json
import asyncio
import logging
import re
import gspread
import google.auth.transport.requests
from google.oauth2.credentials import Credentials
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import ReplyKeyboardBuilder

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
    waiting_for_phone = State()

def get_sheet():
    creds = Credentials.from_authorized_user_file('token.json', [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ])
    
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(google.auth.transport.requests.Request())
        
    gc = gspread.authorize(creds)
    return gc.open(SPREADSHEET_NAME).worksheet(WORKSHEET_NAME)

def is_valid_name(text: str) -> bool:
    pattern = r'^[a-zA-Zа-яА-ЯёЁӘәІіҢңҒғҮүҰұҚқӨөҺһ\-]+$'
    return bool(re.match(pattern, text))

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await message.answer(
        "👋 Здравствуйте! Это бот регистрации курьеров.\n\n"
        "Пожалуйста, введите **ИИН** курьера (12 цифр):"
    )
    await state.set_state(RegState.waiting_for_iin)

@dp.message(RegState.waiting_for_iin)
async def process_iin(message: types.Message, state: FSMContext):
    iin = message.text.strip()
    
    if not iin.isdigit() or len(iin) != 12:
        await message.answer("❌ Неверный формат! ИИН должен состоять **ровно из 12 цифр**. Попробуйте снова:")
        return

    try:
        sheet = get_sheet()
        iins = sheet.col_values(1)
        if iin in iins:
            await message.answer(f"⚠️ Ошибка: Курьер с ИИН `{iin}` уже зарегистрирован в базе!")
            await state.clear()
            return
    except Exception as e:
        logging.error(f"Ошибка проверки дубликатов ИИН: {e}")

    await state.update_data(iin=iin)
    await message.answer("✅ ИИН принят.\n\nТеперь введите **Имя** курьера:")
    await state.set_state(RegState.waiting_for_first_name)

@dp.message(RegState.waiting_for_first_name)
async def process_first_name(message: types.Message, state: FSMContext):
    first_name = message.text.strip()
    
    if not is_valid_name(first_name):
        await message.answer("❌ Имя должно содержать **только буквы**! Введите имя заново:")
        return

    await state.update_data(first_name=first_name)
    await message.answer("✅ Имя принято.\n\nТеперь введите **Фамилию** курьера:")
    await state.set_state(RegState.waiting_for_last_name)

@dp.message(RegState.waiting_for_last_name)
async def process_last_name(message: types.Message, state: FSMContext):
    last_name = message.text.strip()
    
    if not is_valid_name(last_name):
        await message.answer("❌ Фамилия должна содержать **только буквы**! Введите фамилию заново:")
        return

    data = await state.get_data()
    first_name = data.get('first_name')

    try:
        sheet = get_sheet()
        rows = sheet.get_all_values()
        for row in rows[1:]:
            if len(row) >= 3:
                row_first = row[1].strip().lower()
                row_last = row[2].strip().lower()
                if row_first == first_name.lower() and row_last == last_name.lower():
                    await message.answer(f"⚠️ Ошибка: Курьер **{first_name} {last_name}** уже зарегистрирован в базе!")
                    await state.clear()
                    return
    except Exception as e:
        logging.error(f"Ошибка проверки дубликатов ФИО: {e}")

    await state.update_data(last_name=last_name)
    
    builder = ReplyKeyboardBuilder()
    builder.button(text="📱 Поделиться номером телефона", request_contact=True)
    
    await message.answer(
        "✅ Фамилия принята.\n\n"
        "Теперь нажмите на кнопку ниже, чтобы передать номер телефона:",
        reply_markup=builder.as_markup(resize_keyboard=True, one_time_keyboard=True)
    )
    await state.set_state(RegState.waiting_for_phone)

@dp.message(RegState.waiting_for_phone, lambda message: message.contact is not None)
async def process_phone(message: types.Message, state: FSMContext):
    phone = message.contact.phone_number
    if not phone.startswith("+"):
        phone = "+" + phone
        
    data = await state.get_data()
    iin = data.get('iin')
    first_name = data.get('first_name')
    last_name = data.get('last_name')

    try:
        sheet = get_sheet()
        
        phones = sheet.col_values(4)
        if phone in phones:
            await message.answer(
                f"⚠️ Ошибка: Номер **{phone}** уже зарегистрирован в базе!",
                reply_markup=types.ReplyKeyboardRemove()
            )
            await state.clear()
            return

        next_row = len(sheet.col_values(1)) + 1
        sheet.update(f'A{next_row}:E{next_row}', [[iin, first_name, last_name, phone, "Мото"]])
        
        await message.answer(
            "🎉 **Регистрация успешно завершена!**\n\n"
            f"👤 ФИО: {first_name} {last_name}\n"
            f"🆔 ИИН: {iin}\n"
            f"📞 Телефон: {phone}\n"
            f"🛵 Транспорт: Мото\n\n"
            "Данные успешно добавлены в таблицу.",
            reply_markup=types.ReplyKeyboardRemove()
        )
    except Exception as e:
        logging.error(f"Ошибка записи: {e}")
        await message.answer(
            "❌ Произошла ошибка при сохранении данных в таблицу.",
            reply_markup=types.ReplyKeyboardRemove()
        )

    await state.clear()

@dp.message(RegState.waiting_for_phone)
async def process_phone_incorrect(message: types.Message):
    await message.answer("⚠️ Пожалуйста, нажмите на кнопку **«📱 Поделиться номером телефона»**, чтобы передать контакт.")

async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())