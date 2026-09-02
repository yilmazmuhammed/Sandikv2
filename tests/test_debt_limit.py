"""Borç limiti (`utils/sandik_preferences.py` -> `remaining_debt_balance`).

Limit, sandık kuralının verdiği değerin **tam kendisidir**. Eskiden sonuç 1000'in üst katına
yuvarlanıyor ve en az 1000 kabul ediliyordu; bu, altın gramı gibi birimlerde "hiç aidat ödememiş
üye 1000 gr borç alabilir" anlamına geliyordu.
"""
from decimal import Decimal

from pony.orm import db_session, flush

from sandik.utils import period as period_utils, sandik_preferences
from sandik.utils.db_models import SandikRule
from sandik.utils.money import Currency

from tests import factories


def setup_share_with_debt_rule(currency, contribution_amount, paid_amount, value_formula):
    wu = factories.make_web_user()
    sandik = factories.make_sandik(created_by=wu, currency=currency,
                                   contribution_amount=contribution_amount)
    factories.make_sandik_rule(sandik=sandik, created_by=wu, value_formula=value_formula,
                               type=SandikRule.TYPE.MAX_AMOUNT_OF_DEBT)
    share = factories.make_member_with_share(sandik=sandik, web_user=wu, created_by=wu)
    if paid_amount:
        factories.pay_contribution_partially(share=share, term=period_utils.current_period(),
                                             paid_amount=paid_amount, created_by=wu,
                                             contribution_amount=paid_amount)
    flush()
    return sandik, share


@db_session
def test_debt_limit_is_not_rounded_up_anymore():
    """2.500 ₺ aidat x 3 = 7.500 ₺; eskiden 8.000'e yuvarlanıyordu."""
    sandik, share = setup_share_with_debt_rule(Currency.TRY, Decimal("100"), Decimal("2500"),
                                               value_formula="{hisse_toplam_aidat}*3")

    assert sandik_preferences.remaining_debt_balance(sandik=sandik, whose=share) == Decimal("7500")


@db_session
def test_there_is_no_minimum_debt_limit_anymore():
    """Hiç aidat ödememiş hisse için kural 0 diyorsa limit 0'dır; eskiden taban 1000'di."""
    sandik, share = setup_share_with_debt_rule(Currency.TRY, Decimal("100"), None,
                                               value_formula="{hisse_toplam_aidat}*3")

    assert sandik_preferences.remaining_debt_balance(sandik=sandik, whose=share) == Decimal("0")


@db_session
def test_gold_debt_limit_stays_in_grams():
    """Altında 1,5 gr aidatın 2 katı 3 gr'dır; 1000'lik taban olsaydı 1000 gr çıkardı."""
    sandik, share = setup_share_with_debt_rule(Currency.GOLD_GRAM, Decimal("1"), Decimal("1.5"),
                                               value_formula="{hisse_toplam_aidat}*2")

    assert sandik_preferences.remaining_debt_balance(sandik=sandik, whose=share) == Decimal("3")


@db_session
def test_debt_limit_accepts_a_decimal_rule():
    """Kural formülünde ondalık kullanılabilir (doğrulayıcı artık noktayı kabul ediyor)."""
    sandik, share = setup_share_with_debt_rule(Currency.TRY, Decimal("100"), Decimal("1000"),
                                               value_formula="{hisse_toplam_aidat}*1.5")

    assert sandik_preferences.remaining_debt_balance(sandik=sandik, whose=share) == Decimal("1500")


@db_session
def test_passive_share_has_no_debt_limit():
    sandik, share = setup_share_with_debt_rule(Currency.TRY, Decimal("100"), Decimal("1000"),
                                               value_formula="{hisse_toplam_aidat}*3")
    share.is_active = False
    flush()

    assert sandik_preferences.remaining_debt_balance(sandik=sandik, whose=share) == Decimal("0")
