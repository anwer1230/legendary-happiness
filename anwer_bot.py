import asyncio
import json
import logging
import os
from datetime import datetime
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
from server import keep_alive
import zipfile
from telethon import TelegramClient, events
from telethon.tl.types import Channel, Chat
from telethon.errors import FloodWaitError, AuthKeyUnregisteredError
import uvicorn
import uuid
from pathlib import Path
import sqlite3
import time
import signal
import threading

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
templates = Jinja2Templates(directory="anwer_templates")

# إنشاء مجلد للمستخدمين
anwer_users_dir = Path("anwer_users")
anwer_users_dir.mkdir(exist_ok=True)

# إنشاء مجلد القوالب
anwer_templates_dir = Path("anwer_templates")
anwer_templates_dir.mkdir(exist_ok=True)

# تخزين العملاء والجلسات
anwer_clients = {}
anwer_sessions = {}
anwer_monitoring_tasks = {}

# بيانات API الافتراضية
DEFAULT_API_ID = 22043994
DEFAULT_API_HASH = '56f64582b363d367280db96586b97801'

async def anwer_monitor_connection_health():
    """مراقبة صحة الاتصالات"""
    while True:
        try:
            for user_id, client in anwer_clients.items():
                if client and client.is_connected():
                    try:
                        await client.get_me()
                    except Exception as e:
                        logger.error(f"⚠️ فقدان الاتصال للمستخدم {user_id}: {e}")
                        if user_id in anwer_monitoring_tasks:
                            anwer_monitoring_tasks[user_id].cancel()
                            del anwer_monitoring_tasks[user_id]
            await asyncio.sleep(300)  # فحص كل 5 دقائق
        except Exception as e:
            logger.error(f"خطأ في مراقبة الاتصال: {e}")
            await asyncio.sleep(60)

def anwer_load_user_settings(user_id):
    """تحميل إعدادات المستخدم"""
    settings_file = anwer_users_dir / f"anwer_settings_{user_id}.json"
    if settings_file.exists():
        try:
            with open(settings_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"خطأ في تحميل الإعدادات: {e}")

    return {
        "api_id": DEFAULT_API_ID,
        "api_hash": DEFAULT_API_HASH,
        "phone": "",
        "keywords": ["حل واجب", "انجاز", "assignment", "homework"],
        "notifications_chat": "التنبيهات",
        "auto_send_enabled": False,
        "auto_send_interval": 3600,
        "auto_send_groups": [],
        "message": ""
    }

def anwer_save_user_settings(user_id, settings):
    """حفظ إعدادات المستخدم"""
    settings_file = anwer_users_dir / f"anwer_settings_{user_id}.json"
    try:
        with open(settings_file, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"خطأ في حفظ الإعدادات: {e}")
        return False

def anwer_load_user_alerts(user_id):
    """تحميل تنبيهات المستخدم"""
    alerts_file = anwer_users_dir / f"anwer_alerts_{user_id}.json"
    if alerts_file.exists():
        try:
            with open(alerts_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"خطأ في تحميل التنبيهات: {e}")
    return []

def anwer_save_alert(user_id, alert):
    """حفظ تنبيه جديد"""
    alerts = anwer_load_user_alerts(user_id)
    alerts.append(alert)

    # الاحتفاظ بآخر 1000 تنبيه فقط
    if len(alerts) > 1000:
        alerts = alerts[-1000:]

    alerts_file = anwer_users_dir / f"anwer_alerts_{user_id}.json"
    try:
        with open(alerts_file, 'w', encoding='utf-8') as f:
            json.dump(alerts, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"خطأ في حفظ التنبيه: {e}")
        return False

async def anwer_create_notifications_chat(client, chat_name="التنبيهات"):
    """إنشاء محادثة التنبيهات إذا لم تكن موجودة"""
    try:
        # البحث عن المحادثة
        async for dialog in client.iter_dialogs():
            if dialog.name == chat_name and dialog.is_user:
                return dialog.entity

        # إذا لم توجد، إنشاء محادثة مع النفس
        me = await client.get_me()
        return me
    except Exception as e:
        logger.error(f"خطأ في إنشاء محادثة التنبيهات: {e}")
        return None

async def anwer_send_notification(client, user_id, keyword, message_text, sender_info, chat_info):
    """إرسال تنبيه للمحادثة الخاصة"""
    try:
        settings = anwer_load_user_settings(user_id)
        notifications_chat = settings.get("notifications_chat", "التنبيهات")

        # إنشاء أو العثور على محادثة التنبيهات
        target_chat = await anwer_create_notifications_chat(client, notifications_chat)
        if not target_chat:
            logger.error("لا يمكن العثور على محادثة التنبيهات")
            return

        # تكوين رسالة التنبيه
        notification_text = f"""🚨 تنبيه كلمة مراقبة 🚨

🔍 الكلمة المراقبة: {keyword}
👤 المرسل: {sender_info.get('name', 'غير معروف')} (@{sender_info.get('username', 'غير متوفر')})
💬 المجموعة: {chat_info.get('title', 'غير معروف')}
🔗 رابط المجموعة: {chat_info.get('link', 'غير متوفر')}

📝 نص الرسالة:
{message_text[:500]}{'...' if len(message_text) > 500 else ''}

⏰ الوقت: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

        # إرسال التنبيه
        await client.send_message(target_chat, notification_text)

        # حفظ التنبيه في الملف
        alert_data = {
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "keyword": keyword,
            "message": message_text[:200] + "..." if len(message_text) > 200 else message_text,
            "sender_name": sender_info.get('name', 'غير معروف'),
            "sender_username": f"@{sender_info.get('username', 'غير متوفر')}",
            "chat_title": chat_info.get('title', 'غير معروف'),
            "chat_link": chat_info.get('link', 'غير متوفر'),
            "chat_link_type": chat_info.get('link_type', 'unknown'),
            "chat_id": chat_info.get('id', 0)
        }

        anwer_save_alert(user_id, alert_data)

        logger.info(f"✅ تم إرسال تنبيه للمستخدم {user_id}")

    except Exception as e:
        logger.error(f"خطأ في إرسال التنبيه: {e}")

async def anwer_monitor_messages(user_id):
    """مراقبة الرسائل في المجموعات"""
    try:
        if user_id not in anwer_clients:
            logger.error(f"العميل غير موجود للمستخدم {user_id}")
            return

        client = anwer_clients[user_id]
        settings = anwer_load_user_settings(user_id)
        keywords = settings.get("keywords", [])

        @client.on(events.NewMessage)
        async def anwer_message_handler(event):
            try:
                # التحقق من أن الرسالة من مجموعة
                if not event.is_group and not event.is_channel:
                    return

                message_text = event.message.message or ""

                # البحث عن الكلمات المراقبة
                found_keyword = None
                for keyword in keywords:
                    if keyword.lower() in message_text.lower():
                        found_keyword = keyword
                        break

                if found_keyword:
                    # جمع معلومات المرسل
                    sender = await event.get_sender()
                    sender_info = {
                        'name': getattr(sender, 'first_name', '') + ' ' + getattr(sender, 'last_name', ''),
                        'username': getattr(sender, 'username', '')
                    }

                    # جمع معلومات المحادثة
                    chat = await event.get_chat()
                    chat_info = {
                        'title': getattr(chat, 'title', 'محادثة خاصة'),
                        'id': chat.id,
                        'link': f"tg://openmessage?chat_id={chat.id}",
                        'link_type': 'group' if hasattr(chat, 'username') and chat.username else 'private'
                    }

                    if hasattr(chat, 'username') and chat.username:
                        chat_info['link'] = f"https://t.me/{chat.username}"
                        chat_info['link_type'] = 'public'

                    # إرسال التنبيه
                    await anwer_send_notification(client, user_id, found_keyword, message_text, sender_info, chat_info)

                    logger.info(f"📨 تم رصد كلمة '{found_keyword}' في {chat_info['title']}")

            except Exception as e:
                logger.error(f"خطأ في معالجة الرسالة: {e}")

        # بدء المراقبة
        await client.run_until_disconnected()

    except Exception as e:
        logger.error(f"خطأ في مراقبة الرسائل للمستخدم {user_id}: {e}")

@app.get("/anwer", response_class=HTMLResponse)
async def anwer_home(request: Request):
    """الصفحة الرئيسية لمراقب Anwer"""
    user_id = str(uuid.uuid4())
    return RedirectResponse(f"/anwer/{user_id}", status_code=303)

@app.get("/anwer/{user_id}", response_class=HTMLResponse)
async def anwer_dashboard(request: Request, user_id: str):
    """لوحة تحكم المستخدم"""
    settings = anwer_load_user_settings(user_id)
    alerts = anwer_load_user_alerts(user_id)

    # حالة الاتصال
    connection_status = "غير متصل"
    if user_id in anwer_clients and anwer_clients[user_id]:
        if anwer_clients[user_id].is_connected():
            connection_status = "متصل"

    # حالة المراقبة
    monitoring_status = "متوقف"
    if user_id in anwer_monitoring_tasks and not anwer_monitoring_tasks[user_id].done():
        monitoring_status = "يعمل"

    return templates.TemplateResponse("anwer_index.html", {
        "request": request,
        "user_id": user_id,
        "settings": settings,
        "alerts": alerts[:50],  # آخر 50 تنبيه
        "connection_status": connection_status,
        "monitoring_status": monitoring_status,
        "total_alerts": len(alerts)
    })

@app.post("/anwer/{user_id}/login")
async def anwer_login(user_id: str, phone: str = Form(...), api_id: int = Form(DEFAULT_API_ID), api_hash: str = Form(DEFAULT_API_HASH)):
    """تسجيل الدخول"""
    try:
        settings = anwer_load_user_settings(user_id)
        settings.update({"phone": phone, "api_id": api_id, "api_hash": api_hash})
        anwer_save_user_settings(user_id, settings)

        # إنشاء العميل
        session_file = anwer_users_dir / f"anwer_session_{user_id}_{phone.replace('+', '')}.session"
        client = TelegramClient(str(session_file), api_id, api_hash)

        await client.connect()

        if not await client.is_user_authorized():
            await client.send_code_request(phone)
            anwer_clients[user_id] = client
            return JSONResponse({"status": "code_required", "message": "تم إرسال رمز التحقق"})
        else:
            anwer_clients[user_id] = client
            return JSONResponse({"status": "success", "message": "تم تسجيل الدخول بنجاح"})

    except Exception as e:
        logger.error(f"خطأ في تسجيل الدخول: {e}")
        return JSONResponse({"status": "error", "message": f"خطأ: {str(e)}"})

@app.post("/anwer/{user_id}/verify")
async def anwer_verify_code(user_id: str, code: str = Form(...), password: str = Form("")):
    """التحقق من الرمز"""
    try:
        if user_id not in anwer_clients:
            return JSONResponse({"status": "error", "message": "جلسة غير صالحة"})

        client = anwer_clients[user_id]

        if password:
            await client.sign_in(password=password)
        else:
            await client.sign_in(code=code)

        return JSONResponse({"status": "success", "message": "تم تسجيل الدخول بنجاح"})

    except Exception as e:
        logger.error(f"خطأ في التحقق: {e}")
        return JSONResponse({"status": "error", "message": f"خطأ في التحقق: {str(e)}"})

@app.post("/anwer/{user_id}/start_monitoring")
async def anwer_start_monitoring(user_id: str):
    """بدء المراقبة"""
    try:
        if user_id not in anwer_clients:
            return JSONResponse({"status": "error", "message": "يجب تسجيل الدخول أولاً"})

        if user_id in anwer_monitoring_tasks and not anwer_monitoring_tasks[user_id].done():
            return JSONResponse({"status": "error", "message": "المراقبة تعمل بالفعل"})

        # بدء مهمة المراقبة
        task = asyncio.create_task(anwer_monitor_messages(user_id))
        anwer_monitoring_tasks[user_id] = task

        return JSONResponse({"status": "success", "message": "تم بدء المراقبة"})

    except Exception as e:
        logger.error(f"خطأ في بدء المراقبة: {e}")
        return JSONResponse({"status": "error", "message": f"خطأ: {str(e)}"})

@app.post("/anwer/{user_id}/stop_monitoring")
async def anwer_stop_monitoring(user_id: str):
    """إيقاف المراقبة"""
    try:
        if user_id in anwer_monitoring_tasks:
            anwer_monitoring_tasks[user_id].cancel()
            del anwer_monitoring_tasks[user_id]

        return JSONResponse({"status": "success", "message": "تم إيقاف المراقبة"})

    except Exception as e:
        logger.error(f"خطأ في إيقاف المراقبة: {e}")
        return JSONResponse({"status": "error", "message": f"خطأ: {str(e)}"})

@app.post("/anwer/{user_id}/update_keywords")
async def anwer_update_keywords(user_id: str, keywords: str = Form(...)):
    """تحديث الكلمات المراقبة"""
    try:
        settings = anwer_load_user_settings(user_id)
        keywords_list = [k.strip() for k in keywords.split(',') if k.strip()]
        settings["keywords"] = keywords_list

        anwer_save_user_settings(user_id, settings)
        return JSONResponse({"status": "success", "message": "تم تحديث الكلمات المراقبة"})

    except Exception as e:
        logger.error(f"خطأ في تحديث الكلمات: {e}")
        return JSONResponse({"status": "error", "message": f"خطأ: {str(e)}"})

@app.get("/anwer/{user_id}/alerts")
async def anwer_get_alerts(user_id: str):
    """الحصول على التنبيهات"""
    try:
        alerts = anwer_load_user_alerts(user_id)
        return JSONResponse({"status": "success", "alerts": alerts[:100]})  # آخر 100 تنبيه
    except Exception as e:
        logger.error(f"خطأ في جلب التنبيهات: {e}")
        return JSONResponse({"status": "error", "message": f"خطأ: {str(e)}"})

@app.get("/anwer/{user_id}/status")
async def anwer_get_status(user_id: str):
    """الحصول على حالة النظام"""
    try:
        connection_status = "غير متصل"
        monitoring_status = "متوقف"

        if user_id in anwer_clients and anwer_clients[user_id]:
            if anwer_clients[user_id].is_connected():
                connection_status = "متصل"

        if user_id in anwer_monitoring_tasks and not anwer_monitoring_tasks[user_id].done():
            monitoring_status = "يعمل"

        return JSONResponse({
            "status": "success",
            "connection_status": connection_status,
            "monitoring_status": monitoring_status
        })
    except Exception as e:
        logger.error(f"خطأ في جلب الحالة: {e}")
        return JSONResponse({"status": "error", "message": f"خطأ: {str(e)}"})

@app.get("/anwer/{user_id}/export")
async def anwer_export_data(user_id: str):
    """تصدير البيانات"""
    try:
        # إنشاء ملف مؤقت
        export_file = anwer_users_dir / f"anwer_export_{user_id}_{int(time.time())}.json"

        data = {
            "settings": anwer_load_user_settings(user_id),
            "alerts": anwer_load_user_alerts(user_id),
            "export_date": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        with open(export_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return FileResponse(
            path=export_file,
            filename=f"anwer_export_{user_id}.json",
            media_type="application/json"
        )

    except Exception as e:
        logger.error(f"خطأ في تصدير البيانات: {e}")
        return JSONResponse({"status": "error", "message": f"خطأ: {str(e)}"})

async def anwer_cleanup_on_shutdown():
    """تنظيف الموارد عند الإغلاق"""
    try:
        # إيقاف جميع مهام المراقبة
        for task in anwer_monitoring_tasks.values():
            if not task.done():
                task.cancel()

        # قطع اتصال جميع العملاء
        for client in anwer_clients.values():
            if client and client.is_connected():
                await client.disconnect()

        logger.info("✅ تم تنظيف جميع الموارد")
    except Exception as e:
        logger.error(f"خطأ في التنظيف: {e}")

if __name__ == "__main__":
    # بدء مراقبة صحة الاتصالات
    asyncio.create_task(anwer_monitor_connection_health())

    # معالجة إشارة الإغلاق
    def signal_handler(signum, frame):
        logger.info("🛑 تم استلام إشارة الإغلاق...")
        asyncio.create_task(anwer_cleanup_on_shutdown())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # بدء السيرفر
    keep_alive()
    try:
        uvicorn.run(app, host="0.0.0.0", port=4000)
    except Exception as e:
        logger.error(f"خطأ في تشغيل السيرفر: {e}")