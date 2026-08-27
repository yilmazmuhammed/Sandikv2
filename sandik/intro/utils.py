"""Tanıtım sayfalarının (özellikle istatistik sayfasının) iş mantığı.

İstatistik sayfası herkese açıktır ve sistemin gerçekte ne kadar kullanıldığını göstermeyi
amaçlar. Bu yüzden **denemelik veriler ayıklanır**: birkaç kayıt girilip bırakılmış sandıklar ve
hiçbir sandıkta üyeliği olmayan site kullanıcıları sayılara dahil edilmez. Ölçütler aşağıdaki
sabitlerdedir; hepsi sayfanın altında kullanıcıya da açıklanır (bkz. `statistics_page.html`).
"""
from datetime import date, datetime, timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta

from sandik.intro import db

# Bir sandığın "gerçekten kullanılıyor" sayılması için gereken en az değerler.
# Sandık tek başına açılıp denenmiş olabilir ya da birkaç deneme kaydından sonra bırakılmış
# olabilir; bu iki eşik bu tür sandıkları eler.
MIN_ACTIVE_MEMBER_COUNT = 3
MIN_MONEY_TRANSACTION_COUNT = 20

# Son para hareketinin üzerinden bu kadar aydan az geçmişse sandık "hâlâ işleyen" sayılır.
RECENTLY_ACTIVE_MONTH_COUNT = 6

# İstatistikler toplu (aggregate) sorgularla hesaplanır ve sayfa herkese açık olduğu için her
# istekte yeniden hesaplanmasın diye kısa süreli önbelleğe alınır. Önbellek süreç belleğindedir:
# uygulama yeniden başlayınca ve her worker için ayrı ayrı dolar.
STATISTICS_CACHE_DURATION = timedelta(minutes=15)
_statistics_cache = {"data": None, "calculated_at": None}


def short_amount_string(amount) -> str:
    """Büyük tutarları öne çıkan kutularda kısa göstermek için: 14560648.95 -> "14,6 milyon".

    Tam tutar zaten tabloların içinde gösterildiği için burada okunabilirlik yeğlenir.
    """
    amount = Decimal(amount or 0)
    if amount >= 1000000:
        return "{:.1f}".format(amount / 1000000).replace(".", ",") + " milyon"
    elif amount >= 1000:
        return "{:.0f}".format(amount / 1000) + " bin"
    return "{:.0f}".format(amount)


def collect_sandik_facts() -> list:
    """Bütün sandıklar için elemede kullanılan sayıları tek seferde toplar.

    Sandık başına ayrı sorgu atmamak için sayımlar sandığa göre gruplanmış üç sorguyla alınır.
    """
    active_member_counts = db.active_member_counts_by_sandik()
    money_transaction_counts = db.money_transaction_counts_by_sandik()
    last_money_transaction_dates = db.last_money_transaction_dates_by_sandik()

    recently_active_limit = date.today() - relativedelta(months=RECENTLY_ACTIVE_MONTH_COUNT)

    facts = []
    for sandik in db.select_sandiks():
        active_member_count = active_member_counts.get(sandik.id, 0)
        money_transaction_count = money_transaction_counts.get(sandik.id, 0)
        last_money_transaction_date = last_money_transaction_dates.get(sandik.id)

        is_real = (
                sandik.is_active
                and active_member_count >= MIN_ACTIVE_MEMBER_COUNT
                and money_transaction_count >= MIN_MONEY_TRANSACTION_COUNT
        )
        facts.append({
            "sandik": sandik,
            "active_member_count": active_member_count,
            "money_transaction_count": money_transaction_count,
            "last_money_transaction_date": last_money_transaction_date,
            "is_real": is_real,
            "is_recently_active": bool(
                is_real and last_money_transaction_date and last_money_transaction_date >= recently_active_limit
            ),
        })
    return facts


def calculate_statistics() -> dict:
    """İstatistik sayfasının bütün verisini hesaplar. Önbellek için `get_statistics()` kullanın."""
    facts = collect_sandik_facts()
    real_facts = [fact for fact in facts if fact["is_real"]]
    sandiks = [fact["sandik"] for fact in real_facts]

    if not sandiks:
        return {"has_data": False, "calculated_at": datetime.now()}

    total_debt_amount = db.sum_of_debts(sandiks=sandiks) or Decimal(0)
    paid_installment_amount = db.sum_of_paid_installments(sandiks=sandiks) or Decimal(0)
    paid_contribution_amount = db.sum_of_paid_contributions(sandiks=sandiks) or Decimal(0)

    first_date_of_opening = min(sandik.date_of_opening for sandik in sandiks)
    debts_by_year = [
        {"year": year, "amount": amount or Decimal(0), "count": debt_count}
        for year, amount, debt_count in db.debt_statistics_by_year(sandiks=sandiks)
    ]
    max_amount_of_years = max([row["amount"] for row in debts_by_year], default=Decimal(0))

    return {
        "has_data": True,
        "calculated_at": datetime.now(),

        # Sandıklar
        "sandik_count": len(sandiks),
        "recently_active_sandik_count": len([fact for fact in real_facts if fact["is_recently_active"]]),
        "classic_sandik_count": len([s for s in sandiks if s.is_type_classic()]),
        "trust_relationship_sandik_count": len([s for s in sandiks if s.is_type_with_trust_relationship()]),
        "first_date_of_opening": first_date_of_opening,
        "operating_year_count": relativedelta(date.today(), first_date_of_opening).years,

        # Kişiler
        "web_user_count": db.count_web_users_of_sandiks(sandiks=sandiks),
        "membership_count": db.count_active_members(sandiks=sandiks),
        "share_count": db.count_active_shares(sandiks=sandiks),
        "average_contribution_amount": db.average_contribution_amount(sandiks=sandiks) or Decimal(0),

        # Para
        "total_debt_amount": total_debt_amount,
        "total_debt_amount_short": short_amount_string(total_debt_amount),
        "debt_count": db.count_debts(sandiks=sandiks),
        "paid_contribution_amount": paid_contribution_amount,
        "paid_installment_amount": paid_installment_amount,
        "unpaid_debt_amount": max(total_debt_amount - paid_installment_amount, Decimal(0)),
        "total_revenue_amount": db.sum_of_revenue_money_transactions(sandiks=sandiks) or Decimal(0),

        # Kayıt sayıları
        "money_transaction_count": db.count_money_transactions(sandiks=sandiks),
        "contribution_count": db.count_contributions(sandiks=sandiks),
        "installment_count": db.count_installments(sandiks=sandiks),

        # Yıllara göre dağılım (basit çubuk grafik için oran da hesaplanır)
        "debts_by_year": [
            dict(row, ratio=int(row["amount"] / max_amount_of_years * 100) if max_amount_of_years else 0)
            for row in debts_by_year
        ],

        # Sayfanın altında açıklanan eleme ölçütleri
        "min_active_member_count": MIN_ACTIVE_MEMBER_COUNT,
        "min_money_transaction_count": MIN_MONEY_TRANSACTION_COUNT,
        "recently_active_month_count": RECENTLY_ACTIVE_MONTH_COUNT,
    }


def get_statistics(use_cache: bool = True) -> dict:
    """İstatistikleri döndürür; `STATISTICS_CACHE_DURATION` süresince önbellekten okur.

    Dönen sözlük önbellekle paylaşılır, **değiştirilmemelidir**.
    """
    cached_data = _statistics_cache["data"]
    calculated_at = _statistics_cache["calculated_at"]
    if use_cache and cached_data and calculated_at and datetime.now() - calculated_at < STATISTICS_CACHE_DURATION:
        return cached_data

    data = calculate_statistics()
    _statistics_cache["data"] = data
    _statistics_cache["calculated_at"] = data["calculated_at"]
    return data
