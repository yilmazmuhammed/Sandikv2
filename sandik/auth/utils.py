from flask_login import LoginManager

from sandik.auth import db
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
