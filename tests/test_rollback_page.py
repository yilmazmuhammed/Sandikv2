"""Hata sonrası `rollback()` yapan form sayfaları sayfayı yine de çizebilmeli.

Pony'de `rollback()` o ana kadar yüklenen nesnelerin önbelleğini kapatır: `g.sandik`, `g.member` ve
`current_user` artık "eski oturumun" nesneleridir ve yüklenmemiş bir alanı okunduğunda
`DatabaseSessionIsOver` fırlar. Sunucu günlüğündeki hata (2026-09): `POST /sandik/10/islem-ekle`
bir hatayla `rollback()` yapınca sol menü `g.sandik.applicant_web_users_set`i okurken 500 verdi.
"""
from decimal import Decimal

import pytest
from pony.orm import db_session, flush

from sandik.app import create_app
from sandik.transaction import utils as transaction_utils
from sandik.transaction.exceptions import TransactionException
from sandik.utils.db_models import MoneyTransaction

from tests import factories


@pytest.fixture
def app():
    flask_app = create_app()
    flask_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, SECRET_KEY="test")
    flask_app.secret_key = "test"
    return flask_app


def _setup():
    with db_session:
        manager = factories.make_web_user()
        sandik = factories.make_sandik(created_by=manager)
        share = factories.make_member_with_share(sandik=sandik, web_user=manager, created_by=manager)
        flush()
        return manager.id, sandik.id, share.member_ref.id


def test_money_transaction_page_renders_after_rollback(app, monkeypatch):
    manager_id, sandik_id, member_id = _setup()

    def failing_add(**kwargs):
        # Yazma yarıda kalmış gibi: bir şey yazılır, sonra hata fırlar ve sayfa rollback() yapar.
        factories.make_web_user()
        raise TransactionException("İşlem yapılamadı: deneme hatası")

    monkeypatch.setattr(transaction_utils, "add_money_transaction", failing_add)

    client = app.test_client()
    with client.session_transaction() as session:
        session["_user_id"] = str(manager_id)
        session["_fresh"] = True

    response = client.post(f"/sandik/{sandik_id}/islem-ekle", data={
        "member": str(member_id), "date": "2026-09-01", "type": str(MoneyTransaction.TYPE.REVENUE),
        "amount": "100", "use_untreated_amount": "", "pay_future_payments": "", "detail": "",
    })

    assert response.status_code == 200, response.data[:500]
    assert "İşlem yapılamadı: deneme hatası" in response.get_data(as_text=True)
    # Geri alınan yazma veritabanında kalmadı
    with db_session:
        from sandik.utils.db_models import WebUser
        assert WebUser.select().count() == 1
