"""Türkçe alfabeye göre sıralama yardımcıları.

Python'un varsayılan sıralaması karakterleri Unicode kod noktasına göre dizer; bu yüzden Türkçe'ye
özgü harfler (ç, ğ, ı, ö, ş, ü) listenin sonuna atılır ("Zeytin" < "Çınar" gibi). Doğru sıralama için
`sorted(..., key=turkish_sort_key)` kullanılır.

Not: `locale.strxfrm` süreç genelinde `setlocale` gerektirdiği (ve sunucuda tr_TR yerelinin
bulunacağı garanti olmadığı) için kullanılmıyor; sıralama tamamen buradaki tabloya dayanır.
"""
import unicodedata

TURKISH_ALPHABET = "abcçdefgğhıijklmnoöprsştuüvyz"

# Türkçe'de bulunmayan latin harfleri kendi latin sıralarında (şu harften hemen sonra) yer alır.
_FOREIGN_LETTERS = {"q": "p", "w": "v", "x": "w"}

# Karakter sınıfları: noktalama < rakam < harf  (böylece "1. Sandık" < "Ahmet" olur)
_SYMBOL, _DIGIT, _LETTER = 0, 1, 2


def _build_letter_order() -> dict:
    order = {letter: index * 10 for index, letter in enumerate(TURKISH_ALPHABET)}
    for letter, previous_letter in _FOREIGN_LETTERS.items():
        order[letter] = order[previous_letter] + 1
    return order


_LETTER_ORDER = _build_letter_order()


def turkish_lower(text: str) -> str:
    """Türkçe kurallarına göre küçük harfe çevirir: I → ı, İ → i.

    `str.lower()` tek başına "I" harfini "i" yapar; ayrıca "İ".lower() "i" + birleşik nokta üretir.
    Bu yüzden bu iki harf önce elle çevrilir.
    """
    return text.replace("I", "ı").replace("İ", "i").lower()


def _strip_accent(char: str) -> str:
    """Şapkalı/aksanlı harfin aksansız halini döndürür (â → a). Türkçe harfler alfabede olduğu için buraya düşmez."""
    return "".join(c for c in unicodedata.normalize("NFD", char) if not unicodedata.combining(c))


def _primary_key(char: str) -> tuple:
    """Harfin alfabedeki yeri. Şapkalı harfler aksansız hâlleriyle aynı yere konur (â = a)."""
    for candidate in (char, _strip_accent(char)):
        letter_order = _LETTER_ORDER.get(candidate)
        if letter_order is not None:
            return _LETTER, letter_order

    if char.isdigit():
        return _DIGIT, ord(char)
    if char.isalpha():
        # Alfabede karşılığı olmayan yabancı harfler (kiril, yunan...) en sona
        return _LETTER, len(TURKISH_ALPHABET) * 10
    return _SYMBOL, ord(char)


def turkish_sort_key(text) -> tuple:
    """`sorted(...)`/`min`/`max` için Türkçe alfabe sırasına uyan anahtar üretir.

    Önce bütün metnin harf sırası karşılaştırılır; ancak bu sıra eşitse aksan ("adet" < "âdet") ve
    büyük/küçük harf farkına bakılır. Böylece "âdet" sıralamada "adres"in önünde, "adet"in hemen
    ardında kalır.
    """
    text = "" if text is None else str(text)
    lowered = turkish_lower(text)
    return tuple(_primary_key(char) for char in lowered), lowered, text
