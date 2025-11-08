"""
پیاده‌سازی pipeline های مختلف برای هر سایت
"""
import asyncio
import re
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from base_pipeline import PipelineBase
from utils import persian_to_latin_digits, normalize_price, normalize_airport_to_city


# =====================================
# ALIBABA PIPELINE
# =====================================
class AlibabaPipeline(PipelineBase):
    def __init__(self):
        super().__init__("Alibaba", "Flights_Alibaba", "price_alibaba")
    
    async def get_api_url(self, search_url: str) -> str:
        """دریافت URL API علی‌بابا از طریق شنود درخواست‌ها"""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            api_url = None
            
            def handle_request(req):
                nonlocal api_url
                try:
                    if "api/v1/flights/domestic/available" in req.url:
                        api_url = req.url
                except Exception:
                    pass
            
            page.on("request", handle_request)
            
            try:
                await page.goto(search_url, timeout=60000)
            except Exception as e:
                print(f"⚠️ خطا در باز کردن صفحه علی‌بابا: {e}")
            
            await page.wait_for_timeout(5000)
            await browser.close()
            
            return api_url
    
    async def fetch_flights(self, origin_iata: str, dest_iata: str, 
                          date_shamsi: str, passengers: int, international: bool = False) -> list:
        """دریافت مستقیم پروازها از API"""
        base_url = "https://www.alibaba.ir/international" if international else "https://www.alibaba.ir/flights"
        search_url = f"{base_url}/{origin_iata}-{dest_iata}?adult={passengers}&child=0&infant=0&departing={date_shamsi}"
        
        api_url = await self.get_api_url(search_url)
        if not api_url:
            print("❌ نتوانستم آدرس API علی‌بابا را پیدا کنم.")
            return []
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            
            try:
                response = await context.request.get(api_url)
                data = await response.json()
            except Exception as e:
                print(f"⚠️ خطا در دریافت JSON از API علی‌بابا: {e}")
                await context.close()
                return []
            
            await context.close()
        
        if not data.get("success") or not data["result"].get("departing"):
            print("⚠️ داده‌ای از API علی‌بابا دریافت نشد.")
            return []
        
        flights = []
        for f in data["result"]["departing"]:
            try:
                # فیلتر پروازهای بدون ظرفیت
                seats = f.get("seat") or 0
                if seats == 0:
                    continue
                
                flights.append({
                    "flight_number": f.get("flightNumber"),
                    "airline": f.get("airlineName"),
                    "departure_city": f.get("originName"),
                    "arrival_city": f.get("destinationName"),
                    "leaveDateTime": f.get("leaveDateTime"),
                    "arrivalDateTime": f.get("arrivalDateTime"),
                    "aircraft_class": f.get("classTypeName"),
                    "price": f.get("priceAdult"),
                })
            except Exception as e:
                print(f"⚠️ خطا در پردازش پرواز از علی‌بابا: {e}")
                continue
        
        print(f"✅ {len(flights)} پرواز از علی‌بابا استخراج شد.")
        return flights


# =====================================
# CHARTER118 PIPELINE
# =====================================
class Charter118Pipeline(PipelineBase):
    def __init__(self):
        super().__init__("Charter118", "Flights_Charter118", "price_charter118")
    
    def build_url(self, origin_iata: str, dest_iata: str, 
                  date: str, passengers: int, international: bool = False) -> str:
        base = "https://charter118.ir/international-flights" if international else "https://charter118.ir/flights"
        return f"{base}/{origin_iata}-{dest_iata}?adult={passengers}&child=0&infant=0&departing={date}"
    
    async def fetch_html(self, url: str, wait_selector: str = None) -> str:
        """override با اسکرول بیشتر برای بارگذاری تمام پروازها"""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            context = await browser.new_context()
            page = await context.new_page()
            
            await page.goto(url, timeout=120000)
            
            if wait_selector:
                try:
                    await page.wait_for_selector(wait_selector, timeout=20000)
                except:
                    print("⚠️ المان پیدا نشد - سعی به اسکرول")
            
            # اسکرول برای بارگذاری lazy
            for _ in range(6):
                await page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
                await asyncio.sleep(1)
            
            html = await page.content()
            await browser.close()
            
            return html
    
    def parse_flights(self, html: str) -> list:
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.find_all("div", class_=lambda c: c and "bg-white" in c and "rounded-lg" in c)
        flights = []
        
        for card in cards:
            try:
                # کلاس پرواز
                tags = card.find_all("p", class_=lambda c: c and "bg-blue-400/10" in c)
                tag_texts = [t.text.strip() for t in tags]
                aircraft_class = next((t for t in tag_texts if "اکونومی" in t or "بیزینس" in t), None)
                
                # شماره پرواز
                num_tag = card.find("p", class_=lambda c: c and "bg-gray-400/10" in c)
                flight_number = num_tag.text.strip() if num_tag else None
                
                # ایرلاین
                airline_tag = card.find("p", class_=lambda c: c and "text-darkGray" in c and "text-center" in c)
                airline = airline_tag.text.strip() if airline_tag else None
                
                # زمان‌ها
                times = card.find_all("span", class_=lambda c: c and "text-black" in c and "text-xl" in c)
                departure_time = times[0].text.strip() if times else None
                arrival_time = times[1].text.strip() if len(times) > 1 else None
                
                # قیمت
                price_tag = card.find("p", class_=lambda c: c and "text-green-700" in c)
                price = normalize_price(price_tag.text) if price_tag else None
                
                if airline and departure_time and price:
                    flights.append({
                        "flight_number": flight_number,
                        "price": price,
                        "airline": airline,
                        "aircraft_class": aircraft_class,
                        "departure_time": departure_time,
                        "arrival_time": arrival_time
                    })
            except Exception:
                continue
        
        return flights


# =====================================
# FLIGHTIO PIPELINE
# =====================================
class FlightioPipeline(PipelineBase):
    def __init__(self):
        super().__init__("Flightio", "Flights_Flightio", "price_flightio")
        self.headless = False  # برای تست بهتر است
    
    def build_url(self, origin_iata: str, dest_iata: str, 
                  date: str, passengers: int, international: bool = False) -> str:
        flight_type = 1 if international else 2
        return (
            f"https://flightio.com/flight/{origin_iata}-{dest_iata}"
            f"?depart={date}&adult={passengers}&child=0&infant=0"
            f"&flightType={flight_type}&cabinType=1"
        )
    
    async def fetch_html(self, url: str, wait_selector: str = "section.transition-input-100") -> str:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.headless,
                args=["--disable-blink-features=AutomationControlled"]
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = await context.new_page()
            await page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            )
            
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=120000)
            except Exception as e:
                print(f"⚠️ خطا در باز کردن صفحه فلاییتو: {e}")
            
            try:
                await page.wait_for_selector(wait_selector, timeout=120000)
            except Exception:
                print("⚠️ پرواز نمایش داده نشد یا سایت Bot رو فهمید")
            
            # اسکرول
            for _ in range(8):
                await page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
                await asyncio.sleep(1)
            
            await asyncio.sleep(2)
            html = await page.content()
            await browser.close()
            
            return html
    
    def parse_flights(self, html: str) -> list:
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.find_all("section", class_=lambda c: c and "transition-input-100" in c)
        flights = []
        
        for card in cards:
            try:
                def safe_text(find):
                    return find.text.strip() if find else None
                
                airline = safe_text(card.find("span", class_=lambda c: c and "text-body-m" in c))
                
                # شماره پرواز
                flight_number = None
                flight_info = card.find_all("span", string=re.compile("پرواز شماره"))
                if flight_info:
                    flight_number = re.sub(r"[^\d]", "", flight_info[0].text)
                
                # قیمت
                price_span = card.find("span", class_=lambda c: c and "font-bold" in c)
                price = None
                if price_span:
                    price_digits = re.findall(r"\d+", price_span.text.replace(",", ""))
                    if price_digits:
                        price = int(price_digits[0])
                
                # زمان‌ها
                time_spans = card.find_all("span", class_=lambda c: c and "text-title-xl" in c)
                dep_time = safe_text(time_spans[0]) if len(time_spans) > 0 else None
                arr_time = safe_text(time_spans[1]) if len(time_spans) > 1 else None
                
                # کلاس
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
                print(f"⚠️ خطا در کارت: {e}")
                continue
        
        print(f"✈️ {len(flights)} پرواز از فلاییتو استخراج شد")
        return flights


# =====================================
# MRBILIT PIPELINE
# =====================================
class MrBilitPipeline(PipelineBase):
    def __init__(self):
        super().__init__("MrBilit", "Flights_MrBilit", "price_mrbilit")
        self.headless = False
    
    def build_url(self, origin_iata: str, dest_iata: str, 
                  date: str, passengers: int, international: bool = False) -> str:
        # MrBilit از تاریخ شمسی استفاده می‌کند
        return f"https://mrbilit.com/flights/{origin_iata}-{dest_iata}?departureDate={date}"
    
    async def fetch_html(self, url: str, wait_selector: str = ".trip-package-info") -> str:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            context = await browser.new_context()
            page = await context.new_page()
            
            try:
                await page.goto(url, timeout=60000)
            except Exception as e:
                print(f"⚠️ خطا در باز کردن مستربلیت: {e}")
            
            try:
                await page.wait_for_selector(wait_selector, timeout=20000)
            except:
                print("⚠️ پروازی نمایش داده نشد در مستربلیت")
            
            # اسکرول
            for _ in range(5):
                await page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
                await asyncio.sleep(0.8)
            
            html = await page.content()
            await browser.close()
            
            return html
    
    def parse_flights(self, html: str) -> list:
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select(".trip-package-info")
        flights = []
        
        for card in cards:
            try:
                origin = card.select(".locations p")[0].text.strip()
                destination = card.select(".locations p")[1].text.strip()
                dep_time = card.select(".time")[0].text.strip()
                
                arr_time = None
                time_nodes = card.select(".time")
                if len(time_nodes) > 1:
                    arr_time = time_nodes[1].text.strip()
                
                airline_tag = card.select_one("div.title-container p")
                airline = airline_tag.text.strip() if airline_tag else "نامشخص"
                
                # قیمت
                price_tag = card.select_one(".price")
                if not price_tag:
                    continue
                price = normalize_price(price_tag.text)
                
                # کلاس پرواز
                class_tag = (
                    card.select_one(".badge") or
                    card.select_one(".ticket-type") or
                    card.select_one(".cabin-type") or
                    card.find(string=lambda t: "اکونومی" in t or "بیزینس" in t or "Economy" in t or "Business" in t)
                )
                
                aircraft_class = None
                if class_tag:
                    txt = class_tag.get_text(strip=True) if hasattr(class_tag, "get_text") else str(class_tag)
                    if "اکونومی" in txt or "Economy" in txt:
                        aircraft_class = "اکونومی"
                    elif "بیزینس" in txt or "Business" in txt:
                        aircraft_class = "بیزینس"
                
                flights.append({
                    "flight_number": None,
                    "price": price,
                    "airline": airline,
                    "aircraft_class": aircraft_class,
                    "departure_time": dep_time,
                    "arrival_time": arr_time,
                    "origin": origin,
                    "destination": destination,
                })
            except Exception as e:
                print(f"⚠️ خطا در کارت مستربلیت: {e}")
                continue
        
        print(f"✈️ {len(flights)} پرواز از مستربلیت استخراج شد")
        return flights


# =====================================
# GHASEDAK PIPELINE
# =====================================
class GhasedakPipeline(PipelineBase):
    def __init__(self):
        super().__init__("Ghasedak24", "Flights_Ghasedak24", "price_ghasedak")
        self.headless = False
    
    def build_url(self, origin_iata: str, dest_iata: str, 
                  date: str, passengers: int, international: bool = False) -> str:
        return (
            f"https://ghasedak24.com/flights/{origin_iata}-{dest_iata}"
            f"?date-time={date}&adult-count={passengers}&child-count=0&infant-count=0"
        )
    
    async def fetch_html(self, url: str, wait_selector: str = "div.ghk-grid.ghk-grid-cols-12") -> str:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            context = await browser.new_context()
            page = await context.new_page()
            
            try:
                await page.goto(url, timeout=120000)
                await page.wait_for_selector(wait_selector, timeout=60000)
                await asyncio.sleep(2)
            except Exception as e:
                print(f"⚠️ خطا در بارگذاری صفحه Ghasedak: {e}")
            
            html = await page.content()
            await browser.close()
            return html
    
    def parse_flights(self, html: str) -> list:
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("div.ghk-grid.ghk-grid-cols-12")
        flights = []
        
        for c in cards:
            try:
                airline_tag = c.select_one("div.ghk-flex.ghk-flex-col.ghk-items-center span.ghk-text-xs14")
                airline = airline_tag.text.strip() if airline_tag else None
                
                times = c.select("div.ghk-flex.ghk-items-center.ghk-text-md22")
                dep_time = times[0].text.strip() if len(times) > 0 else None
                arr_time = times[1].text.strip() if len(times) > 1 else None
                
                airport_spans = c.select("span.ghk-text-sm14")
                origin = normalize_airport_to_city(airport_spans[0].text.strip()) if len(airport_spans) > 0 else None
                dest = normalize_airport_to_city(airport_spans[1].text.strip()) if len(airport_spans) > 1 else None
                
                price_tag = c.select_one("span.ghk-text-md22.ghk-text-blue-primary")
                price = normalize_price(price_tag.text) if price_tag else None
                
                # کلاس پرواز
                aircraft_class = None
                class_divs = c.select("div.ghk-hidden.xl\\:ghk-flex.ghk-justify-center.ghk-gap-x-2 div")
                for div_tag in class_divs:
                    txt = div_tag.get_text(strip=True)
                    if any(word in txt for word in ["اکونومی", "Economy"]):
                        aircraft_class = "اکونومی"
                        break
                    elif any(word in txt for word in ["بیزینس", "بیزنس", "Business"]):
                        aircraft_class = "بیزینس"
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
                print(f"⚠️ خطا در کارت Ghasedak: {e}")
                continue
        
        print(f"✈️ {len(flights)} پرواز از Ghasedak استخراج شد")
        return flights


# =====================================
# FLYTODAY PIPELINE
# =====================================
class FlytodayPipeline(PipelineBase):
    def __init__(self):
        super().__init__("FlyToday", "Flights_Flytoday", "price_flytoday")
        self.headless = False
    
    def build_url(self, origin_iata: str, dest_iata: str, 
                  date: str, passengers: int, international: bool = False) -> str:
        is_domestic = "true" if not international else "false"
        origin_param = f"{origin_iata.lower()},1"
        dest_param = f"{dest_iata.lower()},1"
        
        return (
            f"https://www.flytoday.ir/flight/search?"
            f"departure={origin_param}&arrival={dest_param}&"
            f"departureDate={date}&"
            f"adt={passengers}&chd=0&inf=0&cabin=1&"
            f"isDomestic={is_domestic}&isAnyWhere=false"
        )
    
    async def fetch_and_parse(self, url: str) -> list:
        """دریافت و پارس در یک مرحله"""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            page = await browser.new_page()
            
            try:
                await page.goto(url, timeout=60000)
                await asyncio.sleep(10)  # صبر برای بارگذاری کامل
            except Exception as e:
                print(f"⚠️ خطا در لود صفحه Flytoday: {e}")
                await browser.close()
                return []
            
            content = await page.content()
            await browser.close()
            
            # پارس
            soup = BeautifulSoup(content, "html.parser")
            flight_cards = soup.select("div.w-full.flex.justify-between.gap-2")
            flights = []
            
            for idx, f in enumerate(flight_cards):
                try:
                    # زمان‌ها
                    time_div = f.select_one("div.relative.text-gray-900")
                    if not time_div:
                        continue
                    times = [t.get_text(strip=True) for t in time_div.select("div.inline-block.relative")]
                    if len(times) < 2:
                        continue
                    departure_time, arrival_time = times[0], times[1]
                    
                    # مبدا و مقصد
                    route_div = f.select_one("div.text-nowrap.text-xs.md\\:text-sm.text-gray-700.font-medium")
                    if not route_div:
                        continue
                    cities_raw = [c.get_text(strip=True) for c in route_div.select("div.inline-block.relative")]
                    if len(cities_raw) < 2:
                        continue
                    origin_name = re.sub(r"\s*\(.*?\)", "", cities_raw[0]).strip()
                    dest_name = re.sub(r"\s*\(.*?\)", "", cities_raw[1]).strip()
                    
                    # ایرلاین
                    airline_div = f.select_one("span.text-xs.text-gray-700.font-semibold.text-nowrap")
                    airline = airline_div.get_text(strip=True) if airline_div else "نامشخص"
                    
                    # کلاس
                    aircraft_class_div = f.select_one("span.text-xs.text-gray-700.font-noraml.ms-0\\.5")
                    aircraft_class = aircraft_class_div.get_text(strip=True) if aircraft_class_div else None
                    
                    # قیمت
                    price = None
                    all_spans = f.find_all("span")
                    for span in all_spans:
                        text = span.get_text(strip=True).replace(",", "").replace("٬", "")
                        digits = re.sub(r"[^\d]", "", text)
                        if digits and len(digits) >= 6 and len(digits) <= 9:
                            price = int(digits)
                            break
                    
                    if not price:
                        continue
                    
                    flights.append({
                        "price": price,
                        "airline": airline,
                        "aircraft_class": aircraft_class,
                        "departure_time": departure_time,
                        "arrival_time": arrival_time,
                        "origin_name": origin_name,
                        "dest_name": dest_name,
                    })
                except Exception as e:
                    continue
            
            print(f"✈️ {len(flights)} پرواز از FlyToday استخراج شد")
            return flights


# =====================================
# SNAPPTRIP PIPELINE
# =====================================
class SnappTripPipeline(PipelineBase):
    def __init__(self):
        super().__init__("SnappTrip", "Flights_SnappTrip", "price_snapptrip")
        self.headless = False
    
    def build_url(self, origin_iata: str, dest_iata: str, 
                  date: str, passengers: int, international: bool = False) -> str:
        return (
            f"https://www.snapptrip.com/flights/{origin_iata}_city/{dest_iata}_city"
            f"?adultCount={passengers}&childCount=0&infantCount=0"
            f"&cabinType=ECONOMY&dateType=jalali&departureDate={date}"
            #f"&tripType=oneway&originCode={origin_iata}&destinationCode={dest_iata}"
        )
    #https://www.snapptrip.com/flights/THR_city/MHD_city?
    # adultCount=1&childCount=0&infantCount=0&cabinType=ECONOMY&dateType=jalali&departureDate=2025-11-12
    # &tripType=oneway&originCode=THR&originCity=Tehran&originCityName=
    # %D8%AA%D9%87%D8%B1%D8%A7%D9%86&destinationCode=MHD&destinationCity=Mashhad&
    # destinationCityName=%D9%85%D8%B4%D9%87%D8%AF&source=searchBox
    async def fetch_html(self, url: str, wait_selector: str = "article[data-testid='solution-card']") -> str:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.headless,
                args=["--disable-blink-features=AutomationControlled"]
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = await context.new_page()
            await page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            )
            
            await page.goto(url, timeout=120000)
            
            try:
                await page.wait_for_selector(wait_selector, timeout=15000)
            except:
                print("⚠️ کارت‌ها پیدا نشدن")
            
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
    
    def parse_flights(self, html: str) -> list:
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.find_all("article", {"data-testid": "solution-card"})
        flights = []
        
        for card in cards:
            try:
                dep_time_tag = card.find("div", {"data-testid": "solution-departure-time"})
                arr_time_tag = card.find("div", {"data-testid": "solution-arrival-time"})
                airline_tag = card.find("span", {"data-testid": "solution-airline-name"})
                cabin_tag = card.find("span", string=lambda s: s and ("اکونومی" in s or "بیزینس" in s))
                price_tag = card.find("div", {"data-testid": "solution-price"})
                
                dep_time = persian_to_latin_digits(dep_time_tag.get_text(strip=True)) if dep_time_tag else None
                arr_time = persian_to_latin_digits(arr_time_tag.get_text(strip=True)) if arr_time_tag else None
                airline = airline_tag.get_text(strip=True) if airline_tag else None
                
                cabin = cabin_tag.get_text(strip=True) if cabin_tag else None
                if cabin:
                    if "بیزنس" in cabin or "بیزینس" in cabin:
                        cabin = "بیزینس"
                    elif "اکونومی" in cabin:
                        cabin = "اکونومی"
                
                price = normalize_price(price_tag.get_text()) if price_tag else None
                
                if not price:
                    continue
                
                flights.append({
                    "departure_time": dep_time,
                    "arrival_time": arr_time,
                    "airline": airline,
                    "aircraft_class": cabin,
                    "price": price
                })
            except Exception as e:
                continue
        
        print(f"✈️ {len(flights)} پرواز از SnappTrip استخراج شد")
        return flights


# =====================================
# ELIGASHT PIPELINE
# =====================================
class EligashtPipeline(PipelineBase):
    def __init__(self):
        super().__init__("Eligasht", "Flights_Eligasht", "price_eligasht")
        self.headless = True
    
    def build_url(self, origin_iata: str, dest_iata: str, 
                  date: str, passengers: int, international: bool = False) -> str:
        dest_segment = dest_iata.lower()
        return (
            f"https://www.eligasht.com/flights/{dest_segment}"
            f"?trip={origin_iata}-{dest_iata}-{date}&Adult={passengers}&Child=0&Infant=0&FlightClass=Economy"
        )
    
    async def fetch_html(self, url: str, wait_selector: str = "li[data-id]") -> str:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = await context.new_page()
            
            try:
                await page.goto(url, timeout=120000, wait_until="domcontentloaded")
            except Exception as e:
                print(f"⚠️ خطا در باز کردن صفحه eligasht: {e}")
            
            try:
                await page.wait_for_selector(wait_selector, timeout=15000)
            except Exception:
                for _ in range(6):
                    await page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
                    await asyncio.sleep(0.8)
            
            await asyncio.sleep(1.2)
            html = await page.content()
            await browser.close()
            return html
    
    def parse_flights(self, html: str) -> list:
        soup = BeautifulSoup(html, "html.parser")
        items = soup.find_all("li", attrs={"data-id": True})
        flights = []
        
        for li in items:
            try:
                if not li.find(class_=lambda c: c and "resultFlight_ticket_flight_main_list_content" in c):
                    continue
                
                # ایرلاین
                airline = None
                airline_tag = li.find("div", class_=lambda c: c and "resultFlight_ticket_flight_main_list_content_box_airline_name" in c)
                if airline_tag:
                    airline = airline_tag.get_text(strip=True)
                
                # زمان‌ها
                dep_time = None
                arr_time = None
                dep_label = li.find(attrs={"aria-label": "ساعت پرواز"})
                if dep_label:
                    dep_time = dep_label.get_text(strip=True)
                arr_label = li.find(attrs={"aria-label": "زمان ورود"})
                if arr_label:
                    arr_time = arr_label.get_text(strip=True)
                
                # شماره پرواز
                footer_text = li.get_text(" ", strip=True)
                m_fno = re.search(r"شماره پرواز[:\s]*([A-Za-z0-9\-]+)", footer_text)
                flight_no = m_fno.group(1).strip() if m_fno else None
                
                # کلاس
                text_all = li.get_text(" ", strip=True)
                aircraft_class = "اکونومی"
                if re.search(r"بیزینس|business", text_all, re.IGNORECASE):
                    aircraft_class = "بیزینس"
                
                # قیمت
                price_tag = li.find("b", class_=lambda c: c and "resultFlight_ticket_flight_main_list_footer_left_price" in c)
                price = normalize_price(price_tag.get_text()) if price_tag else None
                
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
                continue
        
        print(f"✅ {len(flights)} پرواز از Eligasht استخراج شد")
        return flights


# =====================================
# ULTRAVS PIPELINE
# =====================================
class UltravsPipeline(PipelineBase):
    def __init__(self):
        super().__init__("Ultravs", "Flights_Ultravs", "price_ultravs")
        self.headless = True
    
    def build_url(self, origin_city: str, dest_city: str, 
                  date: str, passengers: int, international: bool = False) -> str:
        return (
            f"https://utravs.com/flight-search/"
            f"{origin_city}-to-{dest_city}?&adult={passengers}&child=0&infant=0&departing={date}&ticketType=OneWay"
        )
    
    async def fetch_html(self, url: str, wait_selector: str = "div.relative.grid.bg-white") -> str:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.headless,
                args=["--disable-blink-features=AutomationControlled"]
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = await context.new_page()
            await page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            )
            
            await page.goto(url, timeout=120000)
            
            try:
                await page.wait_for_selector(wait_selector, timeout=25000)
            except:
                print("⚠️ کارت‌ها در بارگذاری اولیه پیدا نشدن")
            
            html = await page.content()
            await browser.close()
            return html
    
    def parse_flights(self, html: str) -> list:
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("div.relative.grid.bg-white")
        flights = []
        
        for c in cards:
            try:
                # ایرلاین
                airline_tag = c.select_one("span.font-medium.text-md")
                airline = airline_tag.get_text(strip=True) if airline_tag else None
                
                # زمان‌ها
                time_tags = c.select("strong.font-bold.text-base")
                dep_time = persian_to_latin_digits(time_tags[0].get_text(strip=True)) if len(time_tags) > 0 else None
                arr_time = persian_to_latin_digits(time_tags[1].get_text(strip=True)) if len(time_tags) > 1 else None
                
                # کلاس
                class_tag = c.find(string=lambda s: s and ("بیزینس" in s or "بیزنس" in s))
                aircraft_class = "بیزینس" if class_tag else "اکونومی"
                
                # قیمت
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
                continue
        
        print(f"🛫 {len(flights)} پرواز از Ultravs استخراج شد")
        return flights