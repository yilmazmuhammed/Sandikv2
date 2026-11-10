"""
Ana ekrana eklenen web uygulamasının tanımı (`/manifest.webmanifest`).

Sınır (`scope`) uygulamanın kökü olmalıdır: tanım yokken iPhone sınırı simgenin eklendiği sayfanın klasöründen
tahmin ediyor, alt sayfadan eklenen simgede diğer sayfalarda üstte X'li bir "uygulama dışı" çubuğu açıyordu.
"""
from flask import Flask

from sandik.intro.page import intro_page_bp


def _client():
    app = Flask(__name__, static_folder="../sandik/utils/static", static_url_path="/assets")
    app.register_blueprint(intro_page_bp, url_prefix="/")  # sandik/app.py ile aynı
    app.add_url_rule("/", endpoint="general_page_bp.index_page", view_func=lambda: "")
    return app.test_client()


def test_scope_is_the_mount_point():
    response = _client().get("/manifest.webmanifest", environ_overrides={"SCRIPT_NAME": "/sandikv2"})
    assert response.status_code == 200
    assert response.mimetype == "application/manifest+json"
    manifest = response.get_json(force=True)
    assert manifest["scope"] == manifest["start_url"] == manifest["id"] == "/sandikv2/"
    assert manifest["display"] == "standalone"
    assert manifest["icons"][0]["src"] == "/sandikv2/assets/my_custom/img/apple-touch-icon.png"


def test_scope_is_the_root_on_its_own_domain():
    manifest = _client().get("/manifest.webmanifest").get_json(force=True)
    assert manifest["scope"] == manifest["start_url"] == "/"
