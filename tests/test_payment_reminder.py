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


def collect(web_user):
    return reminder.collect_reminder_data(web_user=web_user, url_builder=fake_url)


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


def _make_recipient_with_days(month_start_day, next_month_day):
    """Bu ay ödenmemiş aidatı olan ve hatırlatma günlerini seçmiş bir kişi."""
    wu = _web_user(month_start_day=month_start_day, next_month_day=next_month_day)
    sandik = factories.make_sandik(created_by=wu)
    share = factories.make_member_with_share(sandik=sandik, web_user=wu, created_by=wu)
    factories.make_contribution(share=share, term=period_utils.current_period(), created_by=wu,
                                amount=Decimal("100"))
    return wu


@pytest.mark.parametrize("day, expected", [
    (1, True),     # varsayılan 1. gün
    (2, False),
    (24, False),
    (25, True),    # varsayılan 2. gün
    (26, False),
    (31, False),
])
@db_session
def test_default_days_decide_what_is_sent_today(day, expected):
    wu = factories.make_web_user()
    assert reminder.is_reminder_day(web_user=wu, today=date(2026, 1, day)) is expected


@db_session
def test_user_can_choose_another_day():
    wu = _web_user(month_start_day=5, next_month_day=20)

    assert reminder.is_reminder_day(web_user=wu, today=date(2026, 1, 1)) is False
    assert reminder.is_reminder_day(web_user=wu, today=date(2026, 1, 5)) is True
    assert reminder.is_reminder_day(web_user=wu, today=date(2026, 1, 20)) is True


@db_session
def test_zero_means_the_user_does_not_want_that_email():
    wu = _web_user(month_start_day=0, next_month_day=25)

    assert reminder.is_reminder_day(web_user=wu, today=date(2026, 1, 1)) is False
    assert reminder.is_reminder_day(web_user=wu, today=date(2026, 1, 25)) is True


@db_session
def test_a_user_who_turned_both_off_is_never_sent_to():
    wu = _web_user(month_start_day=0, next_month_day=0)

    assert not any(reminder.is_reminder_day(web_user=wu, today=date(2026, 1, day)) for day in range(1, 32))
    assert reminder.wants_reminder(wu) is False


@db_session
def test_both_days_the_same_produce_one_email():
    wu = _make_recipient_with_days(month_start_day=10, next_month_day=10)

    result, recorder = run(today=date(2026, 1, 10))
    assert result["sent"] == 1 and [m["to"] for m in recorder.sent] == [wu.email_address]


@db_session
def test_manual_run_ignores_the_day_but_not_the_opt_out():
    wants = _make_recipient_with_days(month_start_day=0, next_month_day=7)
    _make_recipient_with_days(month_start_day=0, next_month_day=0)

    result, recorder = run(manual=True, today=date(2026, 1, 2))
    assert [m["to"] for m in recorder.sent] == [wants.email_address]


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
    assert section["overdue_total"] == Decimal("100")
    assert section["this_month_total"] == Decimal("120")
    assert section["total"] == Decimal("220")
    assert section["payments_url"] == fake_url(sandik.id)


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


@db_session
def test_payments_are_summed_into_contribution_and_installment_per_sandik():
    """E-postada ödemeler tek tek değil, sandık başına iki kalem (aidat, taksit) olarak gösterilir."""
    wu = factories.make_web_user()
    sandik = factories.make_sandik(created_by=wu, contribution_amount=Decimal("100"))
    share = factories.make_member_with_share(sandik=sandik, web_user=wu, created_by=wu)
    factories.make_contribution(share=share, term=period_utils.previous_period(), created_by=wu,
                                amount=Decimal("100"))
    factories.make_contribution(share=share, term=period_utils.current_period(), created_by=wu,
                                amount=Decimal("100"))
    # 3 taksit: geçen ay (gecikmiş), bu ay, gelecek ay (e-postaya girmez)
    factories.make_debt(share=share, amount=Decimal("300"), created_by=wu, number_of_installment=3,
                        start_period=period_utils.previous_period())

    section = collect(wu)["sandiks"][0]

    # Aidat: geçen ay + bu ay
    assert section["contribution_total"] == Decimal("200")
    assert section["installment_total"] == Decimal("200")
    assert section["contribution_total"] + section["installment_total"] == section["total"]


@db_session
def test_next_month_is_not_in_the_email_and_a_paid_up_member_gets_none():
    """Kullanıcı istedi: ay sonu e-postasında gelecek ayın ödemeleri listelenmez. Bu ayın ödemesi bitmiş
    üyeye (gelecek ayın taksiti, hesaplanacak aidatı olsa da) e-posta gitmez."""
    wu = factories.make_web_user()
    sandik = factories.make_sandik(created_by=wu, contribution_amount=Decimal("100"))
    share = factories.make_member_with_share(sandik=sandik, web_user=wu, created_by=wu)
    factories.pay_contribution_partially(share=share, term=period_utils.current_period(),
                                         paid_amount=Decimal("100"), created_by=wu)
    factories.make_debt(share=share, amount=Decimal("200"), created_by=wu, number_of_installment=2,
                        start_period=period_utils.next_period())
    contribution_count_before = Contribution.select().count()

    assert collect(wu) is None
    assert Contribution.select().count() == contribution_count_before


@db_session
def test_amounts_are_grouped_by_term():
    """Kullanıcı sordu: tutarın hangi aya ait olduğu anlaşılmıyordu. Tutarlar dönem dönem ayrılır."""
    wu = factories.make_web_user()
    sandik = factories.make_sandik(created_by=wu)
    share = factories.make_member_with_share(sandik=sandik, web_user=wu, created_by=wu)
    factories.make_contribution(share=share, term=period_utils.previous_period(), created_by=wu,
                                amount=Decimal("100"))
    factories.make_contribution(share=share, term=period_utils.current_period(), created_by=wu,
                                amount=Decimal("120"))

    data = collect(wu)
    terms = data["sandiks"][0]["terms"]

    assert [t["label"] for t in terms] == ["Geçmiş aylardan kalan", data["current_term_text"]]
    assert [t["total"] for t in terms] == [Decimal("100"), Decimal("120")]


@db_session
def test_an_empty_current_month_is_still_listed():
    wu = factories.make_web_user()
    sandik = factories.make_sandik(created_by=wu)
    share = factories.make_member_with_share(sandik=sandik, web_user=wu, created_by=wu)
    factories.make_contribution(share=share, term=period_utils.previous_period(), created_by=wu,
                                amount=Decimal("100"))

    data = collect(wu)
    terms = data["sandiks"][0]["terms"]

    assert [t["label"] for t in terms] == ["Geçmiş aylardan kalan", data["current_term_text"]]
    assert [t["total"] for t in terms] == [Decimal("100"), Decimal("0")]


@db_session
def test_rendered_email_names_each_term_and_says_when_this_month_is_done():
    from flask import render_template
    from sandik.app import create_app

    wu = factories.make_web_user()
    sandik = factories.make_sandik(created_by=wu)
    share = factories.make_member_with_share(sandik=sandik, web_user=wu, created_by=wu)
    factories.make_contribution(share=share, term=period_utils.previous_period(), created_by=wu,
                                amount=Decimal("100"))
    data = collect(wu)

    app = create_app()
    app.config.update(SERVER_NAME="localhost")
    with app.app_context():
        html = render_template("email/payment_reminder.html", data=data)

    overdue_at = html.index("Geçmiş aylardan kalan", html.index(sandik.name))
    current_at = html.index(data["current_term_text"], overdue_at)
    assert "Aidat" in html[overdue_at:current_at]
    assert "Ödenmemiş ödemeniz yok" in html[current_at:]
    assert period_utils.period_to_tr_text(period_utils.next_period()) not in html


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

def test_subject_mentions_the_current_month():
    assert reminder.build_subject({"current_term_text": "Ağustos 2026"}) == "Ağustos 2026 ödemeleriniz"


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
            if reminder.is_reminder_day(web_user=wu, today=date(2026, 1, day))]
    assert days == [3, 18]


def test_run_sends_to_the_member_with_an_unpaid_payment():
    address = _setup_recipient()

    result, recorder = run()
    assert result["recipients"] == 1
    assert result["sent"] == 1
    assert [m["to"] for m in recorder.sent] == [address]


def test_run_keeps_no_record_so_a_second_call_sends_again():
    """Kayıt tutulmadığı için `run_payment_reminder` her çağrıldığında gönderir.

    Bu bilinçli: mükerrer engeli `is_reminder_day()` içindeki tam gün eşitliğidir, burada değil.
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


@db_session
def test_duplicate_contributions_for_a_month_do_not_break_the_projection():
    """Canlı veride aynı hisse ve ay için birden fazla aidat kaydı var; hesap yine çalışmalı."""
    wu = factories.make_web_user()
    sandik = factories.make_sandik(created_by=wu, contribution_amount=Decimal("100"))
    share = factories.make_member_with_share(sandik=sandik, web_user=wu, created_by=wu)
    next_term = period_utils.next_period()
    factories.make_contribution(share=share, term=next_term, created_by=wu, amount=Decimal("100"))
    factories.make_contribution(share=share, term=next_term, created_by=wu, amount=Decimal("50"))

    # Yönetici ön hatırlatması ayın son günü yarınki (yeni ayın) e-postasını hesaplar
    section = reminder.collect_member_section(member=share.member_ref, url_builder=fake_url,
                                              current_term=next_term)
    assert section["this_month_total"] == Decimal("150")  # ikisi de kayıtlı; ayrıca hesaplanan yok
