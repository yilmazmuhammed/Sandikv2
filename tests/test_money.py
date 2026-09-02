"""`sandik/utils/money.py` — biçimlendirme, birime yuvarlama ve doğrulama."""
from decimal import Decimal

import pytest

from sandik.utils import money
from sandik.utils.money import Currency

TRY = Currency.TRY
GOLD = Currency.GOLD_GRAM


def old_tr_number_format(value):
    """Filtrenin `money.format_number`'a taşınmadan önceki hâli (regresyon karşılaştırması için)."""
    if value == int(value):
        return f"{int(value):,}".replace(",", ".")
    integer_part, decimal_part = f"{value:,.2f}".split(".")
    return f"{integer_part.replace(',', '.')}," + decimal_part


@pytest.mark.parametrize("value", ["0", "1", "1500", "1500.50", "1500.75", "1234567.05",
                                   "-1500", "-1500.50", "0.01", "999999.99"])
def test_format_number_eski_filtreyle_ayni(value):
    """TL gösterimi bugünküyle birebir aynı kalmalı — kuruşlu eski kayıtlar dahil."""
    assert money.format_number(Decimal(value)) == old_tr_number_format(Decimal(value))


def test_format_number_bosluklari_tolere_eder():
    assert money.format_number(None) == "0"
    assert money.format_number(0) == "0"


@pytest.mark.parametrize("value,expected", [("1500", "1.500 ₺"), ("0", "0 ₺"),
                                            ("1500.50", "1.500,50 ₺")])
def test_format_amount_tl(value, expected):
    assert money.format_amount(Decimal(value), currency=TRY) == expected


@pytest.mark.parametrize("value,expected", [("5", "5,0 gr"), ("5.2", "5,2 gr"),
                                            ("0.1", "0,1 gr"), ("0", "0,0 gr"),
                                            ("5.25", "5,25 gr")])
def test_format_amount_altin(value, expected):
    """Birim 0,1 gr olduğu için en az bir ondalık gösterilir; daha incesi varsa o da görünür."""
    assert money.format_amount(Decimal(value), currency=GOLD) == expected


def test_format_amount_varsayilan_para_birimi():
    assert money.format_amount(Decimal("10")) == "10 ₺"


def test_birim_ve_basamak():
    assert money.unit_of(TRY) == Decimal("1")
    assert money.unit_of(GOLD) == Decimal("0.1")
    assert money.places_of(TRY) == 0
    assert money.places_of(GOLD) == 1


def test_bilinmeyen_para_birimi_varsayilana_duser():
    assert money.unit_of(9999) == money.unit_of(Currency.DEFAULT)


def test_strings_details_ile_ayni_anahtarlari_tasir():
    assert set(Currency.strings) == set(Currency.details)


@pytest.mark.parametrize("value,unit,ceil,floor", [
    ("100", "1", "100", "100"),
    ("33.4", "1", "34", "33"),
    ("1.55", "0.1", "1.6", "1.5"),
    ("1.5", "0.1", "1.5", "1.5"),
    ("0.05", "0.1", "0.1", "0"),
])
def test_yuvarlama(value, unit, ceil, floor):
    assert money.ceil_to_unit(Decimal(value), Decimal(unit)) == Decimal(ceil)
    assert money.floor_to_unit(Decimal(value), Decimal(unit)) == Decimal(floor)


def test_yuvarlama_bolme_sonucunda_tam_kalir():
    """`Decimal` bölmesi sonsuz basamağa gitse de sonuç birimin katı olmalı."""
    assert money.ceil_to_unit(Decimal("100") / 3, Decimal("1")) == Decimal("34")
    assert money.floor_to_unit(Decimal("100") / 3, Decimal("1")) == Decimal("33")
    assert money.ceil_to_unit(Decimal("1") / 3, Decimal("0.1")) == Decimal("0.4")


@pytest.mark.parametrize("value,unit,expected", [
    ("10", "1", True), ("10.5", "1", False), ("0", "1", True),
    ("1.5", "0.1", True), ("0.05", "0.1", False), ("-2", "1", True),
])
def test_birimin_kati_mi(value, unit, expected):
    assert money.is_multiple_of_unit(Decimal(value), Decimal(unit)) is expected


@pytest.mark.parametrize("text,expected", [
    ("1.5", Decimal("1.5")), ("1,5", Decimal("1.5")), (" 12 ", Decimal("12")),
    ("0.05", Decimal("0.05")), ("abc", None), ("", None), (None, None),
])
def test_parse_amount(text, expected):
    assert money.parse_amount(text) == expected
