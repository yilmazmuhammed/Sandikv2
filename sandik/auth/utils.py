import os
from datetime import datetime, timedelta

import jwt
from flask import current_app, url_for
from flask_login import LoginManager

from sandik.auth import db
from sandik.auth.exceptions import WebUserNotFound, AuthException
from sandik.bot.email_bot import EmailBot
from sandik.general import db as general_db


def setup_login_manager(app):
    lm = LoginManager()

    @lm.user_loader
    def load_user(web_user_id):
        return db.get_web_user(id=web_user_id)

    lm.init_app(app)
    lm.login_message_category = 'danger'
    lm.login_message = u"Lütfen giriş yapınız."
    lm.login_view = "/giris"
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
    print(email_body)

    email_bot = EmailBot(email_address=os.getenv("EMAIL_BOT_EMAIL_ADDRESS"), password=os.getenv("EMAIL_BOT_PASSWORD"),
                         smtp_server=os.getenv("EMAIL_BOT_SMTP_SERVER"),
                         display_name=os.getenv("EMAIL_BOT_DISPLAY_NAME"))
    email_bot.connect_server()
    msg = email_bot.create_email_message(to_addresses=web_user.email_address, subject="Parola sıfırlama",
                                         message=email_body, message_type="html")
    print(msg.as_string())
    email_bot.send_email(to_addresses=web_user.email_address, msg=msg)
    email_bot.disconnect_server()


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
