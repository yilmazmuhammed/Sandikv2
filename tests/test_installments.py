"""Borcun taksitlere bölünmesi (`transaction/db.py` -> `create_installments_of_debt`).

Taksit tutarları sandığın para biriminin **en küçük parçasına** yuvarlanır (TL'de 1 ₺, altında
0,1 gr) ve yuvarlama her adımda kalan tutar üzerinden yeniden yapılır; sabit bir taksit tutarı
yukarı yuvarlanırsa borç son taksitlere sıra gelmeden biter.
"""
from decimal import Decimal

import pytest
from pony.orm import db_session, flush

from sandik.transaction.exceptions import MaximumInstallmentExceeded
from sandik.utils.money import Currency

from tests import factories


def installment_amounts(debt):
    # Taksitler henüz yazılmamışken sorgu boş döner (bkz. CLAUDE.md: sorgudan önce flush)
    flush()
    return [i.amount for i in debt.installments_set.order_by(lambda i: i.term)]


def setup_share(currency=Currency.TRY, contribution_amount=Decimal("100")):
    wu = factories.make_web_user()
    sandik = factories.make_sandik(created_by=wu, currency=currency,
                                   contribution_amount=contribution_amount)
    return factories.make_member_with_share(sandik=sandik, web_user=wu, created_by=wu), wu


@db_session
def test_try_installments_are_whole_liras_and_sum_to_the_debt():
    """TL'de en küçük parça 1 ₺: taksitler tam liradır ve toplamları borca eşittir."""
    share, wu = setup_share()
    debt = factories.make_debt(share=share, amount=Decimal("100"), created_by=wu,
                               number_of_installment=30)

    amounts = installment_amounts(debt)
    assert len(amounts) == 30
    assert sum(amounts) == Decimal("100")
    assert all(amount == amount.to_integral_value() for amount in amounts)
    assert all(amount > 0 for amount in amounts)


@db_session
def test_try_installments_round_up_the_remaining_amount_each_step():
    """100 ₺ / 30 taksit: 4'er liradan başlayıp kalan tutara göre küçülür, son taksite kadar biter."""
    share, wu = setup_share()
    debt = factories.make_debt(share=share, amount=Decimal("100"), created_by=wu,
                               number_of_installment=30)

    amounts = installment_amounts(debt)
    assert amounts[0] == Decimal("4")
    assert sum(amounts) == Decimal("100")


@db_session
def test_debt_smaller_than_one_unit_per_installment_is_rejected():
    """5 ₺ 30 taksite bölünemez: her taksite en az bir birim (1 ₺) düşmeli."""
    share, wu = setup_share()
    with pytest.raises(MaximumInstallmentExceeded):
        factories.make_debt(share=share, amount=Decimal("5"), created_by=wu,
                            number_of_installment=30)


@db_session
def test_gold_installments_use_a_tenth_of_a_gram():
    """Altında en küçük parça 0,1 gr: 5 gr 10 taksite bölünür ve toplam korunur."""
    share, wu = setup_share(currency=Currency.GOLD_GRAM, contribution_amount=Decimal("1"))
    debt = factories.make_debt(share=share, amount=Decimal("5"), created_by=wu,
                               number_of_installment=10)

    amounts = installment_amounts(debt)
    assert amounts == [Decimal("0.5")] * 10
    assert sum(amounts) == Decimal("5")


@db_session
def test_gold_installments_with_a_remainder():
    """0,5 gr 4 taksite bölününce her taksit 0,1 gr'ın katı kalır."""
    share, wu = setup_share(currency=Currency.GOLD_GRAM, contribution_amount=Decimal("1"))
    debt = factories.make_debt(share=share, amount=Decimal("0.5"), created_by=wu,
                               number_of_installment=4)

    amounts = installment_amounts(debt)
    assert sum(amounts) == Decimal("0.5")
    assert all(amount % Decimal("0.1") == 0 for amount in amounts)
    assert all(amount >= Decimal("0.1") for amount in amounts)


@db_session
def test_gold_debt_smaller_than_one_tenth_per_installment_is_rejected():
    share, wu = setup_share(currency=Currency.GOLD_GRAM, contribution_amount=Decimal("1"))
    with pytest.raises(MaximumInstallmentExceeded):
        factories.make_debt(share=share, amount=Decimal("0.3"), created_by=wu,
                            number_of_installment=5)
