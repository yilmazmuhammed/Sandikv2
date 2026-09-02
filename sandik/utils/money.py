"""Para birimi tablosu ve bütün para biçimlendirme / yuvarlama / doğrulama yardımcıları.

Her sandığın bir para birimi vardır (`Sandik.currency`). Her birimin bir **"en küçük parça"sı**
(`unit`) vardır: TL/USD/EUR için `1`, Altın/Gümüş için `0,1 gram`. Sistemdeki bütün tutarlar bu
parçanın katı olmak zorundadır; gösterimdeki ondalık basamak sayısı, borcun taksitlere bölünmesi ve
güven bağlı sandıkta borç paylarının dağıtımı da bu tek değerden türer.

Bu modül `db_models`'ı **import etmez** (döngüsel import olmasın); tersine `Sandik.CURRENCY`
buradaki `Currency` sınıfına işaret eder. Yeni bir para birimi eklemek için `Currency.details`
sözlüğüne bir satır eklemek yeterlidir.
"""
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR

# Para sütunları DECIMAL(12, 2). Birimlerin en küçük parçası bundan daha ince olamaz; eski
# kuruşlu TL kayıtları da bu yüzden hâlâ olduğu gibi gösterilebiliyor.
MAX_PLACES = 2


class Currency:
    TRY = 1
    USD = 2
    EUR = 3
    GOLD_GRAM = 4
    SILVER_GRAM = 5

    # unit          : birimin en küçük parçası; bütün tutarlar bunun katı olmalıdır
    # point_divisor : "sandık puanı" hesabında kullanılan bölen (bkz. Member.calculate_sandik_point)
    details = {
        TRY: {"name": "Türk lirası", "symbol": "₺",
              "unit": Decimal("1"), "point_divisor": Decimal("1000")},
        USD: {"name": "ABD doları", "symbol": "$",
              "unit": Decimal("1"), "point_divisor": Decimal("1000")},
        EUR: {"name": "Euro", "symbol": "€",
              "unit": Decimal("1"), "point_divisor": Decimal("1000")},
        GOLD_GRAM: {"name": "Altın (gram)", "symbol": "gr",
                    "unit": Decimal("0.1"), "point_divisor": Decimal("10")},
        SILVER_GRAM: {"name": "Gümüş (gram)", "symbol": "gr",
                      "unit": Decimal("0.1"), "point_divisor": Decimal("10")},
    }

    # Formlar `Sandik.TYPE.strings` ile aynı kalıbı kullanabilsin diye türetiliyor
    strings = {code: detail["name"] for code, detail in details.items()}

    DEFAULT = TRY


def _detail(currency):
    return Currency.details.get(currency, Currency.details[Currency.DEFAULT])


def name_of(currency) -> str:
    return _detail(currency)["name"]


def symbol_of(currency) -> str:
    return _detail(currency)["symbol"]


def unit_of(currency) -> Decimal:
    return _detail(currency)["unit"]


def point_divisor_of(currency) -> Decimal:
    return _detail(currency)["point_divisor"]


def places_of(currency) -> int:
    """Birimin gerektirdiği ondalık basamak sayısı: TL -> 0, altın (0,1 gr) -> 1"""
    return _significant_places(unit_of(currency))


def to_decimal(value) -> Decimal:
    """`None`, `int`, `float` ve `str` değerleri güvenle `Decimal`'a çevirir.

    `float` doğrudan `Decimal()`e verilirse ikilik gösterim artıkları taşınır (0.1 -> 0.1000...555),
    bu yüzden önce `str`'e çevriliyor.
    """
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal(0)
    return Decimal(str(value))


def _significant_places(value) -> int:
    """Değerin gerçekten ihtiyaç duyduğu ondalık basamak sayısı (sondaki sıfırlar atılır)"""
    exponent = to_decimal(value).normalize().as_tuple().exponent
    return max(0, -exponent)


def format_number(value, min_places=0) -> str:
    """Sayıyı Türkçe biçimde döndürür: binlik ayracı nokta, ondalık ayracı virgül.

    `min_places` birimin gerektirdiği en az ondalık basamak sayısıdır. Değer bundan daha ince bir
    ondalık taşıyorsa (yalnızca eski kayıtlarda olur) doğrudan `MAX_PLACES`e çıkılır. Böylece TL'de
    tam sayılar bugünkü gibi ondalıksız, eski kuruşlu kayıtlar ise "1.500,50" biçiminde görünür.
    """
    value = to_decimal(value)
    significant = _significant_places(value)
    places = min_places if significant <= min_places else MAX_PLACES

    integer_part, _, decimal_part = f"{value:,.{places}f}".partition(".")
    integer_part = integer_part.replace(",", ".")
    return f"{integer_part},{decimal_part}" if decimal_part else integer_part


def format_amount(value, currency=Currency.DEFAULT) -> str:
    """Tutarı birim sembolüyle döndürür: "1.500 ₺", "5,2 gr".

    Sembol her zaman sona yazılır (`$` dahil); bütün şablonlar bu kalıpta.
    """
    return f"{format_number(value, min_places=places_of(currency))} {symbol_of(currency)}"


def ceil_to_unit(value, unit) -> Decimal:
    """Değeri birimin bir üst katına yuvarlar"""
    value, unit = to_decimal(value), to_decimal(unit)
    return (value / unit).to_integral_value(rounding=ROUND_CEILING) * unit


def floor_to_unit(value, unit) -> Decimal:
    """Değeri birimin bir alt katına yuvarlar"""
    value, unit = to_decimal(value), to_decimal(unit)
    return (value / unit).to_integral_value(rounding=ROUND_FLOOR) * unit


def is_multiple_of_unit(value, unit) -> bool:
    value, unit = to_decimal(value), to_decimal(unit)
    return abs(value) % unit == 0


def parse_amount(text):
    """İstekten gelen metni `Decimal`'a çevirir; sayı değilse `None` döner.

    Hem "1.5" hem "1,5" kabul edilir: form alanları `input type=number` olduğu için nokta gönderir,
    ama elle yazılan/eski adreslerden gelen değerlerde virgül de görülebiliyor.
    """
    if text is None:
        return None
    text = str(text).strip()
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None
