from flask import Blueprint, Response, g, render_template, request
from flask_login import current_user

from sandik.intro import utils
from sandik.utils import LayoutPI

intro_page_bp = Blueprint(
    'intro_page_bp', __name__,
    template_folder='templates', static_folder='static', static_url_path='assets'
)


@intro_page_bp.route("/tanitim")
def about_page():
    return render_template("intro/about_page.html",
                           structured_data=utils.about_structured_data(),
                           page_info=LayoutPI(title="Sandık nedir?"))


@intro_page_bp.route("/nasil-kullanilir")
def how_to_use_page():
    return render_template("intro/how_to_use_page.html", faq=utils.FAQ,
                           faq_structured_data=utils.faq_for_structured_data(),
                           page_info=LayoutPI(title="Nasıl kullanılır?"))


@intro_page_bp.route("/istatistikler")
def statistics_page():
    # İstatistikler önbelleğe alınır; site yöneticisi "?yenile=1" ile güncel veriyi görebilir.
    use_cache = not (request.args.get("yenile") and current_user.is_authenticated and current_user.is_admin())
    g.statistics = utils.get_statistics(use_cache=use_cache)
    # Giriş yapmış kullanıcı, açılır listeden kendi sandıklarından birini seçip onun rakamlarını
    # görebilir. Kişiye özel olduğu için yukarıdaki önbelleğe konmaz; seçim yoksa hesaplama da
    # yapılmaz ve sayfa eskisiyle aynı kalır.
    g.sandik_selection = utils.get_sandik_selection(
        web_user=current_user, sandik_id=request.args.get("sandik", type=int)
    ) if current_user.is_authenticated else None
    return render_template("intro/statistics_page.html", page_info=LayoutPI(title="İstatistikler"))


# --------------------------------------------------------------------------------------
# Arama motoru dosyaları
# --------------------------------------------------------------------------------------
# Bu iki adres yalnızca uygulama **kendi alan adının kökünde** çalışırken (ör.
# `sandikv2.myilmaz.tr`) tarayıcı botları tarafından okunur. Mount noktasında çalışırken
# (`www.myilmaz.tr/sandikv2`) kökteki robots.txt ana sitenindir; oradaki dosya bu sitemap'e
# `Sitemap:` satırıyla işaret eder.

@intro_page_bp.route("/robots.txt")
def robots_txt():
    return Response(utils.robots_txt(), mimetype="text/plain; charset=utf-8")


@intro_page_bp.route("/sitemap.xml")
def sitemap_xml():
    return Response(utils.sitemap_xml(), mimetype="application/xml")
