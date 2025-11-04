import asyncio
import pyodbc
import jdatetime
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import re

# --------------------------
# تنظیمات IATA
# --------------------------
IATA_CODES = {
    "tehran": "THR", "mashhad": "MHD", "isfahan": "IFN", "shiraz": "SYZ",
    "tabriz": "TBZ", "kish": "KIH", "ahvaz": "AWZ", "bandar abbas": "BND",
    "urmia": "OMH", "rasht": "RAS", "kermanshah": "KSH", "yazd": "AZD",
    "bushehr": "BUZ", "lar": "LRR", "sari": "SRY", "ardabil": "ADU",
    "baghdad": "BGW", "najaf": "NJF", "erbil": "EBL",
    "istanbul": "IST", "ankara": "ESB", "antalya": "AYT"
}

# --------------------------
# کلاس پایه
# --------------------------
class PipelineBase:
    def __init__(self, site_name, table_name):
        self.site_name = site_name
        self.db_name = "FlightsDB"
        self.table_name = table_name

        # رشته اتصال دیتابیس (همونی که گفتی)
        self.db_conn_str = "DRIVER={SQL Server};SERVER=localhost;DATABASE=FlightsDB;Trusted_Connection=yes;"

        # هر subclass باید این را تنظیم کند (مثلاً "price_alibaba")
        self.price_column = None

        # تنظیم headless عمومی (می توانی override کنی)
        self.HEADLESS = True

    async def fetch_html(self, url, wait_selector=None):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.HEADLESS)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36"
                )
            )
            page = await context.new_page()
            try:
                await page.goto(url, timeout=120000)
            except Exception as e:
                print("⚠️ خطا در باز کردن صفحه:", e)
            if wait_selector:
                try:
                    await page.wait_for_selector(wait_selector, timeout=120000)
                except Exception:
                    print(f"⚠️ المنت {wait_selector} پیدا نشد.")
            await asyncio.sleep(2)
            html = await page.content()
            await browser.close()
            return html

    def _extract_dep_time(self, f):
        """
        استخراج زمان حرکت بصورت 'HH:MM' یا None
        """
        dep_time_full = (f.get("leaveDateTime") or f.get("departure_time") or f.get("departureDateTime") or f.get("leave_date_time") or "").strip()
        if not dep_time_full:
            return None

        # اگر قالب ISO datetime
        if "T" in dep_time_full:
            try:
                return dep_time_full.split("T")[1][:5]
            except Exception:
                return None

        # اگر فقط تاریخ yyyy-mm-dd
        if re.match(r"^\d{4}-\d{2}-\d{2}$", dep_time_full):
            return None

        # سعی برای استخراج ساعت HH:MM از رشته
        m = re.search(r"(\d{1,2}:\d{2})", dep_time_full)
        if m:
            return m.group(1)
        # fallback: اگر طول مناسب داشت برش بزن
        return dep_time_full[:5] if len(dep_time_full) >= 5 else None

    def _extract_arr_time(self, f):
        """
        استخراج زمان رسیدن بصورت 'HH:MM' یا None
        بررسی فیلدهای ممکن: arrivalDateTime, arrival_time, arriveDateTime, arrivalDate, arrival
        """
        arr_time_full = (f.get("arrivalDateTime") or f.get("arrival_time") or f.get("arriveDateTime") or f.get("arrival") or f.get("arrive") or "").strip()
        if not arr_time_full:
            # گاهی اوقات در پارسرها دو تا تگ زمان داریم؛ اگر dict شامل 'times' یا 'departure_time' و 'arrival_time' نیست می‌بینیم
            # اما اینجا فقط از فیلدهای مستقیم استفاده می‌کنیم؛ در parserها هم سعی شده arrival_time جداگانه ارسال شود.
            return None

        if "T" in arr_time_full:
            try:
                return arr_time_full.split("T")[1][:5]
            except Exception:
                return None

        if re.match(r"^\d{4}-\d{2}-\d{2}$", arr_time_full):
            return None

        m = re.search(r"(\d{1,2}:\d{2})", arr_time_full)
        if m:
            return m.group(1)
        return arr_time_full[:5] if len(arr_time_full) >= 5 else None




    def save_to_db(self, flights, origin_city, dest_city, date_shamsi):
        """
        منطق ذخیره بازنویسی‌شده:
          - کلید strict برای UPDATE فقط وقتی اجرا می‌شود که همهٔ فیلدهای کلیدی موجود باشند:
            origin_name, dest_name, departure_date, departure_time, arrival_time, airline, aircraft_class
          - در صورت پیدا شدن رکورد: تنها ستون قیمت مربوط به این سایت آپدیت می‌شود (و airline/aircraft_class آپدیت می‌شوند).
          - در غیر این صورت INSERT جدید انجام می‌شود.
          - قیمت‌ها قبل از مقایسه به int تبدیل می‌شوند.
        """


        if not flights:
            print(f"⚠️ هیچ پروازی برای ذخیره در {self.site_name} وجود ندارد.")
            return
    
        conn = pyodbc.connect(self.db_conn_str)
        cursor = conn.cursor()
    
        inserted = 0
        updated = 0
    
        for f in flights:
            try:
                dep_time = self._extract_dep_time(f)
                arr_time = self._extract_arr_time(f)
    
                flight_no = (
                    f.get("flightNumber")
                    or f.get("flight_number")
                    or f.get("flightNo")
                    or f.get("flight_id")
                    or (f.get("description", "").split("|")[0].strip() if f.get("description") and "|" in f.get("description") else None)
                    or f.get("flight_no")
                )
    
                airline = f.get("airlineName") or f.get("airline") or f.get("airline_name") or "نامشخص"

                # 🧩 نرمال‌سازی نام ایرلاین‌ها (همسان‌سازی حالت‌های مختلف)
                AIRLINE_MAP = {
                    "ماهان": "ماهان",
                    "Mahan Air": "ماهان",
                    "mahan": "ماهان",
                    "آتا": "آتا",
                    "ATA": "آتا",
                    "Ata Airlines": "آتا",
                    "ATA Airlines": "آتا",
                    "آتا ایر": "آتا",
                    "چابهار": "چابهار",
                    "Chabahar Air": "چابهار",
                    "Chabahar": "چابهار",
                    "ساها": "ساها",
                    "Saha": "ساها",
                    "Saha Air": "ساها",
                    "ساها ایر": "ساها",
                    "نسیم ایر": "نسیم ایر",
                    "نسيم اير": "نسیم ایر",
                    "Nasim Air": "نسیم ایر",
                    "ایران ایر": "ایران ایر",
                    "Iran Air": "ایران ایر",
                    "زاگرس": "زاگرس",
                    "Zagros Airlines": "زاگرس",
                    "کاسپین": "کاسپین",
                    "Caspian Airlines": "کاسپین",
                    "فلای کیش": "فلای کیش",
                    "Fly Kish": "فلای کیش",
                    "FlyKish": "فلای کیش",
                    "آوا ایر": "آوا ایر",
                    "Ava Air": "آوا ایر",
                    "ایران ایرتور": "ایران ایرتور",
                    "ایران ایرتور": "ایران ایر تور",
                    "Iran Air Tours": "ایران ایرتور",
                    "کیش ایر": "کیش ایر",
                    "Kish Airlines": "کیش ایر",
                    "اطلس ایر": "اطلس ایر",
                    "اطلس اير": "اطلس ایر",
                    "Atlas Air": "اطلس ایر",
                    "Atlas Airline": "اطلس ایر",
                    "تابان": "تابان",
                    "Taban Air": "تابان",
                    "Taban Airlines": "تابان",
                    "وارش": "وارش",
                    "Varesh Airlines": "وارش",
                    "Varesh": "وارش",
                }

                airline = airline.strip()
                airline = AIRLINE_MAP.get(airline, airline)

    
                # فقط کلاس‌های واقعی (ممکن است pipeline آن را تنظیم کند)
                aircraft_class = (
                    f.get("classTypeName")
                    or f.get("class")
                    or f.get("class_type")
                    or f.get("aircraft_class")
                    or None
                )

                # قیمت ممکن است رشته یا عدد باشد؛ سعی کنیم int بگیریم
                raw_price = f.get("priceAdult") or f.get("price") or f.get("price_adult") or None
                price = None
                if raw_price is not None:
                    if isinstance(raw_price, str):
                        digits = re.sub(r"[^\d]", "", raw_price)
                        price = int(digits) if digits else None
                    elif isinstance(raw_price, (int, float)):
                        price = int(raw_price)
                if price is None:
                    # اگر قیمت موجود نیست از ذخیره پرواز صرف‌نظر کن
                    continue
    
                # اگر فیلدهای کلیدی برای مقایسه وجود ندارند -> درج رکورد جدید
                key_fields_present = all([
                    origin_city is not None and origin_city != "",
                    dest_city is not None and dest_city != "",
                    date_shamsi is not None and date_shamsi != "",
                    dep_time is not None,
                    arr_time is not None,
                    airline is not None and airline != "",
                    aircraft_class is not None and aircraft_class != ""
                ])
    
                if key_fields_present:
                    # SELECT بر اساس کلید دقیقِ خواسته‌شده
                    cursor.execute(f"""
                        SELECT id, {self.price_column}
                        FROM Flights_AllSites
                        WHERE origin_name=? AND dest_name=? AND departure_date=?
                          AND departure_time=? AND arrival_time=? AND airline=? AND aircraft_class=?
                    """, (origin_city, dest_city, date_shamsi, dep_time, arr_time, airline, aircraft_class))
                    row = cursor.fetchone()
                else:
                    row = None

                if row:
                    existing_price = row[1]
                    # تبدیل existing_price به int در صورت نیاز
                    if isinstance(existing_price, str):
                        ep_digits = re.sub(r"[^\d]", "", existing_price)
                        existing_price = int(ep_digits) if ep_digits else None
                    # حالا مقایسه امن
                    if existing_price is None or price < existing_price:
                        cursor.execute(f"""
                            UPDATE Flights_AllSites
                            SET {self.price_column} = ?, airline = ?, aircraft_class = ?
                            WHERE id = ?
                        """, (price, airline, aircraft_class, row[0]))
                        updated += 1
                    else:
                        # قیمت جدید بالاتر یا برابر است -> کاری انجام نمیدیم
                        pass
                else:
                    # INSERT جدید (ستون seats_left حذف شده)
                    cursor.execute(f"""
                        INSERT INTO Flights_AllSites (
                            origin_name, dest_name, departure_date, departure_time, arrival_time,
                            flight_number, airline, aircraft_class, {self.price_column}
                        )
                        VALUES (?,?,?,?,?,?,?,?,?)
                    """, (
                        origin_city, dest_city, date_shamsi, dep_time, arr_time,
                        flight_no, airline, aircraft_class, price
                    ))
                    inserted += 1
    
            except Exception as e:
                print("⚠️ خطا در ذخیره رکورد:", e)
                continue

        conn.commit()
        conn.close()
        print(f"✅ ذخیره در دیتابیس ({self.site_name}) — درج: {inserted}, بروزرسانی: {updated}")


# --------------------------
# Charter118 Pipeline
# --------------------------
class Charter118Pipeline(PipelineBase):
    def __init__(self):
        super().__init__("Charter118", "Flights_Charter118")
        self.price_column = "price_charter118"

    def build_url(self, origin_iata, dest_iata, date_gregorian, passengers, international=False):
        base = "https://charter118.ir/international-flights" if international else "https://charter118.ir/flights"
        return f"{base}/{origin_iata}-{dest_iata}?adult={passengers}&child=0&infant=0&departing={date_gregorian}"
    async def fetch_html(self, url, wait_selector=None):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.HEADLESS)
            context = await browser.new_context()
            page = await context.new_page()
    
            await page.goto(url, timeout=120000)
    
            if wait_selector:
                try:
                    await page.wait_for_selector(wait_selector, timeout=20000)
                except:
                    print("⚠️ المان پیدا نشد - سعی به اسکرول")
            
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
        print("✅ تعداد کارت های پیدا شده در Charter118:", len(cards))

        for card in cards:
            try:
                tags = card.find_all("p", class_=lambda c: c and "bg-blue-400/10" in c)
                tag_texts = [t.text.strip() for t in tags]
                aircraft_class = next((t for t in tag_texts if "اکونومی" in t or "بیزینس" in t), None)
                num_tag = card.find("p", class_=lambda c: c and "bg-gray-400/10" in c)
                flight_number = num_tag.text.strip() if num_tag else None
                airline_tag = card.find("p", class_=lambda c: c and "text-darkGray" in c and "text-center" in c)
                airline = airline_tag.text.strip() if airline_tag else None
                times = card.find_all("span", class_=lambda c: c and "text-black" in c and "text-xl" in c)
                departure_time = times[0].text.strip() if times else None
                arrival_time = times[1].text.strip() if times and len(times) > 1 else None
                price_tag = card.find("p", class_=lambda c: c and "text-green-700" in c)
                price = None
                if price_tag:
                    price_text = price_tag.text.replace(",", "").replace("٬", "").strip()
                    price = int(price_text) if price_text.isdigit() else None

                # حذف استخراج صندلی طبق درخواست

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

# --------------------------
# Flightio Pipeline
# --------------------------
class FlightioPipeline(PipelineBase):
    def __init__(self):
        super().__init__("Flightio", "Flights_Flightio")
        self.price_column = "price_flightio"
        # برای فلاییتو بهتر headless=False کنی در حالت تست
        self.HEADLESS = False

    def build_url(self, origin_iata, dest_iata, date_gregorian, passengers, international=False):
        flight_type = 1 if international else 2
        cabin_type = 1
        return f"https://flightio.com/flight/{origin_iata}-{dest_iata}?depart={date_gregorian}&adult={passengers}&child=0&infant=0&flightType={flight_type}&cabinType={cabin_type}"

    async def fetch_html(self, url, wait_selector="section.transition-input-100"):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.HEADLESS, args=["--disable-blink-features=AutomationControlled"])
            context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
            page = await context.new_page()
            await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=120000)
            except Exception as e:
                print("⚠️ خطا در باز کردن صفحه فلاییتو:", e)
            try:
                await page.wait_for_selector(wait_selector, timeout=120000)
                print("✅ فلاییتو لود شد")
            except Exception:
                print("⚠️ پرواز نمایش داده نشد یا سایت Bot رو فهمید")
            for _ in range(8):
                await page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
                await asyncio.sleep(1)
            await asyncio.sleep(2)
            html = await page.content()
            await browser.close()
            return html

    def parse_flights(self, html):
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.find_all("section", class_=lambda c: c and "transition-input-100" in c)
        flights = []
        for card in cards:
            try:
                def safe_text(find): return find.text.strip() if find else None
                airline = safe_text(card.find("span", class_=lambda c: c and "text-body-m" in c))
                flight_number = None
                flight_info = card.find_all("span", string=re.compile("پرواز شماره"))
                if flight_info:
                    flight_number = re.sub(r"[^\d]", "", flight_info[0].text)
                price_span = card.find("span", class_=lambda c: c and "font-bold" in c)
                price = None
                if price_span:
                    price_digits = re.findall(r"\d+", price_span.text.replace(",", ""))
                    if price_digits:
                        price = int(price_digits[0])
                time_spans = card.find_all("span", class_=lambda c: c and "text-title-xl" in c)
                dep_time = safe_text(time_spans[0]) if len(time_spans) > 0 else None
                arr_time = safe_text(time_spans[1]) if len(time_spans) > 1 else None
                cabin = card.find("span", string=lambda s: s and ("اکونومی" in s or "بیزینس" in s))
                aircraft_class = cabin.get_text(strip=True).split("-")[0] if cabin else None

                # حذف استخراج صندلی

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
                print("⚠️ خطا در کارت:", e)
                continue
        print(f"✈️ {len(flights)} پرواز از فلاییتو استخراج شد")
        return flights

# --------------------------
# Alibaba Pipeline
# --------------------------
class AlibabaPipeline(PipelineBase):
    def __init__(self):
        super().__init__("Alibaba", "Flights_Alibaba")
        self.price_column = "price_alibaba"

    async def get_api_url(self, search_url):
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
                print("⚠️ خطا در باز کردن صفحه علی‌بابا:", e)
            await page.wait_for_timeout(5000)
            await browser.close()
            return api_url

    async def parse_flights(self, html):
        return []

    async def fetch_flights(self, origin_iata, dest_iata, date_shamsi, passengers, international=False):
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
                print("⚠️ خطا در دریافت JSON از API علی‌بابا:", e)
                await context.close()
                return []
            await context.close()

        if not data.get("success") or not data["result"].get("departing"):
            print("⚠️ داده‌ای از API علی‌بابا دریافت نشد.")
            return []

        flights = []
        for f in data["result"]["departing"]:
            try:
                seats = f.get("seat") or 0
                if seats == 0:
                    continue  # حذف پروازهایی که ظرفیت ندارند

                flights.append({
                    "flight_number": f.get("flightNumber"),
                    "airline": f.get("airlineName"),
                    "departure_city": f.get("originName"),
                    "arrival_city": f.get("destinationName"),
                    "leaveDateTime": f.get("leaveDateTime"),  # کل فیلد برای استخراج زمان بعداً
                    "arrivalDateTime": f.get("arrivalDateTime"),
                    "aircraft_class": f.get("classTypeName"),
                    "price": f.get("priceAdult"),
                    # seats_left حذف شد
                })
            except Exception as e:
                print("⚠️ خطا در پردازش پرواز از علی‌بابا:", e)
                continue

        print(f"✅ {len(flights)} پرواز از علی‌بابا استخراج شد (بدون ظرفیت صفر).")
        return flights


# --------------------------
# MrBilit Pipeline
# --------------------------
class MrBilitPipeline(PipelineBase):
    def __init__(self):
        super().__init__("MrBilit", "Flights_MrBilit")
        self.price_column = "price_mrbilit"
        self.HEADLESS = False  # بهتر برای تست
    
    def build_url(self, origin_iata, dest_iata, date_gregorian, passengers, international=False):
        # MrBilit از تاریخ شمسی استفاده می‌کند نه میلادی!
        # انتظار دارد فرمت 1404-08-15
        # پس ورودی date_gregorian را تغییر نمی‌دهیم،
        # بلکه همان تاریخ شمسی را از main پاس می‌دهیم
        return f"https://mrbilit.com/flights/{origin_iata}-{dest_iata}?departureDate={date_gregorian}"

    async def fetch_html(self, url, wait_selector=".trip-package-info"):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.HEADLESS)
            context = await browser.new_context()
            page = await context.new_page()

            try:
                await page.goto(url, timeout=60000)
            except Exception as e:
                print("⚠️ خطا در باز کردن مستربلیت:", e)

            try:
                await page.wait_for_selector(wait_selector, timeout=20000)
            except:
                print("⚠️ پروازی نمایش داده نشد در مستربلیت")

            # اسکرول برای لود کامل
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
                origin = card.select(".locations p")[0].text.strip()
                destination = card.select(".locations p")[1].text.strip()
                dep_time = card.select(".time")[0].text.strip()

                # بعضی زمان‌ها ممکن است با ساختار دیگری برای arrival باشند؛ تلاش برای استخراج
                arr_time = None
                time_nodes = card.select(".time")
                if len(time_nodes) > 1:
                    arr_time = time_nodes[1].text.strip()

                airline_tag = card.select_one("div.title-container p")
                airline = airline_tag.text.strip() if airline_tag else "نامشخص"

                # حذف صندلی

                # ✅ استخراج قیمت
                price_tag = card.select_one(".price")
                if not price_tag:
                    continue
                price_text = price_tag.text.replace(",", "").replace("٬", "")
                price_digits = "".join(re.findall(r"\d+", price_text))
                price = int(price_digits) if price_digits.isdigit() else None

                # ✅ استخراج کلاس پرواز (اکونومی/بیزینس)
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
                    "flight_number": None,   # MrBilit بدون کلیک نشان نمی‌دهد
                    "price": price,
                    "airline": airline,
                    "aircraft_class": aircraft_class,  # ✅ اضافه شد
                    "departure_time": dep_time,
                    "arrival_time": arr_time,
                    "origin": origin,
                    "destination": destination,
                })
    
            except Exception as e:
                print("⚠️ خطا در کارت مستربلیت:", e)
                continue
    
        print(f"✈️ {len(flights)} پرواز از مستربلیت استخراج شد")
        return flights
# --------------------------
# Ghasedak24 Pipeline
# --------------------------
class GhasedakPipeline(PipelineBase):
    def __init__(self):
        super().__init__("Ghasedak24", "Flights_Ghasedak24")
        self.price_column = "price_ghasedak"
        self.HEADLESS = False  # برای تست بهتره False باشه

    def build_url(self, origin_iata, dest_iata, date_gregorian, passengers, international=False):
        # ⚠️ Ghasedak فقط داخلیه فعلاً
        return f"https://ghasedak24.com/flights/{origin_iata}-{dest_iata}?date-time={date_gregorian}&adult-count={passengers}&child-count=0&infant-count=0"

    async def fetch_html(self, url, wait_selector="div.ghk-grid.ghk-grid-cols-12"):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.HEADLESS)
            context = await browser.new_context()
            page = await context.new_page()
            try:
                await page.goto(url, timeout=120000)
                await page.wait_for_selector(wait_selector, timeout=60000)
                await asyncio.sleep(2)
            except Exception as e:
                print("⚠️ خطا در بارگذاری صفحه Ghasedak:", e)
            html = await page.content()
            await browser.close()
            return html


    def parse_flights(self, html):


        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("div.ghk-grid.ghk-grid-cols-12")
        flights = []
    
        print(f"✅ تعداد کارت‌ها در Ghasedak24: {len(cards)}")
    
        for c in cards:
            try:
                airline_tag = c.select_one("div.ghk-flex.ghk-flex-col.ghk-items-center span.ghk-text-xs14")
                airline = airline_tag.text.strip() if airline_tag else None
    
                times = c.select("div.ghk-flex.ghk-items-center.ghk-text-md22")
                dep_time = times[0].text.strip() if len(times) > 0 else None
                arr_time = times[1].text.strip() if len(times) > 1 else None
    
                airport_spans = c.select("span.ghk-text-sm14")
                origin = airport_spans[0].text.strip() if len(airport_spans) > 0 else None
                dest = airport_spans[1].text.strip() if len(airport_spans) > 1 else None
    
                # تبدیل نام فرودگاه به شهر
                def normalize_airport(name):
                    if not name:
                        return None
                    name = re.sub(r"فرودگاه|بین‌المللی|Airport|International", "", name).strip()
                    name = name.replace("مهرآباد", "تهران").replace("امام خمینی", "تهران")
                    return name
    
                origin_city = normalize_airport(origin)
                dest_city = normalize_airport(dest)

                price_tag = c.select_one("span.ghk-text-md22.ghk-text-blue-primary")
                price = None
                if price_tag:
                    txt = price_tag.text.replace(",", "").replace("٬", "").strip()
                    if txt.isdigit():
                        price = int(txt)
    
                # ✅ فقط کلاس پرواز واقعی (اکونومی / بیزینس)
                class_tags = c.select("div.ghk-bg-gray-50.ghk-text-gray-500, div.ghk-text-gray-500, div.ghk-text-xs14")
                # تشخیص کلاس پرواز (اکونومی / بیزینس)
                aircraft_class = None
                try:
                    class_divs = c.select("div.ghk-hidden.xl\\:ghk-flex.ghk-justify-center.ghk-gap-x-2 div")
                    for div_tag in class_divs:
                        txt = div_tag.get_text(strip=True)
                        if any(word in txt for word in ["اکونومی", "Economy"]):
                            aircraft_class = "اکونومی"
                            break
                        elif any(word in txt for word in ["بیزینس", "بیزنس", "Business", "Bussiness"]):
                            aircraft_class = "بیزینس"
                            break
                except Exception as e:
                    aircraft_class = None

    
                if airline and price and dep_time:
                    flights.append({
                        "airline": airline,
                        "aircraft_class": aircraft_class,
                        "departure_time": dep_time,
                        "arrival_time": arr_time,
                        "origin_name": origin_city,
                        "dest_name": dest_city,
                        "price": price,
                    })
    
            except Exception as e:
                print("⚠️ خطا در کارت Ghasedak:", e)
                continue
    
        print(f"✈️ {len(flights)} پرواز از Ghasedak استخراج شد.")
        return flights



# --------------------------
# Flytoday Pipeline - کپی دقیق از کد اصلی که کار می‌کنه
# --------------------------
class FlytodayPipeline(PipelineBase):
    def __init__(self):
        super().__init__("FlyToday", "Flights_Flytoday")
        self.price_column = "price_flytoday"
        self.HEADLESS = True

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
        ⭐ نسخه تست‌شده که کار می‌کنه
        """
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.HEADLESS)
            page = await browser.new_page()
            
            try:
                print("🔄 در حال باز کردن صفحه Flytoday...")
                await page.goto(url, timeout=60000)
                print("✅ صفحه باز شد")
            except Exception as e:
                print(f"⚠️ خطا در لود صفحه Flytoday: {e}")
                await browser.close()
                return []
            
            # ⏳ صبر بیشتر (مثل کد تستی)
            print("⏳ صبر 10 ثانیه برای لود کامل...")
            await asyncio.sleep(10)
            
            # 🔍 چک تعداد کارت‌ها
            try:
                card_count = await page.locator("div.w-full.flex.justify-between.gap-2").count()
                print(f"🔍 تعداد کارت‌های یافت شده: {card_count}")
                
                if card_count == 0:
                    print("❌ هیچ کارتی پیدا نشد!")
                    await browser.close()
                    return []
            except Exception as e:
                print(f"⚠️ خطا در شمارش کارت‌ها: {e}")
            
            # دریافت HTML
            content = await page.content()
            await browser.close()
            
            # پارس کردن
            soup = BeautifulSoup(content, "html.parser")
            flight_cards = soup.select("div.w-full.flex.justify-between.gap-2")
            flights = []
            
            print(f"✅ شروع پردازش {len(flight_cards)} کارت...")
            
            for idx, f in enumerate(flight_cards):
                try:
                    # زمان حرکت و رسیدن
                    time_div = f.select_one("div.relative.text-gray-900")
                    if not time_div:
                        print(f"⚠️ کارت {idx}: time_div پیدا نشد")
                        continue
                    
                    times = [t.get_text(strip=True) for t in time_div.select("div.inline-block.relative")]
                    if len(times) < 2:
                        print(f"⚠️ کارت {idx}: زمان‌ها کافی نیست - {times}")
                        continue
                    departure_time, arrival_time = times[0], times[1]
                    
                    # مبدا و مقصد
                    route_div = f.select_one("div.text-nowrap.text-xs.md\\:text-sm.text-gray-700.font-medium")
                    if not route_div:
                        print(f"⚠️ کارت {idx}: route_div پیدا نشد")
                        continue
                    
                    cities_raw = [c.get_text(strip=True) for c in route_div.select("div.inline-block.relative")]
                    if len(cities_raw) < 2:
                        print(f"⚠️ کارت {idx}: شهرها کافی نیست - {cities_raw}")
                        continue
                    
                    origin_name = re.sub(r"\s*\(.*?\)", "", cities_raw[0]).strip()
                    dest_name = re.sub(r"\s*\(.*?\)", "", cities_raw[1]).strip()
                    
                    # ایرلاین
                    airline_div = f.select_one("span.text-xs.text-gray-700.font-semibold.text-nowrap")
                    airline = airline_div.get_text(strip=True) if airline_div else "نامشخص"
                    
                    # کلاس پروازی
                    aircraft_class_div = f.select_one("span.text-xs.text-gray-700.font-noraml.ms-0\\.5")
                    aircraft_class = aircraft_class_div.get_text(strip=True) if aircraft_class_div else None
                    
                    # 💰 قیمت
                    price = None
                    all_spans = f.find_all("span")
                    
                    for span in all_spans:
                        text = span.get_text(strip=True).replace(",", "").replace("٬", "")
                        digits = re.sub(r"[^\d]", "", text)
                        # قیمت معمولاً 6-8 رقمی
                        if digits and len(digits) >= 6 and len(digits) <= 9:
                            price = int(digits)
                            break
                    
                    if not price:
                        # تلاش دوم: جستجوی دقیق‌تر
                        for span in all_spans:
                            text = span.get_text(strip=True)
                            # اگه "تومان" یا عدد بزرگ داره
                            if "تومان" in text or "ریال" in text:
                                digits = re.sub(r"[^\d]", "", text)
                                if digits and len(digits) >= 5:
                                    price = int(digits)
                                    break
                    
                    if not price:
                        print(f"⚠️ کارت {idx}: قیمت پیدا نشد - {airline}")
                        if idx < 3:  # فقط 3 تای اول debug کن
                            span_texts = [s.get_text(strip=True)[:30] for s in all_spans[:15]]
                            print(f"   📝 Spans: {span_texts}")
                        continue
                    
                    # شماره پرواز
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
                    
                    if idx < 3:  # اولی‌ها رو چاپ کن
                        print(f"✅ کارت {idx}: {airline} | {departure_time}-{arrival_time} | {price:,} تومان")
                    
                except Exception as e:
                    print(f"⚠️ خطا در کارت {idx}: {e}")
                    continue
            
            print(f"✈️ {len(flights)} پرواز از FlyToday استخراج شد")
            return flights

    async def fetch_html(self, url, wait_selector=None):
        """این متد دیگه استفاده نمیشه - fetch_and_parse رو استفاده می‌کنیم"""
        pass

    def parse_flights(self, html):
        """این متد دیگه استفاده نمیشه - fetch_and_parse رو استفاده می‌کنیم"""
        pass
# --------------------------
# اجرای Pipeline
# --------------------------
# --------------------------
# 🔧 تغییرات لازم در main()
# --------------------------

async def main():
    origin_city = input("مبدأ: ").strip().lower()
    dest_city = input("مقصد: ").strip().lower()
    date_shamsi = input("تاریخ شمسی (مثلاً 1404/08/10): ").strip()
    passengers = input("تعداد بزرگسال: ").strip()
    intl = input("پرواز خارجی؟ (y/n): ").strip().lower() == "y"

    origin_iata = IATA_CODES.get(origin_city)
    dest_iata = IATA_CODES.get(dest_city)

    if intl and origin_iata == "THR": origin_iata = "IKA"
    if intl and dest_iata == "THR": dest_iata = "IKA"

    base_jdate = jdatetime.date(*map(int, date_shamsi.split('/')))

    # 🔴 لیست pipeline ها
    pipelines = [
        #AlibabaPipeline(),
        #GhasedakPipeline(),
        #Charter118Pipeline(),
        #FlightioPipeline(),
        #MrBilitPipeline(),
        FlytodayPipeline()  # ✅ اضافه شده
    ]

    for pipeline in pipelines:
        date_gregorian = base_jdate.togregorian().strftime("%Y-%m-%d")

        print(f"\n📡 دریافت پروازهای {origin_city} → {dest_city} از: {pipeline.site_name}")

        # 🔴 این قسمت مهمه - چک کن درست باشه
        if isinstance(pipeline, AlibabaPipeline):
            flights = await pipeline.fetch_flights(origin_iata, dest_iata, date_shamsi, passengers, intl)
        
        elif isinstance(pipeline, MrBilitPipeline):
            url = pipeline.build_url(origin_iata, dest_iata, date_shamsi.replace("/", "-"), passengers, intl)
            html = await pipeline.fetch_html(url)
            flights = pipeline.parse_flights(html)
        
        elif isinstance(pipeline, FlytodayPipeline):  # ✅ باید این قسمت رو اضافه کنی
            url = pipeline.build_url(origin_iata, dest_iata, date_gregorian, passengers, intl)
            print(f"🔗 URL: {url}")  # دیباگ
            flights = await pipeline.fetch_and_parse(url)
        
        elif isinstance(pipeline, GhasedakPipeline):
            url = pipeline.build_url(origin_iata, dest_iata, date_gregorian, passengers, intl)
            html = await pipeline.fetch_html(url)
            flights = pipeline.parse_flights(html)
        
        else:
            # Charter118 و Flightio
            url = pipeline.build_url(origin_iata, dest_iata, date_gregorian, passengers, intl)
            wait_selector = (
                "div.bg-white.rounded-lg"
                if isinstance(pipeline, Charter118Pipeline)
                else "section.transition-input-100"
            )
            html = await pipeline.fetch_html(url, wait_selector=wait_selector)
            flights = pipeline.parse_flights(html)

        pipeline.save_to_db(flights, origin_city, dest_city, date_shamsi)

    print("✅ تمام شد!")


if __name__ == "__main__":
     asyncio.run(main())
