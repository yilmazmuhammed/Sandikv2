"""`sandik/intro/utils.py` içindeki, giriş yapmış kullanıcıya gösterilen sandık istatistikleri.

İstatistik sayfasının herkese açık yarısı yalnızca elemeden geçen sandıkları kapsar. Kullanıcıya
özel yarı ise açılır listeden **seçilen** sandığı gösterir; bu testler seçimin yetkilendirme
görevini de gördüğünü (başkasının sandığı seçilemez), seçim yokken hiçbir şey hesaplanmadığını ve
elemeden geçemeyen sandığın kendi üyesine yine de gösterildiğini doğrular.
"""
from decimal import Decimal

from pony.orm import db_session

from sandik.intro import utils as intro_utils
from sandik.utils import period as period_utils

from tests import factories


@db_session
def test_selected_sandik_statistics_cover_only_that_sandik():
    wu = factories.make_web_user()
    other_wu = factories.make_web_user()

    my_sandik = factories.make_sandik(created_by=wu, name="Benim Sandığım")
    my_share = factories.make_member_with_share(sandik=my_sandik, web_user=wu, created_by=wu)
    factories.make_member_with_share(sandik=my_sandik, created_by=wu)  # aynı sandıkta ikinci üye

    other_sandik = factories.make_sandik(created_by=other_wu)
    other_share = factories.make_member_with_share(sandik=other_sandik, web_user=other_wu, created_by=other_wu)
    factories.make_debt(share=other_share, amount=Decimal("900"), created_by=other_wu, number_of_installment=3)

    # 100 TL'lik aidata 400 TL yatırılıyor: 300 TL işleme konmadan kalıyor, o parayla borç veriliyor.
    factories.pay_contribution_partially(share=my_share, term=period_utils.current_period(),
                                         paid_amount=Decimal("400"), created_by=wu,
                                         contribution_amount=Decimal("100"))
    factories.make_debt(share=my_share, amount=Decimal("300"), created_by=wu, number_of_installment=3)

    selection = intro_utils.get_sandik_selection(web_user=wu, sandik_id=my_sandik.id)

    # Açılır listede yalnızca kullanıcının kendi sandığı vardır
    assert selection["sandiks"] == [my_sandik]
    assert selection["selected_sandik"] == my_sandik
    # Başkasının sandığı (ve oradaki 900 TL'lik borç) hiçbir sayıya karışmaz
    item = selection["statistics"]
    assert item["sandik"] == my_sandik

    assert item["active_member_count"] == 2
    assert item["active_share_count"] == 2
    assert item["money_transaction_count"] == 2  # aidat için para girişi + borç için para çıkışı
    assert item["contribution_count"] == 1
    assert item["installment_count"] == 3
    assert item["debt_count"] == 1

    assert item["money"]["total_debt_amount"] == Decimal("300")
    assert item["money"]["paid_contribution_amount"] == Decimal("100")
    assert item["money"]["paid_installment_amount"] == Decimal("0")
    assert item["money"]["unpaid_debt_amount"] == Decimal("300")
    assert item["money"]["total_revenue_amount"] == Decimal("400")
    assert item["undistributed_amount"] == Decimal("300")
    # 100 (aidat) - 300 (borç) + 0 (taksit) + 300 (işleme konmamış) = 100
    assert item["final_status"] == Decimal("100")

    debts_by_year = item["money"]["debts_by_year"]
    assert [(row["year"], row["amount"], row["count"]) for row in debts_by_year] \
           == [(item["last_money_transaction_date"].year, Decimal("300"), 1)]


@db_session
def test_small_sandik_is_hidden_from_public_totals_but_shown_to_its_own_member():
    """Eleme ölçütlerini geçemeyen sandık genel toplamlara girmez, sahibine yine de gösterilir."""
    wu = factories.make_web_user()
    sandik = factories.make_sandik(created_by=wu)
    share = factories.make_member_with_share(sandik=sandik, web_user=wu, created_by=wu)
    factories.pay_contribution_partially(share=share, term=period_utils.current_period(),
                                         paid_amount=Decimal("100"), created_by=wu,
                                         contribution_amount=Decimal("100"))

    # Tek üye ve tek para hareketi: MIN_ACTIVE_MEMBER_COUNT / MIN_MONEY_TRANSACTION_COUNT'un altında
    assert intro_utils.calculate_statistics()["has_data"] is False

    selection = intro_utils.get_sandik_selection(web_user=wu, sandik_id=sandik.id)
    assert selection["selected_sandik"] == sandik
    assert selection["statistics"]["money"]["paid_contribution_amount"] == Decimal("100")


@db_session
def test_user_without_sandik_gets_an_empty_selection():
    wu = factories.make_web_user()
    selection = intro_utils.get_sandik_selection(web_user=wu)
    assert selection == {"sandiks": [], "selected_sandik": None, "statistics": None}


@db_session
def test_nothing_is_calculated_without_a_selection():
    """Seçim yokken sayfa eskisiyle aynı kalmalı: liste dolu, rakam yok."""
    wu = factories.make_web_user()
    sandik = factories.make_sandik(created_by=wu)
    factories.make_member_with_share(sandik=sandik, web_user=wu, created_by=wu)

    assert intro_utils.get_sandik_selection(web_user=wu)["statistics"] is None


@db_session
def test_someone_elses_sandik_can_not_be_selected():
    """Seçim listeyle kesiştirilir; adrese başka bir sandığın kimliği yazılırsa hiçbir şey açılmaz."""
    wu = factories.make_web_user()
    other_wu = factories.make_web_user()
    other_sandik = factories.make_sandik(created_by=other_wu)
    factories.make_member_with_share(sandik=other_sandik, web_user=other_wu, created_by=other_wu)

    selection = intro_utils.get_sandik_selection(web_user=wu, sandik_id=other_sandik.id)

    assert selection["selected_sandik"] is None
    assert selection["statistics"] is None


def test_short_amount_string_keeps_the_minus_sign_readable():
    """Sandığın son durumu eksi olabilir; kısaltma işareti koruyup okunur kalmalı."""
    assert intro_utils.short_amount_string(14560648) == "14,6 milyon"
    assert intro_utils.short_amount_string(2308) == "2 bin"
    assert intro_utils.short_amount_string(-2308) == "-2 bin"
    assert intro_utils.short_amount_string(-1560648) == "-1,6 milyon"
    assert intro_utils.short_amount_string(-250) == "-250"
    assert intro_utils.short_amount_string(None) == "0"
