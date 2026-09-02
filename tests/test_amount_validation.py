"""Tutar alanlarının para birimine bağlanması (`utils/forms.py`).

Sistemdeki bütün tutarlar para biriminin en küçük parçasının katı olmalıdır (TL'de 1 ₺, altında
0,1 gr). Kural hem tarayıcıya (`step`/`min`) hem sunucuya (`AmountUnitValidator`) yansır.

Formlar `FlaskForm` türevi olduğu için burada düz bir `wtforms.Form` ile sınanıyor: doğrulayıcının
kendisi Flask'e bağlı değil.
"""
from decimal import Decimal

import pytest
from wtforms import DecimalField, Form
from wtforms.validators import NumberRange

from sandik.utils.forms import apply_currency_to_amount_field
from sandik.utils.money import Currency


class AmountForm(Form):
    amount = DecimalField(label="İşlem miktarı:", validators=[NumberRange(min=0.001)])


def build_form(currency, value):
    form = AmountForm(data={"amount": Decimal(value)})
    apply_currency_to_amount_field(form.amount, currency)
    # `data=` ile kurulan formda raw_data yoktur; doğrulayıcılar `field.data` üzerinden çalışır.
    form.amount.raw_data = [value]
    return form


@pytest.mark.parametrize("value", ["1", "10", "1500", "0"])
def test_try_accepts_whole_liras(value):
    form = build_form(Currency.TRY, value)
    form.validate()
    assert "katları" not in " ".join(form.amount.errors)


@pytest.mark.parametrize("value", ["10.5", "0.01", "99.99"])
def test_try_rejects_amounts_smaller_than_one_lira(value):
    form = build_form(Currency.TRY, value)
    assert form.validate() is False
    assert any("katları" in error or "küçük olamaz" in error for error in form.amount.errors)


@pytest.mark.parametrize("value", ["0.1", "1.5", "5", "0.2"])
def test_gold_accepts_tenths_of_a_gram(value):
    form = build_form(Currency.GOLD_GRAM, value)
    form.validate()
    assert "katları" not in " ".join(form.amount.errors)


@pytest.mark.parametrize("value", ["0.05", "1.55"])
def test_gold_rejects_amounts_finer_than_a_tenth(value):
    form = build_form(Currency.GOLD_GRAM, value)
    assert form.validate() is False
    assert any("katları" in error or "küçük olamaz" in error for error in form.amount.errors)


def test_browser_attributes_come_from_the_unit():
    form = AmountForm()
    apply_currency_to_amount_field(form.amount, Currency.GOLD_GRAM)
    assert form.amount.render_kw["step"] == "0.1"
    assert form.amount.render_kw["min"] == "0.1"
    assert form.amount.places == 1

    form = AmountForm()
    apply_currency_to_amount_field(form.amount, Currency.TRY)
    assert form.amount.render_kw["step"] == "1"
    assert form.amount.places == 0


def test_validators_are_not_shared_between_form_instances():
    """Alan tanımı sınıf düzeyinde; doğrulayıcı listesi kopyalanmazsa istekler arasında birikir."""
    first = AmountForm()
    apply_currency_to_amount_field(first.amount, Currency.TRY)
    count_after_first = len(first.amount.validators)

    second = AmountForm()
    apply_currency_to_amount_field(second.amount, Currency.GOLD_GRAM)

    assert len(second.amount.validators) == count_after_first
    assert AmountForm().amount.validators == [] or len(AmountForm().amount.validators) == 1
