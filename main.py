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
# توابع دیتابیس
# --------------------------
#in SQL
'''CREATE TABLE Flights_AllSites (
    id INT IDENTITY(1,1) PRIMARY KEY,
    origin_name NVARCHAR(50),
    dest_name NVARCHAR(50),
    departure_date NVARCHAR(10),
    departure_time NVARCHAR(10),
    flight_number NVARCHAR(50),
    airline NVARCHAR(50),
    aircraft_class NVARCHAR(50),
    seats_left NVARCHAR(20),
    
    price_charter118 BIGINT NULL,
    price_alibaba BIGINT NULL,
    price_flightio BIGINT NULL
);
'''


# --------------------------
# کلاس پایه
# --------------------------
class PipelineBase:
    def __init__(self, site_name, table_name):
        self.site_name = site_name
        self.db_name = "FlightsDB"
        self.table_name = table_name
        

    async def fetch_html(self, url, wait_selector=None):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36"
                )
            )
            page = await context.new_page()
            await page.goto(url, timeout=120000)
            if wait_selector:
                try:
                    await page.wait_for_selector(wait_selector, timeout=120000)
                except:
                    print(f"⚠️ المنت {wait_selector} پیدا نشد.")
            await asyncio.sleep(5)
            html = await page.content()
            await browser.close()
            return html

    def save_to_db(self, flights, origin_city, dest_city, date_shamsi):
        conn = pyodbc.connect(
            f"DRIVER={{SQL Server}};SERVER=localhost;DATABASE=FlightsDB;Trusted_Connection=yes;"
        )
        cursor = conn.cursor()
    
        price_column = {
            "Charter118": "price_charter118",
            "Alibaba": "price_alibaba",
            "Flightio": "price_flightio"
        }[self.site_name]
    
        for f in flights:
            flight_no = f.get("flight_number")
            aircraft_class = f.get("aircraft_class")
            dep_time = f.get("departure_time")
    
            cursor.execute(f"""
                SELECT id FROM Flights_AllSites
                WHERE flight_number = ? AND aircraft_class = ? AND departure_date = ?
            """, (flight_no, aircraft_class, date_shamsi))
            
            row = cursor.fetchone()
    
            if row:  # UPDATE
                cursor.execute(f"""
                    UPDATE Flights_AllSites 
                    SET {price_column} = ?
                    WHERE id = ?
                """, (f["price"], row[0]))
            else:  # INSERT
                cursor.execute(f"""
                    INSERT INTO Flights_AllSites (
                        origin_name, dest_name, departure_date, departure_time, 
                        flight_number, airline, aircraft_class, seats_left,
                        {price_column}
                    )
                    VALUES (?,?,?,?,?,?,?,?,?)
                """, (
                    origin_city, dest_city, date_shamsi, dep_time,
                    flight_no, f["airline"], aircraft_class, f.get("seats_left"),
                    f["price"]
                ))
    
        conn.commit()
        conn.close()
        print(f"✅ {len(flights)} رکورد از {self.site_name} در جدول کلی ذخیره/آپدیت شد")
    

# --------------------------
# Charter118 Pipeline
# --------------------------
class Charter118Pipeline(PipelineBase):
    def __init__(self):
        super().__init__("Charter118", "Flights_Charter118")

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
                #is_system = "بله" if any("سیستمی" in t for t in tag_texts) else "خیر"
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
                        #"is_system": is_system,
                        "departure_time": departure_time,
                        "seats_left": seats_left
                    })
            except:
                continue
        return flights

# --------------------------
# Flightio Pipeline
# --------------------------
class FlightioPipeline(PipelineBase):
    def __init__(self):
        super().__init__("Flightio", "Flights_Flightio")

    def build_url(self, origin_iata, dest_iata, date_gregorian, passengers, international=False):
        flight_type = 1 if international else 2
        cabin_type = 1
        return f"https://flightio.com/flight/{origin_iata}-{dest_iata}?depart={date_gregorian}&adult={passengers}&child=0&infant=0&flightType={flight_type}&cabinType={cabin_type}"

    async def fetch_html(self, url, wait_selector="section.transition-input-100"):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
            context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
            page = await context.new_page()
            await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
            await page.goto(url, wait_until="domcontentloaded", timeout=120000)
            try:
                await page.wait_for_selector(wait_selector, timeout=120000)
                print("✅ فلاییتو لود شد")
            except:
                print("⚠️ پرواز نمایش داده نشد یا سایت Bot رو فهمید")
            for _ in range(15):
                await page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
                await asyncio.sleep(2)
            await asyncio.sleep(5)
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
                #system_tag = card.find("span", class_=lambda c: c and "text-dots" in c)
                #system_type = safe_text(system_tag)
                #is_system = "سیستمی" in (system_type or "")
                # ✅ کلاس واقعی پرواز (اکونومی / بیزنس) از بخش جزئیات
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

                        #"is_system": is_system,
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

    def build_url(self, origin_iata, dest_iata, date_shamsi, passengers, international=False):
        base = "https://www.alibaba.ir/international" if international else "https://www.alibaba.ir/flights"
        return f"{base}/{origin_iata}-{dest_iata}?adult={passengers}&child=0&infant=0&departing={date_shamsi}"

    def parse_flights(self, html):
        flights = []
        try:
            soup = BeautifulSoup(html, "html.parser")
            cards = soup.select("div.available-card__content")
            if not cards:
                print("⚠️ هیچ کارت پروازی پیدا نشد.")
                return flights
        except Exception as e:
            print("⚠️ خطا در واکشی کارت‌ها:", e)
            return flights

        for idx, card in enumerate(cards):
            try:
                # ✈️ نام ایرلاین
                airline_tag = card.select_one("div.break-words.text-center.text-grays-500.text-caption")
                airline = airline_tag.get_text(strip=True) if airline_tag else None

                # ⏰ زمان‌ها
                times = card.select("strong.text-5, strong.text-6")
                dep_time = times[0].get_text(strip=True) if len(times) > 0 else None
                arr_time = times[1].get_text(strip=True) if len(times) > 1 else None

                # 🌆 شهرها
                cities = card.select("div.flex.gap-2.items-center > span")
                dep_city = cities[0].get_text(strip=True) if len(cities) > 0 else None
                arr_city = cities[1].get_text(strip=True) if len(cities) > 1 else None

                # 🆔 شماره پرواز
                flight_number = None
                for lbl in card.select("span.text-caption.text-grays-400"):
                    if "شماره پرواز" in lbl.get_text(strip=True):
                        num_span = lbl.find_next("span", class_="text-headline-sm text-grays-600")
                        if num_span:
                            flight_number = num_span.get_text(strip=True)
                        break

                # 💺 کلاس پرواز
                aircraft_class = None
                for lbl in card.select("span.a-label"):
                    txt = lbl.get_text(strip=True)
                    if "اکونومی" in txt or "بیزینس" in txt:
                        aircraft_class = txt
                        break

                # 💰 قیمت
                price_el = card.select_one("strong.text-secondary-400")
                price = int(re.sub(r"[^\d]", "", price_el.get_text())) if price_el else None

                # 🧍 صندلی باقی‌مانده
                seats_el = card.select_one("div.text-2.mt-1.text-danger-400 span.ml-1")
                seats_left = seats_el.get_text(strip=True) if seats_el else None

                if airline and dep_time and price:
                    flights.append({
                        "flight_number": flight_number,
                        "airline": airline,
                        "departure_city": dep_city,
                        "arrival_city": arr_city,
                        "departure_time": dep_time,
                        "arrival_time": arr_time,
                        "aircraft_class": aircraft_class,
                        "price": price,
                        "seats_left": seats_left
                    })
            except Exception as e:
                print(f"⚠️ خطا در کارت {idx}:", e)
                continue

        print(f"✅ {len(flights)} پرواز از علی‌بابا استخراج شد.")
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

    pipelines = [Charter118Pipeline(), 
                 AlibabaPipeline(), FlightioPipeline()]

    for pipeline in pipelines:
        date_gregorian = base_jdate.togregorian().strftime("%Y-%m-%d")
        if isinstance(pipeline, AlibabaPipeline):
            url = pipeline.build_url(origin_iata, dest_iata, date_shamsi, passengers, intl)
        else:
            url = pipeline.build_url(origin_iata, dest_iata, date_gregorian, passengers, intl)

        print(f"📡 دریافت پروازهای {origin_city} → {dest_city} از: {pipeline.site_name}")
        wait_selector = "div.bg-white.rounded-lg" if isinstance(pipeline, Charter118Pipeline) else \
                        "div.available-card__content" if isinstance(pipeline, AlibabaPipeline) else \
                        "section.transition-input-100"
        html = await pipeline.fetch_html(url, wait_selector=wait_selector)
        flights = pipeline.parse_flights(html)
        pipeline.save_to_db(flights, origin_city, dest_city, date_shamsi)


    print("✅ تمام شد!")

if __name__ == "__main__":
    asyncio.run(main())
