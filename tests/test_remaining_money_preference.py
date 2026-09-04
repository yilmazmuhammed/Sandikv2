"""Üyenin "vadesi gelmiş ödemelerden artan para" tercihi (`RemainingMoneyPreference`).

Tercih üç değerlidir: her seferinde sor / vadesi gelmemiş ödemeleri öde / işleme konmamış bırak.
Kararı sunucu verir (`transaction/utils.py` -> `resolve_pay_future_payments`); arayüzdeki soru
yalnızca "her seferinde sor" tercihinde sorulur, o yüzden testler formdan değil bu fonksiyondan
gider.
"""
from decimal import Decimal

import pytest
from pony.orm import db_session, flush

from sandik.sandik import db as sandik_db
from sandik.transaction import utils as transaction_utils
from sandik.utils import period as period_utils
from sandik.utils.db_models import MoneyTransaction, RemainingMoneyPreference

from tests import factories


def new_member():
    created_by = factories.make_web_user()
    sandik = factories.make_sandik(created_by=created_by)
    return factories.make_member(sandik=sandik, created_by=created_by), created_by


# --- Tercihin okunması -------------------------------------------------------------------------

@db_session
def test_a_member_without_the_key_is_asked_every_time():
    """Tercih eklenmeden önceki davranış her seferinde sormaktı; mevcut üyeler için değişmemeli."""
    member, _ = new_member()
    member.preferences.clear()

    assert member.get_remaining_money_action() == RemainingMoneyPreference.ASK


@db_session
def test_an_unknown_value_falls_back_to_asking():
    """Elle düzenlenmiş Json'da sessizce bir tarafı seçmek paranın yanlış yere gitmesi olurdu."""
    member, _ = new_member()
    member.preferences[RemainingMoneyPreference.KEY] = "bilinmeyen_deger"

    assert member.get_remaining_money_action() == RemainingMoneyPreference.ASK


@db_session
def test_updating_the_preference_keeps_the_other_keys():
    """`Member.preferences` kalıbı: `update_member_preferences` yalnızca verdiği anahtarlara dokunur."""
    member, created_by = new_member()

    sandik_db.update_member_preferences(
        member=member, updated_by=created_by,
        preferences={RemainingMoneyPreference.KEY: RemainingMoneyPreference.PAY_FUTURE_PAYMENTS},
    )

    assert member.get_remaining_money_action() == RemainingMoneyPreference.PAY_FUTURE_PAYMENTS
    assert member.preferences["pay_at_beginning_of_month"] is True


# --- Kararın verilmesi -------------------------------------------------------------------------

@db_session
@pytest.mark.parametrize("answer", [True, False])
def test_the_form_answer_is_used_only_when_the_member_wants_to_be_asked(answer):
    member, _ = new_member()
    member.preferences[RemainingMoneyPreference.KEY] = RemainingMoneyPreference.ASK

    assert transaction_utils.resolve_pay_future_payments(member=member, answer=answer) is answer


@db_session
@pytest.mark.parametrize("action, expected", [
    (RemainingMoneyPreference.PAY_FUTURE_PAYMENTS, True),
    (RemainingMoneyPreference.LEAVE_UNDISTRIBUTED, False),
])
def test_the_preference_overrides_whatever_the_form_sent(action, expected):
    """Soru sorulmadığı için formdan anlamlı bir cevap gelmez; üç cevapta da tercih kazanmalı."""
    member, _ = new_member()
    member.preferences[RemainingMoneyPreference.KEY] = action

    for answer in (True, False, None):
        assert transaction_utils.resolve_pay_future_payments(member=member, answer=answer) is expected


# --- Uçtan uca: para girişinin dağıtımı --------------------------------------------------------

def _add_revenue(member, amount, created_by):
    """Sayfa katmanının yaptığını yapar: cevabı tercihe göre çözüp para girişini ekler.

    Formdan gelen cevap bilerek `False` verilir; tercihi olan üyede bu cevabın hiç kullanılmadığı
    da böylece görülür.
    """
    return transaction_utils.add_money_transaction(
        member=member, created_by=created_by, amount=amount,
        type=MoneyTransaction.TYPE.REVENUE, creation_type=MoneyTransaction.CREATION_TYPE.BY_MANUEL,
        use_untreated_amount=None,
        pay_future_payments=transaction_utils.resolve_pay_future_payments(member=member, answer=False),
    )


@db_session
@pytest.mark.parametrize("action, expected_future_unpaid, expected_undistributed", [
    (RemainingMoneyPreference.PAY_FUTURE_PAYMENTS, Decimal("50"), Decimal("0")),
    (RemainingMoneyPreference.LEAVE_UNDISTRIBUTED, Decimal("100"), Decimal("50")),
])
def test_the_preference_decides_where_the_extra_money_goes(action, expected_future_unpaid,
                                                           expected_undistributed):
    """Vadesi gelmiş aidatı aşan 50 ₺: tercihe göre gelecek aya gider ya da işleme konmamış kalır."""
    created_by = factories.make_web_user()
    sandik = factories.make_sandik(created_by=created_by, contribution_amount=Decimal("100"))
    share = factories.make_member_with_share(sandik=sandik, created_by=created_by)
    member = share.member_ref
    member.preferences[RemainingMoneyPreference.KEY] = action

    this_period = period_utils.current_period()
    next_period = period_utils.get_period_by_difference(start_period=this_period, diff_count=1)
    due = factories.make_contribution(share=share, term=this_period, created_by=created_by)
    future = factories.make_contribution(share=share, term=next_period, created_by=created_by)

    _add_revenue(member=member, amount=Decimal("150"), created_by=created_by)
    # `get_paid_amount()` SQL'e iner; henüz yazılmamış SubReceipt'leri görmesi için flush gerekir.
    flush()

    assert due.get_unpaid_amount() == Decimal("0")
    assert future.get_unpaid_amount() == expected_future_unpaid
    assert member.total_of_undistributed_amount() == expected_undistributed
