"""`sandik/general/utils.py::get_home_page_data` için testler.

Ana sayfadaki "Aylık ödemelerim" tablosunun, işleme konmamış (henüz bir aidat/taksite dağıtılmamış)
parayı nasıl gösterdiğini doğrular:
    - tutar varsa ayrı bir satır olarak gösterilir,
    - alttaki "Toplam" satırından bu tutar düşülür (net kalan borç),
    - hiçbir sandıkta işleme konmamış para yoksa satır hiç oluşturulmaz.

Ayrıca "Gelecek ayların aidatlarını da göster" seçeneğinin tablosunu
(`payments_table_with_contributions`): henüz oluşturulmamış aidatlar hesaplanıp eklenir, ama
veritabanına yazılmaz ve var olan kayıtlar iki kez sayılmaz.
"""
from decimal import Decimal

from pony.orm import db_session

from sandik.general import utils as general_utils
from sandik.utils.db_models import Contribution
from sandik.utils import period as period_utils

from tests import factories


@db_session
def test_partial_payment_leaves_undistributed_row_and_negative_net_total():
    wu = factories.make_web_user()
    sandik = factories.make_sandik(created_by=wu)
    share = factories.make_member_with_share(sandik=sandik, web_user=wu, created_by=wu)
    member = share.member_ref

    # Bu ayın 100 TL'lik aidatına 150 TL yatırılıyor: 50 TL işleme konmadan kalıyor.
    factories.pay_contribution_partially(share=share, term=period_utils.current_period(), paid_amount=Decimal("150"),
                                         created_by=wu, contribution_amount=Decimal("100"))

    data = general_utils.get_home_page_data(wu)

    assert data["payment_rows"] == []
    assert data["undistributed_row"] == {"cells": {member.id: Decimal("50")}, "total": Decimal("50")}
    # Ödenmemiş borç yok, 50 TL fazladan yatırılmış: net toplam -50 (alacaklı).
    assert data["sandik_totals"] == {member.id: Decimal("-50")}
    assert data["grand_total"] == Decimal("-50")


@db_session
def test_undistributed_amount_is_subtracted_from_future_unpaid_total():
    wu = factories.make_web_user()
    sandik = factories.make_sandik(created_by=wu)
    share = factories.make_member_with_share(sandik=sandik, web_user=wu, created_by=wu)
    member = share.member_ref

    factories.pay_contribution_partially(share=share, term=period_utils.current_period(), paid_amount=Decimal("150"),
                                         created_by=wu, contribution_amount=Decimal("100"))
    # Gelecek ayın 80 TL'lik aidatı hiç ödenmemiş.
    next_term = period_utils.next_period()
    factories.make_contribution(share=share, term=next_term, created_by=wu, amount=Decimal("80"))

    data = general_utils.get_home_page_data(wu)

    assert data["payment_rows"] == [{"term": next_term, "cells": {member.id: Decimal("80")},
                                     "total": Decimal("80"), "projected_member_ids": set()}]
    assert data["undistributed_row"]["total"] == Decimal("50")
    # 80 TL borç - 50 TL işlenmemiş fazla = net 30 TL borç.
    assert data["sandik_totals"] == {member.id: Decimal("30")}
    assert data["grand_total"] == Decimal("30")


@db_session
def test_no_undistributed_money_means_no_row_and_unaffected_total():
    wu = factories.make_web_user()
    sandik = factories.make_sandik(created_by=wu)
    share = factories.make_member_with_share(sandik=sandik, web_user=wu, created_by=wu)
    member = share.member_ref

    # Aidat tam tutarınca ödeniyor, işleme konmamış para kalmıyor.
    factories.pay_contribution_partially(share=share, term=period_utils.current_period(), paid_amount=Decimal("100"),
                                         created_by=wu, contribution_amount=Decimal("100"))

    data = general_utils.get_home_page_data(wu)

    assert data["payment_rows"] == []
    assert data["undistributed_row"] is None
    assert data["sandik_totals"] == {member.id: Decimal("0")}
    assert data["grand_total"] == Decimal("0")


@db_session
def test_undistributed_row_only_lists_members_who_actually_have_it():
    wu = factories.make_web_user()

    sandik_with_extra = factories.make_sandik(created_by=wu, name="Fazla Ödemeli Sandık")
    share_with_extra = factories.make_member_with_share(sandik=sandik_with_extra, web_user=wu, created_by=wu)
    factories.pay_contribution_partially(share=share_with_extra, term=period_utils.current_period(),
                                         paid_amount=Decimal("120"), created_by=wu, contribution_amount=Decimal("100"))

    sandik_exact = factories.make_sandik(created_by=wu, name="Tam Ödemeli Sandık")
    share_exact = factories.make_member_with_share(sandik=sandik_exact, web_user=wu, created_by=wu)
    factories.pay_contribution_partially(share=share_exact, term=period_utils.current_period(),
                                         paid_amount=Decimal("100"), created_by=wu, contribution_amount=Decimal("100"))

    data = general_utils.get_home_page_data(wu)

    member_with_extra_id = share_with_extra.member_ref.id
    member_exact_id = share_exact.member_ref.id

    assert data["undistributed_row"]["cells"] == {member_with_extra_id: Decimal("20")}
    assert member_exact_id not in data["undistributed_row"]["cells"]
    assert data["sandik_totals"] == {member_with_extra_id: Decimal("-20"), member_exact_id: Decimal("0")}


@db_session
def test_future_contributions_are_added_only_to_the_optional_table():
    wu = factories.make_web_user()
    sandik = factories.make_sandik(created_by=wu)
    share = factories.make_member_with_share(sandik=sandik, web_user=wu, created_by=wu)
    member = share.member_ref
    current = period_utils.current_period()
    factories.make_contribution(share=share, term=current, created_by=wu)
    # 300 TL, 3 taksit: bu ay, gelecek ay ve ondan sonraki ay 100'er TL.
    factories.make_debt(share=share, amount=Decimal("300"), created_by=wu, number_of_installment=3)
    contribution_count = Contribution.select().count()

    data = general_utils.get_home_page_data(wu)

    # Varsayılan tablo değişmedi: gelecek aylarda yalnızca taksit var.
    assert [(r["term"], r["cells"]) for r in data["payment_rows"]] == [
        (current, {member.id: Decimal("200")}),
        (period_utils.next_period(1), {member.id: Decimal("100")}),
        (period_utils.next_period(2), {member.id: Decimal("100")}),
    ]
    assert data["grand_total"] == Decimal("400")

    # Seçenek açıkken gelecek ayların aidatı da eklenir; son taksitten sonraki aylara geçilmez.
    table = data["payments_table_with_contributions"]
    assert [(r["term"], r["cells"], r["projected_member_ids"]) for r in table["payment_rows"]] == [
        (current, {member.id: Decimal("200")}, set()),
        (period_utils.next_period(1), {member.id: Decimal("200")}, {member.id}),
        (period_utils.next_period(2), {member.id: Decimal("200")}, {member.id}),
    ]
    assert table["sandik_totals"] == {member.id: Decimal("600")}
    assert table["grand_total"] == Decimal("600")
    # Hesaplanan aidatlar veritabanına yazılmaz.
    assert Contribution.select().count() == contribution_count


@db_session
def test_without_future_payments_the_optional_table_shows_next_month_contribution():
    wu = factories.make_web_user()
    sandik = factories.make_sandik(created_by=wu)
    share = factories.make_member_with_share(sandik=sandik, web_user=wu, created_by=wu)
    member = share.member_ref
    factories.make_share(member=member, created_by=wu)  # iki hisse: aidat iki kez

    data = general_utils.get_home_page_data(wu)

    assert data["payment_rows"] == []
    rows = data["payments_table_with_contributions"]["payment_rows"]
    assert [(r["term"], r["cells"]) for r in rows] == [(period_utils.next_period(), {member.id: Decimal("200")})]


@db_session
def test_existing_future_contribution_is_not_counted_twice():
    wu = factories.make_web_user()
    sandik = factories.make_sandik(created_by=wu)
    share = factories.make_member_with_share(sandik=sandik, web_user=wu, created_by=wu)
    member = share.member_ref
    next_term = period_utils.next_period()
    # Gelecek ayın aidatı elle, farklı tutarla oluşturulmuş: hesaplanan tutar eklenmez.
    factories.make_contribution(share=share, term=next_term, created_by=wu, amount=Decimal("80"))

    data = general_utils.get_home_page_data(wu)

    rows = data["payments_table_with_contributions"]["payment_rows"]
    assert [(r["term"], r["cells"], r["projected_member_ids"]) for r in rows] == [
        (next_term, {member.id: Decimal("80")}, set()),
    ]
