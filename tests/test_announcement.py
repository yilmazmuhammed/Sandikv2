"""`sandik/utils/announcement.py` için testler: yeni özellik duyuruları (kişi başına bir kez)."""
import os
from datetime import date, timedelta
from decimal import Decimal

import pytest
from pony.orm import db_session, flush

from sandik.auth import db as auth_db
from sandik.utils import announcement
from sandik.utils.db_models import WebUser

from tests import factories

TEMPLATES = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sandik", "utils", "templates")

DUYURU = announcement.Announcement(key="deneme_duyurusu", subject="Yeni özellik", audience="isleyen_sandik_yoneticileri",
                                   last_day=date(2026, 12, 31))


class Recorder:
    def __init__(self, fail_for=None):
        self.sent = []
        self.fail_for = fail_for or set()

    def __call__(self, to_address, subject, html):
        if to_address in self.fail_for:
            raise RuntimeError("smtp patladı")
        self.sent.append({"to": to_address, "subject": subject, "html": html})


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("SANDIKv2_REMINDER_EMAIL_SLEEP_SECONDS", "0")
    monkeypatch.delenv("SANDIKv2_REMINDER_EMAIL_TEST_ADDRESS", raising=False)


def run(item=DUYURU, send=None):
    send = send if send is not None else Recorder()
    result = announcement.run_announcement(item, render=lambda data, template: template, send=send,
                                           log=lambda *a: None)
    return result, send


def _running_sandik(manager):
    """İstatistiklerin "işleyen sandık" ölçütünü geçen sandık: 3 aktif üye, 20 para hareketi, bugün."""
    sandik = factories.make_sandik(created_by=manager)
    members = [factories.make_member(sandik=sandik, created_by=manager) for _ in range(3)]
    for i in range(20):
        factories.make_money_transaction(member=members[i % 3], amount=Decimal("10"), created_by=manager)
    flush()
    return sandik


@db_session
def _setup():
    manager = factories.make_web_user(name="Gerçek", surname="Yönetici")
    _running_sandik(manager)
    trial_manager = factories.make_web_user(name="Deneme", surname="Yönetici")
    factories.make_sandik(created_by=trial_manager, name="deneme")  # hiç kullanılmamış
    flush()
    return manager.email_address, trial_manager.email_address


def test_goes_only_to_managers_of_running_sandiks_and_only_once():
    manager_email, _ = _setup()

    result, recorder = run()
    assert [m["to"] for m in recorder.sent] == [manager_email]
    assert recorder.sent[0]["subject"] == "Yeni özellik"
    assert recorder.sent[0]["html"] == "email/duyurular/deneme_duyurusu.html"

    with db_session:
        assert announcement.was_sent(WebUser.get(email_address=manager_email), "deneme_duyurusu")
    assert run()[0]["recipients"] == 0

    # Başka bir duyuru aynı kişiye ayrıca gider; işaretler birbirini ezmez.
    other = announcement.Announcement(key="baska", subject="X", audience="isleyen_sandik_yoneticileri",
                                      last_day=DUYURU.last_day)
    assert run(other)[0]["sent"] == 1
    with db_session:
        assert announcement.was_sent(WebUser.get(email_address=manager_email), "deneme_duyurusu")


def test_members_audience():
    _setup()
    members = announcement.Announcement(key="uyelere", subject="X", audience="isleyen_sandik_uyeleri",
                                        last_day=DUYURU.last_day)
    assert run(members)[0]["recipients"] == 3


def test_skip_and_last_day():
    manager_email, _ = _setup()
    skipping = announcement.Announcement(key="atla", subject="X", audience="isleyen_sandik_yoneticileri",
                                         last_day=DUYURU.last_day, skip=lambda u: u.email_address == manager_email)
    assert run(skipping)[0]["recipients"] == 0

    assert announcement.active_announcements(DUYURU.last_day + timedelta(days=1)) == []


def test_failed_or_test_address_sending_is_not_marked(monkeypatch):
    manager_email, _ = _setup()
    run(send=Recorder(fail_for={manager_email}))
    monkeypatch.setenv("SANDIKv2_REMINDER_EMAIL_TEST_ADDRESS", "test@example.com")
    result, recorder = run()
    assert recorder.sent[0]["to"] == "test@example.com" and recorder.sent[0]["subject"].startswith("[TEST]")

    with db_session:
        assert not announcement.was_sent(WebUser.get(email_address=manager_email), "deneme_duyurusu")


@db_session
def test_mark_keeps_other_preferences():
    wu = factories.make_web_user()
    auth_db.update_reminder_preference(web_user=wu, updated_by=None, month_start_day=3, next_month_day=20)
    from datetime import datetime
    auth_db.mark_announcement_sent(web_user=wu, key="a", when=datetime(2026, 11, 22, 4, 1))
    auth_db.mark_announcement_sent(web_user=wu, key="b", when=datetime(2026, 11, 23, 4, 1))
    assert wu.preferences["announcements"] == {"a": "2026-11-22 04:01", "b": "2026-11-23 04:01"}
    assert wu.get_reminder_days() == (3, 20)


def test_manager_reminder_announcement_skips_who_already_enabled_it():
    with db_session:
        manager = factories.make_web_user()
        sandik = _running_sandik(manager)
        auth_db.update_manager_reminder_preference(web_user=manager, updated_by=manager, sandik_ids=[sandik.id])
    assert run(announcement.get("yonetici_on_hatirlatmasi"))[0]["recipients"] == 0


@pytest.mark.parametrize("item", announcement.ANNOUNCEMENTS, ids=lambda a: a.key)
def test_every_announcement_is_well_formed_and_renders(item):
    from flask import render_template
    from sandik.app import create_app

    assert [a.key for a in announcement.ANNOUNCEMENTS].count(item.key) == 1
    assert item.audience in announcement.AUDIENCES
    assert os.path.exists(os.path.join(TEMPLATES, item.template))

    app = create_app()
    app.config.update(SERVER_NAME="localhost")
    with app.app_context():
        html = render_template(item.template, data={"name_surname": "Ad Soyad", "sandik_names": ["Aile Sandığı"],
                                                    "preference_url": "https://ornek/tercih/abc"})
    assert "Ad Soyad" in html and "Aile Sandığı" in html and "tek seferlik" in html
