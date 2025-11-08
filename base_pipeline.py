"""
کلاس پایه برای تمام pipeline های جمع‌آوری اطلاعات پرواز
"""
import asyncio
import pyodbc
import re
from playwright.async_api import async_playwright
from config import DB_CONNECTION_STRING, USER_AGENT
from utils import (
    normalize_price, 
    normalize_airline, 
    normalize_aircraft_class,
    extract_time_from_datetime
)


class PipelineBase:
    """کلاس پایه برای همه pipeline ها"""
    
    def __init__(self, site_name: str, table_name: str, price_column: str):
        """
        مقداردهی اولیه pipeline
        
        Args:
            site_name: نام سایت (مثلا "Alibaba")
            table_name: نام جدول در دیتابیس
            price_column: نام ستون قیمت (مثلا "price_alibaba")
        """
        self.site_name = site_name
        self.table_name = table_name
        self.price_column = price_column
        self.db_connection_string = DB_CONNECTION_STRING
        self.headless = True  # pipeline های خاص می‌توانند آن را override کنند

    async def fetch_html(self, url: str, wait_selector: str = None) -> str:
        """
        دریافت HTML صفحه با استفاده از Playwright
        
        Args:
            url: آدرس صفحه
            wait_selector: selector برای انتظار بارگذاری المان خاص
        
        Returns:
            محتوای HTML صفحه
        """
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            context = await browser.new_context(user_agent=USER_AGENT)
            page = await context.new_page()
            
            try:
                await page.goto(url, timeout=120000)
            except Exception as e:
                print(f"⚠️ خطا در باز کردن صفحه {self.site_name}: {e}")
            
            # انتظار برای المان خاص (در صورت تعریف)
            if wait_selector:
                try:
                    await page.wait_for_selector(wait_selector, timeout=120000)
                except Exception:
                    print(f"⚠️ المنت {wait_selector} پیدا نشد در {self.site_name}")
            
            # کمی تاخیر برای اطمینان از بارگذاری کامل
            await asyncio.sleep(2)
            
            html = await page.content()
            await browser.close()
            
            return html

    def _extract_flight_data(self, flight: dict) -> dict:
        """
        استخراج و نرمال‌سازی داده‌های پرواز
        
        Args:
            flight: دیکشنری اطلاعات خام پرواز
        
        Returns:
            دیکشنری اطلاعات پردازش‌شده
        """
        # استخراج زمان حرکت
        dep_time = extract_time_from_datetime(
            flight.get("leaveDateTime") or 
            flight.get("departure_time") or 
            flight.get("departureDateTime") or 
            flight.get("leave_date_time") or ""
        )
        
        # استخراج زمان رسیدن
        arr_time = extract_time_from_datetime(
            flight.get("arrivalDateTime") or 
            flight.get("arrival_time") or 
            flight.get("arriveDateTime") or 
            flight.get("arrival") or 
            flight.get("arrive") or ""
        )
        
        # استخراج شماره پرواز
        flight_no = (
            flight.get("flightNumber") or
            flight.get("flight_number") or
            flight.get("flightNo") or
            flight.get("flight_id") or
            flight.get("flight_no")
        )
        
        # اگر شماره پرواز در فیلد description باشد
        if not flight_no and flight.get("description") and "|" in flight.get("description"):
            flight_no = flight.get("description").split("|")[0].strip()
        
        # استخراج و نرمال‌سازی ایرلاین
        airline = normalize_airline(
            flight.get("airlineName") or 
            flight.get("airline") or 
            flight.get("airline_name")
        )
        
        # استخراج و نرمال‌سازی کلاس پرواز
        aircraft_class = normalize_aircraft_class(
            flight.get("classTypeName") or
            flight.get("class") or
            flight.get("class_type") or
            flight.get("aircraft_class")
        )
        
        # استخراج و نرمال‌سازی قیمت
        raw_price = (
            flight.get("priceAdult") or 
            flight.get("price") or 
            flight.get("price_adult")
        )
        price = normalize_price(raw_price)
        
        return {
            "departure_time": dep_time,
            "arrival_time": arr_time,
            "flight_number": flight_no,
            "airline": airline,
            "aircraft_class": aircraft_class,
            "price": price
        }

    def save_to_db(self, flights: list, origin_city: str, dest_city: str, date_shamsi: str):
        """
        ذخیره پروازها در دیتابیس با منطق UPDATE یا INSERT
        
        Args:
            flights: لیست پروازها
            origin_city: شهر مبدا
            dest_city: شهر مقصد
            date_shamsi: تاریخ شمسی
        """
        if not flights:
            print(f"⚠️ هیچ پروازی برای ذخیره در {self.site_name} وجود ندارد.")
            return
        
        conn = pyodbc.connect(self.db_connection_string)
        cursor = conn.cursor()
        
        inserted = 0
        updated = 0
        
        for flight in flights:
            try:
                # استخراج و نرمال‌سازی داده‌های پرواز
                data = self._extract_flight_data(flight)
                
                # اگر قیمت موجود نیست، پرواز را نادیده بگیر
                if data["price"] is None:
                    continue
                
                # بررسی اینکه آیا تمام فیلدهای کلیدی موجود هستند
                key_fields_present = all([
                    origin_city, dest_city, date_shamsi,
                    data["departure_time"], data["arrival_time"],
                    data["airline"], data["aircraft_class"]
                ])
                
                if key_fields_present:
                    # جستجوی رکورد موجود
                    cursor.execute(f"""
                        SELECT id, {self.price_column}
                        FROM Flights_AllSites
                        WHERE origin_name=? AND dest_name=? AND departure_date=?
                        AND departure_time=? AND airline=? AND aircraft_class=?
                    """, (
                        origin_city, dest_city, date_shamsi,
                        data["departure_time"], data["airline"], data["aircraft_class"]
                    ))
                    row = cursor.fetchone()
                else:
                    row = None
                
                if row:
                    # رکورد موجود است - بررسی قیمت
                    existing_price = normalize_price(row[1])
                    
                    # اگر قیمت جدید کمتر است یا قیمت قبلی موجود نیست
                    if existing_price is None or data["price"] < existing_price:
                        cursor.execute(f"""
                            UPDATE Flights_AllSites
                            SET {self.price_column} = ?, airline = ?, 
                                aircraft_class = ?, arrival_time = ?
                            WHERE id = ?
                        """, (
                            data["price"], data["airline"],
                            data["aircraft_class"], data["arrival_time"],
                            row[0]
                        ))
                        updated += 1
                else:
                    # رکورد جدید - INSERT
                    cursor.execute(f"""
                        INSERT INTO Flights_AllSites (
                            origin_name, dest_name, departure_date, 
                            departure_time, arrival_time, flight_number, 
                            airline, aircraft_class, {self.price_column}
                        )
                        VALUES (?,?,?,?,?,?,?,?,?)
                    """, (
                        origin_city, dest_city, date_shamsi,
                        data["departure_time"], data["arrival_time"],
                        data["flight_number"], data["airline"],
                        data["aircraft_class"], data["price"]
                    ))
                    inserted += 1
            
            except Exception as e:
                print(f"⚠️ خطا در ذخیره رکورد {self.site_name}: {e}")
                continue
        
        conn.commit()
        conn.close()
        
        print(f"✅ {self.site_name}: درج={inserted}, بروزرسانی={updated}")

    def build_url(self, origin_iata: str, dest_iata: str, 
                  date: str, passengers: int, international: bool = False) -> str:
        """
        ساخت URL جستجو
        
        هر pipeline باید این متد را override کند
        """
        raise NotImplementedError("باید در کلاس فرزند پیاده‌سازی شود")

    def parse_flights(self, html: str) -> list:
        """
        پارس HTML و استخراج اطلاعات پروازها
        
        هر pipeline باید این متد را override کند
        """
        raise NotImplementedError("باید در کلاس فرزند پیاده‌سازی شود")