import jwt
from flask import current_app, Flask
from flask_login import LoginManager

from sandik.auth import db
from sandik.auth.exceptions import WebUserNotFound, AuthException
from sandik.bot import email_bot
from sandik.general import db as general_db


def setup_login_manager(app: Flask, login_view=None):
    lm = LoginManager()

    @lm.user_loader
    def load_user(web_user_id):
        return db.get_web_user(id=web_user_id)

    lm.init_app(app)
    lm.login_message_category = 'danger'
    lm.login_message = u"Lütfen giriş yapınız."
    lm.login_view = login_view or "/giris"
    return lm


class Notification:
    class WebUserAuth:

        @staticmethod
        def send_register_web_user_notification(registered_web_user):
            for web_user in db.get_admin_web_users():
                general_db.create_notification(
                    to_web_user=web_user,
                    title=f"{registered_web_user.name_surname} siteye üye oldu.", text="ADMIN",
                )


def is_email_configured() -> bool:
    return email_bot.is_configured()


# Parola sıfırlama ortak modüldedir: auth/password_reset.py (myilmaz_tr deposundaki beş uygulamada birebir aynı).


REMINDER_PREFERENCE_TOKEN_PURPOSE = "reminder_preference"


def create_reminder_preference_token(web_user):
    """Hatırlatma e-postalarındaki "tercihimi değiştir" bağlantısının jetonu.

    Parola sıfırlamanın aksine **süresi yoktur**: bağlantı kullanıcının posta kutusunda duruyor ve
    aylar sonra tıklandığında da çalışmalı. Karşılığında yetkisi de dardır — yalnızca hatırlatma
    günlerini değiştirir, hiçbir kişisel veri göstermez.

    `email_address` yüke konur ve kullanılırken doğrulanır: adres değişirse eski bağlantılar düşer.
    """
    return jwt.encode({"purpose": REMINDER_PREFERENCE_TOKEN_PURPOSE, "web_user_id": web_user.id,
                       "email_address": web_user.email_address},
                      current_app.secret_key, algorithm="HS256")


def get_web_user_from_reminder_preference_token(token):
    try:
        data = jwt.decode(token, current_app.secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise AuthException("Bağlantı geçersiz. Lütfen siteye giriş yaparak tercihlerinizi güncelleyiniz.")

    if data.get("purpose") != REMINDER_PREFERENCE_TOKEN_PURPOSE:
        raise AuthException("Bağlantı geçersiz.")

    web_user = db.get_web_user(id=data.get("web_user_id"))
    if not web_user:
        raise WebUserNotFound("Kullanıcı bulunamadı.")

    if web_user.email_address != data.get("email_address"):
        raise AuthException("E-posta adresi değiştiği için bağlantı geçerliliğini yitirdi. "
                            "Lütfen siteye giriş yaparak tercihlerinizi güncelleyiniz.")

    return web_user


# --------------------------------------------------------------------------------------
# Kişisel API anahtarı (Cüzdan bağlantısı)
# --------------------------------------------------------------------------------------
#
# Cüzdan uygulaması (myilmaz_tr deposundaki `cuzdan/`) borç geçmişini bu anahtarla okur
# (`/api/borc-gecmisi`). Anahtar yalnızca **okuma** yetkisi verir ve yalnızca o uca geçer; oturum
# açmaz. Biçimi `<web_user_id>.<rastgele>`: kimlik kısmı kullanıcıyı bulmak içindir, doğrulama
# rastgele kısmın tamamının SHA-256 özetiyle yapılır. Anahtar bir kez gösterilir, saklanmaz.

def _hash_api_token(token: str) -> str:
    import hashlib
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_api_token(web_user) -> str:
    """Yeni anahtar üretir (eskisi geçersiz olur) ve **bir kez** döndürür."""
    import secrets

    from pony.orm import flush
    if web_user.id is None:  # aynı istekte yeni oluşturulmuş kullanıcı
        flush()
    token = f"{web_user.id}.{secrets.token_urlsafe(32)}"
    db.set_api_token_hash(web_user=web_user, updated_by=web_user, token_hash=_hash_api_token(token))
    return token


def revoke_api_token(web_user):
    db.set_api_token_hash(web_user=web_user, updated_by=web_user, token_hash=None)


def api_token_created_at(web_user):
    """Anahtar varsa oluşturulduğu zaman (metin), yoksa None"""
    preferences = web_user.preferences or {}
    if not preferences.get(db.API_TOKEN_HASH_KEY):
        return None
    return preferences.get(db.API_TOKEN_CREATED_KEY) or "?"


def get_web_user_from_api_token(token):
    """Anahtar geçerliyse sahibi, değilse None. Etkin olmayan kullanıcı da None döner."""
    import hmac
    if not token or "." not in token:
        return None
    web_user_id, _ = token.split(".", 1)
    if not web_user_id.isdigit():
        return None
    web_user = db.get_web_user(id=int(web_user_id))
    if not web_user or not web_user.is_active:
        return None
    stored = (web_user.preferences or {}).get(db.API_TOKEN_HASH_KEY)
    if not stored or not hmac.compare_digest(stored, _hash_api_token(token)):
        return None
    return web_user
