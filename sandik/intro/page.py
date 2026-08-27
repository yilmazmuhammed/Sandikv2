from flask import Blueprint, g, render_template, request
from flask_login import current_user

from sandik.intro import utils
from sandik.utils import LayoutPI

intro_page_bp = Blueprint(
    'intro_page_bp', __name__,
    template_folder='templates', static_folder='static', static_url_path='assets'
)


@intro_page_bp.route("/tanitim")
def about_page():
    return render_template("intro/about_page.html", page_info=LayoutPI(title="Sandık nedir?"))


@intro_page_bp.route("/nasil-kullanilir")
def how_to_use_page():
    return render_template("intro/how_to_use_page.html", page_info=LayoutPI(title="Nasıl kullanılır?"))


@intro_page_bp.route("/istatistikler")
def statistics_page():
    # İstatistikler önbelleğe alınır; site yöneticisi "?yenile=1" ile güncel veriyi görebilir.
    use_cache = not (request.args.get("yenile") and current_user.is_authenticated and current_user.is_admin())
    g.statistics = utils.get_statistics(use_cache=use_cache)
    return render_template("intro/statistics_page.html", page_info=LayoutPI(title="İstatistikler"))
