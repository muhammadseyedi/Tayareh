"""
فایل اصلی برای اجرای جمع‌آوری اطلاعات پروازها
"""
import asyncio
import jdatetime
from config import IATA_CODES
from pipelines import (
    AlibabaPipeline,
    Charter118Pipeline,
    FlightioPipeline,
    MrBilitPipeline,
    GhasedakPipeline,
    FlytodayPipeline,
    SnappTripPipeline,
    EligashtPipeline,
    UltravsPipeline
)


async def run_scraper(origin_city: str = None, dest_city: str = None, 
                     date_shamsi: str = None, passengers: int = None, 
                     international: bool = False):
    """
    اجرای جمع‌آوری اطلاعات پروازها
    
    Args:
        origin_city: شهر مبدا
        dest_city: شهر مقصد
        date_shamsi: تاریخ شمسی (فرمت: 1404/08/10)
        passengers: تعداد مسافر
        international: پرواز بین‌المللی؟
    """
    
    # اگر پارامترها داده نشده، از کاربر بگیر
    if not all([origin_city, dest_city, date_shamsi, passengers]):
        origin_city = input("مبدأ: ").strip().lower()
        dest_city = input("مقصد: ").strip().lower()
        date_shamsi = input("تاریخ شمسی (مثلاً 1404/08/10): ").strip()
        passengers = int(input("تعداد بزرگسال: ").strip())
        international = input("پرواز خارجی؟ (y/n): ").strip().lower() == "y"
    
    # دریافت کدهای IATA
    origin_iata = IATA_CODES.get(origin_city)
    dest_iata = IATA_CODES.get(dest_city)
    
    if not origin_iata or not dest_iata:
        print("❌ کد IATA برای شهر مبدا یا مقصد پیدا نشد")
        return
    
    # برای پروازهای بین‌المللی از تهران، از IKA استفاده کن
    if international:
        if origin_iata == "THR":
            origin_iata = "IKA"
        if dest_iata == "THR":
            dest_iata = "IKA"
    
    # تبدیل تاریخ شمسی به میلادی
    base_jdate = jdatetime.date(*map(int, date_shamsi.split('/')))
    date_gregorian = base_jdate.togregorian().strftime("%Y-%m-%d")
    
    # لیست تمام pipeline ها
    pipelines = [
        AlibabaPipeline(),
        Charter118Pipeline(),
        FlightioPipeline(),
        MrBilitPipeline(),
        GhasedakPipeline(),
        FlytodayPipeline(),
        SnappTripPipeline(),
        EligashtPipeline(),
        UltravsPipeline()
    ]
    
    # اجرای هر pipeline
    for pipeline in pipelines:
        try:
            print(f"\n{'='*60}")
            print(f"📡 {pipeline.site_name}: {origin_city} → {dest_city}")
            print(f"{'='*60}")
            
            # pipeline های خاص که API دارند
            if isinstance(pipeline, AlibabaPipeline):
                flights = await pipeline.fetch_flights(
                    origin_iata, dest_iata, date_shamsi, passengers, international
                )
            
            # pipeline هایی که تاریخ شمسی می‌خواهند
            elif isinstance(pipeline, MrBilitPipeline):
                url = pipeline.build_url(
                    origin_iata, dest_iata, 
                    date_shamsi.replace("/", "-"), 
                    passengers, international
                )
                html = await pipeline.fetch_html(url)
                flights = pipeline.parse_flights(html)
            
            # Flytoday - متد خاص fetch_and_parse
            elif isinstance(pipeline, FlytodayPipeline):
                url = pipeline.build_url(
                    origin_iata, dest_iata, 
                    date_gregorian, passengers, international
                )
                flights = await pipeline.fetch_and_parse(url)
            
            # SnappTrip - تاریخ شمسی با فرمت slash
            elif isinstance(pipeline, SnappTripPipeline):
                url = pipeline.build_url(
                    origin_iata, dest_iata, 
                    date_gregorian, passengers, international
                )
                html = await pipeline.fetch_html(url)
                flights = pipeline.parse_flights(html)
            
            # Eligasht - تاریخ میلادی
            elif isinstance(pipeline, EligashtPipeline):
                url = pipeline.build_url(
                    origin_iata, dest_iata, 
                    date_gregorian, passengers, international
                )
                html = await pipeline.fetch_html(url)
                flights = pipeline.parse_flights(html)
            
            # Ultravs - نیاز به نام شهر نه IATA
            elif isinstance(pipeline, UltravsPipeline):
                url = pipeline.build_url(
                    origin_city.title(), dest_city.title(), 
                    date_gregorian, passengers, international
                )
                html = await pipeline.fetch_html(url)
                flights = pipeline.parse_flights(html)
            
            # بقیه pipeline های معمولی
            else:
                url = pipeline.build_url(
                    origin_iata, dest_iata, 
                    date_gregorian, passengers, international
                )
                html = await pipeline.fetch_html(url)
                flights = pipeline.parse_flights(html)
            
            # ذخیره در دیتابیس
            pipeline.save_to_db(flights, origin_city, dest_city, date_shamsi)
            
        except Exception as e:
            print(f"❌ خطا در {pipeline.site_name}: {e}")
            continue
    
    print(f"\n{'='*60}")
    print("✅ جمع‌آوری اطلاعات تمام شد!")
    print(f"{'='*60}\n")


async def main():
    """نقطه ورود اصلی برنامه"""
    await run_scraper()


if __name__ == "__main__":
    asyncio.run(main())