"""`sandik/utils/reminder.py` için testler.

Gerçek SMTP'ye ve Flask'a çıkmadan doğrulanır: `run_payment_reminder` şablon basma ve gönderme
işlerini dışarıdan alır (`render` / `send`), adres üretimi de `url_builder` ile enjekte edilir.
"""
from datetime import date
from decimal import Decimal

import pytest
from pony.orm import db_session

from sandik.utils import period as period_utils
from sandik.utils import reminder
from sandik.auth import db as auth_db
from sandik.utils.db_models import Contribution, ReminderPreference

from tests import factories


def fake_url(sandik_id):
    return f"https://ornek/sandik/{sandik_id}/ozet"


def collect(web_user, include_next_month=False):
    return reminder.collect_reminder_data(web_user=web_user, include_next_month=include_next_month,
                                          url_builder=fake_url)


class Recorder:
    """`send` yerine geçer; gönderilenleri toplar."""

    def __init__(self, fail_for=None):
        self.sent = []
        self.fail_for = fail_for or set()

    def __call__(self, to_address, subject, html):
        if to_address in self.fail_for:
            raise RuntimeError("smtp patladı")
        self.sent.append({"to": to_address, "subject": subject, "html": html})


def run(send=None, **kwargs):
    """Varsayılan: ayın 1'i (herkesin varsayılan ay başı günü)."""
    kwargs.setdefault("today", date(2026, 1, 1))
    send = send if send is not None else Recorder()
    result = reminder.run_payment_reminder(
        url_builder=fake_url, render=lambda data: f"<p>{data['name_surname']}</p>",
        send=send, log=lambda *a: None, **kwargs
    )
    return result, send


# --- Gönderim günleri -------------------------------------------------------------------------
# Gün, kişi tercihidir; karşılaştırmanın tam eşitlik olması mükerrer engelinin ta kendisidir.

@db_session
def _web_user(month_start_day=None, next_month_day=None):
    wu = factories.make_web_user()
    if month_start_day is not None or next_month_day is not None:
        auth_db.update_reminder_preference(
            web_user=wu, updated_by=None,
            month_start_day=1 if month_start_day is None else month_start_day,
            next_month_day=25 if next_month_day is None else next_month_day,
        )
    return wu


@pytest.mark.parametrize("day, expected", [
    (1, False),    # varsayılan ay başı günü -> yalnızca bu ay
    (2, None),
    (24, None),
    (25, True),    # varsayılan ay sonu günü -> gelecek ay dahil
    (26, None),
    (31, None),
])
@db_session
def test_default_days_decide_what_is_sent_today(day, expected):
    wu = factories.make_web_user()
    assert reminder.reminder_for_today(web_user=wu, today=date(2026, 1, day)) is expected


@db_session
def test_user_can_choose_another_day():
    wu = _web_user(month_start_day=5, next_month_day=20)

    assert reminder.reminder_for_today(web_user=wu, today=date(2026, 1, 1)) is None
    assert reminder.reminder_for_today(web_user=wu, today=date(2026, 1, 5)) is False
    assert reminder.reminder_for_today(web_user=wu, today=date(2026, 1, 20)) is True


@db_session
def test_zero_means_the_user_does_not_want_that_email():
    wu = _web_user(month_start_day=0, next_month_day=25)

    assert reminder.reminder_for_today(web_user=wu, today=date(2026, 1, 1)) is None
    assert reminder.reminder_for_today(web_user=wu, today=date(2026, 1, 25)) is True


@db_session
def test_a_user_who_turned_both_off_is_never_sent_to():
    wu = _web_user(month_start_day=0, next_month_day=0)

    assert all(reminder.reminder_for_today(web_user=wu, today=date(2026, 1, day)) is None
               for day in range(1, 32))


@db_session
def test_both_reminders_on_the_same_day_produce_one_email_including_next_month():
    wu = _web_user(month_start_day=10, next_month_day=10)

    assert reminder.reminder_for_today(web_user=wu, today=date(2026, 1, 10)) is True


@db_session
def test_manual_run_ignores_the_day_but_not_the_opt_out():
    wants = _web_user(month_start_day=7, next_month_day=0)

    assert reminder.reminder_for_kind(web_user=wants, kind=reminder.KIND_MONTH_START) is False
    assert reminder.reminder_for_kind(web_user=wants, kind=reminder.KIND_NEXT_MONTH) is None


# --- Veri toplama -----------------------------------------------------------------------------

@db_session
def test_overdue_and_this_month_are_separated():
    wu = factories.make_web_user()
    sandik = factories.make_sandik(created_by=wu)
    share = factories.make_member_with_share(sandik=sandik, web_user=wu, created_by=wu)

    previous_term = period_utils.previous_period()
    current_term = period_utils.current_period()
    factories.make_contribution(share=share, term=previous_term, created_by=wu, amount=Decimal("100"))
    factories.make_contribution(share=share, term=current_term, created_by=wu, amount=Decimal("120"))

    data = collect(wu)
    section = data["sandiks"][0]

    assert [r["term"] for r in section["overdue"]] == [previous_term]
    assert [r["term"] for r in section["this_month"]] == [current_term]
    assert section["next_month"] == []
    assert section["overdue_total"] == Decimal("100")
    assert section["this_month_total"] == Decimal("120")
    assert section["total"] == Decimal("220")
    assert section["summary_url"] == fake_url(sandik.id)


@db_session
def test_member_without_payment_is_not_mailed():
    wu = factories.make_web_user()
    sandik = factories.make_sandik(created_by=wu)
    factories.make_member_with_share(sandik=sandik, web_user=wu, created_by=wu)

    assert collect(wu) is None


@db_session
def test_fully_paid_contribution_is_not_listed():
    wu = factories.make_web_user()
    sandik = factories.make_sandik(created_by=wu)
    share = factories.make_member_with_share(sandik=sandik, web_user=wu, created_by=wu)

    factories.pay_contribution_partially(share=share, term=period_utils.current_period(),
                                         paid_amount=Decimal("100"), created_by=wu,
                                         contribution_amount=Decimal("100"))

    assert collect(wu) is None


@db_session
def test_undistributed_amount_is_subtracted():
    wu = factories.make_web_user()
    sandik = factories.make_sandik(created_by=wu)
    share = factories.make_member_with_share(sandik=sandik, web_user=wu, created_by=wu)

    # 100 TL'lik aidata 150 TL yatırılıyor: aidat kapanıyor, 50 TL işleme konmadan kalıyor.
    factories.pay_contribution_partially(share=share, term=period_utils.previous_period(),
                                         paid_amount=Decimal("150"), created_by=wu,
                                         contribution_amount=Decimal("100"))
    factories.make_contribution(share=share, term=period_utils.current_period(), created_by=wu,
                                amount=Decimal("120"))

    section = collect(wu)["sandiks"][0]
    assert section["undistributed"] == Decimal("50")
    assert section["total"] == Decimal("120")
    assert section["remaining"] == Decimal("70")


@db_session
def test_member_without_web_user_does_not_break_the_job():
    owner = factories.make_web_user()
    sandik = factories.make_sandik(created_by=owner)
    # Site hesabı olmayan üye (Member.web_user_ref Optional'dır)
    member = factories.make_member(sandik=sandik, web_user=None, created_by=owner)
    member.web_user_ref = None
    orphan_share = factories.make_share(member=member, created_by=owner)
    factories.make_contribution(share=orphan_share, term=period_utils.current_period(), created_by=owner,
                                amount=Decimal("100"))

    # Hesabı olan başka bir üye de var; iş onun için çalışmaya devam etmeli.
    payer_share = factories.make_member_with_share(sandik=sandik, web_user=owner, created_by=owner)
    factories.make_contribution(share=payer_share, term=period_utils.current_period(), created_by=owner,
                                amount=Decimal("90"))

    result, recorder = run()
    assert result["failed"] == 0
    assert [m["to"] for m in recorder.sent] == [owner.email_address]


# --- Gelecek ay --------------------------------------------------------------------------------

@db_session
def test_next_month_contribution_is_calculated_without_writing_to_database():
    wu = factories.make_web_user()
    sandik = factories.make_sandik(created_by=wu, contribution_amount=Decimal("100"))
    share = factories.make_member_with_share(sandik=sandik, web_user=wu, created_by=wu)
    factories.make_contribution(share=share, term=period_utils.current_period(), created_by=wu,
                                amount=Decimal("100"))
    contribution_count_before = Contribution.select().count()

    section = collect(wu, include_next_month=True)["sandiks"][0]

    next_term = period_utils.next_period()
    assert [(r["term"], r["type"], r["amount"]) for r in section["next_month"]] == [
        (next_term, "Aidat", Decimal("100"))
    ]
    assert Contribution.select().count() == contribution_count_before


@db_session
def test_next_month_contribution_scales_with_active_share_count():
    wu = factories.make_web_user()
    sandik = factories.make_sandik(created_by=wu, contribution_amount=Decimal("100"))
    share = factories.make_member_with_share(sandik=sandik, web_user=wu, created_by=wu)
    member = share.member_ref
    factories.make_share(member=member, created_by=wu)  # ikinci hisse
    factories.make_contribution(share=share, term=period_utils.current_period(), created_by=wu,
                                amount=Decimal("100"))

    section = collect(wu, include_next_month=True)["sandiks"][0]
    assert section["next_month_total"] == Decimal("200")
    # Birden fazla hisse varsa satırlarda hisse bilgisi gösterilir
    assert {r["share"] for r in section["next_month"]} == {"1. hisse", "2. hisse"}


@db_session
def test_existing_next_month_contribution_is_not_duplicated():
    wu = factories.make_web_user()
    sandik = factories.make_sandik(created_by=wu, contribution_amount=Decimal("100"))
    share = factories.make_member_with_share(sandik=sandik, web_user=wu, created_by=wu)
    next_term = period_utils.next_period()
    # Gelecek ayın aidatı elle oluşturulmuş
    factories.make_contribution(share=share, term=next_term, created_by=wu, amount=Decimal("80"))

    section = collect(wu, include_next_month=True)["sandiks"][0]
    assert [(r["term"], r["amount"]) for r in section["next_month"]] == [(next_term, Decimal("80"))]


@db_session
def test_next_month_is_not_included_in_month_start_mail():
    wu = factories.make_web_user()
    sandik = factories.make_sandik(created_by=wu, contribution_amount=Decimal("100"))
    share = factories.make_member_with_share(sandik=sandik, web_user=wu, created_by=wu)
    factories.make_contribution(share=share, term=period_utils.current_period(), created_by=wu,
                                amount=Decimal("100"))

    section = collect(wu, include_next_month=False)["sandiks"][0]
    assert section["next_month"] == []


# --- Kişi başına tek e-posta -------------------------------------------------------------------

@db_session
def test_one_email_per_person_covering_every_sandik():
    wu = factories.make_web_user()
    for name in ("A sandığı", "B sandığı"):
        sandik = factories.make_sandik(created_by=wu, name=name)
        share = factories.make_member_with_share(sandik=sandik, web_user=wu, created_by=wu)
        factories.make_contribution(share=share, term=period_utils.current_period(), created_by=wu,
                                    amount=Decimal("50"))

    data = collect(wu)
    assert [s["sandik_name"] for s in data["sandiks"]] == ["A sandığı", "B sandığı"]
    assert data["grand_total"] == Decimal("100")

    result, recorder = run()
    assert result["sent"] == 1
    assert len(recorder.sent) == 1


# --- Konu satırı -------------------------------------------------------------------------------

def test_subject_mentions_one_or_two_months():
    base = {"current_term_text": "Ağustos 2026", "next_term_text": "Eylül 2026"}
    assert reminder.build_subject(dict(base, include_next_month=False)) == "Ağustos 2026 ödemeleriniz"
    assert reminder.build_subject(dict(base, include_next_month=True)) == \
        "Ağustos 2026 ve Eylül 2026 ödemeleriniz"


# --- Gönderim davranışı ------------------------------------------------------------------------

def _member_with_unpaid_contribution():
    wu = factories.make_web_user()
    sandik = factories.make_sandik(created_by=wu)
    share = factories.make_member_with_share(sandik=sandik, web_user=wu, created_by=wu)
    factories.make_contribution(share=share, term=period_utils.current_period(), created_by=wu,
                                amount=Decimal("100"))
    return wu


@db_session
def _setup_recipient():
    return _member_with_unpaid_contribution().email_address


@db_session
def test_a_user_is_mailed_on_exactly_two_days_a_month():
    """Mükerrer engeli tamamen buna dayanıyor: kişi başına ayda iki gün, her biri bir kez."""
    wu = _web_user(month_start_day=3, next_month_day=18)
    days = [day for day in range(1, 32)
            if reminder.reminder_for_today(web_user=wu, today=date(2026, 1, day)) is not None]
    assert days == [3, 18]


def test_run_sends_to_the_member_with_an_unpaid_payment():
    address = _setup_recipient()

    result, recorder = run()
    assert result["recipients"] == 1
    assert result["sent"] == 1
    assert [m["to"] for m in recorder.sent] == [address]


def test_run_keeps_no_record_so_a_second_call_sends_again():
    """Kayıt tutulmadığı için `run_payment_reminder` her çağrıldığında gönderir.

    Bu bilinçli: mükerrer engeli `reminder_for_today()` içindeki tam gün eşitliğidir, burada değil.
    """
    _setup_recipient()

    first, _ = run()
    second, second_recorder = run()

    assert first["sent"] == 1
    assert second["sent"] == 1
    assert len(second_recorder.sent) == 1


def test_dry_run_sends_nothing():
    _setup_recipient()

    result, recorder = run(dry_run=True)
    assert result["recipients"] == 1
    assert result["sent"] == 0
    assert recorder.sent == []


def test_a_failing_send_is_counted_and_does_not_stop_the_others():
    first = _setup_recipient()
    second = _setup_recipient()

    result, recorder = run(send=Recorder(fail_for={first}))
    assert result["failed"] == 1
    assert result["sent"] == 1
    assert [m["to"] for m in recorder.sent] == [second]


# --- Tercihin saklanması ve forma çevrilmesi ---------------------------------------------------

@db_session
def test_updating_the_preference_only_touches_its_own_json_keys():
    """`Member.preferences` kalıbı: diğer tercihler korunmalı, yalnızca gün anahtarları değişmeli."""
    wu = factories.make_web_user()
    wu.preferences["baska_bir_tercih"] = "dokunma"

    auth_db.update_reminder_preference(web_user=wu, updated_by=None, month_start_day=3, next_month_day=0)
    auth_db.update_reminder_preference(web_user=wu, updated_by=None, month_start_day=9, next_month_day=20)

    assert wu.get_reminder_days() == (9, 20)
    assert wu.preferences["baska_bir_tercih"] == "dokunma"


@db_session
def test_a_user_row_without_the_keys_falls_back_to_defaults():
    """Sütun sonradan eklendiği için eski satırlarda `preferences` boş olabilir."""
    wu = factories.make_web_user()
    wu.preferences.clear()

    assert wu.get_reminder_days() == (ReminderPreference.DEFAULT_MONTH_START_DAY,
                                      ReminderPreference.DEFAULT_NEXT_MONTH_DAY)


@db_session
def test_an_invalid_day_is_refused():
    wu = factories.make_web_user()
    for bad_day in (-1, 29, 31, 99):
        with pytest.raises(ValueError):
            auth_db.update_reminder_preference(web_user=wu, updated_by=None,
                                               month_start_day=bad_day, next_month_day=25)


@pytest.fixture
def reminder_form():
    """`FlaskForm` uygulama bağlamı ister; testin tamamı için çıplak bir Flask örneği yeter."""
    from flask import Flask
    from sandik.auth.forms import ReminderPreferenceForm

    app = Flask(__name__)
    app.config.update(SECRET_KEY="test", WTF_CSRF_ENABLED=False)
    with app.test_request_context():
        yield ReminderPreferenceForm(formdata=None, meta={"csrf": False})


def test_form_translates_between_two_checkboxes_and_one_number(reminder_form):
    """Veritabanında tek sayı (0 = istemiyorum), arayüzde "istiyorum" + "hangi gün"."""
    form = reminder_form

    form.fill_from_days(month_start_day=0, next_month_day=12)
    assert form.month_start_enabled.data is False
    assert form.next_month_enabled.data is True
    assert form.next_month_day.data == "12"
    assert form.to_days() == (0, 12)

    form.fill_from_days(month_start_day=4, next_month_day=0)
    assert form.to_days() == (4, 0)


def test_form_falls_back_to_the_default_day_when_the_value_is_broken(reminder_form):
    """Kapalı kutunun gün alanı tarayıcıda disabled gider; bozuk/boş değer varsayılana düşmeli."""
    form = reminder_form
    form.month_start_enabled.data = True
    form.month_start_day.data = ""
    form.next_month_enabled.data = True
    form.next_month_day.data = "99"

    assert form.to_days() == (ReminderPreference.DEFAULT_MONTH_START_DAY,
                              ReminderPreference.DEFAULT_NEXT_MONTH_DAY)
