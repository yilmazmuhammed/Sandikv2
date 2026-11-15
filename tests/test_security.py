"""Güvenlik incelemesinden (2026-11) kalan düzeltmelerin testleri.

- Şablonda kullanıcı verisi: FooTable satırları JS dizgisi olarak (`|js_html`) basılır; ters tırnaklı şablon dizgisi
  yoktur, `${...}` ve `</script>` içeren adlar kod çalıştırmaz ama metin olarak doğru görünür.
- Bildirimler (`flash_message`), çok satırlı açıklamalar (`nl2br`).
- CSRF: durum değiştiren uçlar yalnızca POST kabul eder; jetonsuz POST 400, jetonlu POST çalışır.
- Giriş denemesi sınırı, `next` ile açık yönlendirme, toplu atama (formda olmayan alanlar), çerez bayrakları.
"""
import json
import re
from decimal import Decimal

import pytest
from markupsafe import Markup
from pony.orm import db_session, flush

from sandik.app import create_app, flash_message, js_html, nl2br
from sandik.auth import login_limit
from sandik.auth import db as auth_db
from sandik.utils import safe_next_url
from sandik.utils.db_models import BankAccount, MoneyTransaction, SandikRule, WebUser

from tests import factories

BASE_URL = "https://localhost"
ADMIN_EMAIL = "yonetici@example.com"
PAYLOAD_JS = "${alert(`x`+document.domain)}"
PAYLOAD_SCRIPT = "</script><script>alert(1)</script>"


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("SANDIKv2_ADMIN_EMAIL_ADDRESS", ADMIN_EMAIL)
    flask_app = create_app()
    flask_app.config.update(TESTING=True, SECRET_KEY="test")
    flask_app.secret_key = "test"
    login_limit.reset()
    return flask_app


def _client(app, web_user_id=None):
    client = app.test_client()
    if web_user_id is not None:
        with client.session_transaction(base_url=BASE_URL) as session:
            session["_user_id"] = str(web_user_id)
            session["_fresh"] = True
    return client


def _csrf_token(client):
    """Oturumdaki jeton: sayfanın `<meta name="csrf-token">`ından okunur"""
    page = client.get("/banka-hesaplarim", base_url=BASE_URL).get_data(as_text=True)
    return re.search(r'<meta name="csrf-token" content="([^"]+)"', page).group(1)


def _post(client, url, token=None, data=None, **kwargs):
    data = dict(data or {})
    if token:
        data["csrf_token"] = token
    # HTTPS'te Flask-WTF aynı siteden gelen bir Referer ister
    return client.post(url, data=data, base_url=BASE_URL, headers={"Referer": f"{BASE_URL}/ana-sayfa"}, **kwargs)


def _setup_sandik_with_payload_member():
    """Yönetici (sandığın kurucusu), adı XSS yükü olan bir üye, HTML'li açıklamalı bir para girişi"""
    with db_session:
        admin = factories.make_web_user(email_address=ADMIN_EMAIL, name="Site", surname="Yöneticisi")
        manager = factories.make_web_user(name="Sandık", surname="Yöneticisi")
        sandik = factories.make_sandik(created_by=manager, name=PAYLOAD_SCRIPT)
        evil = factories.make_web_user(name=PAYLOAD_JS, surname=PAYLOAD_SCRIPT)
        applicant = factories.make_web_user(name=PAYLOAD_JS, surname="Başvuran")
        sandik.applicant_web_users_set.add(applicant)
        share = factories.make_member_with_share(sandik=sandik, web_user=evil, created_by=manager)
        member_share = factories.make_member_with_share(sandik=sandik, web_user=manager, created_by=manager)
        factories.make_money_transaction(member=share.member_ref, amount=Decimal("100"), created_by=manager,
                                         detail="<img src=x onerror=alert(1)>\nikinci satır")
        rule = factories.make_sandik_rule(sandik=sandik, created_by=manager, type=SandikRule.TYPE.MAX_NUMBER_OF_SHARE,
                                          value_formula="5", order=1)
        factories.make_sandik_rule(sandik=sandik, created_by=manager, type=SandikRule.TYPE.MAX_NUMBER_OF_SHARE,
                                   value_formula="7", order=2)
        flush()
        return dict(admin=admin.id, manager=manager.id, sandik=sandik.id, evil=evil.id, applicant=applicant.id,
                    member=share.member_ref.id, manager_member=member_share.member_ref.id, rule=rule.id)


def _assert_no_executable_payload(html):
    # Ters tırnaklı şablon dizgisi kalmadı; yükün ham hâli HTML'de çalışır biçimde yok
    assert "`${alert" not in html
    assert "<script>alert" not in html
    assert not re.search(r":\s*`[^`]*\{\{", html)


def _js_cells(html, key):
    """`"anahtar": "<JSON dizgisi>"` hücrelerinin çözülmüş değerleri"""
    return [json.loads(m) for m in re.findall(r'"%s":\s*("(?:[^"\\]|\\.)*")' % key, html)]


# --------------------------------------------------------------------------------------------------
# Şablon süzgeçleri
# --------------------------------------------------------------------------------------------------

def test_js_html_escapes_for_both_html_and_js():
    out = js_html(PAYLOAD_JS + PAYLOAD_SCRIPT)
    assert "`" not in out and "<" not in out and out.startswith('"')
    assert json.loads(out) == "${alert(`x`+document.domain)}&lt;/script&gt;&lt;script&gt;alert(1)&lt;/script&gt;"
    # Bilinçli HTML (Markup) bir daha kaçırılmaz
    assert json.loads(js_html(Markup("<span title='a'>1</span>"))) == "<span title='a'>1</span>"


def test_nl2br_escapes_lines_and_keeps_line_breaks():
    assert nl2br("<b>a</b>\nb\r\nc") == "&lt;b&gt;a&lt;/b&gt;<br>b<br>c"
    assert nl2br(None) == ""


def test_flash_message_reopens_only_simple_tags():
    assert flash_message("Üye: <script>x</script><br><b>kalın</b>") == \
        "Üye: &lt;script&gt;x&lt;/script&gt;<br><b>kalın</b>"
    assert flash_message('<a href="x">') == "&lt;a href=&#34;x&#34;&gt;"


# --------------------------------------------------------------------------------------------------
# Sayfalarda kullanıcı verisi
# --------------------------------------------------------------------------------------------------

def test_web_users_page_shows_payload_as_text(app):
    ids = _setup_sandik_with_payload_member()
    html = _client(app, ids["admin"]).get("/kullanicilar", base_url=BASE_URL).get_data(as_text=True)
    _assert_no_executable_payload(html)
    names = _js_cells(html, "name_surname")
    assert f"{PAYLOAD_JS} &lt;/script&gt;&lt;script&gt;alert(1)&lt;/script&gt;" in names


@pytest.mark.parametrize("path", [
    "/sandik/{sandik}/uyeler", "/sandik/{sandik}/uyeler-detayli", "/sandik/{sandik}/uyelik-basvurulari",
    "/sandik/{sandik}/detay", "/sandik/{sandik}/yetkili-kullanicilar", "/sandik/{sandik}/sandik-yetkileri",
    "/sandik/{sandik}/uye-{member}/ozet", "/sandik/{sandik}/s-para-giris-cikislari", "/sandik/{sandik}/s-odemeler",
    "/sandik/{sandik}/s-borclar", "/sandik/{sandik}/s-sandik-islemleri", "/sandik/{sandik}/sandik-kurallari",
])
def test_sandik_pages_show_payload_as_text(app, path):
    ids = _setup_sandik_with_payload_member()
    response = _client(app, ids["manager"]).get(path.format(**ids), base_url=BASE_URL)
    assert response.status_code == 200, response.get_data(as_text=True)[:1000]
    html = response.get_data(as_text=True)
    _assert_no_executable_payload(html)
    # Yük sayfada metin olarak (kaçırılmış) duruyor: sandığın adı her sayfada, üye adı listelerde
    assert "&lt;/script&gt;&lt;script&gt;alert(1)" in html


def test_money_transaction_detail_is_escaped_and_line_breaks_work(app):
    ids = _setup_sandik_with_payload_member()
    html = _client(app, ids["manager"]).get(f"/sandik/{ids['sandik']}/s-para-giris-cikislari",
                                            base_url=BASE_URL).get_data(as_text=True)
    _assert_no_executable_payload(html)
    assert "&lt;img src=x onerror=alert(1)&gt;<br>ikinci satır" in _js_cells(html, "detail")
    assert "<img src=x" not in html


def test_logs_page_renders_for_admin(app):
    ids = _setup_sandik_with_payload_member()
    response = _client(app, ids["admin"]).get("/seyir-defteri", base_url=BASE_URL)
    assert response.status_code == 200
    _assert_no_executable_payload(response.get_data(as_text=True))


def test_flashed_user_data_is_escaped(app):
    ids = _setup_sandik_with_payload_member()
    client = _client(app, ids["manager"])
    with client.session_transaction(base_url=BASE_URL) as session:
        session["_flashes"] = [("danger", "Üye: <script>alert(1)</script><br>ikinci")]
    html = client.get("/banka-hesaplarim", base_url=BASE_URL).get_data(as_text=True)
    assert "<script>alert(1)" not in html
    assert "Üye: &lt;script&gt;alert(1)&lt;/script&gt;<br>ikinci" in html


def test_register_notification_title_is_escaped_in_menu(app):
    ids = _setup_sandik_with_payload_member()
    with db_session:
        from sandik.auth.utils import Notification
        Notification.WebUserAuth.send_register_web_user_notification(registered_web_user=WebUser[ids["evil"]])
    html = _client(app, ids["admin"]).get("/bildirimler", base_url=BASE_URL).get_data(as_text=True)
    assert "<script>alert(1)" not in html
    assert "&lt;/script&gt;&lt;script&gt;alert(1)" in html


# --------------------------------------------------------------------------------------------------
# CSRF ve POST
# --------------------------------------------------------------------------------------------------

STATE_CHANGING_URLS = [
    "/cikis", "/kullanici/{evil}/onayla", "/kullanici/{evil}/engelle", "/banka-hesaplarim/1/sil", "/bildirim/1",
    "/sandik/{sandik}/u-{member}/gb-gonder", "/sandik/{sandik}/gb-1/onayla", "/sandik/{sandik}/gb-1/kaldir",
    "/sandik/{sandik}/basvuru-onayla/{applicant}", "/sandik/{sandik}/basvuru-reddet/{applicant}",
    "/sandik/{sandik}/uye-{member}/sil", "/sandik/{sandik}/uye-{member}/hisse-1/sil",
    "/sandik/{sandik}/sandik-yetkileri/1/sil", "/sandik/{sandik}/sandik-yetkilileri/{manager}/kaldir",
    "/sandik/{sandik}/sk-{rule}/yukari-tasi", "/sandik/{sandik}/sk-{rule}/asagi-tasi", "/sandik/{sandik}/sk-{rule}/sil",
    "/sandik/{sandik}/mt-1/sil", "/sandik/{sandik}/c-1/sil",
    "/sandik/{sandik}/butun-uyeler-icin-vadesi-gelmis-aidatlari-olustur",
    "/sandik/{sandik}/u-odemeleri-yenile", "/sandik/{sandik}/s-odemeleri-yenile?pay_future_payments=1",
    "/sandik/{sandik}/uye-{member}/odemeleri-yenile", "/websitesi-masraflari/wt-1/sil",
]


@pytest.mark.parametrize("url", STATE_CHANGING_URLS)
def test_state_changing_urls_reject_get(app, url):
    ids = _setup_sandik_with_payload_member()
    response = _client(app, ids["admin"]).get(url.format(**ids), base_url=BASE_URL)
    assert response.status_code == 405


@pytest.mark.parametrize("url", STATE_CHANGING_URLS)
def test_state_changing_urls_reject_post_without_token(app, url):
    ids = _setup_sandik_with_payload_member()
    response = _post(_client(app, ids["admin"]), url.format(**ids))
    assert response.status_code == 400
    assert "Güvenlik doğrulaması başarısız" in response.get_data(as_text=True)


def test_rule_move_and_delete_work_with_token(app):
    ids = _setup_sandik_with_payload_member()
    client = _client(app, ids["manager"])
    token = _csrf_token(client)

    response = _post(client, f"/sandik/{ids['sandik']}/sk-{ids['rule']}/asagi-tasi", token=token)
    assert response.status_code == 302
    with db_session:
        assert SandikRule[ids["rule"]].order == 2

    response = _post(client, f"/sandik/{ids['sandik']}/sk-{ids['rule']}/sil", token=token)
    assert response.status_code == 302
    with db_session:
        assert not SandikRule.exists(id=ids["rule"])


def test_redirect_after_post_ignores_foreign_referrer(app):
    ids = _setup_sandik_with_payload_member()
    client = _client(app, ids["manager"])
    token = _csrf_token(client)
    # Referer başka bir siteyse CSRF zaten reddeder; aynı sitedeyse oraya dönülür
    response = client.post(f"/sandik/{ids['sandik']}/sk-{ids['rule']}/yukari-tasi", data={"csrf_token": token},
                           base_url=BASE_URL, headers={"Referer": "https://evil.example/x"})
    assert response.status_code == 400
    response = _post(client, f"/sandik/{ids['sandik']}/sk-{ids['rule']}/yukari-tasi", token=token)
    assert response.headers["Location"].endswith("/ana-sayfa")


def test_membership_application_confirm_with_token(app):
    ids = _setup_sandik_with_payload_member()
    client = _client(app, ids["manager"])
    response = _post(client, f"/sandik/{ids['sandik']}/basvuru-onayla/{ids['applicant']}", token=_csrf_token(client))
    assert response.status_code == 302
    with db_session:
        from sandik.utils.db_models import Member
        assert Member.exists(web_user_ref=WebUser[ids["applicant"]])


def test_bank_account_delete_with_token(app):
    ids = _setup_sandik_with_payload_member()
    with db_session:
        account = auth_db.WebUser[ids["manager"]]
        ba = BankAccount(web_user_ref=account, title="t", holder="h", iban="1" * 24, is_primary=True)
        flush()
        ba_id = ba.id
    client = _client(app, ids["manager"])
    assert _post(client, f"/banka-hesaplarim/{ba_id}/sil", token=_csrf_token(client)).status_code == 302
    with db_session:
        assert not BankAccount.exists(id=ba_id)


def test_debt_events_api_get_is_not_affected_by_csrf(app):
    ids = _setup_sandik_with_payload_member()
    with db_session:
        from sandik.auth import utils as auth_utils
        token = auth_utils.create_api_token(WebUser[ids["manager"]])
    response = app.test_client().get("/api/borc-gecmisi", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.get_json()["result"] is True
    assert "Set-Cookie" not in response.headers


def test_pages_carry_csrf_meta_and_forms_carry_token(app):
    ids = _setup_sandik_with_payload_member()
    client = _client(app, ids["manager"])
    html = client.get(f"/sandik/{ids['sandik']}/sandik-kurallari", base_url=BASE_URL).get_data(as_text=True)
    assert '<meta name="csrf-token"' in html
    assert 'data-method="post"' in html
    login = app.test_client().get("/giris", base_url=BASE_URL).get_data(as_text=True)
    assert 'name="csrf_token"' in login


# --------------------------------------------------------------------------------------------------
# Giriş, yönlendirme, toplu atama, çerezler
# --------------------------------------------------------------------------------------------------

def _make_login_user(password="dogru-parola"):
    from passlib.hash import pbkdf2_sha256 as hasher
    with db_session:
        wu = factories.make_web_user(password_hash=hasher.hash(password))
        flush()
        return wu.id, wu.email_address


def _login(client, email, password, query=""):
    client.get("/giris", base_url=BASE_URL)
    with client.session_transaction(base_url=BASE_URL) as session:
        session.pop("_flashes", None)
    from flask_wtf.csrf import generate_csrf
    page = client.get("/giris", base_url=BASE_URL).get_data(as_text=True)
    token = re.search(r'name="csrf_token" type="hidden" value="([^"]+)"', page).group(1)
    return client.post("/giris" + query, data={"email_address": email, "password": password, "remember_me": "y",
                                              "csrf_token": token},
                       base_url=BASE_URL, headers={"Referer": f"{BASE_URL}/giris"})


def test_login_is_locked_after_too_many_failures_without_revealing_account(app):
    _, email = _make_login_user()
    client = app.test_client()
    for _ in range(login_limit.MAX_FAILED_PER_ADDRESS):
        assert "doğru değil" in _login(client, email, "yanlis").get_data(as_text=True)
    # Kilitliyken doğru parola da reddedilir
    locked = _login(client, email, "dogru-parola")
    assert locked.status_code == 200
    assert "Çok fazla hatalı giriş" in locked.get_data(as_text=True)
    # Kayıtlı olmayan adres de aynı mesajı alır
    for _ in range(login_limit.MAX_FAILED_PER_ADDRESS):
        _login(app.test_client(), "yok@example.com", "x")
    assert "Çok fazla hatalı giriş" in _login(app.test_client(), "yok@example.com", "x").get_data(as_text=True)


def test_login_ignores_foreign_next_and_sets_secure_cookies(app):
    _, email = _make_login_user()
    client = app.test_client()
    response = _login(client, email, "dogru-parola", query="?next=//evil.com/x")
    assert response.status_code == 302
    assert "evil.com" not in response.headers["Location"]
    cookies = response.headers.getlist("Set-Cookie")
    for name in ("session-sandikv2", "remember-sandikv2"):
        cookie = next(c for c in cookies if c.startswith(name + "="))
        assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=Lax" in cookie


def test_safe_next_url():
    for bad in ["//evil.com", "https://evil.com", "/\\evil.com", "/\t/evil.com", "javascript:alert(1)", ""]:
        assert safe_next_url(bad, "/varsayilan") == "/varsayilan"
    assert safe_next_url("/sandikv2/ana-sayfa?x=1", "/v") == "/sandikv2/ana-sayfa?x=1"


def test_register_ignores_fields_not_in_form(app):
    client = app.test_client()
    page = client.get("/kayit", base_url=BASE_URL).get_data(as_text=True)
    token = re.search(r'name="csrf_token" type="hidden" value="([^"]+)"', page).group(1)
    response = client.post("/kayit", data={
        "csrf_token": token, "name": "Yeni", "surname": "Üye", "email_address": "yeni@example.com",
        "password": "parola12", "password_verification": "parola12",
        "password_hash": "elle-yazilmis", "preferences": '{"api_token_hash": "x"}', "is_active_": "",
    }, base_url=BASE_URL, headers={"Referer": f"{BASE_URL}/kayit"})
    assert response.status_code == 302, response.get_data(as_text=True)[:2000]
    with db_session:
        wu = WebUser.get(email_address="yeni@example.com")
        assert wu.password_hash != "elle-yazilmis"
        assert "api_token_hash" not in (wu.preferences or {})


def test_bank_account_update_cannot_move_account(app):
    ids = _setup_sandik_with_payload_member()
    with db_session:
        ba = BankAccount(web_user_ref=WebUser[ids["manager"]], title="t", holder="h", iban="1" * 24, is_primary=True)
        flush()
        ba_id = ba.id
    client = _client(app, ids["manager"])
    response = _post(client, f"/banka-hesabi/{ba_id}/duzenle", token=_csrf_token(client), data={
        "title": "yeni", "holder": "h", "iban": "1" * 24, "is_primary": "y", "web_user_ref": str(ids["evil"]),
    })
    assert response.status_code in (200, 302)
    with db_session:
        assert BankAccount[ba_id].web_user_ref.id == ids["manager"]


def test_reminder_preference_by_token_page_works_with_csrf(app):
    """Jetonlu `/tercih/<token>` sayfası giriş gerektirmez (tanıtım kabuğu); formu CSRF jetonuyla gönderilir"""
    ids = _setup_sandik_with_payload_member()
    with app.test_request_context(), db_session:
        from sandik.auth import utils as auth_utils
        token = auth_utils.create_reminder_preference_token(WebUser[ids["manager"]])
    client = app.test_client()
    page = client.get(f"/tercih/{token}", base_url=BASE_URL).get_data(as_text=True)
    csrf = re.search(r'name="csrf_token" type="hidden" value="([^"]+)"', page).group(1)
    assert _post(client, f"/tercih/{token}", data={"month_start_day": "5"}).status_code == 400
    response = _post(client, f"/tercih/{token}", token=csrf, data={"month_start_day": "5"})
    assert response.status_code == 200
    assert "kaydedildi" in response.get_data(as_text=True)
    with db_session:
        assert WebUser[ids["manager"]].get_reminder_days()[0] == 0
