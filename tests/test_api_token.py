"""Cüzdan bağlantısı: kişisel API anahtarı ve `/api/borc-gecmisi` (`general/api.py`).

Cüzdan uygulaması (myilmaz_tr deposundaki `cuzdan/`) sandık borcunu ve geçmişini bu uçtan okur. En önemli
kural: olayların toplamı bugünkü borçtur ve "Borç geçmişim" sayfasının bugünkü değeriyle (mil sonunun
tersi) aynıdır.
"""
from decimal import Decimal

from flask import Flask
from pony.flask import Pony
from pony.orm import db_session

from sandik.auth import utils as auth_utils
from sandik.general import utils as general_utils
from sandik.general.api import general_api_bp
from sandik.utils import period as period_utils

from tests import factories


def _setup_member_with_debt():
    wu = factories.make_web_user()
    sandik = factories.make_sandik(created_by=wu)
    share = factories.make_member_with_share(sandik=sandik, web_user=wu, created_by=wu)
    factories.pay_contribution_partially(share=share, term=period_utils.previous_period(), paid_amount=Decimal("130"),
                                         created_by=wu)
    factories.make_contribution(share=share, term=period_utils.current_period(), created_by=wu)
    factories.make_debt(share=share, amount=Decimal("600"), created_by=wu, number_of_installment=3)
    return wu, share.member_ref


@db_session
def test_token_is_verified_by_hash_and_can_be_revoked():
    wu = factories.make_web_user()
    other = factories.make_web_user()
    token = auth_utils.create_api_token(wu)

    assert token.startswith(f"{wu.id}.")
    # Anahtarın kendisi saklanmaz
    assert token not in str(wu.preferences)
    assert auth_utils.get_web_user_from_api_token(token) == wu
    assert auth_utils.api_token_created_at(wu)
    # Başka kullanıcının kimliğiyle ya da bozuk anahtarla olmaz
    assert auth_utils.get_web_user_from_api_token(f"{other.id}.{token.split('.', 1)[1]}") is None
    assert auth_utils.get_web_user_from_api_token(token + "x") is None
    assert auth_utils.get_web_user_from_api_token("") is None
    assert auth_utils.get_web_user_from_api_token("abc.def") is None

    # Yeni anahtar eskisini geçersiz kılar
    new_token = auth_utils.create_api_token(wu)
    assert auth_utils.get_web_user_from_api_token(token) is None
    assert auth_utils.get_web_user_from_api_token(new_token) == wu

    auth_utils.revoke_api_token(wu)
    assert auth_utils.get_web_user_from_api_token(new_token) is None
    assert auth_utils.api_token_created_at(wu) is None
    # Diğer tercihler korunur
    assert "reminder_month_start_day" in wu.preferences


@db_session
def test_debt_events_sum_to_the_debt_history_value_of_today():
    wu, member = _setup_member_with_debt()

    data = general_utils.get_debt_events(wu)
    history = general_utils.get_mile_end_history(
        wu, general_utils.parse_history_selection({"dilim": "ay", "aralik": "12ay"}))

    [row] = data["sandiks"]
    assert row["currency"] == "TRY"
    assert row["member_id"] == member.id
    expected = history["member_debts"][member.id][-1]
    assert Decimal(row["debt"]) == expected > 0
    assert sum(Decimal(value) for _, value in row["events"]) == expected
    # Günler artan sırada ve tekrarsız
    days = [day for day, _ in row["events"]]
    assert days == sorted(set(days))


def _api_client():
    app = Flask(__name__)
    app.secret_key = "test"
    Pony(app)
    app.register_blueprint(general_api_bp, url_prefix="/api/")
    return app.test_client()


def test_api_requires_a_valid_bearer_token():
    with db_session:
        wu, _ = _setup_member_with_debt()
        token = auth_utils.create_api_token(wu)

    client = _api_client()
    assert client.get("/api/borc-gecmisi").status_code == 401
    assert client.get("/api/borc-gecmisi", headers={"Authorization": "Bearer yanlis"}).status_code == 401

    response = client.get("/api/borc-gecmisi", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    body = response.get_json()
    assert body["result"] is True and body["version"] == 1
    assert len(body["sandiks"]) == 1 and Decimal(body["sandiks"][0]["debt"]) > 0
