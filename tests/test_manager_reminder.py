"""`sandik/utils/manager_reminder.py` için testler: yönetici ön hatırlatması (duyurusu: `test_announcement.py`).

Gönderim `render`/`send` enjekte edilerek SMTP'siz sınanır (`test_payment_reminder.py` ile aynı kalıp). Tarihler
gerçek bugünden türetilir: tutarlar `period_utils.current_period()` (date.today) ile hesaplandığı için "ayın son
günü → yarın yeni ay" durumu ancak gerçek ayın son günü verilerek sınanabilir.
"""
import calendar
import re
from datetime import date, timedelta
from decimal import Decimal

import pytest
from pony.orm import db_session, flush

from sandik.auth import db as auth_db
from sandik.utils import manager_reminder
from sandik.utils import period as period_utils
from sandik.utils.db_models import Contribution, WebUser

from tests import factories

BASE_URL = "https://localhost"


class Recorder:
    def __init__(self, fail_for=None):
        self.sent = []
        self.fail_for = fail_for or set()

    def __call__(self, to_address, subject, html):
        if to_address in self.fail_for:
            raise RuntimeError("smtp patladı")
        self.sent.append({"to": to_address, "subject": subject, "html": html})


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setenv("SANDIKv2_REMINDER_EMAIL_SLEEP_SECONDS", "0")
    monkeypatch.delenv("SANDIKv2_REMINDER_EMAIL_TEST_ADDRESS", raising=False)


def this_month_day(day):
    t = date.today()
    return date(t.year, t.month, day)


def last_day_of_this_month():
    t = date.today()
    return date(t.year, t.month, calendar.monthrange(t.year, t.month)[1])


def run(today, send=None):
    send = send if send is not None else Recorder()
    result = manager_reminder.run_manager_reminder(render=lambda data: repr(data), send=send, today=today,
                                                   log=lambda *a: None)
    return result, send


def collect(today):
    return manager_reminder.collect_recipients(today=today, url_builder=lambda sid: f"https://ornek/{sid}/islem-ekle")


def _set_days(web_user, month_start_day=1, next_month_day=25):
    auth_db.update_reminder_preference(web_user=web_user, updated_by=None, month_start_day=month_start_day,
                                       next_month_day=next_month_day)


def _sandik_with_manager(opt_in=True):
    """Yönetici + iki üye (her biri bu ayın 100'lük aidatını borçlu)."""
    manager = factories.make_web_user(name="Yönetici", surname="Başkan")
    sandik = factories.make_sandik(created_by=manager, name="Aile Sandığı")
    members = []
    for name in ("Zeynep", "Ahmet"):
        wu = factories.make_web_user(name=name, surname="Üye")
        share = factories.make_member_with_share(sandik=sandik, web_user=wu, created_by=manager)
        factories.make_contribution(share=share, term=period_utils.current_period(), created_by=manager,
                                    amount=Decimal("100"))
        members.append(wu)
    if opt_in:
        auth_db.update_manager_reminder_preference(web_user=manager, updated_by=manager, sandik_ids=[sandik.id])
    flush()
    return manager, sandik, members


# --- Tercih -------------------------------------------------------------------------------------

@db_session
def test_feature_is_off_by_default():
    manager, sandik, members = _sandik_with_manager(opt_in=False)
    for wu in members:
        _set_days(wu, next_month_day=this_month_day(25).day)

    assert manager.get_manager_reminder_sandik_ids() == []
    assert collect(this_month_day(24)) == []


@db_session
def test_only_sandiks_the_user_can_write_are_saved():
    manager, sandik, members = _sandik_with_manager(opt_in=False)
    other_sandik = factories.make_sandik(created_by=factories.make_web_user())
    flush()

    auth_db.update_manager_reminder_preference(web_user=manager, updated_by=manager,
                                               sandik_ids=[sandik.id, other_sandik.id])
    assert manager.get_manager_reminder_sandik_ids() == [sandik.id]

    # Yalnızca okuma yetkisi olan kişi açamaz; yazma yetkilisi açabilir.
    reader, writer = members
    factories.sandik_db.create_sandik_authority(created_by=manager, name="Okur", can_read=True,
                                                sandik_ref=sandik, web_users_set=reader)
    factories.sandik_db.create_sandik_authority(created_by=manager, name="Sayman", can_write=True,
                                                sandik_ref=sandik, web_users_set=writer)
    assert reader.get_managed_sandiks() == []
    assert writer.get_managed_sandiks() == [sandik]


@db_session
def test_other_preferences_are_kept():
    manager, sandik, _ = _sandik_with_manager()
    _set_days(manager, month_start_day=3, next_month_day=20)

    assert manager.get_manager_reminder_sandik_ids() == [sandik.id]
    assert manager.get_reminder_days() == (3, 20)


# --- Yarın kime gidecek? ------------------------------------------------------------------------

@db_session
def test_manager_is_told_a_day_before_with_each_members_own_day():
    manager, sandik, (zeynep, ahmet) = _sandik_with_manager()
    _set_days(manager, month_start_day=0, next_month_day=0)  # yöneticinin kendi hatırlatması yok
    _set_days(zeynep, month_start_day=5, next_month_day=20)
    _set_days(ahmet, month_start_day=10, next_month_day=20)

    assert collect(this_month_day(3)) == []

    on_4th = collect(this_month_day(4))
    assert [m["name_surname"] for m in on_4th[0]["sandiks"][0]["members"]] == ["Zeynep Üye"]
    assert on_4th[0]["sandiks"][0]["members"][0]["kind_text"] == "Ay başı hatırlatması"

    on_19th = collect(this_month_day(19))
    rows = on_19th[0]["sandiks"][0]["members"]
    assert [m["name_surname"] for m in rows] == ["Ahmet Üye", "Zeynep Üye"]  # türkçe alfabetik
    assert {m["kind_text"] for m in rows} == {"Ay sonu hatırlatması"}
    assert on_19th[0]["member_count"] == 2
    assert on_19th[0]["email_address"] == manager.email_address


@db_session
def test_amounts_match_the_members_email_and_count_undistributed_money():
    manager, sandik, (zeynep, ahmet) = _sandik_with_manager()
    # Ahmet 30 yatırmış, henüz bir ödemeye dağıtılmamış (işleme konmamış para).
    factories.make_money_transaction(member=ahmet.members_set.select().first(), amount=Decimal("30"),
                                     created_by=manager)
    for wu in (zeynep, ahmet):
        _set_days(wu, month_start_day=1, next_month_day=15)

    data = collect(this_month_day(14))[0]
    section = data["sandiks"][0]
    by_name = {m["name_surname"]: m for m in section["members"]}

    # Ay sonu: bu ayın 100'ü + gelecek ayın hesaplanan 100'ü
    assert by_name["Zeynep Üye"]["remaining"] == Decimal("200")
    assert by_name["Ahmet Üye"]["undistributed"] == Decimal("30")
    assert by_name["Ahmet Üye"]["remaining"] == Decimal("170")
    assert section["remaining_total"] == Decimal("370")
    assert section["undistributed_member_count"] == 1
    assert section["add_transaction_url"] == f"https://ornek/{sandik.id}/islem-ekle"


@db_session
def test_on_the_last_day_of_the_month_the_new_months_contribution_is_projected():
    """Yarın ayın 1'i: o ayın aidatı gece oluşturulacak, bugün hesaplanır (yazılmaz)."""
    manager, sandik, (zeynep, _) = _sandik_with_manager()
    contribution_count = Contribution.select().count()

    data = collect(last_day_of_this_month())[0]
    zeynep_row = next(m for m in data["sandiks"][0]["members"] if m["name_surname"] == "Zeynep Üye")

    assert data["reminder_day"].day == 1
    assert zeynep_row["kind_text"] == "Ay başı hatırlatması"
    # Bu ayın ödenmemiş 100'ü (yarın "geçmiş aydan kalan") + yeni ayın hesaplanan 100'ü
    assert zeynep_row["remaining"] == Decimal("200")
    assert Contribution.select().count() == contribution_count


@db_session
def test_members_without_payments_or_reminders_are_left_out_and_no_empty_email_is_sent():
    manager, sandik, (zeynep, ahmet) = _sandik_with_manager()
    _set_days(zeynep, month_start_day=0, next_month_day=0)
    _set_days(ahmet, month_start_day=0, next_month_day=0)
    _set_days(manager, month_start_day=0, next_month_day=0)

    result, recorder = run(this_month_day(24))
    assert result["recipients"] == 0
    assert recorder.sent == []


@db_session
def test_lost_authority_stops_the_email():
    manager, sandik, members = _sandik_with_manager()
    for wu in members:
        _set_days(wu, next_month_day=25)
    authority = manager.get_sandik_authority(sandik=sandik)
    authority.web_users_set.remove(manager)
    flush()

    assert collect(this_month_day(24)) == []


@db_session
def test_one_email_per_manager_with_an_attention_grabbing_subject():
    manager, sandik, members = _sandik_with_manager()
    for wu in members:
        _set_days(wu, next_month_day=25)

    result, recorder = run(this_month_day(24))

    assert result == {"sent": 1, "failed": 0, "recipients": 1}
    assert recorder.sent[0]["to"] == manager.email_address
    subject = recorder.sent[0]["subject"]
    assert subject.startswith("⚠️ Hesap güncel mi?")
    assert "Yarın 2 üyeye" in subject
    assert "(Aile Sandığı)" in subject


# --- Şablonlar ve sayfa -------------------------------------------------------------------------

@pytest.fixture
def app():
    from sandik.app import create_app
    from sandik.auth import login_limit

    flask_app = create_app()
    flask_app.config.update(TESTING=True, SECRET_KEY="test", SERVER_NAME="localhost")
    flask_app.secret_key = "test"
    login_limit.reset()
    return flask_app


def test_email_templates_render(app):
    from flask import render_template

    with db_session:
        manager, sandik, members = _sandik_with_manager()
        for wu in members:
            _set_days(wu, next_month_day=25)
        data = collect(this_month_day(24))[0]
        data["preference_url"] = "https://ornek/tercih/abc"

    with app.app_context():
        html = render_template("email/manager_reminder.html", data=data)
        assert "Zeynep Üye" in html and "Para girişi ekle" in html and "E-posta tercihlerim" in html
        assert "Ay sonu hatırlatması" in html


def _login(app, web_user_id):
    client = app.test_client()
    with client.session_transaction(base_url=BASE_URL) as session:
        session["_user_id"] = str(web_user_id)
        session["_fresh"] = True
    return client


def test_preference_page_shows_the_option_only_to_managers_and_saves_it(app):
    with db_session:
        manager, sandik, members = _sandik_with_manager(opt_in=False)
        manager_id, member_id, sandik_id = manager.id, members[0].id, sandik.id

    member_page = _login(app, member_id).get("/tercihlerim", base_url=BASE_URL).get_data(as_text=True)
    assert "Sandık yöneticisi bildirimi" not in member_page

    client = _login(app, manager_id)
    page = client.get("/tercihlerim", base_url=BASE_URL).get_data(as_text=True)
    assert "Sandık yöneticisi bildirimi" in page
    card = page.split("Sandık yöneticisi bildirimi")[1].split("rp-actions")[0]
    assert f'value="{sandik_id}"' in card and "checked" not in card

    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page).group(1)
    data = {"csrf_token": token, "month_start_enabled": "y", "month_start_day": "1",
            "next_month_enabled": "y", "next_month_day": "25", "manager_sandik_ids": str(sandik_id)}
    response = client.post("/tercihlerim", data=data, base_url=BASE_URL,
                           headers={"Referer": f"{BASE_URL}/tercihlerim"})
    assert response.status_code == 200
    with db_session:
        assert WebUser[manager_id].get_manager_reminder_sandik_ids() == [sandik_id]

    data.pop("manager_sandik_ids")
    client.post("/tercihlerim", data=data, base_url=BASE_URL, headers={"Referer": f"{BASE_URL}/tercihlerim"})
    with db_session:
        assert WebUser[manager_id].get_manager_reminder_sandik_ids() == []
