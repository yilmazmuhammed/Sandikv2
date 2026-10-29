"""`sandik/general/utils.py` -> mil sonu geçmişi (`/mil-sonu-gecmisi`) için testler.

En önemli kural: bugünle biten noktanın değeri ana sayfadaki mil sonuyla (`get_home_page_data` ->
`status_rows[...]["mile_end"]`) birebir aynıdır. Geçmiş değerler bugünkü kayıtlardan geriye doğru
hesaplandığı için bu eşitlik, olay listesinin hiçbir kalemi atlamadığını da gösterir.
"""
from datetime import date, timedelta
from decimal import Decimal

from pony.orm import db_session

from sandik.general import utils as general_utils
from sandik.transaction import db as transaction_db
from sandik.utils import period as period_utils
from sandik.utils.db_models import MoneyTransaction, Sandik

from tests import factories


def _monthly(**overrides):
    selection = general_utils.parse_history_selection({"dilim": "ay", "aralik": "12ay"})
    selection.update(overrides)
    return selection


def _first_day(months_ago):
    return period_utils.period_to_date(period_utils.previous_period(months_ago)) if months_ago else \
        date.today().replace(day=1)


def _home_mile_ends(web_user):
    return {row["member"].id: row["mile_end"] for row in general_utils.get_home_page_data(web_user)["status_rows"]}


@db_session
def test_todays_value_equals_the_home_page_mile_end():
    wu = factories.make_web_user()
    sandik = factories.make_sandik(created_by=wu)
    share = factories.make_member_with_share(sandik=sandik, web_user=wu, created_by=wu)
    member = share.member_ref
    factories.make_share(member=member, created_by=wu)

    # Geçen ayın aidatı kısmen ödenmiş, fazlası işleme konmadan duruyor.
    factories.pay_contribution_partially(share=share, term=period_utils.previous_period(), paid_amount=Decimal("130"),
                                         created_by=wu)
    factories.make_contribution(share=share, term=period_utils.current_period(), created_by=wu)
    # Gelecek ayın aidatı elle oluşturulup önceden ödenmiş: bugün mil sonunda sayılmıyor.
    future = factories.make_contribution(share=share, term=period_utils.next_period(), created_by=wu)
    prepaid = factories.make_money_transaction(member=member, amount=Decimal("100"), created_by=wu)
    factories.make_sub_receipt(money_transaction=prepaid, amount=Decimal("40"), created_by=wu, contribution_ref=future)
    # 600 TL borç, 3 taksit; ilk taksit kısmen ödenmiş.
    debt = factories.make_debt(share=share, amount=Decimal("600"), created_by=wu, number_of_installment=3)
    installment = min(debt.installments_set, key=lambda i: i.term)
    factories.make_sub_receipt(money_transaction=prepaid, amount=Decimal("50"), created_by=wu,
                               installment_ref=installment)
    # İşleme konmamış paranın 5 TL'si üyeye geri verilmiş.
    refund = factories.make_money_transaction(member=member, amount=Decimal("5"), created_by=wu,
                                              type=MoneyTransaction.TYPE.EXPENSE)
    transaction_db.create_retracted(amount=Decimal("5"), untreated_money_transaction=prepaid, money_transaction=refund,
                                    created_by=wu)

    history = general_utils.get_mile_end_history(wu, _monthly())

    expected = _home_mile_ends(wu)[member.id]
    assert history["points"][-1] == date.today()
    assert history["member_values"][member.id][-1] == expected
    assert history["groups"][0]["total"][-1] == expected


@db_session
def test_past_month_ends_are_computed_from_dated_events():
    wu = factories.make_web_user()
    sandik = factories.make_sandik(created_by=wu)
    share = factories.make_member_with_share(sandik=sandik, web_user=wu, created_by=wu)
    member = share.member_ref
    two_ago, one_ago = period_utils.previous_period(2), period_utils.previous_period(1)

    # İki ay önce: 100 TL aidat, 250 TL yatırılmış (100'ü aidata).
    contribution = factories.make_contribution(share=share, term=two_ago, created_by=wu)
    mt = factories.make_money_transaction(member=member, amount=Decimal("250"), created_by=wu,
                                          date=_first_day(2) + timedelta(days=4))
    factories.make_sub_receipt(money_transaction=mt, amount=Decimal("100"), created_by=wu,
                               contribution_ref=contribution)
    # Geçen ay: 100 TL aidat (ödenmemiş) ve 2 taksitli 400 TL borç.
    factories.make_contribution(share=share, term=one_ago, created_by=wu)
    expense = factories.make_money_transaction(member=member, amount=Decimal("400"), created_by=wu,
                                               type=MoneyTransaction.TYPE.EXPENSE, date=_first_day(1) + timedelta(days=9))
    factories.make_debt(share=share, amount=Decimal("400"), created_by=wu, number_of_installment=2,
                        start_period=one_ago, money_transaction=expense)
    # Bu ay: 100 TL aidat.
    factories.make_contribution(share=share, term=period_utils.current_period(), created_by=wu)

    history = general_utils.get_mile_end_history(wu, _monthly())
    by_date = dict(zip(history["points"], history["member_values"][member.id]))

    assert by_date[_first_day(2) - timedelta(days=1)] == Decimal("0")
    assert by_date[_first_day(1) - timedelta(days=1)] == Decimal("150")       # 250 - 100
    assert by_date[_first_day(0) - timedelta(days=1)] == Decimal("-350")      # 150 - 100 - 400
    assert by_date[date.today()] == Decimal("-450") == _home_mile_ends(wu)[member.id]


@db_session
def test_payment_recorded_later_than_its_money_transaction_counts_from_the_later_day():
    """Gelecek ayın aidatına önceden yapılan ödeme, aidat sayılmaya başlayana kadar yalnızca işleme
    konmamış paradan düşer; aidat sayılmaya başlayınca toplam değişmez."""
    wu = factories.make_web_user()
    sandik = factories.make_sandik(created_by=wu)
    share = factories.make_member_with_share(sandik=sandik, web_user=wu, created_by=wu)
    member = share.member_ref
    future = factories.make_contribution(share=share, term=period_utils.next_period(), created_by=wu)
    mt = factories.make_money_transaction(member=member, amount=Decimal("100"), created_by=wu)
    factories.make_sub_receipt(money_transaction=mt, amount=Decimal("100"), created_by=wu, contribution_ref=future)

    history = general_utils.get_mile_end_history(wu, _monthly())

    assert history["member_values"][member.id][-1] == Decimal("0") == _home_mile_ends(wu)[member.id]


@db_session
def test_different_currencies_are_grouped_and_never_summed():
    wu = factories.make_web_user()
    try_sandik = factories.make_sandik(created_by=wu, name="Lira Sandığı")
    gold_sandik = factories.make_sandik(created_by=wu, name="Altın Sandığı", currency=Sandik.CURRENCY.GOLD_GRAM,
                                        contribution_amount=Decimal("1"))
    try_share = factories.make_member_with_share(sandik=try_sandik, web_user=wu, created_by=wu)
    gold_share = factories.make_member_with_share(sandik=gold_sandik, web_user=wu, created_by=wu)
    factories.make_contribution(share=try_share, term=period_utils.current_period(), created_by=wu)
    factories.make_contribution(share=gold_share, term=period_utils.current_period(), created_by=wu)

    history = general_utils.get_mile_end_history(wu, _monthly())

    assert len(history["groups"]) == 2
    totals = sorted(group["total"][-1] for group in history["groups"])
    assert totals == [Decimal("-100"), Decimal("-1")]


@db_session
def test_daily_table_lists_only_the_days_that_changed():
    wu = factories.make_web_user()
    sandik = factories.make_sandik(created_by=wu)
    share = factories.make_member_with_share(sandik=sandik, web_user=wu, created_by=wu)
    member = share.member_ref
    factories.make_contribution(share=share, term=period_utils.previous_period(), created_by=wu)
    factories.make_money_transaction(member=member, amount=Decimal("100"), created_by=wu,
                                     date=_first_day(1) + timedelta(days=2))

    selection = general_utils.parse_history_selection({"dilim": "gun", "baslangic": period_utils.previous_period(),
                                                       "bitis": period_utils.current_period()})
    history = general_utils.get_mile_end_history(wu, selection)

    listed = [history["points"][i] for i in history["row_indexes"]]
    # En yeniden eskiye: bugün (değişmemiş olsa da), para girişi günü ve aralığın ilk günü.
    assert listed == [date.today(), _first_day(1) + timedelta(days=2), _first_day(1)]
    assert len(history["points"]) == (date.today() - _first_day(1)).days + 1


def test_point_dates_follow_the_calendar_and_end_with_the_range_end():
    points = general_utils.history_point_dates(date(2025, 11, 1), date(2026, 10, 29), "3ay")
    assert points == [date(2025, 12, 31), date(2026, 3, 31), date(2026, 6, 30), date(2026, 9, 30), date(2026, 10, 29)]

    assert general_utils.history_point_dates(date(2026, 1, 1), date(2026, 3, 31), "ay") == [
        date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)]
    # Hafta pazar günü biter.
    assert general_utils.history_point_dates(date(2026, 10, 1), date(2026, 10, 14), "hafta") == [
        date(2026, 10, 4), date(2026, 10, 11), date(2026, 10, 14)]
    assert general_utils.history_point_dates(date(2026, 2, 1), date(2026, 1, 1), "gun") == []


def test_selection_parsing_falls_back_to_defaults_and_swaps_reversed_ranges():
    assert general_utils.parse_history_selection({})["args"] == {"aralik": "12ay", "dilim": "ay"}
    assert general_utils.parse_history_selection({"aralik": "x", "dilim": "y"})["args"] == {"aralik": "12ay",
                                                                                          "dilim": "ay"}
    selection = general_utils.parse_history_selection({"baslangic": "2026-05", "bitis": "2025-01", "dilim": "yil"})
    assert (selection["start_period"], selection["end_period"], selection["slice"]) == ("2025-01", "2026-05", "yil")
    # Eksik özel aralık hazır aralığa düşer.
    assert general_utils.parse_history_selection({"baslangic": "2026-05", "aralik": "tumu"})["range"] == "tumu"
