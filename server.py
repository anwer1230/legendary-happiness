
from flask import Flask
from threading import Thread
import logging

# إعداد السجل للسيرفر
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.route('/')
def home():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>🤖 مرسل تليجرام - حالة السيرفر</title>
        <meta charset="UTF-8">
        <style>
            body {
                font-family: Arial, sans-serif;
                text-align: center;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 50px;
                margin: 0;
            }
            .status-card {
                background: rgba(255,255,255,0.1);
                border-radius: 15px;
                padding: 30px;
                max-width: 400px;
                margin: 0 auto;
                backdrop-filter: blur(10px);
                box-shadow: 0 8px 32px rgba(0,0,0,0.1);
            }
            .icon {
                font-size: 48px;
                margin-bottom: 20px;
            }
            .status {
                font-size: 24px;
                font-weight: bold;
                margin-bottom: 10px;
            }
            .details {
                font-size: 16px;
                opacity: 0.8;
            }
        </style>
    </head>
    <body>
        <div class="status-card">
            <div class="icon">🤖</div>
            <div class="status">✅ السيرفر يعمل بنجاح</div>
            <div class="details">
                مرسل تليجرام التلقائي<br>
                السيرفر نشط ومتاح 24/7<br>
                جاهز لـ UptimeRobot
            </div>
        </div>
    </body>
    </html>
    """

@app.route('/status')
def status():
    return {
        "status": "active",
        "message": "Server is running",
        "service": "Telegram Bot Server",
        "uptime": "24/7"
    }

@app.route('/health')
def health():
    return "OK", 200

def run():
    try:
        logger.info("🚀 بدء تشغيل السيرفر المستقل على المنفذ 8080")
        app.run(host='0.0.0.0', port=8080, debug=False)
    except Exception as e:
        logger.error(f"❌ خطأ في تشغيل السيرفر: {e}")

def keep_alive():
    """تشغيل السيرفر في خيط منفصل"""
    t = Thread(target=run)
    t.daemon = True  # يتوقف مع توقف البرنامج الرئيسي
    t.start()
    logger.info("✅ تم تشغيل السيرفر المستقل بنجاح")

if __name__ == "__main__":
    # إذا تم تشغيل الملف مباشرة
    run()
