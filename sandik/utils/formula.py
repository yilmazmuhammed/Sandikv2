"""Sandık kuralı formüllerini hesaplar (simpleeval üzerinde ince bir katman).

Eskiden `cexprtk` (ExprTk C++ kütüphanesi) kullanılıyordu; kurulu hâlde ~108 MB tutuyordu, PythonAnywhere'in
2 GB disk kotasında bu çok fazlaydı. Yerine saf Python, tek dosyalık `simpleeval` kullanılır (~36 KB, MIT).
`eval` kullanılmaz: simpleeval formülü Python'un `ast`iyle ayrıştırır ve yalnızca aşağıda izin verilen
işleçleri çalıştırır; ad, fonksiyon, öznitelik, metin, `//`, `**`, `%`, `^` gibi her şey `FormulaError` verir. Ayrıca
formülde yalnızca rakam, nokta, işaret ve parantez bulunabilir (Python'un `and`/`if` gibi yazımları kapalı).

Formun kabul ettiği yazımda (sayı, `{değişken}`, `+ - * /`, en çok bir karşılaştırma) sonuçlar ExprTk ile
aynıdır; 2026-11'de sunucudaki bütün kurallar gerçek değerlerle iki hesaplayıcıda karşılaştırıldı (bkz.
CLAUDE.md → "Kural formülleri"). ExprTk'in anlamını korumak için iki ayar yapılır:

- Sonuç her zaman `float`tır; karşılaştırma `1.0` / `0.0` verir.
- Sıfıra bölme hata vermez, ExprTk gibi `inf` / `-inf` / `nan` verir.

Bilinen tek fark: ExprTk bazı ondalıkları 1 ulp farklı okur (`2.53*14`: ExprTk 35.42, burada
35.419999999999995). Para tutarları 2 basamaklı Decimal, taksit/hisse sayısı `int()` ile kesildiği için
bu, sunucudaki kurallarda hiçbir sonucu değiştirmedi.
"""
import ast
import math
import operator
import re

import simpleeval

__all__ = ["FormulaError", "evaluate_expression"]


class FormulaError(ValueError):
    """Formül okunamadı (geçersiz yazım ya da desteklenmeyen bir ifade)."""


def _divide(a, b):
    # ExprTk (IEEE 754) gibi: 1/0 = inf, -1/0 = -inf, 0/0 = nan
    if b == 0:
        if a == 0 or math.isnan(a):
            return math.nan
        return math.copysign(math.inf, a) * math.copysign(1.0, b)
    return a / b


_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: _divide,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
}


class _Evaluator(simpleeval.SimpleEval):
    def _eval_constant(self, node):
        # Sayılar float okunur: `-0` ExprTk'teki gibi -0.0 olsun (1/-0 = -inf), tam sayıda işaretli sıfır yok.
        value = super()._eval_constant(node)
        if isinstance(value, int) and not isinstance(value, bool):
            return float(value)
        return value


# Formülde olabilecek karakterler: rakam, nokta, üs (Decimal'in str()'i "1E+3" verebilir), işaretler, parantez.
# simpleeval Python yazımlarını da kabul ederdi (`1 and 0`, `1 if 1 else 0`, `1;2`); bunlar baştan reddedilir.
_ALLOWED_CHARACTERS = re.compile(r"[0-9.eE+\-*/<>=!()\s]*")

# "05" Python'da sözdizimi hatasıdır, ExprTk'te 5'tir. Ondalık kısımdaki sıfırlara ("1.05") dokunulmaz.
_LEADING_ZEROS = re.compile(r"(?<![\d.])0+(?=\d)")


def evaluate_expression(expression):
    """Formülü hesaplar ve `float` döndürür; okunamazsa `FormulaError` atar."""
    if not isinstance(expression, str):
        raise FormulaError("Formül metin olmalıdır")
    if not _ALLOWED_CHARACTERS.fullmatch(expression):
        raise FormulaError(f"Formülde geçersiz karakter var: {expression}")
    evaluator = _Evaluator(operators=_OPERATORS, functions={}, names={})
    try:
        result = evaluator.eval(_LEADING_ZEROS.sub("", expression))
    except Exception as e:  # simpleeval'in kendi hataları, SyntaxError, OverflowError ...
        raise FormulaError(f"Formül hesaplanamadı: {expression}") from e
    if isinstance(result, bool) or isinstance(result, (int, float)):
        return float(result)
    raise FormulaError(f"Formül bir sayı vermedi: {expression}")
