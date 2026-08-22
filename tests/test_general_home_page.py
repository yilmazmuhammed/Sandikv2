"""`sandik/general/utils.py::get_home_page_data` için testler.

Ana sayfadaki "Aylık ödemelerim" tablosunun, işleme konmamış (henüz bir aidat/taksite dağıtılmamış)
parayı nasıl gösterdiğini doğrular:
    - tutar varsa ayrı bir satır olarak gösterilir,
    - alttaki "Toplam" satırından bu tutar düşülür (net kalan borç),
    - hiçbir sandıkta işleme konmamış para yoksa satır hiç oluşturulmaz.
"""
from decimal import Decimal

from pony.orm import db_session

from sandik.general import utils as general_utils
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
                                     "total": Decimal("80")}]
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
