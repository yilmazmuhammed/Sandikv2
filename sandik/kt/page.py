import os

from flask import Blueprint, redirect, url_for, request, g, abort, session

from sandik.kt.requirement import kt_login_required
from sandik.bot.kt_api import KtApi, KtApiAppType

kt_page_bp = Blueprint(
    'kt_page_bp', __name__,
    template_folder='templates', static_folder='static', static_url_path='assets'
)


@kt_page_bp.route('/giris')
def login_page():
    if os.getenv("FLASK_DEBUG"):
        app_type = KtApiAppType.PREP
    else:
        app_type = KtApiAppType.PROD

    scope = "loans payments digital_payments donations accounts cards transfers public crm api"
    kt_api = KtApi(
        client_id=os.getenv('SANDIKv2_KT_CLIENT_ID'),
        client_secret=os.getenv('SANDIKv2_KT_CLIENT_SECRET'),
        environment=KtApiAppType.PREP,
        redirect_uri=url_for("kt_page_bp.callback_page", _external=True),
        scope=scope,
        private_key_file="Sandikv2/sandik/bot/kt_api/a.txt"
    )

    kt_url = kt_api.get_authorization_url()
    print(kt_url)
    return redirect(kt_url)


@kt_page_bp.route('/callback')
def callback_page():
    auth_code = request.args.get('code')
    g.scope = request.args.get('scope')
    g.state = request.args.get('state')

    if not auth_code:
        abort(400, "Hata: Yetkilendirme kodu alınamadı!")

    session["kt_auth_code"] = auth_code

    print("scope:", g.scope)
    print("state:", g.state)

    return redirect(url_for("kt_page_bp.auth_code_test_page"))


@kt_page_bp.route('/auth_code_test_page')
@kt_login_required
def auth_code_test_page():
    return f"Yetkilendirme kodunuz: {g.kt_auth_code}"
