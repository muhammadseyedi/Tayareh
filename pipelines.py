# pipelines.py - تمام scraperهای سایت‌های مختلف
"""
این فایل شامل تمام pipelines برای سایت‌های مختلف است
هر کلاس از PipelineBase ارث‌بری می‌کند و متدهای خاص خود را پیاده‌سازی می‌کند
"""

import asyncio
import re
import logging
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from base_pipeline import PipelineBase
from utils import (
    safe_get_text, persian_to_latin_digits, clean_city_name,
    extract_flight_number, normalize_aircraft_class
)

logger = logging.getLogger(__name__)


# ================================
# 📗 Alibaba Pipeline
# ================================
class AlibabaPipeline(PipelineBase):
    """Scraper برای سایت علی‌بابا"""
    
    def __init__(self):
        super().__init__("Alibaba", "price_alibaba")
    
    def build_url(self, origin_iata, dest_iata, date_shamsi, passengers, international=False):
        base = "https://www.alibaba.ir/international" if international else "https://www.alibaba.ir/flights"
        return f"{base}/{origin_iata}-{dest_iata}?adult={passengers}&child=0&infant=0&departing={date_shamsi}"
    
    async def get_api_url(self, search_url):
        """استخراج URL واقعی API از درخواست‌های شبکه"""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            api_url = None
            
            def handle_request(req):
                nonlocal api_url
                if "api/v1/flights/domestic/available" in req.url:
                    api_url = req.url
            
            page.on("request", handle_request)
            
            try:
                await page.goto(search_url, timeout=60000)
                await page.wait_for_timeout(5000)
            except Exception as e:
                logger.error(f"خطا در باز کردن علی‌بابا: {e}")
            
            await browser.close()
            return api_url
    
    async def fetch_flights(self, origin_iata, dest_iata, date_shamsi, passengers, international=False):
        """دریافت مستقیم از API علی‌بابا"""
        search_url = self.build_url(origin_iata, dest_iata, date_shamsi, passengers, international)
        api_url = await self.get_api_url(search_url)
        
        if not api_url:
            logger.error("نتوانستم API علی‌بابا را پیدا کنم")
            return []
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            
            try:
                response = await context.request.get(api_url)
                data = await response.json()
            except Exception as e:
                logger.error(f"خطا در دریافت JSON علی‌بابا: {e}")
                await context.close()
                return []
            
            await context.close()
        
        if not data.get("success") or not data["result"].get("departing"):
            logger.warning("داده‌ای از API علی‌بابا دریافت نشد")
            return []
        
        flights = []
        for f in data["result"]["departing"]:
            if f.get("seat", 0) == 0:
                continue  # حذف پروازهای بدون ظرفیت
            
            flights.append({
                "flight_number": f.get("flightNumber"),
                "airline": f.get("airlineName"),
                "leaveDateTime": f.get("leaveDateTime"),
                "arrivalDateTime": f.get("arrivalDateTime"),
                "aircraft_class": f.get("classTypeName"),
                "price": f.get("priceAdult"),
            })
        
        logger.info(f"✈️ {len(flights)} پرواز از علی‌بابا استخراج شد")
        return flights


# ================================
# 📘 Charter118 Pipeline
# ================================
class Charter118Pipeline(PipelineBase):
    """Scraper برای سایت Charter118"""
    
    def __init__(self):
        super().__init__("Charter118", "price_charter118")
    
    def build_url(self, origin_iata, dest_iata, date_gregorian, passengers, international=False):
        base = "https://charter118.ir/international-flights" if international else "https://charter118.ir/flights"
        return f"{base}/{origin_iata}-{dest_iata}?adult={passengers}&child=0&infant=0&departing={date_gregorian}"
    
    async def fetch_html(self, url, wait_selector=None):
        """override با اسکرول بیشتر برای Charter118"""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.HEADLESS)
            page = await browser.new_page()
            
            await page.goto(url, timeout=120000)
            
            if wait_selector:
                try:
                    await page.wait_for_selector(wait_selector, timeout=20000)
                except:
                    logger.warning("المان Charter118 پیدا نشد - اسکرول می‌کنم")
            
            # اسکرول برای بارگذاری lazy
            for _ in range(6):
                await page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
                await asyncio.sleep(1)
            
            html = await page.content()
            await browser.close()
            return html
    
    def parse_flights(self, html):
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.find_all("div", class_=lambda c: c and "bg-white" in c and "rounded-lg" in c)
        flights = []
        
        for card in cards:
            try:
                # استخراج کلاس پرواز
                tags = card.find_all("p", class_=lambda c: c and "bg-blue-400/10" in c)
                tag_texts = [t.text.strip() for t in tags]
                aircraft_class = next((t for t in tag_texts if "اکونومی" in t or "بیزینس" in t), None)
                
                # شماره پرواز
                num_tag = card.find("p", class_=lambda c: c and "bg-gray-400/10" in c)
                flight_number = num_tag.text.strip() if num_tag else None
                

                airline_tag = card.find("p", class_=lambda c: c and "text-darkGray" in c and "text-center" in c)
                airline = airline_tag.text.strip() if airline_tag else None
                # زمان‌ها
                times = card.find_all("span", class_=lambda c: c and "text-black" in c and "text-xl" in c)
                departure_time = times[0].text.strip() if times else None
                arrival_time = times[1].text.strip() if len(times) > 1 else None
                
                # قیمت
                price_tag = card.find("p", class_=lambda c: c and "text-green-700" in c)
                price = None
                if price_tag:
                    price_text = price_tag.text.replace(",", "").replace("٬", "").strip()
                    price = int(price_text) if price_text.isdigit() else None
                
                if airline and departure_time and price:
                    flights.append({
                        "flight_number": flight_number,
                        "price": price,
                        "airline": airline,
                        "aircraft_class": aircraft_class,
                        "departure_time": departure_time,
                        "arrival_time": arrival_time
                    })
            except Exception as e:
                logger.debug(f"خطا در کارت Charter118: {e}")
                continue
        
        logger.info(f"✈️ {len(flights)} پرواز از Charter118 استخراج شد")
        return flights


# ================================
# 📙 Flightio Pipeline
# ================================
class FlightioPipeline(PipelineBase):
    """Scraper برای سایت Flightio"""
    
    def __init__(self):
        super().__init__("Flightio", "price_flightio")
        self.HEADLESS = False  # برای تست بهتر است
    
    def build_url(self, origin_iata, dest_iata, date_gregorian, passengers, international=False):
        flight_type = 1 if international else 2
        return f"https://flightio.com/flight/{origin_iata}-{dest_iata}?depart={date_gregorian}&adult={passengers}&child=0&infant=0&flightType={flight_type}&cabinType=1"
    
    async def fetch_html(self, url, wait_selector="section.transition-input-100"):
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.HEADLESS,
                args=["--disable-blink-features=AutomationControlled"]
            )
            page = await browser.new_page()
            await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
            
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=120000)
            except Exception as e:
                logger.error(f"خطا در باز کردن Flightio: {e}")
            
            try:
                await page.wait_for_selector(wait_selector, timeout=120000)
            except:
                logger.warning("Flightio: پرواز نمایش داده نشد")
            
            # اسکرول
            for _ in range(8):
                await page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
                await asyncio.sleep(1)
            
            html = await page.content()
            await browser.close()
            return html
    
    def parse_flights(self, html):
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.find_all("section", class_=lambda c: c and "transition-input-100" in c)
        flights = []
        
        for card in cards:
            try:
                airline = safe_get_text(card.find("span", class_=lambda c: c and "text-body-m" in c))
                
                flight_info = card.find_all("span", string=re.compile("پرواز شماره"))
                flight_number = None
                if flight_info:
                    flight_number = re.sub(r"[^\d]", "", flight_info[0].text)
                
                price_span = card.find("span", class_=lambda c: c and "font-bold" in c)
                price = None
                if price_span:
                    price_digits = re.findall(r"\d+", price_span.text.replace(",", ""))
                    if price_digits:
                        price = int(price_digits[0])
                
                time_spans = card.find_all("span", class_=lambda c: c and "text-title-xl" in c)
                dep_time = safe_get_text(time_spans[0]) if len(time_spans) > 0 else None
                arr_time = safe_get_text(time_spans[1]) if len(time_spans) > 1 else None
                
                cabin = card.find("span", string=lambda s: s and ("اکونومی" in s or "بیزینس" in s))
                aircraft_class = cabin.get_text(strip=True).split("-")[0] if cabin else None
                
                if airline and price and dep_time:
                    flights.append({
                        "flight_number": flight_number,
                        "price": price,
                        "airline": airline,
                        "aircraft_class": aircraft_class,
                        "departure_time": dep_time,
                        "arrival_time": arr_time
                    })
            except Exception as e:
                logger.debug(f"خطا در کارت Flightio: {e}")
                continue
        
        logger.info(f"✈️ {len(flights)} پرواز از Flightio استخراج شد")
        return flights


# ================================
# 📕 MrBilit Pipeline
# ================================
class MrBilitPipeline(PipelineBase):
    """Scraper برای سایت MrBilit"""
    
    def __init__(self):
        super().__init__("MrBilit", "price_mrbilit")
        self.HEADLESS = False
    
    def build_url(self, origin_iata, dest_iata, date_shamsi, passengers, international=False):
        # MrBilit از تاریخ شمسی استفاده می‌کند
        return f"https://mrbilit.com/flights/{origin_iata}-{dest_iata}?departureDate={date_shamsi}"
    
    async def fetch_html(self, url, wait_selector=".trip-package-info"):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.HEADLESS)
            page = await browser.new_page()
            
            try:
                await page.goto(url, timeout=60000)
            except Exception as e:
                logger.error(f"خطا در باز کردن MrBilit: {e}")
            
            try:
                await page.wait_for_selector(wait_selector, timeout=20000)
            except:
                logger.warning("پرواز MrBilit نمایش داده نشد")
            
            for _ in range(5):
                await page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
                await asyncio.sleep(0.8)
            
            html = await page.content()
            await browser.close()
            return html
    
    def parse_flights(self, html):
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select(".trip-package-info")
        flights = []
        
        for card in cards:
            try:
                times = card.select(".time")
                dep_time = times[0].text.strip() if times else None
                arr_time = times[1].text.strip() if len(times) > 1 else None
                
                airline_tag = card.select_one("div.title-container p")
                airline = airline_tag.text.strip() if airline_tag else "نامشخص"
                
                price_tag = card.select_one(".price")
                if not price_tag:
                    continue
                price_text = price_tag.text.replace(",", "").replace("٬", "")
                price_digits = "".join(re.findall(r"\d+", price_text))
                price = int(price_digits) if price_digits.isdigit() else None
                
                class_tag = (
                    card.select_one(".badge") or
                    card.select_one(".ticket-type") or
                    card.find(string=lambda t: t and ("اکونومی" in t or "بیزینس" in t))
                )
                
                aircraft_class = None
                if class_tag:
                    txt = safe_get_text(class_tag) if hasattr(class_tag, "get_text") else str(class_tag)
                    aircraft_class = normalize_aircraft_class(txt)
                
                if airline and price and dep_time:
                    flights.append({
                        "flight_number": None,
                        "price": price,
                        "airline": airline,
                        "aircraft_class": aircraft_class,
                        "departure_time": dep_time,
                        "arrival_time": arr_time,
                    })
            except Exception as e:
                logger.debug(f"خطا در کارت MrBilit: {e}")
                continue
        
        logger.info(f"✈️ {len(flights)} پرواز از MrBilit استخراج شد")
        return flights


# ================================
# 📗 Ghasedak24 Pipeline
# ================================
class GhasedakPipeline(PipelineBase):
    """Scraper برای سایت Ghasedak24"""
    
    def __init__(self):
        super().__init__("Ghasedak24", "price_ghasedak")
        self.HEADLESS = False
    
    def build_url(self, origin_iata, dest_iata, date_gregorian, passengers, international=False):
        return f"https://ghasedak24.com/flights/{origin_iata}-{dest_iata}?date-time={date_gregorian}&adult-count={passengers}&child-count=0&infant-count=0"
    
    def parse_flights(self, html):
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("div.ghk-grid.ghk-grid-cols-12")
        flights = []
        
        for c in cards:
            try:
                airline = safe_get_text(c.select_one("div.ghk-flex.ghk-flex-col.ghk-items-center span.ghk-text-xs14"))
                
                times = c.select("div.ghk-flex.ghk-items-center.ghk-text-md22")
                dep_time = times[0].text.strip() if len(times) > 0 else None
                arr_time = times[1].text.strip() if len(times) > 1 else None
                
                airport_spans = c.select("span.ghk-text-sm14")
                origin = clean_city_name(airport_spans[0].text.strip() if len(airport_spans) > 0 else None)
                dest = clean_city_name(airport_spans[1].text.strip() if len(airport_spans) > 1 else None)
                
                price_tag = c.select_one("span.ghk-text-md22.ghk-text-blue-primary")
                price = None
                if price_tag:
                    txt = price_tag.text.replace(",", "").replace("٬", "").strip()
                    if txt.isdigit():
                        price = int(txt)
                
                aircraft_class = None
                class_divs = c.select("div.ghk-hidden.xl\\:ghk-flex.ghk-justify-center.ghk-gap-x-2 div")
                for div_tag in class_divs:
                    txt = div_tag.get_text(strip=True)
                    aircraft_class = normalize_aircraft_class(txt)
                    if aircraft_class:
                        break
                
                if airline and price and dep_time:
                    flights.append({
                        "airline": airline,
                        "aircraft_class": aircraft_class,
                        "departure_time": dep_time,
                        "arrival_time": arr_time,
                        "origin_name": origin,
                        "dest_name": dest,
                        "price": price,
                    })
            except Exception as e:
                logger.debug(f"خطا در کارت Ghasedak: {e}")
                continue
        
        logger.info(f"✈️ {len(flights)} پرواز از Ghasedak استخراج شد")
        return flights


# ================================
# 📘 FlyToday Pipeline
# ================================
class FlytodayPipeline(PipelineBase):
    """Scraper برای سایت FlyToday - نسخه تست‌شده و کامل"""
    
    def __init__(self):
        super().__init__("FlyToday", "price_flytoday")
        self.HEADLESS = True  # می‌تونی برای تست False کنی
    
    def build_url(self, origin_iata, dest_iata, date_gregorian, passengers, international=False):
        """ساخت URL برای Flytoday"""
        is_domestic = "true" if not international else "false"
        origin_param = f"{origin_iata.lower()},1"
        dest_param = f"{dest_iata.lower()},1"
        
        return (
            f"https://www.flytoday.ir/flight/search?"
            f"departure={origin_param}&arrival={dest_param}&"
            f"departureDate={date_gregorian}&"
            f"adt={passengers}&chd=0&inf=0&cabin=1&"
            f"isDomestic={is_domestic}&isAnyWhere=false"
        )
    
    async def fetch_and_parse(self, url):
        """
        ⭐ نسخه تست‌شده که کار می‌کنه - با استخراج دقیق قیمت
        """
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.HEADLESS)
            page = await browser.new_page()
            
            try:
                logger.info("🔄 در حال باز کردن صفحه Flytoday...")
                await page.goto(url, timeout=60000)
                logger.info("✅ صفحه باز شد")
            except Exception as e:
                logger.error(f"⚠️ خطا در لود صفحه Flytoday: {e}")
                await browser.close()
                return []
            
            # ⏳ صبر بیشتر (مثل کد تستی که کار می‌کرد)
            logger.info("⏳ صبر 10 ثانیه برای لود کامل...")
            await asyncio.sleep(10)
            
            # 🔍 چک تعداد کارت‌ها
            try:
                card_count = await page.locator("div.w-full.flex.justify-between.gap-2").count()
                logger.info(f"🔍 تعداد کارت‌های یافت شده: {card_count}")
                
                if card_count == 0:
                    logger.warning("❌ هیچ کارتی پیدا نشد!")
                    await browser.close()
                    return []
            except Exception as e:
                logger.warning(f"⚠️ خطا در شمارش کارت‌ها: {e}")
            
            # دریافت HTML
            content = await page.content()
            await browser.close()
            
            # پارس کردن
            soup = BeautifulSoup(content, "html.parser")
            flight_cards = soup.select("div.w-full.flex.justify-between.gap-2")
            flights = []
            
            logger.info(f"✅ شروع پردازش {len(flight_cards)} کارت...")
            
            for idx, f in enumerate(flight_cards):
                try:
                    # زمان حرکت و رسیدن
                    time_div = f.select_one("div.relative.text-gray-900")
                    if not time_div:
                        logger.debug(f"⚠️ کارت {idx}: time_div پیدا نشد")
                        continue
                    
                    times = [t.get_text(strip=True) for t in time_div.select("div.inline-block.relative")]
                    if len(times) < 2:
                        logger.debug(f"⚠️ کارت {idx}: زمان‌ها کافی نیست - {times}")
                        continue
                    departure_time, arrival_time = times[0], times[1]
                    
                    # مبدا و مقصد
                    route_div = f.select_one("div.text-nowrap.text-xs.md\\:text-sm.text-gray-700.font-medium")
                    if not route_div:
                        logger.debug(f"⚠️ کارت {idx}: route_div پیدا نشد")
                        continue
                    
                    cities_raw = [c.get_text(strip=True) for c in route_div.select("div.inline-block.relative")]
                    if len(cities_raw) < 2:
                        logger.debug(f"⚠️ کارت {idx}: شهرها کافی نیست - {cities_raw}")
                        continue
                    
                    origin_name = re.sub(r"\s*\(.*?\)", "", cities_raw[0]).strip()
                    dest_name = re.sub(r"\s*\(.*?\)", "", cities_raw[1]).strip()
                    
                    # ایرلاین
                    airline_div = f.select_one("span.text-xs.text-gray-700.font-semibold.text-nowrap")
                    airline = airline_div.get_text(strip=True) if airline_div else "نامشخص"
                    
                    # کلاس پروازی
                    aircraft_class_div = f.select_one("span.text-xs.text-gray-700.font-noraml.ms-0\\.5")
                    aircraft_class = aircraft_class_div.get_text(strip=True) if aircraft_class_div else None
                    
                    # 💰 قیمت - روش دقیق‌تر
                    price = None
                    all_spans = f.find_all("span")
                    
                    # روش اول: جستجوی عدد 6-9 رقمی
                    for span in all_spans:
                        text = span.get_text(strip=True).replace(",", "").replace("٬", "")
                        digits = re.sub(r"[^\d]", "", text)
                        # قیمت معمولاً 6-8 رقمی
                        if digits and len(digits) >= 6 and len(digits) <= 9:
                            price = int(digits)
                            break
                    
                    # روش دوم: اگر پیدا نشد، جستجوی دقیق‌تر
                    if not price:
                        for span in all_spans:
                            text = span.get_text(strip=True)
                            # اگه "تومان" یا عدد بزرگ داره
                            if "تومان" in text or "ریال" in text:
                                digits = re.sub(r"[^\d]", "", text)
                                if digits and len(digits) >= 5:
                                    price = int(digits)
                                    break
                    
                    if not price:
                        logger.debug(f"⚠️ کارت {idx}: قیمت پیدا نشد - {airline}")
                        if idx < 3:  # فقط 3 تای اول debug کن
                            span_texts = [s.get_text(strip=True)[:30] for s in all_spans[:15]]
                            logger.debug(f"   📝 Spans: {span_texts}")
                        continue
                    
                    # شماره پرواز (اختیاری)
                    flight_number = None
                    
                    flights.append({
                        "flight_number": flight_number,
                        "price": price,
                        "airline": airline,
                        "aircraft_class": aircraft_class,
                        "departure_time": departure_time,
                        "arrival_time": arrival_time,
                        "origin_name": origin_name,
                        "dest_name": dest_name,
                    })
                    
                    if idx < 3:  # اولی‌ها رو چاپ کن برای debug
                        logger.debug(f"✅ کارت {idx}: {airline} | {departure_time}-{arrival_time} | {price:,} تومان")
                    
                except Exception as e:
                    logger.debug(f"⚠️ خطا در کارت {idx}: {e}")
                    continue
            
            logger.info(f"✈️ {len(flights)} پرواز از FlyToday استخراج شد")
            return flights
    
    async def fetch_html(self, url, wait_selector=None):
        """این متد دیگه استفاده نمیشه - fetch_and_parse رو استفاده می‌کنیم"""
        pass
    
    def parse_flights(self, html):
        """این متد دیگه استفاده نمیشه - fetch_and_parse رو استفاده می‌کنیم"""
        pass


# ================================
# 📙 SnappTrip Pipeline
# ================================
class SnappTripPipeline(PipelineBase):
    """Scraper برای سایت SnappTrip"""
    
    def __init__(self):
        super().__init__("SnappTrip", "price_snapptrip")
    
    def build_url(self, origin_iata, dest_iata, date_jalali, passengers, international=False):
        return (
            f"https://www.snapptrip.com/flights/{origin_iata}_city/{dest_iata}_city"
            f"?adultCount={passengers}&childCount=0&infantCount=0"
            f"&cabinType=ECONOMY&dateType=jalali&departureDate={date_jalali}"
            f"&tripType=oneway&originCode={origin_iata}&destinationCode={dest_iata}"
        )
    
    async def fetch_html(self, url, wait_selector="article[data-testid='solution-card']"):
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.HEADLESS,
                args=["--disable-blink-features=AutomationControlled"]
            )
            page = await browser.new_page()
            await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
            
            await page.goto(url, timeout=120000)
            
            try:
                await page.wait_for_selector(wait_selector, timeout=15000)
            except:
                logger.warning("کارت‌های SnappTrip پیدا نشدن")
            
            # کلیک روی دکمه "مشاهده بیشتر"
            more_selector = "button.button.round.md.secondary.outline"
            for _ in range(20):
                try:
                    btn = await page.query_selector(more_selector)
                    if btn:
                        await btn.click()
                        await asyncio.sleep(1.0)
                    else:
                        break
                except:
                    break
                await page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
                await asyncio.sleep(0.5)
            
            html = await page.content()
            await browser.close()
            return html
    
    def parse_flights(self, html):
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.find_all("article", {"data-testid": "solution-card"})
        flights = []
        
        for card in cards:
            try:
                dep_time = persian_to_latin_digits(
                    safe_get_text(card.find("div", {"data-testid": "solution-departure-time"}))
                )
                arr_time = persian_to_latin_digits(
                    safe_get_text(card.find("div", {"data-testid": "solution-arrival-time"}))
                )
                airline = safe_get_text(card.find("span", {"data-testid": "solution-airline-name"}))
                
                cabin_tag = card.find("span", string=lambda s: s and ("اکونومی" in s or "بیزینس" in s))
                cabin = normalize_aircraft_class(safe_get_text(cabin_tag)) if cabin_tag else "اکونومی"
                
                price_tag = card.find("div", {"data-testid": "solution-price"})
                price = None
                if price_tag:
                    price_clean = re.sub(r"[^\d]", "", price_tag.get_text(strip=True))
                    price = int(price_clean) if price_clean else None
                
                if price and airline and dep_time:
                    flights.append({
                        "departure_time": dep_time,
                        "arrival_time": arr_time,
                        "airline": airline,
                        "aircraft_class": cabin,
                        "price": price
                    })
            except Exception as e:
                logger.debug(f"خطا در کارت SnappTrip: {e}")
                continue
        
        logger.info(f"✈️ {len(flights)} پرواز از SnappTrip استخراج شد")
        return flights


# ================================
# 📕 Eligasht Pipeline
# ================================
class EligashtPipeline(PipelineBase):
    """Scraper برای سایت Eligasht"""
    
    def __init__(self):
        super().__init__("Eligasht", "price_eligasht")
    
    def build_url(self, origin_iata, dest_iata, date_gregorian, passengers, international=False):
        dest_segment = dest_iata.lower()
        return (
            f"https://www.eligasht.com/flights/{dest_segment}"
            f"?trip={origin_iata}-{dest_iata}-{date_gregorian}&Adult={passengers}&Child=0&Infant=0&FlightClass=Economy"
        )
    
    async def fetch_html(self, url, wait_selector="li[data-id]"):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.HEADLESS)
            page = await browser.new_page()
            
            try:
                await page.goto(url, timeout=120000, wait_until="domcontentloaded")
            except Exception as e:
                logger.error(f"خطا در باز کردن Eligasht: {e}")
            
            try:
                await page.wait_for_selector(wait_selector, timeout=15000)
            except:
                for _ in range(6):
                    await page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
                    await asyncio.sleep(0.8)
            
            await asyncio.sleep(1.2)
            html = await page.content()
            await browser.close()
            return html
    
    def parse_flights(self, html):
        soup = BeautifulSoup(html, "html.parser")
        items = soup.find_all("li", attrs={"data-id": True})
        flights = []
        
        for li in items:
            try:
                if not li.find(class_=lambda c: c and "resultFlight_ticket_flight_main_list_content" in c):
                    continue
                
                airline = safe_get_text(
                    li.find("div", class_=lambda c: c and "airline_name" in c)
                )
                
                times_found = re.findall(r"(\d{1,2}:\d{2})", li.get_text())
                dep_time = times_found[0] if len(times_found) >= 1 else None
                arr_time = times_found[1] if len(times_found) >= 2 else None
                
                flight_no = extract_flight_number(li.get_text())
                
                text_all = li.get_text(" ", strip=True)
                aircraft_class = normalize_aircraft_class(text_all) or "اکونومی"
                
                price_tag = li.find("b", class_=lambda c: c and "price" in c)
                price = None
                if price_tag:
                    price_clean = re.sub(r"[^\d]", "", price_tag.get_text())
                    price = int(price_clean) if price_clean else None
                
                if price and airline and dep_time:
                    flights.append({
                        "flightNumber": flight_no,
                        "priceAdult": price,
                        "airlineName": airline,
                        "classTypeName": aircraft_class,
                        "leaveDateTime": dep_time,
                        "arrivalDateTime": arr_time,
                    })
            except Exception as e:
                logger.debug(f"خطا در کارت Eligasht: {e}")
                continue
        
        logger.info(f"✈️ {len(flights)} پرواز از Eligasht استخراج شد")
        return flights


# ================================
# 📗 Ultravs Pipeline
# ================================
class UltravsPipeline(PipelineBase):
    """Scraper برای سایت Ultravs"""
    
    def __init__(self):
        super().__init__("Ultravs", "price_ultravs")
    
    def build_url(self, origin_city, dest_city, date_gregorian, passengers, international=False):
        return (
            f"https://utravs.com/flight-search/"
            f"{origin_city}-to-{dest_city}?&adult={passengers}&child=0&infant=0&departing={date_gregorian}&ticketType=OneWay"
        )
    
    async def fetch_html(self, url, wait_selector="div.relative.grid.bg-white"):
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.HEADLESS,
                args=["--disable-blink-features=AutomationControlled"]
            )
            page = await browser.new_page()
            await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
            
            await page.goto(url, timeout=120000)
            
            try:
                await page.wait_for_selector(wait_selector, timeout=25000)
            except:
                logger.warning("کارت‌های Ultravs در بارگذاری اولیه پیدا نشدن")
            
            html = await page.content()
            await browser.close()
            return html
    
    def parse_flights(self, html):
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("div.relative.grid.bg-white")
        flights = []
        
        for c in cards:
            try:
                airline = safe_get_text(c.select_one("span.font-medium.text-md"))
                
                time_tags = c.select("strong.font-bold.text-base")
                dep_time = persian_to_latin_digits(safe_get_text(time_tags[0])) if len(time_tags) > 0 else None
                arr_time = persian_to_latin_digits(safe_get_text(time_tags[1])) if len(time_tags) > 1 else None
                
                class_tag = c.find(string=lambda s: s and ("بیزینس" in s or "بیزنس" in s))
                aircraft_class = "بیزینس" if class_tag else "اکونومی"
                
                price_tag = c.select_one("strong.font-bold.text-lg, strong.font-bold.text-xl")
                price = None
                if price_tag:
                    txt = persian_to_latin_digits(price_tag.get_text(strip=True))
                    txt = re.sub(r"[^\d]", "", txt)
                    if txt.isdigit():
                        price = int(txt)
                
                if airline and price and dep_time:
                    flights.append({
                        "airline": airline,
                        "aircraft_class": aircraft_class,
                        "departure_time": dep_time,
                        "arrival_time": arr_time,
                        "price": price
                    })
            except Exception as e:
                logger.debug(f"خطا در کارت Ultravs: {e}")
                continue
        
        logger.info(f"✈️ {len(flights)} پرواز از Ultravs استخراج شد")
        return flights


# ================================
# 📦 لیست تمام Pipelines
# ================================
ALL_PIPELINES = [
    AlibabaPipeline,
    Charter118Pipeline,
    FlightioPipeline,
    MrBilitPipeline,
    GhasedakPipeline,
    FlytodayPipeline,
    SnappTripPipeline,
    EligashtPipeline,
    UltravsPipeline
]