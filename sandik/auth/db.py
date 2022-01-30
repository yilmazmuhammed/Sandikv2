from passlib.hash import pbkdf2_sha256 as hasher

from sandik.auth.exceptions import EmailAlreadyExist
from sandik.utils.db_models import WebUser, Log


def get_web_user(password=None, **kwargs) -> WebUser:
    web_user = WebUser.get(**kwargs)
    if web_user and password:
        if not hasher.verify(password, web_user.password_hash):
            return None
    return web_user


def add_web_user(email_address, password, **kwargs):
    if get_web_user(email_address=email_address):
        raise EmailAlreadyExist('Bu e-posta adresiyle daha önce kaydolunmuş.')

    web_user = WebUser(email_address=email_address, password_hash=hasher.hash(password), **kwargs)
    return web_user


def select_web_users(**kwargs):
    return WebUser.select(**kwargs)


def confirm_web_user(web_user_id, updated_by) -> WebUser:
    web_user = get_web_user(id=web_user_id)
    web_user.set(is_active_=True)
    web_user.logs_set.add(Log(web_user_ref=updated_by, type=Log.TYPE.WEB_USER.CONFIRM))
    return web_user


def block_web_user(web_user_id, updated_by) -> WebUser:
    web_user = get_web_user(id=web_user_id)
    web_user.set(is_active_=False)
    web_user.logs_set.add(Log(web_user_ref=updated_by, type=Log.TYPE.WEB_USER.BLOCK))

    return web_user


def web_users_form_choices():
    choices = [(wu.id, wu.display_name()) for wu in WebUser.select()]
    return choices
