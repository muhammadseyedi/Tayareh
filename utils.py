# utils.py - توابع کمکی مشترک
"""
این فایل شامل توابع کمکی است که در تمام pipelines استفاده می‌شود
"""

import re
import logging
from config import AIRLINE_NORMALIZATION

# تنظیم لاگر
logger = logging.getLogger(__name__)


def normalize_airline(airline_name: str) -> str:
    """
    نرمال‌سازی نام ایرلاین
    
    Args:
        airline_name: نام ایرلاین (ممکن است فارسی، انگلیسی یا مختلط باشد)
    
    Returns:
        نام استاندارد شده ایرلاین
    """
    if not airline_name:
        return "نامشخص"
    
    airline_name = airline_name.strip()
    return AIRLINE_NORMALIZATION.get(airline_name, airline_name)


def normalize_aircraft_class(class_text: str) -> str:
    """
    نرمال‌سازی کلاس پرواز به اکونومی یا بیزینس
    
    Args:
        class_text: متن کلاس پرواز
    
    Returns:
        "اکونومی" یا "بیزینس" یا None
    """
    if not class_text:
        return None
    
    class_text = class_text.strip().lower()
    
    if any(word in class_text for word in ["بیزنس", "بیزینس", "business"]):
        return "بیزینس"
    elif any(word in class_text for word in ["اکونومی", "اقتصادی", "economy"]):
        return "اکونومی"
    
    return None


def extract_price(price_text: str) -> int:
    """
    استخراج قیمت از متن (حذف کاراکترهای غیرعددی)
    
    Args:
        price_text: متن حاوی قیمت
    
    Returns:
        قیمت به صورت عدد صحیح یا None
    """
    if not price_text:
        return None
    
    # حذف تمام کاراکترهای غیرعددی
    if isinstance(price_text, str):
        digits = re.sub(r"[^\d]", "", price_text)
        return int(digits) if digits else None
    elif isinstance(price_text, (int, float)):
        return int(price_text)
    
    return None


def extract_time_from_text(time_text: str) -> str:
    """
    استخراج زمان به فرمت HH:MM از متن
    
    Args:
        time_text: متن حاوی زمان
    
    Returns:
        زمان به فرمت HH:MM یا None
    """
    if not time_text:
        return None
    
    time_text = time_text.strip()
    
    # اگر فرمت ISO datetime (2024-01-01T12:30:00)
    if "T" in time_text:
        try:
            return time_text.split("T")[1][:5]
        except Exception:
            return None
    
    # اگر فقط تاریخ (yyyy-mm-dd)
    if re.match(r"^\d{4}-\d{2}-\d{2}$", time_text):
        return None
    
    # جستجوی الگوی HH:MM
    match = re.search(r"(\d{1,2}:\d{2})", time_text)
    if match:
        return match.group(1)
    
    # اگر طول مناسب داشت، 5 کاراکتر اول را برگردان
    return time_text[:5] if len(time_text) >= 5 else None


def persian_to_latin_digits(text: str) -> str:
    """
    تبدیل اعداد فارسی و عربی به لاتین
    
    Args:
        text: متن حاوی اعداد فارسی/عربی
    
    Returns:
        متن با اعداد لاتین
    """
    if not text:
        return text
    
    persian_digits = {
        '۰': '0', '۱': '1', '۲': '2', '۳': '3', '۴': '4',
        '۵': '5', '۶': '6', '۷': '7', '۸': '8', '۹': '9',
        '٠': '0', '١': '1', '٢': '2', '٣': '3', '٤': '4',
        '٥': '5', '٦': '6', '٧': '7', '٨': '8', '٩': '9'
    }
    
    return ''.join(persian_digits.get(ch, ch) for ch in text)


def clean_city_name(city_name: str) -> str:
    """
    پاکسازی نام شهر از کلمات اضافی مثل "فرودگاه"
    
    Args:
        city_name: نام شهر یا فرودگاه
    
    Returns:
        نام پاک شده شهر
    """
    if not city_name:
        return None
    
    # حذف کلمات اضافی
    city_name = re.sub(
        r"فرودگاه|بین‌المللی|Airport|International", 
        "", 
        city_name
    ).strip()
    
    # نرمال‌سازی نام‌های خاص تهران
    city_name = city_name.replace("مهرآباد", "تهران")
    city_name = city_name.replace("امام خمینی", "تهران")
    
    return city_name


def extract_flight_number(text: str, patterns: list = None) -> str:
    """
    استخراج شماره پرواز از متن
    
    Args:
        text: متن حاوی شماره پرواز
        patterns: لیست الگوهای regex اضافی
    
    Returns:
        شماره پرواز یا None
    """
    if not text:
        return None
    
    # الگوهای پیش‌فرض
    default_patterns = [
        r"شماره پرواز[:\s]*([A-Za-z0-9\-]+)",
        r"Flight\s*No\.?\s*[:\-]?\s*([A-Za-z0-9]+)",
        r"پرواز شماره[:\s]*([A-Za-z0-9\-]+)"
    ]
    
    if patterns:
        default_patterns.extend(patterns)
    
    for pattern in default_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    
    return None


def safe_get_text(element, default: str = None) -> str:
    """
    دریافت ایمن متن از المنت BeautifulSoup
    
    Args:
        element: المنت BeautifulSoup
        default: مقدار پیش‌فرض
    
    Returns:
        متن المنت یا مقدار پیش‌فرض
    """
    if element is None:
        return default
    
    try:
        return element.get_text(strip=True)
    except Exception:
        return default


def validate_flight_data(flight: dict) -> bool:
    """
    اعتبارسنجی داده‌های پرواز قبل از ذخیره
    
    Args:
        flight: دیکشنری اطلاعات پرواز
    
    Returns:
        True اگر داده‌ها معتبر باشند
    """
    # حداقل باید قیمت، ایرلاین و زمان حرکت داشته باشد
    required_fields = ["price", "airline", "departure_time"]
    
    for field in required_fields:
        value = flight.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            logger.debug(f"فیلد {field} موجود نیست یا خالی است")
            return False
    
    # قیمت باید عدد معتبر باشد
    if not isinstance(flight.get("price"), (int, float)) or flight.get("price") <= 0:
        logger.debug("قیمت نامعتبر است")
        return False
    
    return True


def get_iata_for_international(iata_code: str, city_name: str) -> str:
    """
    تبدیل کد IATA برای پروازهای بین‌المللی
    (مثلاً THR به IKA برای تهران)
    
    Args:
        iata_code: کد IATA فعلی
        city_name: نام شهر
    
    Returns:
        کد IATA مناسب برای پرواز بین‌المللی
    """
    if city_name == "tehran" and iata_code == "THR":
        return "IKA"
    
    return iata_code