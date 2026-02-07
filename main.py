"""
Backend для Telegram Mini App: FastAPI + Aiogram 3.x
Запуск: uvicorn main:app --reload --port 8000
"""

import os
import asyncio
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.filters import CommandStart
from aiogram.enums import ParseMode

from recommendation import recommend, load_programs

# ===================== КОНФИГУРАЦИЯ =====================
# Переменные окружения (настроить на хостинге)
BOT_TOKEN = os.getenv("BOT_TOKEN")  # Токен бота из BotFather
SITE_URL = os.getenv("SITE_URL")    # URL сайта на хостинге
WELCOME_VIDEO_FILE_ID = None        # Кэш для ускорения отправки видео

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN environment variable is required!")
if not SITE_URL:
    raise ValueError("❌ SITE_URL environment variable is required!")

# ===================== МОДЕЛИ ДАННЫХ =====================
class QuizAnswers(BaseModel):
    uid: str
    selected_tag: Optional[str] = None
    history: Optional[List[str]] = None
    # Старые поля для обратной совместимости
    mood: Optional[str] = None
    budget: Optional[str] = None
    company: Optional[str] = None
    time: Optional[str] = None
    location: Optional[str] = None
    interests: Optional[List[str]] = None

class TildaWebhookData(BaseModel):
    """Данные от Tilda вебхука"""
    uid: str
    answers: Dict[str, Any]

# ===================== AIOGRAM BOT =====================
bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()
router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message):
    """Обработчик команды /start — отправляет приветственное видео с описанием"""
    user_id = message.from_user.id
    first_name = message.from_user.first_name or "Гость"
    # Экранируем имя для URL
    import urllib.parse
    safe_name = urllib.parse.quote(first_name)
    quiz_url = f"{SITE_URL}/quiz?uid={user_id}&name={safe_name}"
    
    # Приветственный текст
    welcome_text = (
        "You pick the mood. NINA handles the rest.\n\n"
        "✦ 3 curated scenarios, tailored specifically for you.\n"
        "✦ Premium transfer picks you up and drops you off.\n"
        "✦ One single payment for the entire service.\n\n"
        f"Tap <a href='{quiz_url}'>Start</a> to see what I've prepared 👇"
    )
    
    # Путь к видео файлу
    video_path = "assets/welcome.mp4"
    
    # Кнопка START с Web App
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="START",
                web_app=WebAppInfo(url=quiz_url)
            )]
        ]
    )
    
    global WELCOME_VIDEO_FILE_ID
    
    try:
        # Если видео уже загружалось, отправляем по file_id (мгновенно)
        if WELCOME_VIDEO_FILE_ID:
            await message.answer_video(
                video=WELCOME_VIDEO_FILE_ID,
                caption=welcome_text,
                reply_markup=keyboard
            )
            print(f"✅ Видео отправлено (из кэша) пользователю {user_id}")
        else:
            # Если первый раз — загружаем файл
            video_file = FSInputFile(video_path)
            sent_message = await message.answer_video(
                video=video_file,
                caption=welcome_text,
                reply_markup=keyboard
            )
            # Сохраняем file_id для будущего использования
            WELCOME_VIDEO_FILE_ID = sent_message.video.file_id
            print(f"✅ Видео загружено и кэшировано (file_id: {WELCOME_VIDEO_FILE_ID})")
            
    except FileNotFoundError:
        print(f"⚠️ Видео не найдено: {video_path}")
        await message.answer(welcome_text, reply_markup=keyboard)
    except Exception as e:
        print(f"❌ Ошибка отправки видео: {e}")
        await message.answer(welcome_text, reply_markup=keyboard)

dp.include_router(router)

# ===================== FASTAPI APP =====================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Жизненный цикл приложения — запуск бота"""
    # Запуск polling в фоне (только если токен настроен)
    if BOT_TOKEN != "YOUR_BOT_TOKEN_HERE":
        asyncio.create_task(dp.start_polling(bot))
        print(f"🤖 Бот запущен! SITE_URL: {SITE_URL}")
    else:
        print(f"⚠️ BOT_TOKEN не настроен, бот не запущен. SITE_URL: {SITE_URL}")
    yield
    if BOT_TOKEN != "YOUR_BOT_TOKEN_HERE":
        await bot.session.close()
        print("🤖 Бот остановлен")

app = FastAPI(title="Era Entertainment Bot", lifespan=lifespan)

# CORS для работы с Tilda и другими фронтендами
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене ограничь домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===================== ЭНДПОИНТЫ =====================

@app.get("/", response_class=HTMLResponse)
async def root():
    """Главная страница — редирект на квиз"""
    return """
    <html>
        <head><meta http-equiv="refresh" content="0; url=/quiz"></head>
        <body>Redirecting...</body>
    </html>
    """

@app.get("/quiz", response_class=HTMLResponse)
async def serve_quiz():
    """Отдаём HTML страницу с квизом"""
    return FileResponse("index.html")

@app.get("/quiz_data.json")
async def serve_quiz_data():
    """Отдаём данные квиза"""
    return FileResponse("quiz_data.json")

@app.get("/programs.json")
async def serve_programs():
    """Отдаём список программ"""
    return FileResponse("programs.json")

@app.post("/webhook")
async def webhook(data: QuizAnswers):
    """
    Принимает данные формы и возвращает рекомендации.
    """
    uid = data.uid
    selected_tag = data.selected_tag
    history = data.history or []
    
    print(f"📬 ПОЛУЧЕНЫ ДАННЫЕ:")
    print(f"   - UID: {uid}")
    print(f"   - Тег: {selected_tag}")
    print(f"   - История: {history}")
    
    # Загружаем программы и фильтруем по тегу
    import json
    try:
        with open('programs.json', 'r', encoding='utf-8') as f:
            all_programs = json.load(f)
        
        if selected_tag:
            filtered = [p for p in all_programs if selected_tag in p.get('tags', [])]
        else:
            filtered = all_programs[:3]
        
        result_programs = filtered[:5] if filtered else all_programs[:3]
    except Exception as e:
        print(f"❌ Ошибка загрузки программ: {e}")
        result_programs = []
    
    # Формируем ответ
    response_data = {
        "status": "success",
        "programs": result_programs,
        "tag": selected_tag
    }
    
    # Отправляем результат пользователю в Telegram
    if BOT_TOKEN != "YOUR_BOT_TOKEN_HERE" and uid.isdigit() and result_programs:
        try:
            # Формируем сообщение
            message_lines = ["🎉 <b>Мы подобрали для тебя программы!</b>\n"]
            
            for i, program in enumerate(result_programs, 1):
                message_lines.append(f"<b>{i}. {program['name']}</b>")
                message_lines.append(f"{program.get('details', '')[:100]}")
                message_lines.append(f"🎬 <a href='{program.get('video_url', '#')}'>Видео</a> | 🛒 <a href='{program.get('photo_url', '#')}'>Заказать</a>\n")
            
            message_text = "\n".join(message_lines)
            await bot.send_message(chat_id=int(uid), text=message_text)
            print(f"✅ Сообщение отправлено пользователю {uid}")
            
        except Exception as e:
            print(f"❌ Ошибка отправки в Telegram: {e}")
            response_data["telegram_error"] = str(e)
    
    return JSONResponse(content=response_data)


@app.post("/tilda-webhook")
async def tilda_webhook(data: TildaWebhookData):
    """
    Специальный эндпоинт для Tilda.
    Tilda отправляет данные в своём формате.
    """
    uid = data.uid
    answers = data.answers
    
    print(f"📬 Tilda webhook: uid={uid}, answers={answers}")
    
    # Получаем рекомендации
    programs = recommend(answers, top_n=3)
    
    return JSONResponse(content={
        "status": "success",
        "programs": programs
    })


@app.get("/programs")
async def get_programs():
    """Возвращает все программы (для отладки)"""
    programs = load_programs()
    return JSONResponse(content={"count": len(programs), "programs": programs})


@app.get("/health")
async def health():
    """Проверка работоспособности сервера"""
    return {"status": "ok", "bot_configured": BOT_TOKEN != "YOUR_BOT_TOKEN_HERE"}


# ===================== ЗАПУСК =====================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
