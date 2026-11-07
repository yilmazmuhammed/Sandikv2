"""Parola sıfırlama (ortak modül `auth/password_reset.py`; myilmaz_tr deposundaki beş uygulamada birebir aynı).

Sayfaların kendisi myilmaz_tr deposundaki uygulamaların testlerinde sınanır; burada modülün Sandıkv2'nin kullanıcı
modeli ve `db.password_reset` ile birlikte çalıştığı sınanır.
"""
import re

import pytest
from passlib.hash import pbkdf2_sha256
from pony.orm import db_session, flush

from sandik.auth import db as auth_db
from sandik.auth import password_reset

from tests import factories

SECRET = "test-secret"


@pytest.fixture(autouse=True)
def _limits():
    password_reset.reset_limits()


def _request(email, sent, ip="1.1.1.1"):
    password_reset.request_reset(
        email, ip=ip, secret_key=SECRET, find_user=lambda address: auth_db.get_web_user(email_address=address),
        send_email=lambda to, subject, html: sent.append((to, subject, html)),
        make_url=lambda token: f"https://www.myilmaz.tr/sandikv2/parola-sifirla/{token}")


@db_session
def test_link_works_once_and_does_not_carry_the_password_hash():
    wu = factories.make_web_user(email_address="ali@example.com", password_hash=pbkdf2_sha256.hash("eski1234"),
                                 name="<b>Ali</b>")
    flush()
    sent = []
    _request("ali@example.com", sent)
    [(to, subject, html)] = sent
    assert to == "ali@example.com" and subject == "Sandıkv2 — parola sıfırlama"
    assert "&lt;b&gt;Ali" in html
    token = re.search(r"parola-sifirla/([^\"<\s]+)", html).group(1)
    assert wu.password_hash not in token

    assert password_reset.read_token(token, SECRET, get_user=lambda i: auth_db.get_web_user(id=i)) == wu
    auth_db.password_reset(web_user=wu, new_password="yeni12345")
    with pytest.raises(password_reset.ResetError) as error:
        password_reset.read_token(token, SECRET, get_user=lambda i: auth_db.get_web_user(id=i))
    assert str(error.value) == password_reset.USED


@db_session
def test_unknown_address_sends_nothing_and_requests_are_limited():
    factories.make_web_user(email_address="can@example.com")
    sent = []
    _request("yok@example.com", sent)
    assert sent == []
    for _ in range(password_reset.MAX_REQUESTS_PER_IP - 1):
        _request("can@example.com", sent)
    assert len(sent) == password_reset.MAX_EMAILS_PER_ADDRESS
    with pytest.raises(password_reset.ResetError):
        _request("can@example.com", sent)


def test_tampered_token_is_rejected():
    with pytest.raises(password_reset.ResetError) as error:
        password_reset.read_token("bozuk.jeton", SECRET, get_user=lambda i: None)
    assert str(error.value) == password_reset.INVALID
