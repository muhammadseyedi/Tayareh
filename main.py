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
def connect_db():
    return pyodbc.connect("DRIVER={SQL Server};SERVER=localhost;Trusted_Connection=yes;")

def init_db(db_name, table_name):
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute(f"""
    IF DB_ID(N'{db_name}') IS NULL
    BEGIN
        CREATE DATABASE [{db_name}];
    END;
    """)
    cursor.commit()
    cursor.close()
    conn.close()

    conn2 = pyodbc.connect(
        f"DRIVER={{SQL Server}};SERVER=localhost;DATABASE={db_name};Trusted_Connection=yes;"
    )
    cursor2 = conn2.cursor()
    cursor2.execute(f"""
    IF OBJECT_ID('dbo.{table_name}', 'U') IS NULL
    CREATE TABLE dbo.{table_name} (
        id INT IDENTITY(1,1) PRIMARY KEY,
        origin_code NVARCHAR(10),
        origin_name NVARCHAR(50),
        dest_code NVARCHAR(10),
        dest_name NVARCHAR(50),
        departure_date NVARCHAR(10),
        departure_time NVARCHAR(10),
        flight_number NVARCHAR(50),
        price BIGINT,
        airline NVARCHAR(50),
        aircraft_class NVARCHAR(50),
        is_system NVARCHAR(5),
        seats_left NVARCHAR(20)
    );
    """)
    conn2.commit()
    conn2.close()

# --------------------------
# کلاس پایه
# --------------------------
class PipelineBase:
    def __init__(self, site_name, table_name):
        self.site_name = site_name
        self.db_name = "FlightsDB"
        self.table_name = table_name
        init_db(self.db_name, self.table_name)

    async def fetch_html(self, url, wait_selector=None):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url)
            if wait_selector:
                try:
                    await page.wait_for_selector(wait_selector, timeout=15000)
                except:
                    print(f"⚠️ المنت {wait_selector} پیدا نشد.")
            await asyncio.sleep(3)
            html = await page.content()
            await browser.close()
            return html

    def save_to_db(self, flights, origin_iata, origin_city, dest_iata, dest_city, date_shamsi):
        conn = pyodbc.connect(
            f"DRIVER={{SQL Server}};SERVER=localhost;DATABASE={self.db_name};Trusted_Connection=yes;"
        )
        cursor = conn.cursor()
        for f in flights:
            cursor.execute(f"""
                INSERT INTO {self.table_name} (
                    origin_code, origin_name, dest_code, dest_name, departure_date, 
                    departure_time, flight_number, price, airline, aircraft_class, 
                    is_system, seats_left
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                origin_iata, origin_city, dest_iata, dest_city, date_shamsi,
                f["departure_time"], f["flight_number"], f["price"], f["airline"],
                f["aircraft_class"], f["is_system"], f["seats_left"]
            ))
        conn.commit()
        conn.close()
        print(f"✅ {len(flights)} پرواز از {self.site_name} ذخیره شد")

# --------------------------
# Charter118
# --------------------------
class Charter118Pipeline(PipelineBase):
    def __init__(self):
        super().__init__("charter118", "Flights_Charter118")

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
                is_system = "بله" if any("سیستمی" in t for t in tag_texts) else "خیر"

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
                        "is_system": is_system,
                        "departure_time": departure_time,
                        "seats_left": seats_left
                    })
            except Exception:
                continue
        return flights

# --------------------------
# Alibaba
# --------------------------
class AlibabaPipeline(PipelineBase):
    def __init__(self):
        super().__init__("Alibaba", "Flights_Alibaba")

    def build_url(self, origin_iata, dest_iata, date_shamsi, passengers, international=False):
        base = "https://www.alibaba.ir/international" if international else "https://www.alibaba.ir/flights"
        return f"{base}/{origin_iata}-{dest_iata}?adult={passengers}&child=0&infant=0&departing={date_shamsi}"

    async def fetch_html(self, url, wait_selector="div.available-card__content"):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            page = await browser.new_page()
            await page.goto(url, wait_until="networkidle")

            try:
                await page.wait_for_selector(wait_selector, timeout=25000)
            except:
                print("⚠️ کارت‌ها لود نشدند")

            await asyncio.sleep(5)
            html = await page.content()
            await browser.close()
            return html

    def parse_flights(self, html):
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.find_all("div", class_="available-card__content")
        flights = []
        for card in cards:
            try:
                airline = card.find("div", class_="break-words").text.strip()
                times = card.find_all("strong", class_="text-5 md:text-6")
                departure_time = times[0].text.strip() if times else None
                price_tag = card.find("strong", class_="text-secondary-400")
                price = int(price_tag.text.replace(",", "")) if price_tag else None

                if airline and departure_time and price:
                    flights.append({
                        "flight_number": None,
                        "price": price,
                        "airline": airline,
                        "aircraft_class": None,
                        "is_system": None,
                        "departure_time": departure_time,
                        "seats_left": None
                    })
            except:
                continue
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

    pipelines = [Charter118Pipeline(), AlibabaPipeline()]

    for pipeline in pipelines:
        date_gregorian = base_jdate.togregorian().strftime("%Y-%m-%d")
        url = pipeline.build_url(origin_iata, dest_iata, date_shamsi, passengers, intl)
        html = await pipeline.fetch_html(url)
        flights = pipeline.parse_flights(html)
        pipeline.save_to_db(flights, origin_iata, origin_city, dest_iata, dest_city, date_shamsi)

    print("✅ تمام شد!")

# اجرای برنامه
if __name__ == "__main__":
    asyncio.run(main())
