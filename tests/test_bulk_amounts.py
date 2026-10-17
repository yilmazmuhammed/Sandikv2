"""Performans için eklenen toplu hesapların, satır satır hesaplayan asıl metotlarla aynı sonucu verdiğini
doğrular (bkz. Sandikv2/CLAUDE.md → "Listeleme sayfalarında performans").

- `get_*_in_memory()` eşleri ↔ `get_paid_amount()` / `get_unpaid_amount()` / `get_undistributed_amount()`
- `sandik.utils.get_members_financial_summary()` ↔ `Member.sum_of_*()` / `total_of_undistributed_amount()`
- `Sandik.sum_of_contributions()` ↔ aktif üyelerin `sum_of_paid_contributions()` toplamı
"""
from decimal import Decimal

from pony.orm import db_session

from sandik.sandik import utils as sandik_utils
from sandik.transaction import utils as transaction_utils
from sandik.utils import period as period_utils
from sandik.utils.db_models import Contribution, Debt, Installment, MoneyTransaction

from tests import factories


def _build_sandik():
    """Kısmi ödenmiş aidat, işleme konmamış para, kısmen ödenmiş borç ve pasif üye içeren bir sandık."""
    admin = factories.make_web_user()
    sandik = factories.make_sandik(created_by=admin)
    term = period_utils.current_period()

    paying = factories.make_member_with_share(sandik=sandik, created_by=admin)
    # 100'lük aidata 150 yatırılır: 100 aidata gider, 50 işleme konmadan kalır.
    factories.pay_contribution_partially(share=paying, term=term, paid_amount=Decimal("150"), created_by=admin,
                                         contribution_amount=Decimal("100"))
    # Geçen ayın aidatı yarım ödenmiş.
    factories.pay_contribution_partially(share=paying, term=period_utils.previous_period(), paid_amount=Decimal("40"),
                                         created_by=admin, contribution_amount=Decimal("100"))

    borrower = factories.make_member_with_share(sandik=sandik, created_by=admin)
    factories.pay_contribution_partially(share=borrower, term=term, paid_amount=Decimal("100"), created_by=admin,
                                         contribution_amount=Decimal("100"))
    debt = factories.make_debt(share=borrower, amount=Decimal("300"), created_by=admin, number_of_installment=3)
    first_installment = sorted(debt.installments_set, key=lambda i: i.term)[0]
    mt = factories.make_money_transaction(member=borrower.member_ref, amount=Decimal("130"), created_by=admin)
    factories.make_sub_receipt(money_transaction=mt, amount=Decimal("100"), created_by=admin,
                               installment_ref=first_installment)
    second_installment = sorted(debt.installments_set, key=lambda i: i.term)[1]
    factories.make_sub_receipt(money_transaction=mt, amount=Decimal("30"), created_by=admin,
                               installment_ref=second_installment)

    passive = factories.make_member_with_share(sandik=sandik, created_by=admin)
    factories.pay_contribution_partially(share=passive, term=term, paid_amount=Decimal("100"), created_by=admin,
                                         contribution_amount=Decimal("100"))
    passive.member_ref.is_active = False

    factories.make_member(sandik=sandik, created_by=admin)  # hiç hareketi olmayan üye
    return sandik


@db_session
def test_in_memory_amounts_match_query_amounts():
    _build_sandik()

    for c in Contribution.select():
        assert c.get_paid_amount_in_memory() == c.get_paid_amount()
        assert c.get_unpaid_amount_in_memory() == c.get_unpaid_amount()
    for i in Installment.select():
        assert i.get_paid_amount_in_memory() == i.get_paid_amount()
        assert i.get_unpaid_amount_in_memory() == i.get_unpaid_amount()
    for d in Debt.select():
        assert d.get_paid_amount_in_memory() == d.get_paid_amount()
        assert d.get_unpaid_amount_in_memory() == d.get_unpaid_amount()
    for mt in MoneyTransaction.select():
        assert mt.get_undistributed_amount_in_memory() == mt.get_undistributed_amount()


@db_session
def test_prefetched_lists_give_same_amounts():
    sandik = _build_sandik()

    for p in transaction_utils.get_payments(whose=sandik, prefetch_details=True):
        assert p.get_unpaid_amount_in_memory() == p.get_unpaid_amount()
    for d in transaction_utils.get_debts(whose=sandik, prefetch_details=True):
        assert d.get_unpaid_amount_in_memory() == d.get_unpaid_amount()
    for mt in transaction_utils.get_latest_money_transactions(whose=sandik, prefetch_details=True):
        assert mt.get_undistributed_amount_in_memory() == mt.get_undistributed_amount()


@db_session
def test_in_memory_amount_sees_sub_receipt_added_in_same_session():
    sandik = _build_sandik()
    contribution = next(p for p in transaction_utils.get_payments(whose=sandik, prefetch_details=True)
                        if isinstance(p, Contribution) and not p.is_fully_paid)
    before = contribution.get_paid_amount_in_memory()

    mt = factories.make_money_transaction(member=contribution.member_ref, amount=Decimal("10"),
                                          created_by=contribution.member_ref.web_user_ref)
    factories.make_sub_receipt(money_transaction=mt, amount=Decimal("10"), created_by=mt.member_ref.web_user_ref,
                               contribution_ref=contribution)

    assert contribution.get_paid_amount_in_memory() == before + Decimal("10") == contribution.get_paid_amount()


@db_session
def test_members_financial_summary_matches_member_methods():
    sandik = _build_sandik()

    summary = sandik_utils.get_members_financial_summary(sandik=sandik)

    assert set(summary) == {m.id for m in sandik.members_set}
    for member in sandik.members_set:
        assert summary[member.id] == {
            "sum_of_paid_contributions": member.sum_of_paid_contributions(),
            "sum_of_debts": member.sum_of_debts(),
            "sum_of_paid_installments": member.sum_of_paid_installments(),
            "total_of_undistributed_amount": member.total_of_undistributed_amount(),
            "sum_of_unpaid_amount_of_debts": member.sum_of_unpaid_amount_of_debts(),
        }
    # Senaryonun gerçekten sıfırdan farklı değerler ürettiğinden emin ol.
    assert any(v["total_of_undistributed_amount"] for v in summary.values())
    assert any(v["sum_of_unpaid_amount_of_debts"] for v in summary.values())


@db_session
def test_sum_of_contributions_counts_only_active_members():
    sandik = _build_sandik()

    expected = sum((m.sum_of_paid_contributions() for m in sandik.get_active_members()), Decimal(0))
    assert sandik.sum_of_contributions() == expected == Decimal("240")
