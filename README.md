# 🛫 سیستم جمع‌آوری خودکار قیمت پروازها

این سیستم به صورت خودکار از ۹ سایت اصلی رزرو بلیط هواپیما قیمت‌ها را جمع‌آوری و در SQL Server ذخیره می‌کند.

## 📋 فهرست مطالب
- [ویژگی‌ها](#-ویژگیها)
- [نصب و راه‌اندازی](#-نصب-و-راهاندازی)
- [نحوه استفاده](#-نحوه-استفاده)
- [ساختار پروژه](#-ساختار-پروژه)
- [سایت‌های پشتیبانی شده](#-سایتهای-پشتیبانی-شده)

---

## ✨ ویژگی‌ها

- ✅ **جمع‌آوری از ۹ سایت مختلف** به صورت همزمان
- ✅ **اجرای خودکار** هر نیم ساعت
- ✅ **آپدیت هوشمند قیمت‌ها** - فقط در صورت ارزان‌تر بودن
- ✅ **تشخیص صندلی‌های پر شده** و علامت‌گذاری
- ✅ **نرمال‌سازی نام ایرلاین‌ها** برای یکسان‌سازی
- ✅ **لاگ جامع** با ذخیره در فایل
- ✅ **مدیریت خطا** بدون توقف کل سیستم

---

## 🚀 نصب و راه‌اندازی

### پیش‌نیازها
```bash
# Python 3.8 یا بالاتر
# SQL Server با دیتابیس FlightsDB
```

### مرحله ۱: نصب کتابخانه‌ها
```bash
pip install -r requirements.txt
```

### مرحله ۲: نصب Playwright Browsers
```bash
playwright install chromium
```

### مرحله ۳: تنظیم دیتابیس
دیتابیس `FlightsDB` باید از قبل ساخته شده باشد با جدول `Flights_AllSites`:

```sql
CREATE TABLE Flights_AllSites (
    id INT IDENTITY(1,1) PRIMARY KEY,
    origin_name NVARCHAR(100),
    dest_name NVARCHAR(100),
    departure_date NVARCHAR(20),
    departure_time NVARCHAR(10),
    arrival_time NVARCHAR(10),
    flight_number NVARCHAR(20),
    airline NVARCHAR(100),
    aircraft_class NVARCHAR(50),
    
    -- ستون‌های قیمت برای هر سایت
    price_alibaba INT NULL,
    price_charter118 INT NULL,
    price_flightio INT NULL,
    price_mrbilit INT NULL,
    price_ghasedak INT NULL,
    price_flytoday INT NULL,
    price_snapptrip INT NULL,
    price_eligasht INT NULL,
    price_ultravs INT NULL,
    
    created_at DATETIME DEFAULT GETDATE(),
    updated_at DATETIME DEFAULT GETDATE()
);
```

### مرحله ۴: تنظیم Connection String
فایل `config.py` را باز کنید و connection string دیتابیس را ویرایش کنید:

```python
DB_CONFIG = {
    "driver": "SQL Server",
    "server": "localhost",  # یا نام سرور شما
    "database": "FlightsDB",
    "trusted_connection": "yes"  # یا از username/password استفاده کنید
}
```

---

## 📖 نحوه استفاده

### حالت ۱: اجرای تعاملی (یکبار)
```bash
python main.py
```

سپس اطلاعات را وارد کنید:
```
🛫 مبدأ (مثلاً tehran): tehran
🛬 مقصد (مثلاً mashhad): mashhad
📅 تاریخ شمسی (مثلاً 1404/08/10): 1404/08/20
👥 تعداد مسافران: 1
🌍 پرواز بین‌المللی؟ (y/n): n
```

### حالت ۲: اجرای خودکار (Daemon)
```bash
python main.py daemon
```

این دستور برنامه را در حالت پس‌زمینه اجرا می‌کند که:
- ✅ بلافاصله یکبار اجرا می‌شود
- ✅ سپس هر **۳۰ دقیقه** به صورت خودکار تکرار می‌شود
- ✅ تمام لاگ‌ها در فایل `flight_scraper.log` ذخیره می‌شوند

#### توقف Daemon
برای توقف، `Ctrl+C` را فشار دهید.

---

## 📁 ساختار پروژه

```
flight-scraper/
│
├── config.py              # تنظیمات مرکزی (دیتابیس، IATA، ...)
├── utils.py               # توابع کمکی مشترک
├── base_pipeline.py       # کلاس پایه برای scraperها
├── pipelines.py           # تمام scraperها (۹ سایت)
├── main.py                # برنامه اصلی + scheduler
├── requirements.txt       # لیست کتابخانه‌ها
├── README.md             # این فایل
└── flight_scraper.log    # فایل لاگ (خودکار ساخته می‌شود)
```

---

## 🌐 سایت‌های پشتیبانی شده

| # | سایت | نام کلاس | ستون قیمت |
|---|------|-----------|-----------|
| 1 | علی‌بابا | `AlibabaPipeline` | `price_alibaba` |
| 2 | چارتر ۱۱۸ | `Charter118Pipeline` | `price_charter118` |
| 3 | فلاییتو | `FlightioPipeline` | `price_flightio` |
| 4 | مستر بلیط | `MrBilitPipeline` | `price_mrbilit` |
| 5 | قاصدک ۲۴ | `GhasedakPipeline` | `price_ghasedak` |
| 6 | فلای تودی | `FlytodayPipeline` | `price_flytoday` |
| 7 | اسنپ‌تریپ | `SnappTripPipeline` | `price_snapptrip` |
| 8 | ای‌لی‌گشت | `EligashtPipeline` | `price_eligasht` |
| 9 | یوتراوس | `UltravsPipeline` | `price_ultravs` |

---

## ⚙️ تنظیمات پیشرفته

### تغییر بازه زمانی اجرای خودکار
فایل `config.py` را ویرایش کنید:

```python
SCHEDULE_CONFIG = {
    "run_every_minutes": 30,  # هر ۳۰ دقیقه (می‌توانید تغییر دهید)
    "first_run_delay": 5,     # تاخیر اولیه به ثانیه
}
```

### اضافه کردن مسیرهای جستجو
فایل `main.py` را ویرایش کنید:

```python
searches = [
    {
        "origin": "tehran",
        "dest": "mashhad",
        "date": "1404/08/20",
        "passengers": 1,
        "international": False
    },
    {
        "origin": "tehran",
        "dest": "kish",
        "date": "1404/08/25",
        "passengers": 2,
        "international": False
    },
    # می‌توانید موارد بیشتری اضافه کنید
]
```

---

## 🐛 عیب‌یابی

### خطای "Module not found"
```bash
pip install -r requirements.txt
playwright install
```

### خطای Connection به SQL Server
- مطمئن شوید SQL Server در حال اجراست
- Connection String را در `config.py` بررسی کنید
- اگر از Authentication استفاده می‌کنید، username/password را اضافه کنید

### برخی سایت‌ها داده برنمی‌گردانند
این طبیعی است - بعضی سایت‌ها:
- ممکن است Bot Detection داشته باشند
- در زمان اجرا پرواز موجود نداشته باشند
- تغییر ساختار داده باشند

لاگ‌ها را بررسی کنید: `flight_scraper.log`

---

## 📊 مثال خروجی

```
============================================================
شروع جستجوی پروازهای tehran → mashhad
تاریخ: 1404/08/20 | مسافران: 1 | بین‌المللی: False
============================================================
▶ شروع Alibaba
✈️ 45 پرواز از علی‌بابا استخراج شد
✅ Alibaba: درج=12, آپدیت=33, رد شده=0
✓ Alibaba تمام شد
▶ شروع Charter118
✈️ 28 پرواز از Charter118 استخراج شد
✅ Charter118: درج=8, آپدیت=20, رد شده=0
✓ Charter118 تمام شد
...
============================================================
✅ اتمام جستجو
موفق: 9 | ناموفق: 0
============================================================
```

---

## 📝 یادداشت‌ها

- همه قیمت‌ها به **تومان** ذخیره می‌شوند
- تاریخ‌ها به فرمت **شمسی** (۱۴۰۴/۰۸/۲۰) وارد شوند
- برای پروازهای بین‌المللی، سیستم خودکار کد فرودگاه را تغییر می‌دهد (مثلاً THR → IKA)
- اگر پروازی در چند سایت موجود باشد، تنها **ارزان‌ترین قیمت** در هر ستون ذخیره می‌شود

---

## 🔒 امنیت

- ⚠️ فایل `config.py` را در `.gitignore` قرار دهید (اگر از Git استفاده می‌کنید)
- ⚠️ اطلاعات دیتابیس را از environment variables بخوانید (برای production)
- ⚠️ از VPN استفاده کنید اگر سایت‌ها IP شما را بلاک کردند

---

## 📞 پشتیبانی

در صورت بروز مشکل:
1. فایل `flight_scraper.log` را بررسی کنید
2. مطمئن شوید تمام پیش‌نیازها نصب شده‌اند
3. ساختار HTML سایت‌ها ممکن است تغییر کرده باشد

---

**نسخه:** 2.0  
**آخرین آپدیت:** ۱۴۰۴/۰۸/۱۷