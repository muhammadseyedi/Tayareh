# test_scraper.py - تست سریع برای اطمینان از کارکرد سیستم
"""
این فایل یک تست سریع انجام می‌دهد تا مطمئن شویم همه چیز درست کار می‌کند
"""

import asyncio
import logging
import jdatetime
from datetime import datetime, timedelta

# تنظیم لاگ
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import از ماژول‌های پروژه
from config import IATA_CODES
from pipelines import ALL_PIPELINES
from db_manager import DatabaseManager


async def test_single_pipeline(pipeline_class, test_name="تست"):
    """
    تست یک pipeline خاص
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"🧪 تست {test_name}")
    logger.info(f"{'='*60}")
    
    try:
        # پارامترهای تست - تهران به مشهد، فردا
        origin_iata = "THR"
        dest_iata = "MHD"
        origin_city = "tehran"
        dest_city = "mashhad"
        
        # تاریخ فردا
        tomorrow = datetime.now() + timedelta(days=1)
        tomorrow_jalali = jdatetime.date.fromgregorian(date=tomorrow.date())
        date_shamsi = tomorrow_jalali.strftime("%Y/%m/%d")
        date_gregorian = tomorrow.strftime("%Y-%m-%d")
        
        passengers = 1
        international = False
        
        logger.info(f"📍 مسیر: {origin_city} ({origin_iata}) → {dest_city} ({dest_iata})")
        logger.info(f"📅 تاریخ: {date_shamsi} ({date_gregorian})")
        
        # ایجاد نمونه pipeline
        pipeline = pipeline_class()
        logger.info(f"▶ شروع {pipeline.site_name}...")
        
        # اجرای بر اساس نوع pipeline
        if pipeline.__class__.__name__ == "AlibabaPipeline":
            flights = await pipeline.fetch_flights(
                origin_iata, dest_iata, date_shamsi, passengers, international
            )
        
        elif pipeline.__class__.__name__ == "FlytodayPipeline":
            url = pipeline.build_url(origin_iata, dest_iata, date_gregorian, passengers, international)
            logger.info(f"🔗 URL: {url}")
            flights = await pipeline.fetch_and_parse(url)
        
        elif pipeline.__class__.__name__ == "MrBilitPipeline":
            date_for_mrbilit = date_shamsi.replace("/", "-")
            url = pipeline.build_url(origin_iata, dest_iata, date_for_mrbilit, passengers, international)
            html = await pipeline.fetch_html(url)
            flights = pipeline.parse_flights(html)
        
        elif pipeline.__class__.__name__ == "UltravsPipeline":
            url = pipeline.build_url(origin_city, dest_city, date_gregorian, passengers, international)
            html = await pipeline.fetch_html(url)
            flights = pipeline.parse_flights(html)
        
        else:
            url = pipeline.build_url(origin_iata, dest_iata, date_gregorian, passengers, international)
            html = await pipeline.fetch_html(url)
            flights = pipeline.parse_flights(html)
        
        # نمایش نتایج
        if flights:
            logger.info(f"✅ {len(flights)} پرواز پیدا شد")
            
            # نمایش 3 پرواز اول
            for i, flight in enumerate(flights[:3], 1):
                price = flight.get('price') or flight.get('priceAdult')
                airline = flight.get('airline') or flight.get('airlineName')
                dep = flight.get('departure_time') or flight.get('leaveDateTime', '')
                
                logger.info(f"  {i}. {airline} - {price:,} تومان - {dep[:5]}")
            
            # ذخیره در دیتابیس
            logger.info("💾 ذخیره در دیتابیس...")
            pipeline.save_to_db(flights, origin_city, dest_city, date_shamsi)
            
            return True
        else:
            logger.warning(f"⚠️ هیچ پروازی پیدا نشد")
            return False
            
    except Exception as e:
        logger.error(f"❌ خطا در تست {test_name}: {e}", exc_info=True)
        return False


async def test_all_pipelines():
    """
    تست تمام pipelines
    """
    logger.info("\n" + "="*60)
    logger.info("🚀 شروع تست کامل تمام Pipelines")
    logger.info("="*60)
    
    results = {}
    
    for pipeline_class in ALL_PIPELINES:
        site_name = pipeline_class().site_name
        success = await test_single_pipeline(pipeline_class, site_name)
        results[site_name] = "✅ موفق" if success else "❌ ناموفق"
        
        # کمی صبر بین هر تست
        await asyncio.sleep(2)
    
    # گزارش نهایی
    logger.info("\n" + "="*60)
    logger.info("📊 نتیجه تست‌ها")
    logger.info("="*60)
    for site, status in results.items():
        logger.info(f"{site:.<30} {status}")
    
    successful = sum(1 for s in results.values() if "✅" in s)
    total = len(results)
    logger.info(f"\n✅ موفق: {successful}/{total}")
    logger.info("="*60 + "\n")


async def quick_test():
    """
    تست سریع فقط یک pipeline (Alibaba)
    """
    logger.info("⚡ تست سریع - فقط Alibaba")
    from pipelines import AlibabaPipeline
    await test_single_pipeline(AlibabaPipeline, "Alibaba")
    
    # نمایش آمار
    logger.info("\n📊 آمار دیتابیس بعد از تست:")
    db = DatabaseManager()
    db.print_statistics()


async def main():
    """انتخاب نوع تست"""
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "all":
        # تست همه
        await test_all_pipelines()
    else:
        # تست سریع
        await quick_test()


if __name__ == "__main__":
    print("\n" + "="*60)
    print("🧪 اسکریپت تست Flight Scraper")
    print("="*60)
    print("برای تست همه سایت‌ها: python test_scraper.py all")
    print("برای تست سریع (فقط Alibaba): python test_scraper.py")
    print("="*60 + "\n")
    
    asyncio.run(main())