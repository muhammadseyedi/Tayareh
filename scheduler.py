"""Scheduled flight scraping with one search configuration reused per run."""
import asyncio
import schedule
import time
from datetime import datetime

import jdatetime

from config import IATA_CODES, SCHEDULE_CONFIG
from main import run_scraper


def prompt_search_parameters():
    """Ask once for a valid search; scheduled cycles reuse these parameters."""
    while True:
        origin_city = input("مبدأ (نام انگلیسی شهر، مثلاً tehran): ").strip().lower()
        dest_city = input("مقصد (نام انگلیسی شهر، مثلاً mashhad): ").strip().lower()
        if origin_city not in IATA_CODES or dest_city not in IATA_CODES:
            print("❌ کد شهر پیدا نشد؛ نام شهر را مطابق IATA_CODES در config.py وارد کنید.")
            continue
        if origin_city == dest_city:
            print("❌ مبدأ و مقصد نباید یکسان باشند.")
            continue
        break

    while True:
        date_shamsi = input("تاریخ شمسی (مثلاً 1405/08/20): ").strip()
        try:
            jdatetime.date(*map(int, date_shamsi.split("/")))
            break
        except (TypeError, ValueError):
            print("❌ تاریخ نامعتبر است؛ قالب YYYY/MM/DD را وارد کنید.")

    while True:
        try:
            passengers = int(input("تعداد مسافران: ").strip())
            if passengers < 1:
                raise ValueError
            break
        except ValueError:
            print("❌ تعداد مسافران باید عدد صحیح و مثبت باشد.")

    international = input("پرواز بین‌المللی؟ (y/n): ").strip().lower() in {"y", "yes"}
    return {
        "origin_city": origin_city,
        "dest_city": dest_city,
        "date_shamsi": date_shamsi,
        "passengers": passengers,
        "international": international,
    }


def job(search_params):
    """Run one collection cycle for the configured search."""
    print(f"\n{'=' * 60}")
    print(f"⏰ شروع جمع‌آوری اطلاعات - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(
        f"✈️ {search_params['origin_city']} → {search_params['dest_city']} | "
        f"{search_params['date_shamsi']} | مسافران: {search_params['passengers']}"
    )
    print(f"{'=' * 60}\n")

    try:
        asyncio.run(run_scraper(**search_params))
        print("\n✅ چرخه‌ی جمع‌آوری پایان یافت")
    except Exception as exc:
        print(f"\n❌ خطا در جمع‌آوری: {exc}")


def start_scheduler():
    """Prompt once, run the initial cycle, and then repeat at the configured interval."""
    interval = int(SCHEDULE_CONFIG.get("run_every_minutes", 30))
    if interval < 1:
        raise ValueError("SCHEDULE_CONFIG['run_every_minutes'] must be at least 1")

    first_run_delay = max(0, int(SCHEDULE_CONFIG.get("first_run_delay", 0)))
    search_params = prompt_search_parameters()

    print("🚀 زمان‌بند راه‌اندازی شد")
    print(f"⏰ اجرای مجدد هر {interval} دقیقه انجام می‌شود")
    print("🔁 در هر اجرا همین مسیر و تاریخ تکرار می‌شود.")
    print("⌨️ برای توقف Ctrl+C بزنید\n")

    if first_run_delay:
        print(f"⏳ انتظار {first_run_delay} ثانیه پیش از اجرای اولیه...")
        time.sleep(first_run_delay)

    job(search_params)
    schedule.every(interval).minutes.do(job, search_params)

    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n⏹️ زمان‌بند متوقف شد")


if __name__ == "__main__":
    start_scheduler()
