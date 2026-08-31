from datetime import datetime, timedelta

import jwt
from flask import current_app, url_for, Flask
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


def send_renew_password_email(web_user):
    expiration_time = datetime.now() + timedelta(hours=5)
    info = {
        'email_address': web_user.email_address,
        'password_hash': web_user.password_hash,
        'expiration_time': {
            "year": expiration_time.year,
            "month": expiration_time.month,
            "day": expiration_time.day,
            "hour": expiration_time.hour,
            "minute": expiration_time.minute
        }
    }
    token = jwt.encode(info, current_app.secret_key, algorithm="HS256")

    url = url_for("auth_page_bp.password_reset_page", token=token, _external=True)
    email_body = f"""
        <h3>Sayın {web_user.name_surname}</h3>
        <p>Sandıkv2 hesap parolanızın sıfırlanması için talepte bulunuldu.</p>
        <a href="{url}" ><button type="button">Şifremi sıfırla</button></a>
        <p>Eğer üstteki düğme çalışmazsa aşağıdaki bağlantıyı tarayıcınızın adres çubuğuna yapıştırabilirsiniz:
        <br>
        <a href="{url}">{url}</a></p>
        <p>Eğer parola sıfırlama talebinde bulunmadıysanız bu epostayı önemsemeyiniz.</p>
    """
    # NOT: e-posta gövdesi ve mesajın tamamı bilerek yazdırılmıyor; içinde tek kullanımlık parola
    # sıfırlama bağlantısı var ve sunucu günlüğüne düşmemeli.
    email_bot.send_single_html_email(to_address=web_user.email_address, subject="Parola sıfırlama",
                                     html=email_body)


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


def get_web_user_from_password_reset_token(token):
    data = jwt.decode(token, current_app.secret_key, algorithms=["HS256"])

    if datetime.now() > datetime(**data.get("expiration_time")):
        raise AuthException("Parola sıfırlama bağlantısının süresi dolmuş. "
                            "Lütfen tekrar parola sıfırlama isteği gönderiniz.")

    web_user = db.get_web_user(email_address=data.get("email_address"))
    if not web_user:
        raise WebUserNotFound("Kullanıcı bulunamadı.")

    if web_user.password_hash != data.get("password_hash"):
        raise AuthException("Kullanıcı şifresi değiştirildiği için bağlantı geçerliliği iptal edildi.")

    return web_user
