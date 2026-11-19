"""Sandık kuralı formül hesaplayıcısı (`sandik/utils/formula.py`, simpleeval üzerinde).

`cexprtk` (ExprTk) kaldırılırken simpleeval'e geçildi; formun kabul ettiği yazımda sonuçların ExprTk ile aynı
olması gerekir. Tablodaki değerler cexprtk 0.4.1'in verdiği değerlerdir. Ortamda `cexprtk==0.4.1` kuruluysa
`test_matches_exprtk_*` testleri iki hesaplayıcıyı doğrudan karşılaştırır; kurulu değilse atlanır.
"""
import math
import random
import re
from decimal import Decimal

import pytest
from pony.orm import db_session, flush

from sandik.sandik import utils as sandik_utils
from sandik.sandik.exceptions import InvalidRuleCharacter, InvalidRuleFormula
from sandik.utils import period as period_utils, sandik_preferences
from sandik.utils.db_models import SandikRule
from sandik.utils.formula import FormulaError, evaluate_expression
from sandik.utils.money import Currency

from tests import factories

INF = float("inf")
NAN = float("nan")

# (formül, cexprtk 0.4.1'in sonucu)
EXPRTK_RESULTS = [
    ('1', 1.0),
    ('12', 12.0),
    ('05', 5.0),
    ('007.5', 7.5),
    ('1.5', 1.5),
    ('1500.00', 1500.0),
    ('1234.56', 1234.56),
    ('0.00', 0.0),
    ('2*3+4/5-1', 5.8),
    ('8/2/2', 2.0),
    ('8/2*2', 8.0),
    ('1-2-3', -4.0),
    ('5--3', 8.0),
    ('5+-3', 2.0),
    ('-5+2', -3.0),
    ('+5', 5.0),
    ('2*-3', -6.0),
    ('1<2', 1.0),
    ('2<1', 0.0),
    ('1<=1', 1.0),
    ('2>=3', 0.0),
    ('3>2', 1.0),
    ('5==5', 1.0),
    ('5==5.00', 1.0),
    ('1+2*3<7', 0.0),
    ('7>1+2*3', 0.0),
    ('1+2==3', 1.0),
    ('5<-3', 0.0),
    ('1/0', INF),
    ('-1/0', -INF),
    ('0/0', NAN),
    ('1/-0', -INF),
    ('5/(2-2)', INF),
    ('1/0>5', 1.0),
    ('10000', 10000.0),
    ('5', 5.0),
    ('99999', 99999.0),
    ('1234.56*3', 3703.68),
    ('1666.67*3<=5000', 0.0),
    ('1666.66*3<=5000', 1.0),
    ('19999.00<=19999', 1.0),
    ('19999.01<=19999', 0.0),
    ('10*2500.50', 25005.0),
    ('150000.00/2500.00', 60.0),
    ('0/0.00', NAN),
    ('29999.50>29999', 1.0),
    ('4999.99*3<5000', 0.0),
    ('(1+2)*3', 9.0),
]

# 2026-11'de sunucudaki kuralların biçimleri (sayılar değiştirilmeden, sandık bilgisi olmadan)
SERVER_RULE_FORMULAS = [
    "10000", "5", "3", "99999", "99", "{hisse_toplam_aidat}*3", "{borc-miktari}<=19999", "{borc-miktari}<5000",
    "{borc-miktari}>29999", "{hisse_toplam_aidat}*3<=5000", "{hisse_toplam_aidat}*3<10000",
    "10*{uye_toplam_aidat}", "{borc-miktari}/{uye_toplam_aidat}", "{uye_toplam_aidat}/{hisse_toplam_aidat}",
]


def same_float(a, b):
    if math.isnan(b):
        return math.isnan(a)
    return a == b and math.copysign(1, a) == math.copysign(1, b)


@pytest.mark.parametrize("expression, expected", EXPRTK_RESULTS)
def test_result_is_the_same_as_exprtk(expression, expected):
    result = evaluate_expression(expression)
    assert isinstance(result, float)
    assert same_float(result, expected), (expression, result, expected)


def test_known_difference_number_parsing():
    """ExprTk bazı ondalıkları 1 ulp farklı okur; simpleeval Python'un en yakın değerini kullanır."""
    assert evaluate_expression("2.486") == 2.486
    assert evaluate_expression("2.486") - 2.4859999999999998 <= math.ulp(2.486)


@pytest.mark.parametrize("expression", [
    "", "   ", "()", "5<", "<5", "5=5", "5<>3", "5**3", "5//2", "5%2", "2^3", "1 2", "(1+2", "1+2)", "1e400**2",
    "x", "{x}", "1;2", "abs(1)", "max(1,2)", "1 if 1 else 0", "1 and 0", "'a'", '"a"', "[1]", "(1,2)",
    "__import__('os')", "().__class__", "open('/etc/passwd')", "lambda: 1", "a:=1", "~1", "1<<2", "1@2",
])
def test_invalid_formula_raises_formula_error(expression):
    with pytest.raises(FormulaError):
        evaluate_expression(expression)


def test_non_string_is_rejected():
    with pytest.raises(FormulaError):
        evaluate_expression(None)


@pytest.mark.parametrize("formula", ["{borc-miktari}//2", "{hisse_toplam_aidat}**2"])
def test_validator_rejects_ambiguous_operators(formula):
    variables = SandikRule.FORMULA_VARIABLE.strings.keys()
    operators = list(SandikRule.COMPARISON_OPERATOR.strings) + list(SandikRule.ARITHMETIC_OPERATOR.strings)
    with pytest.raises(InvalidRuleCharacter):
        sandik_utils.rule_formula_validator(formula_string=formula, variables=variables, operators=operators,
                                            formula_type=SandikRule.FORMULA_TYPE.VALUE)


@pytest.mark.parametrize("formula, formula_type", [
    ("{hisse_toplam_aidat}*1.5", SandikRule.FORMULA_TYPE.VALUE),
    ("{uye_toplam_aidat}/2+-1000", SandikRule.FORMULA_TYPE.VALUE),
    ("{borc-miktari}>=10000", SandikRule.FORMULA_TYPE.CONDITION),
    ("{borc-miktari}==10000.5", SandikRule.FORMULA_TYPE.CONDITION),
] + [(f, SandikRule.FORMULA_TYPE.CONDITION) for f in SERVER_RULE_FORMULAS])
def test_every_formula_the_validator_accepts_can_be_evaluated(formula, formula_type):
    variables = SandikRule.FORMULA_VARIABLE.strings.keys()
    operators = list(SandikRule.COMPARISON_OPERATOR.strings) + list(SandikRule.ARITHMETIC_OPERATOR.strings)
    sandik_utils.rule_formula_validator(formula_string=formula, variables=variables, operators=operators,
                                        formula_type=formula_type)
    for variable in variables:
        formula = formula.replace("{" + variable + "}", "12345.67")
    assert isinstance(evaluate_expression(formula), float)


# ----------------------------------------------------------------------------------------------------------
# Sandık kuralları üzerinden
# ----------------------------------------------------------------------------------------------------------

def setup_share(paid_amount):
    wu = factories.make_web_user()
    sandik = factories.make_sandik(created_by=wu, currency=Currency.TRY, contribution_amount=Decimal("100"))
    share = factories.make_member_with_share(sandik=sandik, web_user=wu, created_by=wu)
    factories.pay_contribution_partially(share=share, term=period_utils.current_period(),
                                         paid_amount=paid_amount, created_by=wu, contribution_amount=paid_amount)
    flush()
    return wu, sandik, share


@db_session
def test_rule_condition_and_value_are_evaluated():
    """Koşulu tutmayan kural atlanır, sıradaki kuralın değeri kullanılır (sunucudaki kural biçimi)."""
    wu, sandik, share = setup_share(Decimal("1234.56"))
    factories.make_sandik_rule(sandik=sandik, created_by=wu, type=SandikRule.TYPE.MAX_AMOUNT_OF_DEBT, order=1,
                               condition_formula="{hisse_toplam_aidat}*3<=3000", value_formula="5000")
    rule = factories.make_sandik_rule(sandik=sandik, created_by=wu, type=SandikRule.TYPE.MAX_AMOUNT_OF_DEBT,
                                      order=2, condition_formula="", value_formula="{hisse_toplam_aidat}*3")
    flush()

    assert rule.evaluate_condition_formula(whose=share) == 1.0
    assert rule.evaluate_value_formula(whose=share) == 3703.68  # cexprtk de 3703.68 verir
    assert sandik_preferences.remaining_debt_balance(sandik=sandik, whose=share) == Decimal("3703.68")


@db_session
def test_installment_rules_pick_the_first_matching_threshold():
    wu, sandik, share = setup_share(Decimal("100"))
    for order, (condition, value) in enumerate([("{borc-miktari}<=19999", "3"), ("{borc-miktari}<=49999", "5"),
                                                ("", "10")], start=1):
        factories.make_sandik_rule(sandik=sandik, created_by=wu, type=SandikRule.TYPE.MAX_NUMBER_OF_INSTALLMENT,
                                   order=order, condition_formula=condition, value_formula=value)
    flush()

    def installments(amount):
        return sandik_preferences.max_number_of_installment(sandik=sandik, amount=Decimal(amount))

    assert (installments("19999"), installments("20000"), installments("49999"), installments("49999.99")) \
        == (3, 5, 5, 10)


# ----------------------------------------------------------------------------------------------------------
# cexprtk kuruluysa: doğrudan karşılaştırma
# ----------------------------------------------------------------------------------------------------------

def _random_amount(rng):
    if rng.random() < .5:
        return f"{rng.randint(0, 300000)}.{rng.randint(0, 99):02d}"  # Decimal'in str()'i gibi
    return str(rng.randint(0, 300000))


def _exprtk(cexprtk, expression):
    try:
        return ("ok", cexprtk.evaluate_expression(expression, {}))
    except Exception:
        return ("error", None)


def _ours(expression):
    try:
        return ("ok", evaluate_expression(expression))
    except FormulaError:
        return ("error", None)


def test_matches_exprtk_on_server_rule_formulas():
    """Sunucudaki kural biçimlerinde sonuç bit bit aynıdır."""
    cexprtk = pytest.importorskip("cexprtk")
    rng = random.Random(1)
    differences = []
    for formula in SERVER_RULE_FORMULAS:
        for _ in range(2000):
            expression = formula
            for variable in SandikRule.FORMULA_VARIABLE.strings:
                expression = expression.replace("{" + variable + "}", _random_amount(rng))
            expected, actual = _exprtk(cexprtk, expression), _ours(expression)
            if expected[0] != actual[0] or (expected[0] == "ok" and not same_float(actual[1], expected[1])):
                differences.append((expression, expected, actual))
    assert differences == []


def _validator_like(rng):
    def number():
        k = rng.random()
        if k < .4:
            return str(rng.randint(0, 100000))
        if k < .8:
            return _random_amount(rng)
        return f"{rng.randint(0, 9)}.{rng.randint(0, 999)}"

    def side():
        parts = [number()]
        for _ in range(rng.randint(0, 4)):
            parts.append(rng.choice("+-*/") + ("-" if rng.random() < .1 else "") + number())
        return "".join(parts)

    formula = side()
    if rng.random() < .6:
        formula += rng.choice(["<", "<=", "==", ">=", ">"]) + side()
    return formula


def test_matches_exprtk_on_random_validator_formulas():
    """Formun kabul edeceği rastgele formüllerde sonuç aynıdır; tek fark sayı okumadan gelen birkaç ulp."""
    cexprtk = pytest.importorskip("cexprtk")
    rng = random.Random(2)
    differences = []
    for _ in range(20000):
        expression = _validator_like(rng)
        expected, actual = _exprtk(cexprtk, expression), _ours(expression)
        if expected[0] != actual[0]:
            differences.append((expression, expected, actual))
        elif expected[0] == "ok" and not same_float(actual[1], expected[1]):
            a, b = actual[1], expected[1]
            if not (math.isfinite(b) and abs(a - b) <= 8 * math.ulp(b)):
                differences.append((expression, expected, actual))
    assert differences == []


# ----------------------------------------------------------------------------------------------------------
# Kural eklenirken formülün hesaplanabilmesi
# ----------------------------------------------------------------------------------------------------------

def _validate(formula, formula_type):
    variables = SandikRule.FORMULA_VARIABLE.strings.keys()
    operators = list(SandikRule.COMPARISON_OPERATOR.strings) + list(SandikRule.ARITHMETIC_OPERATOR.strings)
    sandik_utils.rule_formula_validator(formula_string=formula, variables=variables, operators=operators,
                                        formula_type=formula_type)


@pytest.mark.parametrize("formula, formula_type", [
    ("+", SandikRule.FORMULA_TYPE.VALUE),  # sunucuda bu biçimde kayıtlı bozuk kurallar vardı
    ("{hisse_toplam_aidat}*", SandikRule.FORMULA_TYPE.VALUE),
    ("*3", SandikRule.FORMULA_TYPE.VALUE),
    ("5/*2", SandikRule.FORMULA_TYPE.VALUE),
    ("{borc-miktari}<", SandikRule.FORMULA_TYPE.CONDITION),
    ("<5000", SandikRule.FORMULA_TYPE.CONDITION),
    ("{borc-miktari}<=+", SandikRule.FORMULA_TYPE.CONDITION),
])
def test_incomplete_formula_is_rejected_when_the_rule_is_added(formula, formula_type):
    with pytest.raises(InvalidRuleFormula):
        _validate(formula, formula_type)


@pytest.mark.parametrize("formula, formula_type", [
    ("", SandikRule.FORMULA_TYPE.CONDITION),  # koşul boş bırakılabilir: her zaman geçerli
    ("{borc-miktari}/{uye_toplam_aidat}", SandikRule.FORMULA_TYPE.VALUE),
    ("-{hisse_toplam_aidat}+5000", SandikRule.FORMULA_TYPE.VALUE),
    ("{hisse_toplam_aidat}*3<=5000", SandikRule.FORMULA_TYPE.CONDITION),
])
def test_complete_formula_is_accepted(formula, formula_type):
    _validate(formula, formula_type)


@pytest.fixture
def app(monkeypatch):
    from sandik.app import create_app
    flask_app = create_app()
    flask_app.config.update(TESTING=True, SECRET_KEY="test")
    flask_app.secret_key = "test"
    return flask_app


def test_add_rule_page_shows_the_error_and_saves_nothing(app):
    base_url = "https://localhost"
    with db_session:
        manager = factories.make_web_user()
        sandik = factories.make_sandik(created_by=manager)
        flush()
        ids = dict(manager=manager.id, sandik=sandik.id)

    client = app.test_client()
    with client.session_transaction(base_url=base_url) as session:
        session["_user_id"] = str(ids["manager"])
        session["_fresh"] = True
    url = f"/sandik/{ids['sandik']}/sandik-kurali-ekle"
    page = client.get(url, base_url=base_url).get_data(as_text=True)
    token = re.search(r'<meta name="csrf-token" content="([^"]+)"', page).group(1)

    def post(value_formula):
        return client.post(url, base_url=base_url, headers={"Referer": base_url + url}, data={
            "csrf_token": token, "type": str(SandikRule.TYPE.MAX_NUMBER_OF_SHARE), "condition_formula": "",
            "value_formula": value_formula})

    response = post("+")
    assert response.status_code == 200
    assert "Formül eksik ya da hatalı yazılmış" in response.get_data(as_text=True)
    with db_session:
        assert SandikRule.select().count() == 0

    assert post("5").status_code == 302
    with db_session:
        assert [r.value_formula for r in SandikRule.select()] == ["5"]
