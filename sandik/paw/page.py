from flask import Blueprint, request, render_template, g

from sandik.auth.requirement import admin_required
from sandik.utils import LayoutPI

paw_page_bp = Blueprint(
    'paw_page_bp', __name__,
    template_folder='templates', static_folder='static', static_url_path='assets'
)


@paw_page_bp.route("/kaynak-kodu-ve-web-uygulamasi")
@admin_required
def source_code_and_webapp_page():
    return render_template("paw/source_code_and_webapp_page.html",
                           page_info=LayoutPI(title="Kaynak kodu ve web uygulaması", active_dropdown="developer"))