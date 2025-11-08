# config.py - تنظیمات مرکزی پروژه
"""
این فایل تمام تنظیمات ثابت و مشترک پروژه را نگه‌داری می‌کند
"""

# --------------------------
# 🗄️ تنظیمات دیتابیس
# --------------------------
DB_CONFIG = {
    "driver": "SQL Server",
    "server": "localhost",
    "database": "FlightsDB",
    "trusted_connection": "yes"
}

DB_CONNECTION_STRING = (
    f"DRIVER={{{DB_CONFIG['driver']}}};"
    f"SERVER={DB_CONFIG['server']};"
    f"DATABASE={DB_CONFIG['database']};"
    f"Trusted_Connection={DB_CONFIG['trusted_connection']};"
)

# نام جدول مرکزی
TABLE_NAME = "Flights_AllSites"

# --------------------------
# 🌍 کدهای IATA شهرها
# --------------------------
IATA_CODES = {
    # شهرهای ایران
    "tehran": "THR", "mashhad": "MHD", "isfahan": "IFN", "shiraz": "SYZ",
    "tabriz": "TBZ", "kish": "KIH", "ahvaz": "AWZ", "bandar abbas": "BND",
    "urmia": "OMH", "rasht": "RAS", "kermanshah": "KSH", "yazd": "AZD",
    "bushehr": "BUZ", "lar": "LRR", "sari": "SRY", "ardabil": "ADU",
    
    # شهرهای بین‌المللی
    "baghdad": "BGW", "najaf": "NJF", "erbil": "EBL",
    "istanbul": "IST", "ankara": "ESB", "antalya": "AYT"
}

# --------------------------
# ✈️ نرمال‌سازی نام ایرلاین‌ها
# --------------------------
AIRLINE_NORMALIZATION = {
    # ماهان
    "ماهان": "ماهان", "ماهان ایر": "ماهان", "Mahan Air": "ماهان",
    "mahan": "ماهان", "Mahan": "ماهان",
    
    # معراج
    "Meraj": "معراج", "معراج": "معراج",
    
    # آتا
    "آتا": "آتا", "ATA": "آتا", "Ata Airlines": "آتا", "ATA Airlines": "آتا",
    "آتا ایر": "آتا", "Ata": "آتا",
    
    # چابهار
    "چابهار": "چابهار", "Chabahar": "چابهار", "Chabahar Air": "چابهار",
    "Chabahar Airlines": "چابهار",
    
    # ساها
    "ساها": "ساها", "Saha": "ساها", "Saha Air": "ساها", "ساها ایر": "ساها",
    
    # نسیم ایر
    "نسیم ایر": "نسیم ایر", "نسيم اير": "نسیم ایر", "Nasim Air": "نسیم ایر",
    "Nasim Airlines": "نسیم ایر",
    
    # ایران ایر
    "ایران ایر": "ایران ایر", "Iran Air": "ایران ایر",
    
    # ایران ایرتور
    "ایران ایرتور": "ایران ایرتور", "ایران ایر تور": "ایران ایرتور",
    "Iran Air Tours": "ایران ایرتور", "Iran Airtour": "ایران ایرتور",
    "Iran Airtours": "ایران ایرتور",
    
    # قشم ایر
    "قشم ایر": "قشم ایر", "Qeshm Air": "قشم ایر", "Qeshm Airlines": "قشم ایر",
    "Qeshm": "قشم ایر",
    
    # آسمان
    "آسمان": "آسمان", "Iran Aseman Airlines": "آسمان", "Aseman Airlines": "آسمان",
    "Aseman": "آسمان",
    
    # آوا ایر
    "آوا ایر": "آوا ایر", "آوا": "آوا ایر", "Ava Air": "آوا ایر",
    "Ava Airlines": "آوا ایر",
    
    # اروند
    "اروان": "اروان", "اروان ایرلاین": "اروان", "Ervan": "اروان",
    "Ervan Air": "اروان", "Ervan Airlines": "اروان",
    
    # زاگرس
    "زاگرس": "زاگرس", "Zagros": "زاگرس", "Zagros Airlines": "زاگرس",
    
    # کاسپین
    "کاسپین": "کاسپین", "Caspian": "کاسپین", "Caspian Airlines": "کاسپین",
    
    # فلای کیش
    "فلای کیش": "فلای کیش", "Fly Kish": "فلای کیش", "FlyKish": "فلای کیش",
    "Flykish Airlines": "فلای کیش",
    
    # کیش ایر
    "کیش ایر": "کیش ایر", "Kish Airlines": "کیش ایر", "Kish Air": "کیش ایر",
    
    # اطلس ایر
    "اطلس ایر": "اطلس ایر", "اطلس اير": "اطلس ایر", "Atlas Air": "اطلس ایر",
    "Atlas Airline": "اطلس ایر", "Atlas Airlines": "اطلس ایر",
    
    # تابان
    "تابان": "تابان", "Taban Air": "تابان", "Taban Airlines": "تابان",
    
    # وارش
    "وارش": "وارش", "Varesh": "وارش", "Varesh Airlines": "وارش",
}

# --------------------------
# 🎨 تنظیمات نمایش
# --------------------------
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)

# --------------------------
# ⏰ تنظیمات Scheduler
# --------------------------
SCHEDULE_CONFIG = {
    "run_every_minutes": 30,  # هر نیم ساعت
    "first_run_delay": 5,     # تاخیر اولیه (ثانیه)
}

# --------------------------
# 📊 تنظیمات لاگ
# --------------------------
LOG_CONFIG = {
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    "level": "INFO",
    "file": "flight_scraper.log"
}