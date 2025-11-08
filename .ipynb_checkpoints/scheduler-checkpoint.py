"""
زمان‌بند برای اجرای خودکار جمع‌آوری اطلاعات هر 30 دقیقه
"""
import asyncio
import schedule
import time
from datetime import datetime
from main import run_scraper


def job():
    """تابعی که هر 30 دقیقه اجرا می‌شود"""
    print(f"\n{'='*60}")
    print(f"⏰ شروع جمع‌آوری اطلاعات - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")
    
    try:
        # اجرای async scraper
        asyncio.run(run_scraper())
        print(f"\n✅ جمع‌آوری با موفقیت انجام شد")
    except Exception as e:
        print(f"\n❌ خطا در جمع‌آوری: {e}")


def start_scheduler():
    """شروع زمان‌بند"""
    print("🚀 زمان‌بند راه‌اندازی شد")
    print("⏰ جمع‌آوری اطلاعات هر 30 دقیقه انجام می‌شود")
    print("⌨️  برای توقف Ctrl+C بزنید\n")
    
    # اجرای فوری اولیه
    print("🔄 اجرای اولیه...")
    job()
    
    # زمان‌بندی هر 30 دقیقه
    schedule.every(30).minutes.do(job)
    
    # حلقه اجرا
    try:
        while True:
            schedule.run_pending()
            time.sleep(60)  # هر 60 ثانیه یکبار چک کن
    except KeyboardInterrupt:
        print("\n\n⏹️  زمان‌بند متوقف شد")


if __name__ == "__main__":
    start_scheduler()