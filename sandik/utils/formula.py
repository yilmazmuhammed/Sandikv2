"""Sandık kuralı formüllerini hesaplayan küçük, güvenli ifade hesaplayıcı.

Eskiden `cexprtk` (ExprTk C++ kütüphanesinin Python sarmalayıcısı) kullanılıyordu; kurulu hâlde ~108 MB
tutuyordu, PythonAnywhere'in 2 GB disk kotasında bu çok fazlaydı. Buradaki kod ek bağımlılık getirmez,
`eval` kullanmaz: metin kendi sözcük çözümleyicisi ve özyinelemeli ayrıştırıcısıyla okunur, yalnızca
aşağıda sayılan yazımlar kabul edilir, gerisi `FormulaError` verir.

ExprTk'in bu yazımlardaki **sonuç anlamı birebir korunur** (cexprtk 0.4.1 ile binlerce formül üzerinde
karşılaştırıldı, bkz. `tests/test_formula.py`):

- Sonuç her zaman `float`tır; karşılaştırma ve mantıksal işlemler `1.0` / `0.0` verir.
- Sıfıra bölme hata vermez: `1/0` = inf, `-1/0` = -inf, `0/0` = nan (IEEE 754). `%` C'nin `fmod`udur
  (`-7%3` = -1, `3%0` = nan), `^` C'nin `pow`udur (`(-8)^(1/3)` = nan, `0^-1` = inf).
- Öncelik (düşükten yükseğe): `|` `or` < `&` `and` < karşılaştırmalar < `+ -` < `* / %` < tekli `- +`
  < `^`. Karşılaştırmaların hepsi aynı düzeydedir ve soldan birleşir (`3>2>1` = `(3>2)>1` = 0);
  `^` sağdan birleşir (`2^3^2` = 512) ve tekli eksiden önce gelir (`-2^2` = -4, `2^-1` = 0.5).
- Karşılaştırmalar: `<`, `<=`, `>`, `>=`, `==` ve `=` (eşit), `!=` ve `<>` (eşit değil). Eşitlik
  tam karşılaştırmadır (`0.1+0.2==0.3` = 0, ExprTk'te de öyle).
- Sayılar: `12`, `1.5`, `1.`, `.5`, `1e3`, `1E+3`; üs ±308'i aşamaz (`1e400`, `1e-320` hatadır).
  Sayı metni ExprTk'in kendi algoritmasıyla okunur (`_parse_number`): Python'un `float()`u bazı
  ondalıklarda 1 ulp farklı sonuç verirdi (`2.486`).
- Art arda işaretler ExprTk gibi ikişer ikişer birleştirilir (`5--3` = 8, `5+-+-3` = 8) ve ExprTk'in
  reddettiği diziler (`+++5`, `--++5`) hata verir. `=`, `==`, `===` hepsi eşitliktir.
- Yorumlar atlanır: `#` ve `//` satır sonuna kadar, `/* ... */` arası. Form doğrulayıcısı `/` işaretine
  izin verdiği için `{x}//2` gibi bir kural ExprTk'te de burada da `{x}` demektir.
- Parantez: `()` ve `[]`. Örtük çarpma: `2(3)`, `(2)3`, `(2)(3)`, `2abs(-1)` (ExprTk'teki gibi).
- Ek olarak (form doğrulayıcısı harfe izin vermediği için yalnızca elle yazılmış eski kayıtlar için):
  `and`, `or`, `not(x)`, `true`, `false`, `abs`, `min`, `max` (bir ya da daha çok argüman), `floor`,
  `ceil`, `round` (yarımı sıfırdan uzağa), `trunc`, `sqrt`. ExprTk'in bunların dışındaki yazımları
  (değişkenler, atama, `;` ile çoklu ifade, `nand`/`xor` gibi işleçler, `{}` parantezi, diğer
  fonksiyonlar) desteklenmez ve `FormulaError` verir; cexprtk bunları hesaplıyordu.
"""
import math
import re
import sys

__all__ = ["FormulaError", "evaluate_expression"]

INF = float("inf")
NAN = float("nan")

# Uzun olanlar önce: "<=" "<" sanılmasın.
_OPERATORS = ("<=", ">=", "==", "!=", "<>", "<", ">", "=", "+", "-", "*", "/", "%", "^", "&", "|", ",")
_OPENING = {"(": ")", "[": "]"}
_CLOSING = {")", "]"}

_COMPARISONS = {
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "==": lambda a, b: a == b,
    "=": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    "<>": lambda a, b: a != b,
}

_CONSTANTS = {"true": 1.0, "false": 0.0}


class FormulaError(ValueError):
    """Formül okunamadı (geçersiz yazım ya da desteklenmeyen bir ifade)."""


def _bool(value):
    return 1.0 if value else 0.0


def _divide(a, b):
    if b == 0:
        if a == 0 or math.isnan(a):
            return NAN
        return math.copysign(INF, a) * math.copysign(1.0, b)
    return a / b


def _modulo(a, b):
    if b == 0 or math.isinf(a) or math.isnan(a) or math.isnan(b):
        return NAN
    return math.fmod(a, b)


def _is_odd_integer(x):
    return math.isfinite(x) and x == math.floor(x) and math.fmod(x, 2) != 0


def _power(a, b):
    # C'nin pow()'u: Python'un `**`ı negatif tabanda karmaşık sayı döndürür, math.pow ise hata atar.
    try:
        return math.pow(a, b)
    except OverflowError:
        if a < 0 and _is_odd_integer(b):
            return -INF
        return INF
    except ValueError:
        if a == 0:  # 0 üzeri negatif sayı
            if _is_odd_integer(b):
                return math.copysign(INF, a)
            return INF
        return NAN  # negatif tabanın tam sayı olmayan kuvveti


def _round_half_away_from_zero(x):
    if not math.isfinite(x):
        return x
    # ExprTk: (v < 0) ? ceil(v - 0.5) : floor(v + 0.5); sıfırın işareti de aynı çıksın diye birebir.
    if x < 0:
        return float(math.ceil(x - 0.5)) or -0.0
    return float(math.floor(x + 0.5))


def _float_function(function):
    # C'nin floor/ceil'i gibi: işaret sıfırda da korunur (ceil(-0.5) = -0.0).
    def wrapper(x):
        if not math.isfinite(x):
            return x
        return math.copysign(float(function(x)), x)

    return wrapper


def _trunc(x):
    # ExprTk: `static_cast<long long>(x)`; aralık dışı ve nan, x86'da en küçük 64 bit tam sayıyı verir.
    if math.isnan(x) or not -2.0 ** 63 <= x < 2.0 ** 63:
        return -9.223372036854776e18
    return float(math.trunc(x))


def _sqrt(x):
    if math.isnan(x) or x < 0:
        return NAN
    return math.sqrt(x)


# ad: (fonksiyon, en az argüman, en çok argüman; None = sınırsız)
_FUNCTIONS = {
    "abs": (lambda x: -x if x < 0 else x, 1, 1),
    "min": (lambda *xs: min(xs), 1, None),
    "max": (lambda *xs: max(xs), 1, None),
    "floor": (_float_function(math.floor), 1, 1),
    "ceil": (_float_function(math.ceil), 1, 1),
    "trunc": (_trunc, 1, 1),
    "round": (_round_half_away_from_zero, 1, 1),
    "sqrt": (_sqrt, 1, 1),
    "not": (lambda x: _bool(x == 0), 1, 1),
}

_WORD_OPERATORS = {"and": "&", "or": "|"}


_POWERS_OF_TEN = [0.0] + [float("1e%d" % k) for k in range(1, 309)]
_MIN_EXPONENT10 = sys.float_info.min_10_exp  # -307


def _compute_pow10(d, exponent):
    # ExprTk: details::compute_pow10
    e = abs(exponent)
    if exponent >= _MIN_EXPONENT10:
        if e < len(_POWERS_OF_TEN):
            return d * _POWERS_OF_TEN[e] if exponent > 0 else d / _POWERS_OF_TEN[e]
        return d * math.pow(10.0, 10.0 * exponent)
    d /= _POWERS_OF_TEN[-_MIN_EXPONENT10]
    return d / _POWERS_OF_TEN[-exponent + _MIN_EXPONENT10]


def _parse_number(text):
    """ExprTk'in `string_to_real`ının aynısı.

    Python'un `float()`u en yakın değeri bulur; ExprTk ise rakamları tek tek çarpıp toplar ve kesir kısmını
    ayrıca böler, bu yüzden bazı ondalıklarda 1 ulp farklı sonuç verir (`2.486` → 2.4859999999999998).
    Kayıtlı formüllerin sonucu değişmesin diye (ör. taksit sayısında `int()` kesmesi) aynı yol izlenir.
    """
    n = len(text)
    i = 0
    d = 0.0
    instate = False
    while i < n and text[i].isdigit():
        d = d * 10.0 + int(text[i])
        i += 1
        instate = True
    if i < n and text[i] == ".":
        i += 1
        start = i
        fraction = 0.0
        while i < n and text[i].isdigit():
            fraction = fraction * 10.0 + int(text[i])
            i += 1
        if i > start:
            instate = True
            if -(i - start) < -308:
                raise FormulaError(f"Geçersiz sayı: {text}")
            d += _compute_pow10(fraction, -(i - start))
    exponent = 0
    if i < n and text[i] in "eE":
        match = re.match(r"[+-]?\d+", text[i + 1:])
        if not match:
            raise FormulaError(f"Geçersiz sayı: {text}")
        exponent = int(match.group())
        i += 1 + match.end()
    if i != n or not instate or not -308 <= exponent <= 308:
        raise FormulaError(f"Geçersiz sayı: {text}")
    if exponent:
        d = _compute_pow10(d, exponent)
    return d


def _scan_number(expression, i):
    """ExprTk sözcük çözümleyicisinin `scan_number`ı: sayının bittiği yeri döndürür."""
    n = len(expression)
    dot_found = e_found = post_e_sign_found = post_e_digit_found = False
    while i < n:
        char = expression[i]
        if char == ".":
            if dot_found:
                raise FormulaError("Geçersiz sayı")
            dot_found = True
        elif char in "eE":
            if i + 1 >= n or not (expression[i + 1] in "+-" or expression[i + 1].isdigit()):
                raise FormulaError("Geçersiz sayı")
            e_found = True
        elif e_found and char in "+-" and not post_e_digit_found:
            if post_e_sign_found:
                raise FormulaError("Geçersiz sayı")
            post_e_sign_found = True
        elif e_found and char.isdigit():
            post_e_digit_found = True
        elif not char.isdigit():
            break
        i += 1
    return i


def _is_symbol_char(char):
    return (char.isascii() and char.isalnum()) or char == "_"


def _scan_symbol(expression, i):
    """ExprTk'in `scan_symbol`ı: adlar harf, rakam, `_` ve (arada kalan) `.` içerebilir (`and.3` tek addır)."""
    start = i
    n = len(expression)
    while i < n:
        char = expression[i]
        if not _is_symbol_char(char):
            if char != ".":
                break
            if i != start and i + 1 < n and not _is_symbol_char(expression[i + 1]):
                break
        i += 1
    return i


def _tokenize(expression):
    """(tür, değer) çiftleri: ("num", float), ("name", str), ("op", str), ("open"/"close", str)."""
    tokens = []
    i = 0
    n = len(expression)
    while i < n:
        char = expression[i]
        if char.isspace():
            i += 1
            continue

        # Yorumlar ExprTk'teki gibi atlanır: `#` ve `//` satır sonuna kadar, `/* ... */` arası.
        # (Form doğrulayıcısı "/" işaretine izin verdiği için `{x}//2` gibi bir kural `{x}` demektir.)
        if char == "#" or expression.startswith("//", i):
            end = expression.find("\n", i)
            i = n if end == -1 else end + 1
            continue
        if expression.startswith("/*", i):
            end = expression.find("*/", i + 2)
            if end == -1:
                raise FormulaError("Kapanmamış yorum")
            i = end + 2
            continue

        if char.isdigit() or char == ".":
            end = _scan_number(expression, i)
            tokens.append(("num", _parse_number(expression[i:end])))
            i = end
            continue

        if char.isascii() and char.isalpha():
            end = _scan_symbol(expression, i)
            name = expression[i:end].lower()
            if name in _WORD_OPERATORS:
                tokens.append(("op", _WORD_OPERATORS[name]))
            else:
                tokens.append(("name", name))
            i = end
            continue

        if char in _OPENING:
            tokens.append(("open", char))
            i += 1
            continue
        if char in _CLOSING:
            tokens.append(("close", char))
            i += 1
            continue

        for operator in _OPERATORS:
            if expression.startswith(operator, i):
                tokens.append(("op", operator))
                i += len(operator)
                break
        else:
            raise FormulaError(f"Geçersiz karakter: {char!r} ({i}. karakter)")

    return _insert_implicit_multiplication(_check_sign_sequences(_join_signs(tokens)))


_JOINS = {("+", "-"): "-", ("-", "+"): "-", ("-", "-"): "+", ("=", "="): "=="}
_INVALID_SIGN_TRIPLES = {("+", "+", "+"), ("-", "-", "-"), ("+", "-", "+"), ("-", "+", "-")}


def _sign(token):
    return token[1] if token[0] == "op" and token[1] in ("+", "-") else None


def _joinable(token):
    # ExprTk'te "=" ile "==" aynı türdür (eşitlik), `= =` de `==` olur: `1===1`, `1====1` geçerlidir.
    if token[0] == "op" and token[1] in ("=", "=="):
        return "="
    return _sign(token)


def _join_signs(tokens):
    """ExprTk'in `operator_joiner`ı (`process_stride_2`): `+-` → `-`, `-+` → `-`, `--` → `+`, `==` `=` → `==`.

    Birleştirme tek geçişte ve ikişer ikişer yapılır, birleşen işaret bir sonrakiyle yeniden
    birleşmez; geride kalan dizi `_check_sign_sequences` ile denetlenir. Sonuç değeri değiştirmez
    (`5--3` = `5+3`), yalnızca hangi uzun işaret dizilerinin hata olduğunu belirler (`+++5`, `--++5`).
    """
    if len(tokens) < 2:
        return tokens
    result = []
    i = 0
    while i < len(tokens) - 1:
        while True:
            joined = _JOINS.get((_joinable(tokens[i]), _joinable(tokens[i + 1])))
            if joined is None:
                result.append(tokens[i])
                break
            result.append(("op", joined))
            i += 2
            if i >= len(tokens) - 1:
                break
        i += 1
    result.append(tokens[-1])
    return result


def _check_sign_sequences(tokens):
    signs = [_sign(token) for token in tokens]
    for k in range(len(signs) - 2):
        if tuple(signs[k:k + 3]) in _INVALID_SIGN_TRIPLES:
            raise FormulaError("Geçersiz işaret dizisi")
    return tokens


def _insert_implicit_multiplication(tokens):
    """ExprTk gibi `2(3)`, `(2)3`, `(2)(3)`, `2abs(-1)` yazımlarına araya `*` koyar."""
    result = []
    for token in tokens:
        if result:
            previous_kind = result[-1][0]
            kind = token[0]
            after_value = previous_kind in ("num", "close")
            before_value = kind == "open" or (kind == "num" and previous_kind == "close") or (
                kind == "name" and token[1] in _FUNCTIONS and token[1] != "not")  # ExprTk'te not bir işleçtir
            if after_value and before_value:
                result.append(("op", "*"))
        result.append(token)
    return result


class _Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.position = 0

    def peek(self):
        if self.position < len(self.tokens):
            return self.tokens[self.position]
        return None

    def next(self):
        token = self.peek()
        if token is None:
            raise FormulaError("Formül yarım kalmış")
        self.position += 1
        return token

    def accept_op(self, *operators):
        token = self.peek()
        if token is not None and token[0] == "op" and token[1] in operators:
            self.position += 1
            return token[1]
        return None

    def parse(self):
        if not self.tokens:
            raise FormulaError("Formül boş")
        value = self.parse_or()
        if self.peek() is not None:
            raise FormulaError(f"Beklenmeyen ifade: {self.peek()[1]}")
        return value

    def parse_or(self):
        value = self.parse_and()
        while self.accept_op("|"):
            right = self.parse_and()
            value = _bool(value != 0 or right != 0)
        return value

    def parse_and(self):
        value = self.parse_comparison()
        while self.accept_op("&"):
            right = self.parse_comparison()
            value = _bool(value != 0 and right != 0)
        return value

    def parse_comparison(self):
        value = self.parse_additive()
        while True:
            operator = self.accept_op(*_COMPARISONS)
            if operator is None:
                return value
            right = self.parse_additive()
            value = _bool(_COMPARISONS[operator](value, right))

    def parse_additive(self):
        value = self.parse_multiplicative()
        while True:
            operator = self.accept_op("+", "-")
            if operator is None:
                return value
            right = self.parse_multiplicative()
            value = value + right if operator == "+" else value - right

    def parse_multiplicative(self):
        value = self.parse_unary()
        while True:
            operator = self.accept_op("*", "/", "%")
            if operator is None:
                return value
            right = self.parse_unary()
            if operator == "*":
                value = value * right
            elif operator == "/":
                value = _divide(value, right)
            else:
                value = _modulo(value, right)

    def parse_unary(self):
        operator = self.accept_op("-", "+")
        if operator == "-":
            return -self.parse_unary()
        if operator == "+":
            return self.parse_unary()
        return self.parse_power()

    def parse_power(self):
        base = self.parse_primary()
        if self.accept_op("^"):
            # Sağdan birleşir ve üs tekli eksi alabilir: 2^-1^2 = 2^(-(1^2))
            return _power(base, self.parse_unary())
        return base

    def parse_primary(self):
        kind, value = self.next()
        if kind == "num":
            return value
        if kind == "open":
            inner = self.parse_or()
            self.expect_close(value)
            return inner
        if kind == "name":
            if value in _CONSTANTS:
                return _CONSTANTS[value]
            if value in _FUNCTIONS:
                return self.parse_call(value)
            raise FormulaError(f"Tanınmayan ad: {value}")
        raise FormulaError(f"Beklenmeyen ifade: {value}")

    def expect_close(self, opening):
        token = self.next()
        if token != ("close", _OPENING[opening]):
            raise FormulaError("Parantezler eşleşmiyor")

    def parse_call(self, name):
        function, min_args, max_args = _FUNCTIONS[name]
        token = self.next()
        if token[0] != "open":
            raise FormulaError(f"'{name}' fonksiyonundan sonra parantez bekleniyordu")
        args = [self.parse_or()]
        while self.accept_op(","):
            args.append(self.parse_or())
        self.expect_close(token[1])
        if len(args) < min_args or (max_args is not None and len(args) > max_args):
            raise FormulaError(f"'{name}' fonksiyonu için argüman sayısı yanlış")
        return function(*args)


def evaluate_expression(expression):
    """Formülü hesaplar ve `float` döndürür; okunamazsa `FormulaError` atar."""
    if not isinstance(expression, str):
        raise FormulaError("Formül metin olmalıdır")
    try:
        return float(_Parser(_tokenize(expression)).parse())
    except RecursionError:
        raise FormulaError("Formül çok derin iç içe") from None
