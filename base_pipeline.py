# base_pipeline.py - کلاس پایه برای تمام pipelines
"""
این فایل شامل کلاس پایه‌ای است که تمام pipelines از آن ارث‌بری می‌کنند
"""

import asyncio
import pyodbc
import logging
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

from config import DB_CONNECTION_STRING, TABLE_NAME, USER_AGENT
from utils import (
    normalize_airline, normalize_aircraft_class, extract_price,
    extract_time_from_text, validate_flight_data
)

# تنظیم لاگر
logger = logging.getLogger(__name__)


class PipelineBase:
    """
    کلاس پایه برای تمام pipelines
    تمام متدهای مشترک و منطق ذخیره‌سازی در اینجا قرار دارد
    """
    
    def __init__(self, site_name: str, price_column: str):
        """
        مقداردهی اولیه pipeline
        
        Args:
            site_name: نام سایت (مثلاً "Alibaba")
            price_column: نام ستون قیمت در دیتابیس (مثلاً "price_alibaba")
        """
        self.site_name = site_name
        self.price_column = price_column
        self.db_conn_str = DB_CONNECTION_STRING
        self.table_name = TABLE_NAME
        self.HEADLESS = True
        
        logger.info(f"Pipeline {site_name} آماده شد")
    
    
    async def fetch_html(self, url: str, wait_selector: str = None) -> str:
        """
        دانلود HTML صفحه با Playwright
        
        Args:
            url: آدرس صفحه
            wait_selector: selector برای انتظار (اختیاری)
        
        Returns:
            HTML صفحه
        """
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.HEADLESS)
            context = await browser.new_context(user_agent=USER_AGENT)
            page = await context.new_page()
            
            try:
                logger.info(f"در حال باز کردن {url}")
                await page.goto(url, timeout=120000)
            except Exception as e:
                logger.error(f"خطا در باز کردن صفحه {self.site_name}: {e}")
            
            # انتظار برای selector مشخص
            if wait_selector:
                try:
                    await page.wait_for_selector(wait_selector, timeout=120000)
                except Exception:
                    logger.warning(f"المنت {wait_selector} در {self.site_name} پیدا نشد")
            
            # کمی صبر برای بارگذاری کامل
            await asyncio.sleep(2)
            
            html = await page.content()
            await browser.close()
            
            return html
    
    
    def parse_flights(self, html: str) -> list:
        """
        پارس کردن HTML و استخراج پروازها
        این متد باید در هر pipeline override شود
        
        Args:
            html: کد HTML صفحه
        
        Returns:
            لیست دیکشنری‌های پرواز
        """
        raise NotImplementedError("هر pipeline باید این متد را پیاده‌سازی کند")
    
    
    def build_url(self, origin_iata: str, dest_iata: str, date: str, 
                  passengers: int, international: bool = False) -> str:
        """
        ساخت URL جستجو برای سایت
        این متد باید در هر pipeline override شود
        
        Args:
            origin_iata: کد IATA مبدا
            dest_iata: کد IATA مقصد
            date: تاریخ (فرمت بستگی به سایت دارد)
            passengers: تعداد مسافران
            international: آیا پرواز بین‌المللی است؟
        
        Returns:
            URL کامل
        """
        raise NotImplementedError("هر pipeline باید این متد را پیاده‌سازی کند")
    
    
    def _normalize_flight_data(self, flight: dict) -> dict:
        """
        نرمال‌سازی داده‌های پرواز
        
        Args:
            flight: دیکشنری خام پرواز
        
        Returns:
            دیکشنری نرمال‌شده
        """
        # استخراج و نرمال‌سازی ایرلاین
        airline = (
            flight.get("airlineName") or 
            flight.get("airline") or 
            flight.get("airline_name") or 
            "نامشخص"
        )
        airline = normalize_airline(airline)
        
        # استخراج و نرمال‌سازی کلاس پرواز
        aircraft_class = (
            flight.get("classTypeName") or 
            flight.get("class") or 
            flight.get("class_type") or 
            flight.get("aircraft_class")
        )
        aircraft_class = normalize_aircraft_class(aircraft_class)
        
        # استخراج زمان حرکت
        dep_time = extract_time_from_text(
            flight.get("leaveDateTime") or 
            flight.get("departure_time") or 
            flight.get("departureDateTime")
        )
        
        # استخراج زمان رسیدن
        arr_time = extract_time_from_text(
            flight.get("arrivalDateTime") or 
            flight.get("arrival_time") or 
            flight.get("arriveDateTime") or
            flight.get("arrival")
        )
        
        # استخراج قیمت
        price = extract_price(
            flight.get("priceAdult") or 
            flight.get("price") or 
            flight.get("price_adult")
        )
        
        # شماره پرواز
        flight_no = (
            flight.get("flightNumber") or 
            flight.get("flight_number") or 
            flight.get("flightNo") or 
            flight.get("flight_id")
        )
        
        return {
            "airline": airline,
            "aircraft_class": aircraft_class,
            "departure_time": dep_time,
            "arrival_time": arr_time,
            "price": price,
            "flight_number": flight_no
        }
    
    
    def save_to_db(self, flights: list, origin_city: str, dest_city: str, 
                   date_shamsi: str):
        """
        ذخیره پروازها در دیتابیس
        منطق: اگر پرواز موجود باشد فقط قیمت آپدیت می‌شود (اگر ارزان‌تر باشد)
              اگر موجود نباشد، رکورد جدید درج می‌شود
        
        Args:
            flights: لیست پروازها
            origin_city: نام شهر مبدا
            dest_city: نام شهر مقصد
            date_shamsi: تاریخ شمسی
        """
        if not flights:
            logger.warning(f"هیچ پروازی برای ذخیره از {self.site_name} وجود ندارد")
            return
        
        conn = pyodbc.connect(self.db_conn_str)
        cursor = conn.cursor()
        
        inserted = 0
        updated = 0
        skipped = 0
        
        for flight in flights:
            try:
                # نرمال‌سازی داده‌ها
                normalized = self._normalize_flight_data(flight)
                
                # اعتبارسنجی
                if not validate_flight_data(normalized):
                    skipped += 1
                    continue
                
                # بررسی اینکه آیا تمام فیلدهای کلیدی موجود هستند
                key_fields_present = all([
                    origin_city,
                    dest_city,
                    date_shamsi,
                    normalized["departure_time"],
                    #normalized["arrival_time"],
                    normalized["airline"],
                    normalized["aircraft_class"]
                ])
                
                if key_fields_present:
                    # جستجوی رکورد موجود
                    cursor.execute(f"""
                        SELECT id, {self.price_column}
                        FROM {self.table_name}
                        WHERE origin_name = ? 
                          AND dest_name = ? 
                          AND departure_date = ?
                          AND departure_time = ? 
                          AND airline = ? 
                          AND aircraft_class = ?
                    """, (
                        origin_city, dest_city, date_shamsi,
                        normalized["departure_time"],
                        normalized["airline"],
                        normalized["aircraft_class"]
                    ))
                    
                    row = cursor.fetchone()
                else:
                    row = None
                
                if row:
                    # رکورد موجود است - آپدیت قیمت اگر ارزان‌تر باشد
                    existing_price = extract_price(row[1])
                    new_price = normalized["price"]
                    
                    #if existing_price is None or new_price < existing_price:
                    cursor.execute(f"""
                        UPDATE {self.table_name}
                        SET {self.price_column} = ?, 
                            airline = ?, 
                            aircraft_class = ?, 
                            arrival_time = ?
                        WHERE id = ?
                        """, (
                        new_price,
                        normalized["airline"],
                        normalized["aircraft_class"],
                        normalized["arrival_time"],
                        row[0]
                        ))
                    updated += 1
                    logger.debug(f"قیمت آپدیت شد: {existing_price} -> {new_price}")
                    #else:
                     #   skipped += 1
                
                else:
                    # رکورد جدید - درج
                    cursor.execute(f"""
                        INSERT INTO {self.table_name} (
                            origin_name, dest_name, departure_date, 
                            departure_time, arrival_time,
                            flight_number, airline, aircraft_class, 
                            {self.price_column}
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        origin_city, dest_city, date_shamsi,
                        normalized["departure_time"],
                        normalized["arrival_time"],
                        normalized["flight_number"],
                        normalized["airline"],
                        normalized["aircraft_class"],
                        normalized["price"]
                    ))
                    inserted += 1
                    logger.debug(f"پرواز جدید درج شد: {normalized['airline']}")
            
            except Exception as e:
                logger.error(f"خطا در ذخیره رکورد از {self.site_name}: {e}")
                skipped += 1
                continue
        
        conn.commit()
        conn.close()
        
        logger.info(
            f"✅ {self.site_name}: "
            f"درج={inserted}, آپدیت={updated}, رد شده={skipped}"
        )