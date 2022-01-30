from flask_login import LoginManager

from sandik.auth import db


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
