# db_manager.py - مدیریت پیشرفته دیتابیس
"""
این فایل شامل توابعی برای مدیریت دیتابیس است
مثل تشخیص پروازهای پر شده، cleanup و گزارش‌گیری
"""

import pyodbc
import logging
from datetime import datetime
from config import DB_CONNECTION_STRING, TABLE_NAME

logger = logging.getLogger(__name__)


class DatabaseManager:
    """کلاس مدیریت دیتابیس"""
    
    def __init__(self):
        self.conn_str = DB_CONNECTION_STRING
        self.table = TABLE_NAME
    
    def get_connection(self):
        """دریافت connection به دیتابیس"""
        return pyodbc.connect(self.conn_str)
    
    def mark_sold_out_flights(self):
        """
        علامت‌گذاری پروازهایی که در تمام سایت‌ها قیمت ندارند (صندلی‌ها پر شده)
        این تابع باید بعد از هر scrape اجرا شود
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # جستجوی پروازهایی که هیچ قیمتی ندارند
            query = f"""
                UPDATE {self.table}
                SET 
                    price_alibaba = CASE WHEN price_alibaba IS NULL THEN -1 ELSE price_alibaba END,
                    price_charter118 = CASE WHEN price_charter118 IS NULL THEN -1 ELSE price_charter118 END,
                    price_flightio = CASE WHEN price_flightio IS NULL THEN -1 ELSE price_flightio END,
                    price_mrbilit = CASE WHEN price_mrbilit IS NULL THEN -1 ELSE price_mrbilit END,
                    price_ghasedak = CASE WHEN price_ghasedak IS NULL THEN -1 ELSE price_ghasedak END,
                    price_flytoday = CASE WHEN price_flytoday IS NULL THEN -1 ELSE price_flytoday END,
                    price_snapptrip = CASE WHEN price_snapptrip IS NULL THEN -1 ELSE price_snapptrip END,
                    price_eligasht = CASE WHEN price_eligasht IS NULL THEN -1 ELSE price_eligasht END,
                    price_ultravs = CASE WHEN price_ultravs IS NULL THEN -1 ELSE price_ultravs END,
                    updated_at = GETDATE()
                WHERE 
                    departure_date >= CONVERT(DATE, GETDATE())  -- فقط پروازهای آینده
                    AND (
                        price_alibaba IS NULL AND
                        price_charter118 IS NULL AND
                        price_flightio IS NULL AND
                        price_mrbilit IS NULL AND
                        price_ghasedak IS NULL AND
                        price_flytoday IS NULL AND
                        price_snapptrip IS NULL AND
                        price_eligasht IS NULL AND
                        price_ultravs IS NULL
                    )
            """
            
            cursor.execute(query)
            rows_affected = cursor.rowcount
            conn.commit()
            
            if rows_affected > 0:
                logger.info(f"🔴 {rows_affected} پرواز به عنوان 'پر شده' علامت‌گذاری شد (قیمت = -1)")
            
            return rows_affected
            
        except Exception as e:
            logger.error(f"خطا در علامت‌گذاری پروازهای پر شده: {e}")
            conn.rollback()
            return 0
        finally:
            cursor.close()
            conn.close()
    
    def cleanup_old_flights(self, days_old: int = 7):
        """
        حذف پروازهای قدیمی (مثلاً بیش از ۷ روز گذشته)
        
        Args:
            days_old: پروازهای قدیمی‌تر از این تعداد روز حذف شوند
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            query = f"""
                DELETE FROM {self.table}
                WHERE departure_date < DATEADD(day, -{days_old}, GETDATE())
            """
            
            cursor.execute(query)
            rows_deleted = cursor.rowcount
            conn.commit()
            
            if rows_deleted > 0:
                logger.info(f"🗑️ {rows_deleted} پرواز قدیمی حذف شد")
            
            return rows_deleted
            
        except Exception as e:
            logger.error(f"خطا در حذف پروازهای قدیمی: {e}")
            conn.rollback()
            return 0
        finally:
            cursor.close()
            conn.close()
    
    def get_statistics(self):
        """
        دریافت آمار کلی از دیتابیس
        
        Returns:
            dict با آمارهای مختلف
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        stats = {}
        
        try:
            # تعداد کل پروازها
            cursor.execute(f"SELECT COUNT(*) FROM {self.table}")
            stats['total_flights'] = cursor.fetchone()[0]
            
            # تعداد پروازهای آینده (چون تاریخ شمسی است، همه را می‌شماریم)
            # یا می‌توانید با تبدیل تاریخ شمسی به میلادی این کار را انجام دهید
            cursor.execute(f"""
                SELECT COUNT(*) FROM {self.table}
                WHERE departure_date IS NOT NULL AND departure_date != ''
            """)
            stats['future_flights'] = cursor.fetchone()[0]
            
            # تعداد پروازهای پر شده (همه قیمت‌ها -1)
            cursor.execute(f"""
                SELECT COUNT(*) FROM {self.table}
                WHERE 
                    price_alibaba = -1 AND
                    price_charter118 = -1 AND
                    price_flightio = -1 AND
                    price_mrbilit = -1 AND
                    price_ghasedak = -1 AND
                    price_flytoday = -1 AND
                    price_snapptrip = -1 AND
                    price_eligasht = -1 AND
                    price_ultravs = -1
            """)
            stats['sold_out_flights'] = cursor.fetchone()[0]
            
            # میانگین قیمت (برای هر سایت)
            price_columns = [
                'price_alibaba', 'price_charter118', 'price_flightio',
                'price_mrbilit', 'price_ghasedak', 'price_flytoday',
                'price_snapptrip', 'price_eligasht', 'price_ultravs'
            ]
            
            stats['avg_prices'] = {}
            for col in price_columns:
                cursor.execute(f"""
                    SELECT AVG(CAST({col} AS FLOAT))
                    FROM {self.table}
                    WHERE {col} > 0
                """)
                result = cursor.fetchone()[0]
                stats['avg_prices'][col] = int(result) if result else 0
            
            return stats
            
        except Exception as e:
            logger.error(f"خطا در دریافت آمار: {e}")
            return None
        finally:
            cursor.close()
            conn.close()
    
    def get_cheapest_flights(self, origin: str, dest: str, date: str, limit: int = 10):
        """
        دریافت ارزان‌ترین پروازها برای یک مسیر خاص
        
        Args:
            origin: شهر مبدا
            dest: شهر مقصد
            date: تاریخ شمسی
            limit: تعداد نتایج
        
        Returns:
            لیست پروازها به ترتیب ارزانی
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            query = f"""
                SELECT TOP {limit}
                    airline,
                    aircraft_class,
                    departure_time,
                    arrival_time,
                    COALESCE(
                        NULLIF(price_alibaba, -1),
                        NULLIF(price_charter118, -1),
                        NULLIF(price_flightio, -1),
                        NULLIF(price_mrbilit, -1),
                        NULLIF(price_ghasedak, -1),
                        NULLIF(price_flytoday, -1),
                        NULLIF(price_snapptrip, -1),
                        NULLIF(price_eligasht, -1),
                        NULLIF(price_ultravs, -1)
                    ) AS min_price
                FROM {self.table}
                WHERE 
                    origin_name = ? 
                    AND dest_name = ?
                    AND departure_date = ?
                    AND (
                        price_alibaba > 0 OR
                        price_charter118 > 0 OR
                        price_flightio > 0 OR
                        price_mrbilit > 0 OR
                        price_ghasedak > 0 OR
                        price_flytoday > 0 OR
                        price_snapptrip > 0 OR
                        price_eligasht > 0 OR
                        price_ultravs > 0
                    )
                ORDER BY min_price ASC
            """
            
            cursor.execute(query, (origin, dest, date))
            rows = cursor.fetchall()
            
            flights = []
            for row in rows:
                flights.append({
                    'airline': row[0],
                    'aircraft_class': row[1],
                    'departure_time': row[2],
                    'arrival_time': row[3],
                    'price': row[4]
                })
            
            return flights
            
        except Exception as e:
            logger.error(f"خطا در دریافت ارزان‌ترین پروازها: {e}")
            return []
        finally:
            cursor.close()
            conn.close()
    
    def print_statistics(self):
        """چاپ آمار دیتابیس"""
        stats = self.get_statistics()
        
        if not stats:
            print("❌ خطا در دریافت آمار")
            return
        
        print("\n" + "="*60)
        print("📊 آمار دیتابیس پروازها")
        print("="*60)
        print(f"🔢 کل پروازها: {stats['total_flights']:,}")
        print(f"📅 پروازهای آینده: {stats['future_flights']:,}")
        print(f"🔴 پروازهای پر شده: {stats['sold_out_flights']:,}")
        print("\n💰 میانگین قیمت‌ها (تومان):")
        print("-"*60)
        
        site_names = {
            'price_alibaba': 'علی‌بابا',
            'price_charter118': 'چارتر ۱۱۸',
            'price_flightio': 'فلاییتو',
            'price_mrbilit': 'مستر بلیط',
            'price_ghasedak': 'قاصدک ۲۴',
            'price_flytoday': 'فلای تودی',
            'price_snapptrip': 'اسنپ‌تریپ',
            'price_eligasht': 'ای‌لی‌گشت',
            'price_ultravs': 'یوتراوس'
        }
        
        for col, price in stats['avg_prices'].items():
            site_fa = site_names.get(col, col)
            print(f"  {site_fa:.<20} {price:>15,}")
        
        print("="*60 + "\n")


# ================================
# 🔧 توابع کمکی
# ================================

def setup_database():
    """
    ایجاد جدول اگر وجود نداشته باشد
    """
    conn = pyodbc.connect(DB_CONNECTION_STRING)
    cursor = conn.cursor()
    
    try:
        create_table_query = f"""
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='{TABLE_NAME}' AND xtype='U')
        CREATE TABLE {TABLE_NAME} (
            id INT IDENTITY(1,1) PRIMARY KEY,
            origin_name NVARCHAR(100),
            dest_name NVARCHAR(100),
            departure_date NVARCHAR(20),
            departure_time NVARCHAR(10),
            arrival_time NVARCHAR(10),
            flight_number NVARCHAR(20),
            airline NVARCHAR(100),
            aircraft_class NVARCHAR(50),
            
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
        )
        """
        
        cursor.execute(create_table_query)
        conn.commit()
        logger.info("✅ جدول دیتابیس بررسی/ایجاد شد")
        
    except Exception as e:
        logger.error(f"خطا در setup دیتابیس: {e}")
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    # تست
    logging.basicConfig(level=logging.INFO)
    
    # ایجاد جدول
    setup_database()
    
    # ایجاد نمونه
    db = DatabaseManager()
    
    # نمایش آمار
    db.print_statistics()
    
    # علامت‌گذاری پروازهای پر شده
    db.mark_sold_out_flights()
    
    # حذف پروازهای قدیمی‌تر از ۷ روز
    # db.cleanup_old_flights(7)