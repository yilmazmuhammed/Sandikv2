"""Sandık kuralı formül hesaplayıcısı (`sandik/utils/formula.py`).

`cexprtk` (ExprTk) kaldırılırken yerine yazıldı; sonuçların ExprTk ile **birebir aynı** olması gerekir.
Aşağıdaki tablo cexprtk 0.4.1'in verdiği değerlerle doldurulmuştur. Ortamda `cexprtk` kuruluysa
(`pip install cexprtk==0.4.1`) `test_matches_exprtk_on_random_formulas` rastgele üretilmiş binlerce formülü
iki hesaplayıcıda karşılaştırır; kurulu değilse atlanır (üretimde artık kurulu değildir).
"""
import math
import random
from decimal import Decimal

import pytest
from pony.orm import db_session, flush

from sandik.sandik import utils as sandik_utils
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
    ('1.5', 1.5),
    ('1.', 1.0),
    ('.5', 0.5),
    ('1e3', 1000.0),
    ('1E+3', 1000.0),
    ('1.5e-2', 0.015),
    ('00012', 12.0),
    ('1500.00', 1500.0),
    ('2.486', 2.4859999999999998),
    ('4.363', 4.3629999999999995),
    ('1234.56', 1234.56),
    ('4.35e-5', 4.3499999999999993e-05),
    ('2*3+4/5-1', 5.8),
    ('8/2/2', 2.0),
    ('8/2*2', 8.0),
    ('1-2-3', -4.0),
    ('2^3^2', 512.0),
    ('-2^2', -4.0),
    ('2^-1', 0.5),
    ('2^-1^2', 0.5),
    ('-2^-2', -0.25),
    ('2*3^2', 18.0),
    ('2^3*2', 16.0),
    ('2*3%4', 2.0),
    ('2%3*4', 8.0),
    ('10%3', 1.0),
    ('-7%3', -1.0),
    ('7%-3', 1.0),
    ('5.5%2', 1.5),
    ('5--3', 8.0),
    ('5++3', 8.0),
    ('--5', 5.0),
    ('+-5', -5.0),
    ('5+-+-3', 8.0),
    ('1---5', -4.0),
    ('1----5', 6.0),
    ('2^---1', 0.5),
    ('1<2', 1.0),
    ('2<1', 0.0),
    ('1<=1', 1.0),
    ('2>=3', 0.0),
    ('3>2', 1.0),
    ('5=5', 1.0),
    ('5==5', 1.0),
    ('5===5', 1.0),
    ('5====5', 1.0),
    ('5<>3', 1.0),
    ('5!=3', 1.0),
    ('5<>5', 0.0),
    ('0.1+0.2==0.3', 0.0),
    ('1/3*3==1', 1.0),
    ('3>2>1', 0.0),
    ('1<2<3', 1.0),
    ('2==1<3', 1.0),
    ('1<3==2', 0.0),
    ('1+2*3<7', 0.0),
    ('7>1+2*3', 0.0),
    ('1+2==3', 1.0),
    ('1+2>=3==1', 1.0),
    ('5<-3', 0.0),
    ('5>-3', 1.0),
    ('1&0', 0.0),
    ('1|0', 1.0),
    ('1&0|1', 1.0),
    ('1|0&0', 1.0),
    ('0|1&0', 0.0),
    ('3>2&0', 0.0),
    ('0<1&2', 1.0),
    ('0==1|1', 1.0),
    ('2&3', 1.0),
    ('-1|0', 1.0),
    ('(1)and(0)', 0.0),
    ('(1)or(0)', 1.0),
    ('1and 0', 0.0),
    ('1/0', INF),
    ('-1/0', -INF),
    ('0/0', NAN),
    ('1/-0', -INF),
    ('1/(1-1)', INF),
    ('(1/0)>5', 1.0),
    ('(0/0)==(0/0)', 0.0),
    ('(0/0)<1', 0.0),
    ('(0/0)&1', 1.0),
    ('3%0', NAN),
    ('(1/0)%2', NAN),
    ('5%(1/0)', 5.0),
    ('0^0', 1.0),
    ('0^-1', INF),
    ('(-0)^-1', -INF),
    ('(-2)^3', -8.0),
    ('(-2)^0.5', NAN),
    ('(-8)^(1/3)', NAN),
    ('2^1024', INF),
    ('1e308*10', INF),
    ('10^-400', 0.0),
    ('2(3)', 6.0),
    ('(2)3', 6.0),
    ('(2)(3)', 6.0),
    ('2(3)4', 24.0),
    ('2(3)^2', 18.0),
    ('-(2)(3)', -6.0),
    ('3(2+1)', 9.0),
    ('2[3]', 6.0),
    ('[2]', 2.0),
    ('2abs(-1)', 2.0),
    ('(2)abs(-1)', 2.0),
    ('2max(1,3)', 6.0),
    ('abs(-3)', 3.0),
    ('abs(-0)', -0.0),
    ('min(3,1,2)', 1.0),
    ('max(1)', 1.0),
    ('floor(-1.5)', -2.0),
    ('ceil(-1.5)', -1.0),
    ('round(2.5)', 3.0),
    ('round(-2.5)', -3.0),
    ('round(-0.5)', -1.0),
    ('trunc(-1.5)', -1.0),
    ('trunc(1e20)', -9.223372036854776e+18),
    ('trunc(0/0)', -9.223372036854776e+18),
    ('sqrt(4)', 2.0),
    ('sqrt(-1)', NAN),
    ('not(0)', 1.0),
    ('not(1)+1', 1.0),
    ('-not(0)', -1.0),
    ('true', 1.0),
    ('false', 0.0),
    ('1//2', 1.0),
    ('100//2+3', 100.0),
    ('1#2', 1.0),
    ('1/*2*/+3', 4.0),
    ('1500.00*1.5', 2250.0),
    ('1500.00>=1000', 1.0),
    ('0.00<1', 1.0),
    ('100*12/100', 12.0),
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


def test_number_is_read_like_exprtk_not_like_python():
    """ExprTk sayıyı kendi algoritmasıyla okur; Python'un en yakın değerinden 1 ulp farklı olabilir."""
    assert evaluate_expression("2.486") == 2.4859999999999998 != float("2.486")


@pytest.mark.parametrize("expression", [
    "", "   ", "()", "5<", "<5", "5<<3", "5>>3", "5=<3", "5=>3", "5>=<3", "5**3", "1 2", "(1+2", "1+2)",
    "[1)", "(1]", "2,3", "max(1,)", "min()", "abs(1,2)", "abs", "abs 1", "1e", "1e+", "1..2", "1.5.", "5e0.5",
    "1e400", "1e-320", "+++5", "--++5", "1+++5", "5=====5", "1/*2", "5*/2", "1and0", "not1", "not 1", "2true",
    "(2)true", "2not(1)", "!1", "x", "{x}", "1;2", "1 xor 1", "1 nand 1", "a:=1",
    # Python'a kaçış denemeleri: hesaplayıcı hiçbirini çalıştırmaz, hepsi okunamayan formüldür.
    "__import__('os')", "().__class__", "open('/etc/passwd')", "1 if 1 else 0", "lambda: 1", "'a'", '"a"',
    "1@2", "~1", "1<<2",
])
def test_invalid_formula_raises_formula_error(expression):
    with pytest.raises(FormulaError):
        evaluate_expression(expression)


def test_non_string_is_rejected():
    with pytest.raises(FormulaError):
        evaluate_expression(None)


def test_deep_nesting_does_not_crash():
    assert evaluate_expression("(" * 50 + "1" + ")" * 50) == 1.0
    with pytest.raises(FormulaError):
        evaluate_expression("(" * 5000 + "1" + ")" * 5000)


def test_formula_error_is_a_value_error():
    assert issubclass(FormulaError, ValueError)


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
    """Koşulu tutmayan kural atlanır, sıradaki kuralın değeri kullanılır."""
    wu, sandik, share = setup_share(Decimal("1234.56"))
    factories.make_sandik_rule(sandik=sandik, created_by=wu, type=SandikRule.TYPE.MAX_AMOUNT_OF_DEBT, order=1,
                               condition_formula="{hisse_toplam_aidat}>=5000", value_formula="{hisse_toplam_aidat}*5")
    rule = factories.make_sandik_rule(sandik=sandik, created_by=wu, type=SandikRule.TYPE.MAX_AMOUNT_OF_DEBT,
                                      order=2, condition_formula="{hisse_toplam_aidat}<5000",
                                      value_formula="{hisse_toplam_aidat}*3-1000")
    flush()

    assert rule.evaluate_condition_formula(whose=share) == 1.0
    assert rule.evaluate_value_formula(whose=share) == 2703.68  # cexprtk de 2703.68 verir
    assert sandik_preferences.remaining_debt_balance(sandik=sandik, whose=share) == Decimal("2703.68")


@db_session
def test_empty_condition_means_always():
    wu, sandik, share = setup_share(Decimal("100"))
    rule = factories.make_sandik_rule(sandik=sandik, created_by=wu, type=SandikRule.TYPE.MAX_NUMBER_OF_INSTALLMENT,
                                      condition_formula="", value_formula="{borc-miktari}/1000")
    flush()

    assert rule.evaluate_condition_formula(amount=Decimal("5000")) == 1.0
    assert sandik_preferences.max_number_of_installment(sandik=sandik, amount=Decimal("5500")) == 5


@pytest.mark.parametrize("formula, formula_type", [
    ("{hisse_toplam_aidat}*1.5", SandikRule.FORMULA_TYPE.VALUE),
    ("{uye_toplam_aidat}/2+-1000", SandikRule.FORMULA_TYPE.VALUE),
    ("{borc-miktari}//2", SandikRule.FORMULA_TYPE.VALUE),
    ("{borc-miktari}>=10000", SandikRule.FORMULA_TYPE.CONDITION),
    ("{borc-miktari}==10000.5", SandikRule.FORMULA_TYPE.CONDITION),
])
def test_every_formula_the_validator_accepts_can_be_evaluated(formula, formula_type):
    variables = SandikRule.FORMULA_VARIABLE.strings.keys()
    operators = list(SandikRule.COMPARISON_OPERATOR.strings) + list(SandikRule.ARITHMETIC_OPERATOR.strings)
    sandik_utils.rule_formula_validator(formula_string=formula, variables=variables, operators=operators,
                                        formula_type=formula_type)
    for variable in variables:
        formula = formula.replace("{" + variable + "}", "12345.67")
    assert isinstance(evaluate_expression(formula), float)


# ----------------------------------------------------------------------------------------------------------
# cexprtk kuruluysa: rastgele formüllerle karşılaştırma
# ----------------------------------------------------------------------------------------------------------

def _random_number(rng):
    k = rng.random()
    if k < .3:
        return str(rng.randint(0, 20))
    if k < .5:
        return str(rng.randint(0, 100000))
    if k < .75:
        return f"{rng.randint(0, 99999)}.{rng.randint(0, 99):02d}"  # Decimal'in str()'i gibi
    if k < .9:
        return f"{rng.randint(0, 9)}.{rng.randint(0, 999)}"
    return rng.choice(["0", "0.00", "1", "0.5", "1.5", "1e3", "1E+3", "2.5E+2", ".5", "1."])


def _validator_like(rng):
    def side():
        parts = [_random_number(rng)]
        for _ in range(rng.randint(0, 4)):
            parts.append(rng.choice("+-*/") + ("-" if rng.random() < .1 else "") + _random_number(rng))
        return "".join(parts)

    formula = side()
    if rng.random() < .6:
        formula += rng.choice(["<", "<=", "==", ">=", ">"]) + side()
    return formula


_OPERATORS = ["+", "-", "*", "/", "%", "^", "<", "<=", ">", ">=", "==", "=", "!=", "<>", "&", "|"]


def _nested(rng, depth=0):
    k = rng.random()
    if depth > 4 or k < .3:
        return _random_number(rng)
    if k < .4:
        return rng.choice(["-", "+", "--"]) + _nested(rng, depth + 1)
    if k < .5:
        return "(" + _nested(rng, depth + 1) + ")"
    if k < .55:
        return rng.choice(["abs", "floor", "ceil", "round", "trunc", "sqrt", "not"]) + "(" + _nested(rng, depth + 1) + ")"
    if k < .58:
        return rng.choice(["min", "max"]) + "(" + ",".join(_nested(rng, depth + 1) for _ in range(rng.randint(1, 3))) + ")"
    if k < .62:
        return "(" + _nested(rng, depth + 1) + ")(" + _nested(rng, depth + 1) + ")"
    return _nested(rng, depth + 1) + rng.choice(_OPERATORS) + _nested(rng, depth + 1)


_PIECES = list("0123456789.+-*/<>=()[]^%&|eE,#!") + [
    "<=", ">=", "==", "<>", "!=", "abs(", "min(", "max(", "round(", "not(", "true", "and", "or", "/*", "*/", "//", "1.5"]


def _soup(rng):
    return "".join(rng.choice(_PIECES) for _ in range(rng.randint(1, 12)))


@pytest.mark.parametrize("generator", [_validator_like, _nested, _soup])
def test_matches_exprtk_on_random_formulas(generator):
    cexprtk = pytest.importorskip("cexprtk")
    rng = random.Random(generator.__name__)
    differences = []
    for _ in range(5000):
        expression = generator(rng)
        try:
            expected = ("ok", cexprtk.evaluate_expression(expression, {}))
        except Exception:
            expected = ("error", None)
        try:
            actual = ("ok", evaluate_expression(expression))
        except FormulaError:
            actual = ("error", None)
        if expected[0] != actual[0] or (expected[0] == "ok" and not same_float(actual[1], expected[1])):
            differences.append((expression, expected, actual))
    assert differences == []
