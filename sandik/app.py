import os
from datetime import datetime

import re

from flask import Flask, render_template
from flask_login import LoginManager
from flask_wtf.csrf import CSRFError, CSRFProtect
from jinja2.utils import htmlsafe_json_dumps
from markupsafe import Markup, escape
from pony.flask import Pony
from werkzeug.exceptions import HTTPException

from sandik.auth.page import auth_page_bp
from sandik.auth.utils import setup_login_manager
from sandik.backup.download import backup_dw_bp
from sandik.backup.page import backup_page_bp
from sandik.general.api import general_api_bp
from sandik.general.page import general_page_bp
from sandik.intro.page import intro_page_bp
from sandik.paw.api import paw_api_bp
from sandik.paw.page import paw_page_bp
from sandik.sandik.api import sandik_api_bp
from sandik.sandik.page import sandik_page_bp
from sandik.transaction.api import transaction_api_bp
from sandik.transaction.page import transaction_page_bp
from sandik.utils import CustomJSONEncoder, money, sandik_preferences, seo, set_parameters_of_url
from sandik.utils.db_models import MoneyTransaction, Installment, Contribution, SandikRule, RemainingMoneyPreference
from sandik.website_transaction.page import website_transaction_page_bp

os.environ["DATETIME_STR_FORMAT"] = "%Y-%m-%d %H:%M:%S.%f"
os.environ["RUN_TIME"] = datetime.now().strftime(os.getenv("DATETIME_STR_FORMAT"))


def initialize_flask() -> Flask:
    flask_app = Flask(
        __name__, instance_relative_config=True,
        template_folder='utils/templates', static_folder='utils/static', static_url_path='/assets'
    )
    flask_app.secret_key = os.getenv("SANDIKv2_SECRET_KEY")
    flask_app.config["SESSION_COOKIE_NAME"] = "session-sandikv2"
    flask_app.config["REMEMBER_COOKIE_NAME"] = "remember-sandikv2"
    # Oturum ve "beni hatırla" çerezleri javascript'e kapalı, başka sitelerden gelen POST'larda gönderilmez ve
    # (yerel geliştirme dışında) yalnızca HTTPS'te taşınır.
    secure_cookies = not os.getenv("FLASK_DEBUG")
    flask_app.config.update(
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_SECURE=secure_cookies,
        REMEMBER_COOKIE_HTTPONLY=True, REMEMBER_COOKIE_SAMESITE="Lax", REMEMBER_COOKIE_SECURE=secure_cookies,
    )
    # CSRF jetonu oturum boyunca geçerlidir (varsayılan 1 saatti): siteye çoğunlukla telefondan giriliyor ve sekme
    # saatlerce açık kalıyor; süre dolunca açık sayfadaki her düğme (çıkış dahil) 400 verirdi. Jeton yine oturuma
    # bağlıdır, oturum kapanınca geçersiz olur.
    flask_app.config["WTF_CSRF_TIME_LIMIT"] = None
    flask_app.json_encoder = CustomJSONEncoder
    return flask_app


def initialize_database(flask_app: Flask) -> Pony:
    return Pony(flask_app)


def initialize_csrf(flask_app: Flask) -> CSRFProtect:
    """Bütün POST/PUT/PATCH/DELETE istekleri CSRF jetonu ister (form alanı `csrf_token` ya da `X-CSRFToken`
    başlığı). Durum değiştiren her uç yalnızca POST kabul eder; jeton sayfalara `<meta name="csrf-token">` ile
    basılır, `custom.js` POST bağlantılarına ve jQuery AJAX isteklerine ekler (bkz. CLAUDE.md → "CSRF").

    **Pony'den (db_session) sonra kurulmalıdır**: jeton hatası `before_request`te fırlar; `db_session` açılmamışsa
    hata sayfası giriş yapmış kullanıcıyı yüklerken 400 yerine 500 verir. GET istekleri (ör. Cüzdan'ın
    `/api/borc-gecmisi`ye attığı istek) etkilenmez.
    """
    return CSRFProtect(flask_app)


def initialize_login_manager(flask_app: Flask) -> LoginManager:
    return setup_login_manager(flask_app, login_view="auth_page_bp.login_page")


def register_blueprints(flask_app: Flask) -> Flask:
    flask_app.register_blueprint(general_page_bp, url_prefix="/")
    flask_app.register_blueprint(general_api_bp, url_prefix="/api/")
    flask_app.register_blueprint(auth_page_bp, url_prefix="/")
    flask_app.register_blueprint(intro_page_bp, url_prefix="/")
    flask_app.register_blueprint(sandik_page_bp, url_prefix="/sandik/")
    flask_app.register_blueprint(sandik_api_bp, url_prefix="/api/sandik/")
    flask_app.register_blueprint(transaction_page_bp, url_prefix="/sandik/<int:sandik_id>/")
    flask_app.register_blueprint(transaction_api_bp, url_prefix="/api/sandik/<int:sandik_id>/")
    flask_app.register_blueprint(backup_page_bp, url_prefix="/yedek/")
    flask_app.register_blueprint(backup_dw_bp, url_prefix="/indir/yedek/")
    flask_app.register_blueprint(website_transaction_page_bp, url_prefix="/websitesi-masraflari/")
    flask_app.register_blueprint(paw_page_bp, url_prefix="/paw/")
    flask_app.register_blueprint(paw_api_bp, url_prefix="/api/paw/")
    return flask_app


def catch_exception(func, default_value, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except Exception as e:
        # flash(str(e), "danger") # BUG: Bir soraki sayfada gösteriliyor
        return default_value


# Bildirimlerde (flash) ve form hatalarında geri açılan etiketler; geri kalan her şey kaçırılır
_FLASH_TAGS = re.compile(r"&lt;(/?(?:b|i|br))&gt;")


def flash_message(message) -> Markup:
    """Bildirim metnini güvenle basar: tamamı HTML'e karşı kaçırılır, yalnızca `<b>`, `<i>` ve `<br>` geri
    açılır (myilmaz_tr deposundaki uygulamalardaki `flash_message` süzgeciyle aynı yaklaşım). Bildirimlerin
    içine üye/sandık adı, istisna mesajı gibi kullanıcı verisi girer; eskiden `|safe` ile basılıyordu.
    Bağlantı içeren bir bildirim gerekirse `Markup(...).format(...)` ile verilir, o olduğu gibi basılır."""
    if isinstance(message, Markup):
        return message
    return Markup(_FLASH_TAGS.sub(r"<\1>", str(escape(message))))


def js_html(value) -> Markup:
    """Değeri HTML'e karşı kaçırıp **JavaScript dizgisi** (JSON) olarak basar: `"ad": {{ x|js_html }},`.

    FooTable satırları şablonda JS nesnesi olarak üretilir ve hücre HTML olarak çizilir; değer hem JS hem HTML
    bağlamında güvenli olmalıdır. Eskiden ters tırnaklı (`...`) şablon dizgisi kullanılıyordu: Jinja'nın
    kaçırması ters tırnağı ve `${` ifadesini kaçırmaz, adı `${...}` olan bir kullanıcı sayfada kod çalıştırıyordu.
    Bilinçli HTML içeren hücre `{% set hucre %}...{% endset %}` ile kurulur (içindeki kullanıcı verisi otomatik
    kaçırılır, sonuç `Markup`tır ve bir daha kaçırılmaz) ve yine bu süzgeçle basılır."""
    # Ters tırnak da kaçırılır: değer yanlışlıkla bir şablon dizgisinin içine yazılsa bile dizgiyi kapatamasın
    return Markup(htmlsafe_json_dumps(str(escape(value))).replace("`", "\\u0060"))


def nl2br(value) -> Markup:
    """Çok satırlı kullanıcı metni (işlem açıklaması ...): satırlar kaçırılır, aralarına `<br>` konur.

    `{{ x|replace("\\n", "<br>")|safe }}` kalıbının yerine: o, metnin içindeki HTML'i hiç kaçırmıyordu. Kaçırılmış
    metin (`x|e|replace(...)`) de çözüm değildir: `Markup.replace` argümanları da kaçırır, `<br>` yazı olarak görünür."""
    if value is None:
        return Markup("")
    return Markup("<br>").join(str(value).splitlines())


def log_exception_detail(detail) -> Markup:
    """Seyir defterindeki hata kaydının "(ERRCODE: ... FUNCTION: ... EXCEPTION: ...)" kısmını okunur basar.
    Metin kaçırılır; yalnızca etiketler kalın yazılır ve alt satıra geçilir."""
    if not detail or "(ERRCODE" not in detail:
        return Markup("")
    text = escape("ERRCODE" + detail.split("(ERRCODE", 1)[1][:-1])
    return (text.replace("ERRCODE:", Markup("<strong>ERRCODE:</strong>"))
            .replace("FUNCTION:", Markup("<br><strong>FUNCTION:</strong>"))
            .replace("EXCEPTION:", Markup("<br><strong>EXCEPTION:</strong>")))


def jinja2_integration(flask_app: Flask) -> Flask:
    seo.register(flask_app)
    flask_app.jinja_env.filters.update(flash_message=flash_message, js_html=js_html, nl2br=nl2br,
                                       log_exception_detail=log_exception_detail)
    flask_app.jinja_env.globals.update(MoneyTransaction=MoneyTransaction)
    flask_app.jinja_env.globals.update(isinstance=isinstance)
    flask_app.jinja_env.globals.update(Installment=Installment)
    flask_app.jinja_env.globals.update(Contribution=Contribution)
    flask_app.jinja_env.globals.update(sandik_preferences=sandik_preferences)
    flask_app.jinja_env.globals.update(SandikRule=SandikRule)
    flask_app.jinja_env.globals.update(RemainingMoneyPreference=RemainingMoneyPreference)
    flask_app.jinja_env.globals.update(catch_exception=catch_exception)
    flask_app.jinja_env.globals.update(set_parameters_of_url=set_parameters_of_url)

    @flask_app.template_filter('tr_number_format')
    def tr_number_format(value):
        """Sayıyı Türkçe biçimde gösterir. Para birimi eklemez; tutarlar için `money` kullanın."""
        return money.format_number(value)

    @flask_app.template_filter('money')
    def money_filter(value, sandik=None):
        """Tutarı sandığın para birimiyle gösterir: `{{ x|money(g.sandik) }}` -> "1.500 ₺".

        `Sandik` nesnesi yerine para birimi kodu da verilebilir; e-posta şablonları gibi entity
        taşımayan verilerde bu gerekiyor. Hiçbiri verilmezse (sitenin kendi masrafları gibi
        sandığa bağlı olmayan tutarlar) varsayılan para birimi kullanılır.
        """
        currency = getattr(sandik, "currency", sandik)
        if currency is None:
            currency = money.Currency.DEFAULT
        return money.format_amount(value, currency=currency)

    return flask_app


def initialize_exceptions_handlers(flask_app: Flask) -> Flask:
    HTTP_ERRORS = {
        401: {"title": "Kimlik Doğrulama Başarısız",
              "msg": "Bu sayfaya erişebilmek için lütfen giriş yapınız.",
              "style": {"text-color": "#e53e3e", "btn-hover": "#c53030"}},
        403: {"title": "Yetkisiz Erişim",
              "msg": "Bu sayfaya erişim izniniz yok. Lütfen geri dönün veya yetkili kişiyle iletişime geçin.",
              "style": {"text-color": "#e53e3e", "btn-hover": "#c53030"}},
        404: {"title": "Sayfa Bulunamadı",
              "msg": "Üzgünüz, aradığınız sayfa mevcut değil veya kaldırılmış olabilir.",
              "style": {"text-color": "#3182ce", "btn-hover": "#2b6cb0"}},
    }

    @flask_app.errorhandler(HTTPException)
    def http_error_handler(e: HTTPException):

        # HTTP_ERRORS istekler arasında paylaşılır; kopyalanmadan üzerine yazılırsa bir isteğin
        # özel hata mesajı sonraki isteklerde de görünür.
        http_error: dict = dict(HTTP_ERRORS.get(e.code, {"style": {"text-color": "#3182ce", "btn-hover": "#2b6cb0"}}))
        http_error["code"] = e.code

        if not http_error.get("title"):
            http_error["title"] = e.name

        if not http_error.get("msg") or e.description != type(e).description:
            http_error["msg"] = e.description

        return render_template("utils/http_errors.html", http_error=http_error), e.code

    @flask_app.errorhandler(CSRFError)
    def csrf_error_handler(e: CSRFError):
        http_error = {
            "code": 400, "title": "İşlem Doğrulanamadı",
            "msg": "Güvenlik doğrulaması başarısız oldu; işlem yapılmadı. Sayfa uzun süre açık kaldıysa ya da "
                   "oturumunuz kapandıysa sayfayı yenileyip işlemi tekrar deneyiniz.",
            "style": {"text-color": "#e53e3e", "btn-hover": "#c53030"},
        }
        return render_template("utils/http_errors.html", http_error=http_error), 400

    return flask_app


def create_app() -> Flask:
    flask_app = initialize_flask()
    initialize_database(flask_app)
    initialize_csrf(flask_app)
    initialize_login_manager(flask_app)
    jinja2_integration(flask_app)
    initialize_exceptions_handlers(flask_app)
    register_blueprints(flask_app)
    return flask_app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
