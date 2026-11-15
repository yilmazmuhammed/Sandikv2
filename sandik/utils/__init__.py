import os
from datetime import date, datetime, time, timedelta
from json import JSONEncoder

from flask import g
from pony.orm import ObjectNotFound, rollback
from pony.orm.core import Entity


class LayoutPI:
    website_name = "Sandık v2"
    short_website_name = "Sandık v2"
    # Sayfa kendi açıklamasını vermezse arama sonucunda ve paylaşımlarda bu görünür
    default_description = ("İmece usulü yardımlaşma sandıkları için aidat, borç ve taksit takip "
                           "sistemi. Kimin ne ödediği, kimin ne kadar borçlu olduğu tek ekranda.")

    def __init__(self, title, active_dropdown=None, description=None, robots=None, image=None):
        self.title = title
        self.active_dropdown = active_dropdown
        # `<meta name="description">` ve paylaşım açıklaması (og:description)
        self.description = description or self.default_description
        # `<meta name="robots">`. Yönetim paneli ve giriş sayfaları koşulsuz "noindex"tir
        # (kabukları öyle yazar); bu alan yalnızca tanıtım sayfaları için anlamlıdır.
        self.robots = robots
        # Paylaşımda görünecek görselin site içi adresi (og:image)
        self.image = image
        g.now = tz_to_tr(datetime.now(), tz="UTC")


def rollback_and_reload():
    """İşlemi geri alır ve isteğin `g` üzerindeki nesnelerini (`g.sandik`, `g.member`, oturum açmış
    kullanıcı = `g._login_user` ...) yeni oturumdan yeniden yükler.

    Pony'de `rollback()` o ana kadar yüklenen nesnelerin önbelleğini kapatır; hatadan sonra sayfa
    yeniden çizilirken (sol menü `g.sandik.applicant_web_users_set`i okur) bu eski nesneler
    `DatabaseSessionIsOver` / "mix objects belonging to different transactions" hatası verir. Bu
    yüzden sayfa route'larında çıplak `rollback()` değil bu fonksiyon çağrılır. Geri alınan işlemde
    oluşturulmuş (artık var olmayan) bir nesne `None` olur.
    """
    rollback()
    for name in list(g):
        value = g.get(name)
        if isinstance(value, Entity):
            try:
                setattr(g, name, type(value)[value._pkval_])
            except ObjectNotFound:
                setattr(g, name, None)


class CustomJSONEncoder(JSONEncoder):
    DATETIME_STR_FORMAT = os.getenv("DATETIME_STR_FORMAT", "%Y-%m-%d %H:%M:%S.%f")
    DATE_STR_FORMAT = os.getenv("DATE_STR_FORMAT", "%Y-%m-%d")
    TIME_STR_FORMAT = os.getenv("TIME_STR_FORMAT", "%H:%M")

    def default(self, obj):
        try:
            if isinstance(obj, datetime):
                return obj.strftime(self.DATETIME_STR_FORMAT)
            elif isinstance(obj, date):
                return obj.strftime(self.DATE_STR_FORMAT)
            elif isinstance(obj, time):
                return obj.strftime(self.TIME_STR_FORMAT)
            iterable = iter(obj)
        except TypeError:
            pass
        else:
            return list(iterable)
        return JSONEncoder.default(self, obj)


def tz_to_tr(coming_time, tz="utc"):
    if tz.lower() == "utc":
        return coming_time + timedelta(hours=3)


def add_parameters_to_url(url, parameters):
    if "?" in url:
        url += "&"
    else:
        url += "?"
    for key, value in parameters.items():
        url += str(key) + "=" + str(value) + "&"
    url = url[:-1]
    return url


def set_parameters_of_url(url, parameters: dict):
    url_args = []
    if "?" in url:
        args_part = url[url.find("?") + 1:]
        url = url[:url.find("?")]
        url_args = [a.split("=") for a in args_part.split("&")]
    url += "?"

    for key, value in url_args:
        if key not in parameters.keys():
            url += f"{key}={value}&"

    for key, value in parameters.items():
        url += f"{key}={value}&"

    url = url[:-1]
    return url


def safe_next_url(next_url, default_url):
    """Açık yönlendirme (open redirect) olmasın diye yalnızca bu sitedeki yollara izin verir.

    Kurallar myilmaz_tr deposundaki uygulamalardaki (`family_tree` → `utils.safe_next_url`) eşiyle aynıdır:
    yol "/" ile başlamalı, "//" ile başlamamalı; ters bölü ve kontrol karakterleri reddedilir (tarayıcılar
    "\\" işaretini "/" sayar, tab ve satır sonunu siler: "/\\kotu.com" ve "/<tab>/kotu.com" ikisi de
    "//kotu.com", yani başka bir site olur). Tam adresler (`https://...`) de reddedilir; adresler
    `url_for` ile üretildiği için mount noktası (`/sandikv2`) zaten yolun içindedir.
    """
    if (next_url and next_url.startswith("/") and not next_url.startswith("//")
            and "\\" not in next_url and not any(ord(c) < 32 or ord(c) == 127 for c in next_url)):
        return next_url
    return default_url


def get_next_url(args, parameters=None, default_url=""):
    """`?next=` adresi; güvenli değilse (`safe_next_url`) `default_url`"""
    if parameters is None:
        parameters = {}
    next_url = safe_next_url(args.get("next"), default_url)
    if next_url:
        next_url = add_parameters_to_url(next_url, parameters)
    return next_url


def safe_referrer(default_url):
    """İşlemden sonra kullanıcının geldiği sayfaya dönmek için: `Referer` aynı siteden değilse ya da hiç yoksa
    `default_url`. Eskiden `redirect(request.referrer)` başlık yoksa `None`a (500), başka bir siteyse oraya
    yönlendiriyordu."""
    from urllib.parse import urlsplit
    from flask import request

    referrer = request.referrer
    if not referrer:
        return default_url
    parts = urlsplit(referrer)
    if parts.scheme not in ("http", "https") or parts.netloc != request.host:
        return default_url
    path = parts.path + (f"?{parts.query}" if parts.query else "")
    return safe_next_url(path, default_url)
