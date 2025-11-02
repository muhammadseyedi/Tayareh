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
        ورودی: دیکشنری فلیتی از API یا پارسر
        خروجی: departure_time بصورت 'HH:MM' یا None
        منطق:
          - اگر leaveDateTime دارای 'T' بود -> قسمت ساعت بعد از T را برمی‌گردانیم (HH:MM)
          - اگر فقط 'YYYY-MM-DD' بود -> None (ما تاریخ را جدا نگه می‌داریم)
          - در غیر این صورت سعی می‌کنیم کوتاهترین شکل ساعت را استخراج کنیم.
        """
        dep_time_full = (f.get("leaveDateTime") or f.get("departure_time") or "").strip()
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

    def save_to_db(self, flights, origin_city, dest_city, date_shamsi):
        """
        منطق ذخیره:
          - اگر رکوردی با (origin,dest,date,flight_number,departure_time,aircraft_class)
            وجود داشته باشد، مقدار price در ستون مخصوص سایت فقط در صورتی آپدیت می‌شود
            که قیمت جدید کمتر از قیمت موجود باشد یا مقدار موجود NULL باشد.
          - اگر رکورد وجود نداشت -> INSERT جدید.
          - اگر departure_time یا flight_number موجود نباشد، رکورد جدید درج می‌شود
            (برای جلوگیری از حذف داده‌های ناقص).
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
                aircraft_class = (
                    f.get("classTypeName")
                    or f.get("class")
                    or f.get("class_type")
                    or f.get("aircraft_class")
                    or "Unknown"
                )
                seats_left = f.get("seat") or f.get("seats_left") or None
                price = f.get("priceAdult") or f.get("price") or f.get("price_adult") or None

                # اگر price صحیح نیست، نادیده بگیر
                if price is None:
                    # اگر سایت دیگری قیمت دارد، ممکن است بعداً تکمیل شود، ولی این رکورد فعلاً ذخیره نشود
                    # (قابل تغییر) — برای حالا رد می‌کنیم تا دیتابیس با قیمت‌های نامشخص پر نشود
                    continue

                # اگر price column تنظیم نشده، skip
                if not self.price_column:
                    raise RuntimeError("price_column برای این pipeline تنظیم نشده است.")

                # اگر هم شماره پرواز و هم ساعت موجود باشند -> strict match
                if flight_no and dep_time:
                    cursor.execute(f"""
                        SELECT id, {self.price_column}
                        FROM Flights_AllSites
                        WHERE origin_name=? AND dest_name=? AND departure_date=? 
                              AND flight_number=? AND departure_time=? AND aircraft_class=?
                    """, (origin_city, dest_city, date_shamsi, flight_no, dep_time, aircraft_class))
                    row = cursor.fetchone()
                else:
                    # اطلاعات ناقص؛ برای جلوگیری از اشتباهات بهتر است رکورد جدید درج شود
                    row = None

                if row:
                    existing_price = row[1]
                    if existing_price is None or price < existing_price:
                        cursor.execute(f"""
                            UPDATE Flights_AllSites
                            SET {self.price_column} = ?, airline=?, seats_left=?, aircraft_class=?
                            WHERE id = ?
                        """, (price, airline, seats_left, aircraft_class, row[0]))
                        updated += 1
                else:
                    cursor.execute(f"""
                        INSERT INTO Flights_AllSites (
                            origin_name, dest_name, departure_date, departure_time,
                            flight_number, airline, aircraft_class, seats_left,
                            {self.price_column}
                        )
                        VALUES (?,?,?,?,?,?,?,?,?)
                    """, (
                        origin_city, dest_city, date_shamsi, dep_time,
                        flight_no, airline, aircraft_class, seats_left, price
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

    def parse_flights(self, html):
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.find_all("div", class_=lambda c: c and "bg-white" in c and "rounded-lg" in c)
        flights = []
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
                price_tag = card.find("p", class_=lambda c: c and "text-green-700" in c)
                price = None
                if price_tag:
                    price_text = price_tag.text.replace(",", "").replace("٬", "").strip()
                    price = int(price_text) if price_text.isdigit() else None
                seats_tag = card.find("p", class_=lambda c: c and "text-primary" in c)
                seats_left = seats_tag.text.strip() if seats_tag else None
                if airline and departure_time and price:
                    flights.append({
                        "flight_number": flight_number,
                        "price": price,
                        "airline": airline,
                        "aircraft_class": aircraft_class,
                        "departure_time": departure_time,
                        "seats_left": seats_left
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
                cabin = card.find("span", string=lambda s: s and ("اکونومی" in s or "بیزینس" in s))
                aircraft_class = cabin.get_text(strip=True).split("-")[0] if cabin else None

                seats = None
                seat_tag = card.find("label", class_=lambda c: c and "text-red" in c)
                if seat_tag:
                    m = re.search(r"(\d+)", seat_tag.text)
                    if m:
                        seats = int(m.group(1))
                if airline and price and dep_time:
                    flights.append({
                        "flight_number": flight_number,
                        "price": price,
                        "airline": airline,
                        "aircraft_class": aircraft_class,
                        "departure_time": dep_time,
                        "seats_left": seats
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
                    "aircraft_class": f.get("classTypeName"),
                    "price": f.get("priceAdult"),
                    "seats_left": seats
                })
            except Exception as e:
                print("⚠️ خطا در پردازش پرواز از علی‌بابا:", e)
                continue

        print(f"✅ {len(flights)} پرواز از علی‌بابا استخراج شد (بدون ظرفیت صفر).")
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

    pipelines = [Charter118Pipeline(), AlibabaPipeline(), FlightioPipeline()]

    for pipeline in pipelines:
        date_gregorian = base_jdate.togregorian().strftime("%Y-%m-%d")

        print(f"\n📡 دریافت پروازهای {origin_city} → {dest_city} از: {pipeline.site_name}")

        if isinstance(pipeline, AlibabaPipeline):
            flights = await pipeline.fetch_flights(origin_iata, dest_iata, date_shamsi, passengers, intl)
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
