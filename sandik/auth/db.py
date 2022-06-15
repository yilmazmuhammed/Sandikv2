from passlib.hash import pbkdf2_sha256 as hasher
from pony.orm import flush

from sandik.auth.exceptions import EmailAlreadyExist
from sandik.utils.db_models import WebUser, Log, get_updated_fields


def get_web_user(password=None, web_user=None, **kwargs) -> WebUser:
    web_user = web_user or WebUser.get(**kwargs)
    if web_user and password:
        if not hasher.verify(password, web_user.password_hash):
            return None
    return web_user


def get_or_create_bot_user(which):
    bot_user = WebUser.get(email_address=f'{which}@sandik.com')
    if not bot_user:
        bot_user = WebUser(email_address=f'{which}@sandik.com', password_hash=hasher.hash(f'{which}pw'),
                           name=which, surname=which)
        flush()
    return bot_user


def get_admin_web_users():
    return select_web_users(lambda wu: wu.is_admin())


def add_web_user(email_address, password, **kwargs) -> WebUser:
    if get_web_user(email_address=email_address):
        raise EmailAlreadyExist('Bu e-posta adresiyle daha önce kaydolunmuş.')

    web_user = WebUser(email_address=email_address, password_hash=hasher.hash(password), **kwargs)
    Log(web_user_ref=get_or_create_bot_user(which="anonymous"), type=Log.TYPE.WEB_USER.REGISTER,
        logged_web_user_ref=web_user)
    return web_user


def update_web_user(web_user, updated_by, email_address=None, **kwargs) -> WebUser:
    if email_address and get_web_user(email_address=email_address):
        raise EmailAlreadyExist('Bu e-posta adresiyle daha önce kaydolunmuş.')

    if kwargs.get("password"):
        kwargs["password_hash"] = hasher.hash(kwargs.pop("password"))

    updated_fields = get_updated_fields(new_values=kwargs, db_object=web_user)
    Log(web_user_ref=updated_by, type=Log.TYPE.WEB_USER.UPDATE, logged_web_user_ref=web_user,
        detail=str(updated_fields))
    web_user.set(**kwargs)
    return web_user


def select_web_users(*args, **kwargs):
    return WebUser.select(*args, **kwargs)


def confirm_web_user(web_user_id, updated_by) -> WebUser:
    web_user = get_web_user(id=web_user_id)
    web_user.set(is_active_=True)
    web_user.logs_set.add(Log(web_user_ref=updated_by, type=Log.TYPE.WEB_USER.CONFIRM))
    return web_user


def block_web_user(web_user_id, updated_by) -> WebUser:
    # TODO Admin engellenemez
    web_user = get_web_user(id=web_user_id)
    web_user.set(is_active_=False)
    web_user.logs_set.add(Log(web_user_ref=updated_by, type=Log.TYPE.WEB_USER.BLOCK))

    return web_user


def web_users_form_choices(exclusions=None):
    if exclusions is None:
        exclusions = []
    choices = [(wu.id, f"{wu.name_surname} <{wu.email_address}>")
               for wu in WebUser.select(lambda wu: wu not in exclusions).order_by(lambda wu: wu.name_surname.lower())]
    return choices
