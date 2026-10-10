"""زمان‌بند اجرای خودکار جمع‌آوری اطلاعات پروازها."""
import asyncio
import schedule
import time
from datetime import datetime

from config import SCHEDULE_CONFIG
from main import run_scraper


def job():
    """Run one collection cycle."""
    print(f"\n{'=' * 60}")
    print(f"⏰ شروع جمع‌آوری اطلاعات - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 60}\n")

    try:
        # run_scraper currently visits pipelines sequentially.
        asyncio.run(run_scraper())
        print("\n✅ جمع‌آوری با موفقیت انجام شد")
    except Exception as exc:
        print(f"\n❌ خطا در جمع‌آوری: {exc}")


def start_scheduler():
    """Run once immediately, then repeat using SCHEDULE_CONFIG."""
    interval = int(SCHEDULE_CONFIG.get("run_every_minutes", 30))
    if interval < 1:
        raise ValueError("SCHEDULE_CONFIG['run_every_minutes'] must be at least 1")

    print("🚀 زمان‌بند راه‌اندازی شد")
    print(f"⏰ اجرای بعدی هر {interval} دقیقه انجام می‌شود")
    print("⌨️ برای توقف Ctrl+C بزنید\n")

    # Execute an initial run before entering the scheduling loop.
    print("🔄 اجرای اولیه...")
    job()

    schedule.every(interval).minutes.do(job)

    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n⏹️ زمان‌بند متوقف شد")


if __name__ == "__main__":
    start_scheduler()
