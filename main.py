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
from aiogram.types import Message
from aiogram.filters import CommandStart
from aiogram.enums import ParseMode

from recommendation import recommend, load_programs

# ===================== КОНФИГУРАЦИЯ =====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8489331202:AAEenH-FNTxmothImM-KC0oMf9ZAxy4ybuU")  # Замени на свой токен
SITE_URL = os.getenv("SITE_URL", "https://era-front-san-back.vercel.app")   # URL сайта (или Vercel)

# ===================== МОДЕЛИ ДАННЫХ =====================
class QuizAnswers(BaseModel):
    uid: str
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
    """Обработчик команды /start — отправляет ссылку на квиз"""
    user_id = message.from_user.id
    quiz_url = f"{SITE_URL}/quiz?uid={user_id}"
    
    await message.answer(
        f"👋 Привет, <b>{message.from_user.first_name}</b>!\n\n"
        f"🎭 Пройди короткий опрос, и мы подберём для тебя идеальную программу развлечений.\n\n"
        f"👉 <a href='{quiz_url}'>Пройти опрос</a>"
    )

dp.include_router(router)

# ===================== FASTAPI APP =====================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Жизненный цикл приложения — запуск бота"""
    # Запуск polling в фоне (только если токен настроен)
    if BOT_TOKEN != "YOUR_BOT_TOKEN_HERE":
        asyncio.create_task(dp.start_polling(bot))
        print("🤖 Бот запущен!")
    else:
        print("⚠️ BOT_TOKEN не настроен, бот не запущен")
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

@app.post("/webhook")
async def webhook(data: QuizAnswers):
    """
    Принимает данные формы и возвращает рекомендации.
    Также отправляет результат пользователю в Telegram.
    """
    uid = data.uid
    
    # Формируем словарь ответов для алгоритма
    answers = {
        "mood": data.mood,
        "budget": data.budget,
        "company": data.company,
        "time": data.time,
        "location": data.location,
        "interests": data.interests or []
    }
    
    # Убираем None значения
    answers = {k: v for k, v in answers.items() if v}
    
    print(f"📬 Получены данные: uid={uid}, answers={answers}")
    
    # Получаем рекомендации
    programs = recommend(answers, top_n=3)
    
    # Формируем ответ для Tilda
    response_data = {
        "status": "success",
        "programs": programs
    }
    
    # Отправляем результат пользователю в Telegram
    if BOT_TOKEN != "YOUR_BOT_TOKEN_HERE" and uid.isdigit():
        try:
            # Формируем сообщение
            message_lines = ["🎉 <b>Мы подобрали для тебя программы!</b>\n"]
            
            for i, program in enumerate(programs, 1):
                message_lines.append(f"<b>{i}. {program['name']}</b>")
                message_lines.append(f"{program['details'][:150]}...")
                message_lines.append(f"🎬 <a href='{program['video_url']}'>Видео</a> | 🛒 <a href='{program['photo_url']}'>Заказать</a>\n")
            
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
