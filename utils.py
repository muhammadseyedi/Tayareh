"""
توابع کمکی برای پردازش و نرمال‌سازی داده‌ها
"""
import re
from config import AIRLINE_NORMALIZATION


def persian_to_latin_digits(text: str) -> str:
    """تبدیل اعداد فارسی و عربی به لاتین"""
    if not text:
        return text
    
    PERSIAN_DIGITS = {
        '۰': '0', '۱': '1', '۲': '2', '۳': '3', '۴': '4',
        '۵': '5', '۶': '6', '۷': '7', '۸': '8', '۹': '9',
        '٠': '0', '١': '1', '٢': '2', '٣': '3', '٤': '4',
        '٥': '5', '٦': '6', '٧': '7', '٨': '8', '٩': '9'
    }
    return ''.join(PERSIAN_DIGITS.get(ch, ch) for ch in text)


def normalize_price(text):
    """استخراج و نرمال‌سازی قیمت از متن"""
    if not text:
        return None
    
    # تبدیل اعداد فارسی به لاتین
    text = persian_to_latin_digits(str(text))
    
    # حذف کاراکترهای غیرعددی
    digits = re.sub(r"[^\d]", "", text)
    
    return int(digits) if digits else None


def normalize_airline(airline_name: str) -> str:
    """نرمال‌سازی نام ایرلاین"""
    if not airline_name:
        return "نامشخص"
    
    airline_name = airline_name.strip()
    return AIRLINE_NORMALIZATION.get(airline_name, airline_name)


def normalize_aircraft_class(class_text: str) -> str:
    """نرمال‌سازی کلاس پرواز به اکونومی یا بیزینس"""
    if not class_text:
        return None
    
    class_text = class_text.strip()
    
    if "بیزنس" in class_text or "بیزینس" in class_text or "business" in class_text.lower():
        return "بیزینس"
    elif "اکونومی" in class_text or "economy" in class_text.lower():
        return "اکونومی"
    
    return None


def extract_time_from_datetime(datetime_str: str) -> str:
    """استخراج زمان (HH:MM) از رشته تاریخ-زمان"""
    if not datetime_str:
        return None
    
    datetime_str = datetime_str.strip()
    
    # اگر قالب ISO datetime (با T)
    if "T" in datetime_str:
        try:
            return datetime_str.split("T")[1][:5]
        except Exception:
            return None
    
    # اگر فقط تاریخ yyyy-mm-dd
    if re.match(r"^\d{4}-\d{2}-\d{2}$", datetime_str):
        return None
    
    # جستجوی الگوی HH:MM در رشته
    match = re.search(r"(\d{1,2}:\d{2})", datetime_str)
    if match:
        return match.group(1)
    
    # fallback: اگر طول مناسب داشت برش بزن
    return datetime_str[:5] if len(datetime_str) >= 5 else None


def normalize_airport_to_city(airport_name: str) -> str:
    """تبدیل نام فرودگاه به نام شهر"""
    if not airport_name:
        return None
    
    # حذف کلمات اضافی
    airport_name = re.sub(
        r"فرودگاه|بین‌المللی|Airport|International", 
        "", 
        airport_name
    ).strip()
    
    # جایگزینی نام‌های خاص
    replacements = {
        "مهرآباد": "تهران",
        "امام خمینی": "تهران",
        "Mehrabad": "Tehran",
        "Imam Khomeini": "Tehran"
    }
    
    for old, new in replacements.items():
        if old in airport_name:
            return new
    
    return airport_name