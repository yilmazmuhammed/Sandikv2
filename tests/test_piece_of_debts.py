"""Güven bağlı sandıkta borcun paylara bölünmesi ve ödeme dağıtımı.

İki yer sınanıyor:
    - `transaction/db.py` -> `create_piece_of_debts`: borç, güven bağı olan üyelerin bakiyesine
      dağıtılır (eskiden tam sayı bölmesi yüzünden küsurat kalıp ERRCODE 0017 fırlatıyordu),
    - `db_models.py` -> `Debt.update_pieces_of_debt`: yapılan ödeme paylara dağıtılır ve toplamı
      ödemeye **tam** eşit olmalıdır (eskiden ERR U-POD-02).
"""
from decimal import Decimal

from pony.orm import db_session, flush

from sandik.utils import period as period_utils
from sandik.utils.db_models import Sandik
from sandik.utils.money import Currency

from tests import factories


def setup_trust_sandik(currency, contribution_amount, lender_payments):
    """Güven bağlı bir sandık kurar: borcu alacak bir hisse + bakiyesi olan `lender_payments` üye."""
    wu = factories.make_web_user()
    sandik = factories.make_sandik(created_by=wu, currency=currency,
                                   contribution_amount=contribution_amount,
                                   type=Sandik.TYPE.WITH_TRUST_RELATIONSHIP)
    borrower_share = factories.make_member_with_share(sandik=sandik, created_by=wu)

    for amount in lender_payments:
        lender_share = factories.make_member_with_share(sandik=sandik, created_by=wu)
        # Aidat ödemesi üyeye bakiye kazandırır; borç bu bakiyeden dağıtılır.
        factories.pay_contribution_partially(share=lender_share, term=period_utils.current_period(),
                                             paid_amount=amount, created_by=wu,
                                             contribution_amount=amount)
        factories.make_trust_relationship(requester_member=borrower_share.member_ref,
                                          receiver_member=lender_share.member_ref, created_by=wu)
    flush()
    return sandik, borrower_share, wu


def piece_amounts(debt):
    flush()
    return [p.amount for p in debt.piece_of_debts_set]


@db_session
def test_gold_debt_is_distributed_without_a_leftover():
    """0,5 gr borç üç kişiye bölünür: eskiden tam sayı bölmesi küsuratı düşürüp ERRCODE 0017 verirdi."""
    sandik, share, wu = setup_trust_sandik(Currency.GOLD_GRAM, Decimal("1"),
                                           [Decimal("1"), Decimal("1"), Decimal("1")])
    debt = factories.make_debt(share=share, amount=Decimal("0.5"), created_by=wu,
                               number_of_installment=5)

    amounts = piece_amounts(debt)
    assert sum(amounts) == Decimal("0.5")
    assert all(amount % Decimal("0.1") == 0 for amount in amounts)


@db_session
def test_try_debt_is_distributed_without_a_leftover():
    sandik, share, wu = setup_trust_sandik(Currency.TRY, Decimal("100"),
                                           [Decimal("100"), Decimal("100"), Decimal("100")])
    debt = factories.make_debt(share=share, amount=Decimal("100"), created_by=wu,
                               number_of_installment=4)

    assert sum(piece_amounts(debt)) == Decimal("100")


@db_session
def test_partial_payment_is_distributed_exactly_over_the_pieces():
    """Kısmi ödeme paylara dağıtılınca toplam, ödenen tutara tam eşit olmalı (ERR U-POD-02)."""
    sandik, share, wu = setup_trust_sandik(Currency.TRY, Decimal("100"),
                                           [Decimal("100"), Decimal("100"), Decimal("100")])
    debt = factories.make_debt(share=share, amount=Decimal("100"), created_by=wu,
                               number_of_installment=4)
    flush()

    installments = list(debt.installments_set.order_by(lambda i: i.term))
    mt = factories.make_money_transaction(member=share.member_ref, amount=installments[0].amount,
                                          created_by=wu)
    factories.make_sub_receipt(money_transaction=mt, amount=installments[0].amount, created_by=wu,
                               installment_ref=installments[0])
    flush()

    debt.update_pieces_of_debt()
    flush()
    paid = sum(p.paid_amount for p in debt.piece_of_debts_set)
    assert paid == debt.get_paid_amount()


@db_session
def test_partial_payment_of_a_gold_debt_is_distributed_exactly():
    sandik, share, wu = setup_trust_sandik(Currency.GOLD_GRAM, Decimal("1"),
                                           [Decimal("1"), Decimal("1"), Decimal("1")])
    debt = factories.make_debt(share=share, amount=Decimal("0.5"), created_by=wu,
                               number_of_installment=5)
    flush()

    installments = list(debt.installments_set.order_by(lambda i: i.term))
    mt = factories.make_money_transaction(member=share.member_ref, amount=installments[0].amount,
                                          created_by=wu)
    factories.make_sub_receipt(money_transaction=mt, amount=installments[0].amount, created_by=wu,
                               installment_ref=installments[0])
    flush()

    debt.update_pieces_of_debt()
    flush()
    paid = sum(p.paid_amount for p in debt.piece_of_debts_set)
    assert paid == debt.get_paid_amount()
    assert paid > 0
