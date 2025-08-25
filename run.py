
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import asyncio
import logging
from pathlib import Path

# إضافة المجلد الحالي لمسار Python
sys.path.insert(0, str(Path(__file__).parent))

# إعداد السجلات
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('anwer_bot.log', encoding='utf-8')
    ]
)

logger = logging.getLogger(__name__)

def main():
    """تشغيل البوت"""
    try:
        logger.info("🚀 بدء تشغيل Anwer Bot...")
        
        # استيراد وتشغيل البوت
        from anwer_bot import app
        import uvicorn
        
        # الحصول على المنفذ من متغير البيئة أو استخدام 4000
        port = int(os.environ.get("PORT", 4000))
        host = os.environ.get("HOST", "0.0.0.0")
        
        logger.info(f"🌐 تشغيل السيرفر على {host}:{port}")
        
        # تشغيل السيرفر
        uvicorn.run(
            app, 
            host=host, 
            port=port,
            log_level="info",
            access_log=True
        )
        
    except Exception as e:
        logger.error(f"❌ خطأ في تشغيل البوت: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
