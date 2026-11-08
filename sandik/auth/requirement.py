from functools import wraps

from flask import abort, g, jsonify, make_response, request
from flask_login import login_required, current_user

from sandik.auth import db, utils


def admin_required(func):
    @wraps(func)
    @login_required
    def decorated_view(*args, **kwargs):
        if not current_user.is_admin():
            abort(403, "Bu işlem için yetkiniz bulunmamaktadır. Yönetici yetkisi gerekmektedir.")
        return func(*args, **kwargs)

    return decorated_view


def web_user_required(func):
    @wraps(func)
    def decorated_view(web_user_id, *args, **kwargs):
        web_user = db.get_web_user(id=web_user_id)
        if not web_user:
            abort(404, "Kullanıcı bulunamadı")

        g.web_user = web_user
        return func(web_user_id=web_user_id, *args, **kwargs)

    return decorated_view


def api_token_required(func):
    """Kişisel API anahtarıyla (Cüzdan bağlantısı) okunan uçlar için; `login_required`ın API anahtarlı karşılığı.

    Anahtar `Authorization: Bearer <anahtar>` başlığında gelir (`/cuzdan-baglantisi` sayfasında üretilir).
    Geçerliyse sahibi `g.api_web_user`a konur; **oturum açılmaz** (`current_user` değişmez), anahtar yalnızca
    bu dekoratörü taşıyan uçlara geçer. Geçersizse 401 + JSON. Yanıt her durumda `no-store` ve `noindex`tir.
    """
    @wraps(func)
    def decorated_view(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        token = header[7:].strip() if header.lower().startswith("bearer ") else ""
        g.api_web_user = utils.get_web_user_from_api_token(token)
        if g.api_web_user:
            response = make_response(func(*args, **kwargs))
        else:
            response = make_response(jsonify(result=False, msg="API anahtarı geçersiz ya da silinmiş."), 401)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Robots-Tag"] = "noindex"
        return response

    return decorated_view
