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
        منطق ذخیره:
          - برای UPDATE از کلید ترکیبی استفاده می‌کنیم:
            origin_name, dest_name, departure_date, departure_time, arrival_time, airline, aircraft_class
          - اگر رکورد وجود داشت و قیمت جدید کمتر است یا موجود NULL بود -> آپدیت قیمت مخصوص سایت و فیلدهای airline/aircraft_class
          - اگر رکورد وجود نداشت -> INSERT جدید (بدون ستون seats_left)
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

                # flight number قوی‌تر استخراج شود
                flight_no = (
                    f.get("flightNumber")
                    or f.get("flight_number")
                    or f.get("flightNo")
                    or f.get("flight_id")
                    or (f.get("description", "").split("|")[0].strip() if f.get("description") and "|" in f.get("description") else None)
                    or f.get("flight_no")
                )
                airline = f.get("airlineName") or f.get("airline") or f.get("airline_name") or "نامشخص"
                # تبدیل نام انگلیسی ایرلاین‌ها به فارسی
                AIRLINE_MAP = {
                    "Iran Air Tours": "ایران ایرتور",
                    "Zagros Airlines": "زاگرس",
                    "Caspian Airlines": "کاسپین",
                    "Chabahar Air": "چابهار",
                    "Iran Aseman Airlines": "آسمان",
                    "Qeshm Air": "قشم ایر",
                    "Kish Airlines": "کیش ایر",
                    "ATA Airlines": "آتا",
                    "Saha": "ساها",
                    "Saha Air": "ساها",
                    "Iran Air": "ایران ایر",
                    "Fly Persia": "فلای پرشیا",
                    "FlyKish": "فلای کیش",
                    "Fly Kish": "فلای کیش",
                    "Atlas Air": "اطلس ایر",
                    "Atlas Airline": "اطلس ایر",
                    "Ava Air": "آوا ایر",
                    "Nasim Air": "نسیم ایر",
                    "Ervan Air": "اروان",
                    "Ervan": "اروان",
                    "Varesh Airlines": "وارش",
                    "Varesh": "وارش",
                    "Mahan Air": "ماهان",
                    "Taban Airlines": "تابان",
                    "Taban Air": "تابان",
                    "Pars Air": "پارس ایر",
                    "Ata": "آتا",
                    "Ata Airlines": "آتا",
                    "Aseman Airlines": "آسمان",
                }
                airline = AIRLINE_MAP.get(airline.strip(), airline.strip())


                aircraft_class = (
                    f.get("classTypeName")
                    or f.get("class")
                    or f.get("class_type")
                    or f.get("aircraft_class")
                    or "Unknown"
                )

                price = f.get("priceAdult") or f.get("price") or f.get("price_adult") or None

                # حذف پردازش صندلی بر اساس درخواست
                # seats_left = None

                # اگر price صحیح نیست، نادیده بگیر
                if price is None:
                    continue

                # اگر price column تنظیم نشده، skip
                if not self.price_column:
                    raise RuntimeError("price_column برای این pipeline تنظیم نشده است.")

                # Strict match: اگر فیلدهای کلیدی موجودند
                if dep_time and arr_time and airline and aircraft_class:
                    cursor.execute(f"""
                        SELECT id, {self.price_column}
                        FROM Flights_AllSites
                        WHERE origin_name=? AND dest_name=? AND departure_date=? 
                              AND departure_time=? AND arrival_time=? AND airline=? AND aircraft_class=?
                    """, (origin_city, dest_city, date_shamsi, dep_time, arr_time, airline, aircraft_class))
                    row = cursor.fetchone()
                else:
                    # اطلاعات ناقص؛ برای جلوگیری از اشتباهات رکورد جدید درج می‌شود
                    row = None

                if row:
                    existing_price = row[1]
                    if existing_price is None or price < existing_price:
                        cursor.execute(f"""
                            UPDATE Flights_AllSites
                            SET {self.price_column} = ?, airline=?, aircraft_class=?
                            WHERE id = ?
                        """, (price, airline, aircraft_class, row[0]))
                        updated += 1
                else:
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
# اجرای Pipeline
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

    pipelines = [Charter118Pipeline(), AlibabaPipeline(), FlightioPipeline(),MrBilitPipeline() ]

    for pipeline in pipelines:
        date_gregorian = base_jdate.togregorian().strftime("%Y-%m-%d")

        print(f"\n📡 دریافت پروازهای {origin_city} → {dest_city} از: {pipeline.site_name}")

        if isinstance(pipeline, AlibabaPipeline):
            flights = await pipeline.fetch_flights(origin_iata, dest_iata, date_shamsi, passengers, intl)
        elif isinstance(pipeline, MrBilitPipeline):
            url = pipeline.build_url(origin_iata, dest_iata, date_shamsi.replace("/", "-"), passengers, intl)
            html = await pipeline.fetch_html(url)
            flights = pipeline.parse_flights(html)
        else:
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
