"""
Parola sıfırlama ("Parolamı unuttum") — **ortak modül**.

Bu dosya beş uygulamada **birebir aynıdır**; yalnızca hemen aşağıdaki "Uygulamaya özel" bloğu farklıdır:

    Sandikv2/sandik/auth/password_reset.py
    apartman/apartman/auth/password_reset.py
    davetiye/davetiye/auth/password_reset.py
    family_tree/family_tree/auth/password_reset.py
    cuzdan/cuzdan/auth/password_reset.py

Uygulamalar birbirinden import etmediği (ve Sandıkv2 ayrı bir depo olduğu) için kod paylaşılmaz, kopyalanır;
**birinde yapılan değişiklik diğerlerine de taşınmalıdır** (ana depo CLAUDE.md → "Parola sıfırlama"). Kullanıcı
istedi: bütün uygulamalarda "Parolamı unuttum" aynı olsun.

Kurallar (her uygulamada aynı):

* Adresler `/parola-sifirla` (istek formu) ve `/parola-sifirla/<jeton>` (yeni parola).
* Kayıtlı olsun olmasın aynı yanıt verilir; kimin üye olduğu sızmaz. Etkin olmayan hesaba e-posta gitmez.
* Jeton `itsdangerous` ile uygulamanın `secret_key`inden imzalanır (Flask'la gelir, ek paket gerekmez),
  `RESET_HOURS` saat geçerlidir. İçinde kullanıcı kimliği ve **parola özetinin kısa izi** vardır: parola değişince
  (bağlantı bir kez kullanılınca da) geçersiz olur. Özetin kendisi konmaz — eski JWT bağlantılarında tam özet
  vardı ve JWT'nin içi şifreli değil, okunabilir.
* Sınırlar (süreç belleğinde): IP başına saatte `MAX_REQUESTS_PER_IP` istek, adres başına saatte
  `MAX_EMAILS_PER_ADDRESS` e-posta.
* E-postada kullanıcı verisi kaçırılır; bağlantı, düz adres, süre ve "siz istemediyseniz" notu vardır. Gönderilemezse
  ayrıntı sunucu günlüğüne yazılır (bağlantının kendisi yazılmaz), kullanıcıya genel mesaj gösterilir.
* Sayfalar `Cache-Control: no-store` taşır (`private`).

Uygulamaya bağlı olan her şey (kullanıcıyı bulmak, e-posta göndermek, adresi üretmek, parolayı yazmak) çağıran
sayfaya bırakılmıştır; bu modül Flask'ın dışında hiçbir şeyi import etmez.
"""
# --- Uygulamaya özel (beş kopya arasında yalnızca bu blok farklıdır) -------------------------
APP_NAME = "Sandıkv2"
TOKEN_SALT = "sandikv2-parola-sifirlama"
# ---------------------------------------------------------------------------------------------

import hashlib
import time
from collections import defaultdict
from html import escape
from threading import Lock

RESET_HOURS = 2
MAX_REQUESTS_PER_IP = 5
MAX_EMAILS_PER_ADDRESS = 3

# Sayfa metinleri (bütün uygulamalarda aynı)
TITLE_REQUEST = "Parolamı unuttum"
TITLE_RESET = "Yeni parola belirle"
INTRO = "Hesabınızın e-posta adresini yazınız; yeni parola belirleyebileceğiniz bir bağlantı göndereceğiz."
SENT = ("Bu adresle bir hesap varsa parola sıfırlama bağlantısı gönderildi. Gelen kutunuzu (ve istenmeyen "
        "klasörünü) kontrol ediniz.")
NOT_CONFIGURED = ("Bu sitede e-posta gönderimi yapılandırılmamış; parola sıfırlama bağlantısı gönderilemiyor. "
                  "Lütfen site yöneticisiyle iletişime geçiniz.")
TOO_MANY = "Kısa sürede çok fazla istek gönderildi. Lütfen bir saat sonra tekrar deneyiniz."
SEND_FAILED = "E-posta gönderilemedi. Lütfen daha sonra tekrar deneyiniz."
EXPIRED = "Bağlantının süresi dolmuş. Lütfen yeniden parola sıfırlama isteyiniz."
INVALID = "Bağlantı geçersiz. Lütfen e-postadaki bağlantıyı eksiksiz açınız ya da yeniden isteyiniz."
USED = "Bu bağlantı artık geçerli değil (parola zaten değiştirilmiş). Gerekirse yeniden isteyiniz."
DONE = "Parolanız değiştirildi; yeni parolanızla giriş yapabilirsiniz."
NEW_LINK = "Yeni bağlantı iste"
BACK_TO_LOGIN = "Giriş sayfasına dön"


class ResetError(Exception):
    pass


# --------------------------------------------------------------------------------------
# Jeton
# --------------------------------------------------------------------------------------

def fingerprint(password_hash) -> str:
    """Parola özetinin kısa izi: jetona özetin kendisi değil bu konur"""
    return hashlib.sha256((password_hash or "").encode("utf-8")).hexdigest()[:16]


def _serializer(secret_key):
    from itsdangerous import URLSafeTimedSerializer
    return URLSafeTimedSerializer(secret_key, salt=TOKEN_SALT)


def create_token(user_id, password_hash, secret_key) -> str:
    return _serializer(secret_key).dumps({"id": user_id, "p": fingerprint(password_hash)})


def read_token(token, secret_key, get_user):
    """Jetonun kullanıcısı; `get_user(kimlik)` kullanıcıyı ya da None döndürür. Geçersizse `ResetError`."""
    from itsdangerous import BadSignature, SignatureExpired
    try:
        data = _serializer(secret_key).loads(token, max_age=RESET_HOURS * 3600)
    except SignatureExpired:
        raise ResetError(EXPIRED)
    except BadSignature:
        raise ResetError(INVALID)
    user_id = data.get("id") if isinstance(data, dict) else None
    user = get_user(user_id) if isinstance(user_id, int) else None
    if not user or not user.is_active or data.get("p") != fingerprint(user.password_hash):
        raise ResetError(USED)
    return user


# --------------------------------------------------------------------------------------
# İstek
# --------------------------------------------------------------------------------------

_requests = defaultdict(list)
_requests_lock = Lock()


def _allow(key, limit) -> bool:
    now = time.time()
    with _requests_lock:
        _requests[key] = [moment for moment in _requests[key] if now - moment < 3600]
        if len(_requests[key]) >= limit:
            return False
        _requests[key].append(now)
        return True


def reset_limits():
    """Testler için: sayaçları sıfırlar"""
    with _requests_lock:
        _requests.clear()


def display_name(user) -> str:
    return getattr(user, "name_surname", None) or getattr(user, "name", None) or ""


def email_subject() -> str:
    return f"{APP_NAME} — parola sıfırlama"


def email_html(name, url) -> str:
    url = escape(url)
    return f"""
        <p>Merhaba {escape(name)},</p>
        <p>{escape(APP_NAME)} hesabınız için parola sıfırlama istendi. Yeni parolanızı belirlemek için:</p>
        <p><a href="{url}">Parolamı sıfırla</a></p>
        <p>Bağlantı çalışmazsa şu adresi tarayıcınızın adres çubuğuna yapıştırabilirsiniz:<br>{url}</p>
        <p>Bağlantı {RESET_HOURS} saat geçerlidir ve bir kez kullanılabilir. Bu isteği siz yapmadıysanız bu e-postayı
        önemsemeyiniz; parolanız değişmez.</p>
    """


def request_reset(email_address, ip, secret_key, find_user, send_email, make_url, email_configured=True):
    """
    Hesap varsa sıfırlama bağlantısını e-postayla gönderir. Hesap yoksa sessizce döner (çağıran yine `SENT`i
    gösterir). Yapılandırma eksikse, sınır aşıldıysa ya da gönderilemezse `ResetError`.

    `find_user(adres)` -> kullanıcı/None, `send_email(alıcı, konu, html)`, `make_url(jeton)` -> tam adres.
    """
    if not email_configured:
        raise ResetError(NOT_CONFIGURED)
    if not _allow(f"ip:{ip}", MAX_REQUESTS_PER_IP):
        raise ResetError(TOO_MANY)
    # Adres uygulamanın kendi aramasına olduğu gibi verilir (büyük/küçük harf kuralı uygulamanındır, girişteki gibi)
    email_address = (email_address or "").strip()
    user = find_user(email_address)
    if not user or not user.is_active:
        return
    if not _allow(f"email:{email_address.lower()}", MAX_EMAILS_PER_ADDRESS):
        return  # aynı adrese çok fazla e-posta gitmesin; kullanıcıya yine aynı mesaj gösterilir
    url = make_url(create_token(user.id, user.password_hash, secret_key))
    try:
        send_email(user.email_address, email_subject(), email_html(display_name(user), url))
    except Exception as error:  # SMTP hataları çeşitlidir
        print(f"[{APP_NAME}] Parola sıfırlama e-postası gönderilemedi: {type(error).__name__}: {error}")
        raise ResetError(SEND_FAILED)


def client_ip(request) -> str:
    return request.headers.get("X-Real-IP") or request.remote_addr or ""


def private(response):
    """Jetonlu sayfa tarayıcı önbelleğinde ve geçmişte kalmasın"""
    response.headers["Cache-Control"] = "no-store"
    return response
