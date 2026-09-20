"""Tanıtım sayfalarının (özellikle istatistik sayfasının) iş mantığı.

İstatistik sayfası herkese açıktır ve sistemin gerçekte ne kadar kullanıldığını göstermeyi
amaçlar. Bu yüzden **denemelik veriler ayıklanır**: birkaç kayıt girilip bırakılmış sandıklar ve
hiçbir sandıkta üyeliği olmayan site kullanıcıları sayılara dahil edilmez. Ölçütler aşağıdaki
sabitlerdedir; hepsi sayfanın altında kullanıcıya da açıklanır (bkz. `statistics_page.html`).

Sayfanın ikinci yarısı **giriş yapmış kullanıcıya özeldir**: bir açılır listeden kendi
sandıklarından birini seçip onun aynı biçimdeki rakamlarını görür (`get_sandik_selection`). Seçim
yapılmadıkça hiçbir şey hesaplanmaz, yani sayfa herkes için eskisiyle aynı kalır; orada eleme
uygulanmaz ve sonuç önbelleğe alınmaz — gerekçeleri o fonksiyonların açıklamalarındadır.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta

from sandik.intro import db
from sandik.utils import money

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

    Tam tutar zaten tabloların içinde gösterildiği için burada okunabilirlik yeğlenir. Kısaltma
    işaretten bağımsız yapılır: sandığın son durumu eksi olabilir ve "-2308" gibi ham bir sayı
    yerine "-2 bin" yazılmalıdır.
    """
    amount = Decimal(amount or 0)
    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    if amount >= 1000000:
        return sign + "{:.1f}".format(amount / 1000000).replace(".", ",") + " milyon"
    elif amount >= 1000:
        return sign + "{:.0f}".format(amount / 1000) + " bin"
    return sign + "{:.0f}".format(amount)


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


def group_sandiks_by_currency(sandiks) -> list:
    """Sandıkları para birimine göre gruplar; en çok sandığı olan grup başa gelir."""
    groups = {}
    for sandik in sandiks:
        groups.setdefault(sandik.currency, []).append(sandik)
    return sorted(groups.values(), key=len, reverse=True)


def collect_money_statistics(sandiks) -> dict:
    """Aynı para birimindeki bir sandık grubunun parasal toplamları."""
    currency = sandiks[0].currency
    total_debt_amount = db.sum_of_debts(sandiks=sandiks) or Decimal(0)
    paid_installment_amount = db.sum_of_paid_installments(sandiks=sandiks) or Decimal(0)

    debts_by_year = [
        {"year": year, "amount": amount or Decimal(0), "count": debt_count}
        for year, amount, debt_count in db.debt_statistics_by_year(sandiks=sandiks)
    ]
    max_amount_of_years = max([row["amount"] for row in debts_by_year], default=Decimal(0))

    return {
        "currency": currency,
        "currency_name": money.name_of(currency),
        "currency_symbol": money.symbol_of(currency),
        "sandik_count": len(sandiks),
        "total_debt_amount": total_debt_amount,
        "total_debt_amount_short": short_amount_string(total_debt_amount),
        "paid_installment_amount": paid_installment_amount,
        "paid_contribution_amount": db.sum_of_paid_contributions(sandiks=sandiks) or Decimal(0),
        "unpaid_debt_amount": max(total_debt_amount - paid_installment_amount, Decimal(0)),
        "total_revenue_amount": db.sum_of_revenue_money_transactions(sandiks=sandiks) or Decimal(0),
        "average_contribution_amount": db.average_contribution_amount(sandiks=sandiks) or Decimal(0),
        # Yıllara göre dağılım (basit çubuk grafik için oran da hesaplanır)
        "debts_by_year": [
            dict(row, ratio=int(row["amount"] / max_amount_of_years * 100) if max_amount_of_years else 0)
            for row in debts_by_year
        ],
    }


def calculate_statistics() -> dict:
    """İstatistik sayfasının bütün verisini hesaplar. Önbellek için `get_statistics()` kullanın."""
    facts = collect_sandik_facts()
    real_facts = [fact for fact in facts if fact["is_real"]]
    sandiks = [fact["sandik"] for fact in real_facts]

    if not sandiks:
        return {"has_data": False, "calculated_at": datetime.now()}

    first_date_of_opening = min(sandik.date_of_opening for sandik in sandiks)

    # Parasal toplamlar para birimi başına ayrı hesaplanır: farklı birimlerdeki tutarlar
    # toplanamaz. Bütün sandıklar aynı birimdeyse (bugün olağan durum) tek grup çıkar ve sayfa
    # eskisi gibi görünür. Sorgular zaten sandık listesi aldığı için grup başına bir kez çağrılır.
    money_by_currency = [collect_money_statistics(group)
                         for group in group_sandiks_by_currency(sandiks)]
    # Öne çıkan kutu, en çok sandığı olan para birimini gösterir.
    main_money = max(money_by_currency, key=lambda group: group["sandik_count"])

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

        # Para — birim başına bir grup; `main_money` en çok sandığı olan birimdir
        "money_by_currency": money_by_currency,
        "main_money": main_money,
        "debt_count": db.count_debts(sandiks=sandiks),

        # Kayıt sayıları
        "money_transaction_count": db.count_money_transactions(sandiks=sandiks),
        "contribution_count": db.count_contributions(sandiks=sandiks),
        "installment_count": db.count_installments(sandiks=sandiks),

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


def collect_sandik_statistics(sandik) -> dict:
    """Tek bir sandığın kendi rakamları — giriş yapmış üyeye/yöneticiye gösterilen bölüm için.

    Sayfanın genelindeki "çöp veri" elemesi (`MIN_ACTIVE_MEMBER_COUNT` vb.) burada **uygulanmaz**:
    kullanıcı, sandığı henüz küçük ya da kapatılmış olsa bile kendi sandığının rakamlarını
    görebilmelidir. Bu yüzden buradaki sayılar üstteki genel toplamlara girmiyor olabilir; sayfa
    bunu kullanıcıya da yazar.

    Parasal toplamlar tek bir sandığa aittir, yani hepsi aynı para birimindedir; birim gruplaması
    gerekmez ve `collect_money_statistics` tek elemanlı grupla çağrılır.
    """
    sandiks = [sandik]
    money_statistics = collect_money_statistics(sandiks)
    final_status = sandik.get_final_status() or Decimal(0)

    return {
        "sandik": sandik,
        # Parasal toplamlar (genel bölümdekiyle aynı yapı: total_debt_amount, unpaid_debt_amount,
        # debts_by_year, ...) — hepsi sandığın para biriminde
        "money": money_statistics,

        # Sandığın "şu anki" durumu: genel bölümde karşılığı yoktur, çünkü kasadaki para
        # sandığa özeldir.
        "final_status": final_status,
        "final_status_short": short_amount_string(final_status),
        "undistributed_amount": sandik.total_of_undistributed_amount() or Decimal(0),

        # Kişiler ve kayıtlar
        "active_member_count": db.count_active_members(sandiks=sandiks),
        "active_share_count": db.count_active_shares(sandiks=sandiks),
        "money_transaction_count": db.count_money_transactions(sandiks=sandiks),
        "contribution_count": db.count_contributions(sandiks=sandiks),
        "installment_count": db.count_installments(sandiks=sandiks),
        "debt_count": db.count_debts(sandiks=sandiks),

        # Zaman
        "last_money_transaction_date": db.last_money_transaction_date(sandik=sandik),
        "operating_year_count": relativedelta(date.today(), sandik.date_of_opening).years,
    }


def get_sandik_selection(web_user, sandik_id=None) -> dict:
    """İstatistik sayfasındaki açılır listenin verisi: sandıklar ve seçiliyse onun rakamları.

    Liste `WebUser.my_sandiks()`tir: üyelikten **ve** sandık yetkisinden gelen sandıklar (türkçe
    ada göre sıralı). Bu, sandık detay sayfasının erişim kuralıyla
    (`to_be_member_or_manager_of_sandik_required`) aynı kümedir, yani burada kullanıcının başka
    sayfalardan zaten göremeyeceği bir veri gösterilmez. **Yetkilendirme bu kesişimden gelir**:
    `sandik_id` yalnızca listede bulunursa seçili sayılır, adresten başka bir sandığın kimliği
    verilirse hiçbir şey hesaplanmaz (hata da verilmez, sayfa "seçim yapılmamış" hâlinde kalır).

    Rakamlar **yalnızca seçilen sandık için** hesaplanır; seçim yoksa hiç sorgu çalışmaz ve sayfa
    eskisiyle birebir aynı kalır. Sonuç kullanıcıya özel olduğu için **önbelleğe alınmaz**:
    `get_statistics()` önbelleği bütün ziyaretçilerle paylaşılır, kişiye bağlı veri oraya
    konulamaz.
    """
    sandiks = web_user.my_sandiks()
    selected_sandik = next((sandik for sandik in sandiks if sandik.id == sandik_id), None)
    return {
        "sandiks": sandiks,
        "selected_sandik": selected_sandik,
        "statistics": collect_sandik_statistics(sandik=selected_sandik) if selected_sandik else None,
    }


# --------------------------------------------------------------------------------------
# Sık sorulan sorular
# --------------------------------------------------------------------------------------
# Liste hem `how_to_use_page.html` içindeki akordiyonu hem de sayfanın yapısal verisini
# (schema.org `FAQPage`) besler. **Tek kaynaktır**: Google, sayfada bulunmayan bir cevabı
# yapısal veride görürse sayfayı işaretler; iki yerde ayrı ayrı yazılsa metinler zamanla
# birbirinden ayrılırdı. Cevaplarda yalnızca `<b>` gibi basit biçimleme kullanılmalıdır —
# yapısal veriye yazılırken etiketler atılır (`strip_tags`).

FAQ = [
    ("Parayı yatırdım ama sitede görünmüyor.",
     "Para girişini sisteme sandık yöneticisi kaydeder. Kayıt girilene kadar ödemeniz sitede "
     "görünmez; yöneticinize hatırlatmanız yeterlidir."),
    ("Bu ayın aidatı neden oluşmadı?",
     "Aidatlar her ayın başında otomatik oluşur. Oluşmadıysa yönetici, <b>İşlemler</b> menüsünden "
     "vadesi gelmiş aidatları elle oluşturabilir."),
    ("“İşleme konmamış para” ne demek?",
     "Yatırdığınız ama henüz bir aidata veya taksite işlenmemiş tutarınızdır. Örneğin aidatınızdan "
     "fazla para yatırdıysanız, artan kısım burada bekler ve sonraki ödemelerinizde kullanılır. "
     "İstemezseniz yöneticiden geri ödenmesini isteyebilirsiniz."),
    ("Aynı anda birden fazla sandıkta olabilir miyim?",
     "Evet. Tek hesapla istediğiniz kadar sandığa üye olabilirsiniz; ana sayfada hepsinin durumunu "
     "bir arada görürsünüz."),
    ("Borç alabileceğim tutarı neye göre hesaplıyor?",
     "Sandığınızın kurallarına göre. En yaygın kural, bir hissenin o hisse için ödenmiş toplam "
     "aidatın belirli bir katı kadar borç alabilmesidir. Güven bağlı sandıklarda ayrıca güven "
     "halkanızdaki üyelerin birikimi de sınır oluşturur."),
    ("Ekranda “ERRCODE” ile başlayan bir hata gördüm.",
     "Bu, sistemin bir tutarsızlık yakaladığı anlamına gelir. Ekrandaki kodu not alıp site "
     "yöneticisine iletin; kaydın elle düzeltilmesi gerekir."),
    ("Verilerimiz güvende mi?",
     "Sandık verileri düzenli olarak yedeklenir ve her yazma işlemi seyir defterine (log) "
     "kaydedilir; böylece hangi kaydın kim tarafından ne zaman değiştirildiği geriye dönük olarak "
     "görülebilir."),
]


def strip_tags(text) -> str:
    """Cevaptaki basit biçimleme etiketlerini atar (yapısal veri düz metin ister)"""
    import re

    return re.sub(r"<[^>]+>", "", text or "")


def faq_for_structured_data():
    """`(soru, düz metin cevap)` çiftleri — `utils/seo.py:faq_ld` bunu bekler"""
    return [(question, strip_tags(answer)) for question, answer in FAQ]


# --------------------------------------------------------------------------------------
# Arama motoru dosyaları ve yapısal veri
# --------------------------------------------------------------------------------------

# Tarayıcı botlarına kapatılan yollar. Amaç "gizlemek" değil (gizlilik yetkilendirmeyle
# sağlanır), boşuna gezilmesini önlemek: bu adresler giriş ister ya da JSON/dosya döndürür.
DISALLOWED_PATHS = (
    "/api/",
    "/sandik/",
    "/indir/",
    "/yedek/",
    "/paw/",
    "/websitesi-masraflari/",
    "/ana-sayfa",
    "/giris",
    "/kayit",
    "/cikis",
    "/parola-sifirla",
    "/tercihlerim",
    "/tercih/",
)


def robots_txt() -> str:
    """
    `robots.txt` içeriği.

    Dizine girmemesi gereken sayfalar zaten `<meta name="robots">` ile işaretlidir (yönetim
    paneli ve giriş kabukları koşulsuz "noindex" basar); burada yalnızca gezilmesi anlamsız
    olan yollar kapatılır.
    """
    from sandik.utils import seo

    lines = ["User-agent: *"]
    lines += [f"Disallow: {path}" for path in DISALLOWED_PATHS]
    lines += ["", f"Sitemap: {seo.absolute_url('/sitemap.xml')}", ""]
    return "\n".join(lines)


def sitemap_urls():
    """Sitemap'e girecek adresler: `(adres, değişim sıklığı, öncelik)`"""
    from flask import url_for

    from sandik.utils import seo

    return [
        (seo.absolute_url(url_for("intro_page_bp.about_page")), "monthly", "1.0"),
        (seo.absolute_url(url_for("intro_page_bp.how_to_use_page")), "monthly", "0.8"),
        (seo.absolute_url(url_for("intro_page_bp.statistics_page")), "weekly", "0.6"),
    ]


def sitemap_xml() -> str:
    from xml.sax.saxutils import escape

    entries = "".join(
        f"<url><loc>{escape(url)}</loc>"
        f"<changefreq>{changefreq}</changefreq><priority>{priority}</priority></url>"
        for url, changefreq, priority in sitemap_urls()
    )
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            f"{entries}</urlset>")


def about_structured_data() -> dict:
    """Tanıtım sayfası: "bu bir web uygulaması" bilgisi"""
    from sandik.utils import seo

    return {
        "@context": "https://schema.org",
        "@type": "WebApplication",
        "name": "Sandık v2",
        "url": seo.canonical_url(),
        "applicationCategory": "FinanceApplication",
        "operatingSystem": "Web",
        "inLanguage": "tr-TR",
        "description": ("İmece usulü yardımlaşma sandıklarının aidat, borç ve taksit kayıtlarını "
                        "tutan takip sistemi."),
        # Ücretsiz olduğunun standart yazılışı: sıfır fiyatlı teklif
        "offers": {"@type": "Offer", "price": "0", "priceCurrency": "TRY"},
        "featureList": [
            "Aidat takibi",
            "Faizsiz borç ve taksit takibi",
            "Üye ve hisse yönetimi",
            "Aylık ödeme hatırlatma e-postaları",
            "Sandık kurallarıyla borç limiti hesabı",
        ],
    }
