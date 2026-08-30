"""`sandik/utils/sorting.py` ve sandık listelerinin türkçe alfabeye göre sıralanması için testler.

Varsayılan python sıralaması kod noktasına baktığı için türkçe harfler listenin sonuna düşüyordu
("Zeytin" < "Çınar"); burada hem sıralama anahtarı hem de onu kullanan sandık listeleri doğrulanır.
"""
from decimal import Decimal

from pony.orm import db_session

from sandik.general import utils as general_utils
from sandik.sandik import db as sandik_db
from sandik.utils.sorting import turkish_lower, turkish_sort_key

from tests import factories


def test_turkish_letters_are_in_alphabet_order():
    names = ["Zeytin", "Çınar", "Ağrı", "Ordu", "Ödemiş", "Sivas", "Şile", "Urla", "Üsküdar", "Van"]
    assert sorted(names, key=turkish_sort_key) == [
        "Ağrı", "Çınar", "Ordu", "Ödemiş", "Sivas", "Şile", "Urla", "Üsküdar", "Van", "Zeytin"
    ]


def test_dotted_and_dotless_i_are_separate_letters():
    # Türkçede sıra ...h, ı, i, j... şeklindedir; büyük harfler de türkçe kurallarıyla küçültülür.
    assert sorted(["İzmir", "Isparta", "Hatay", "Kars"], key=turkish_sort_key) == \
           ["Hatay", "Isparta", "İzmir", "Kars"]
    assert turkish_lower("IŞIK") == "ışık"
    assert turkish_lower("İSTANBUL") == "istanbul"


def test_case_is_ignored_but_order_is_deterministic():
    assert sorted(["çilek", "Çilek", "Cilek"], key=turkish_sort_key) == ["Cilek", "Çilek", "çilek"]


def test_digits_and_symbols_come_before_letters():
    assert sorted(["Ahmet", "1. Sandık", "(eski) sandık"], key=turkish_sort_key) == \
           ["(eski) sandık", "1. Sandık", "Ahmet"]


def test_foreign_letters_get_their_latin_position():
    # q/w/x türk alfabesinde yoktur; en sona atılmak yerine latin sıralarında yer alır.
    assert sorted(["Yozgat", "Wan", "Van", "Queen", "Posta"], key=turkish_sort_key) == \
           ["Posta", "Queen", "Van", "Wan", "Yozgat"]


def test_accented_letters_sort_next_to_their_plain_form():
    assert sorted(["adres", "âdet", "adet"], key=turkish_sort_key) == ["adet", "âdet", "adres"]


@db_session
def test_my_sandiks_is_sorted_by_turkish_alphabet():
    wu = factories.make_web_user()
    for name in ["Zeytin sandığı", "Çınar sandığı", "Ilgaz sandığı", "İnci sandığı", "Ağrı sandığı"]:
        sandik = factories.make_sandik(created_by=wu, name=name)
        factories.make_member(sandik=sandik, web_user=wu, created_by=wu)

    assert [s.name for s in wu.my_sandiks()] == [
        "Ağrı sandığı", "Çınar sandığı", "Ilgaz sandığı", "İnci sandığı", "Zeytin sandığı"
    ]


@db_session
def test_home_page_rows_are_sorted_by_turkish_alphabet():
    wu = factories.make_web_user()
    for name in ["Zeytin sandığı", "Ödemiş sandığı", "Şile sandığı", "Sivas sandığı"]:
        sandik = factories.make_sandik(created_by=wu, name=name, contribution_amount=Decimal("100"))
        factories.make_member_with_share(sandik=sandik, web_user=wu, created_by=wu)

    data = general_utils.get_home_page_data(wu)

    assert [row["sandik"].name for row in data["status_rows"]] == [
        "Ödemiş sandığı", "Sivas sandığı", "Şile sandığı", "Zeytin sandığı"
    ]


@db_session
def test_sandik_form_choices_are_sorted_by_turkish_alphabet():
    wu = factories.make_web_user()
    for name in ["Zeytin sandığı", "Çınar sandığı", "Ağrı sandığı"]:
        factories.make_sandik(created_by=wu, name=name)

    assert [name for _id, name in sandik_db.sandiks_form_choices()] == [
        "Ağrı sandığı", "Çınar sandığı", "Zeytin sandığı"
    ]
