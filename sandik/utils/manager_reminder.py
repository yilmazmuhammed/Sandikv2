"""Sandık yöneticisine, üyelere ödeme hatırlatması gitmeden **bir gün önce** gönderilen e-posta.

Kullanıcı istedi: üyelerin yatırdığı para sisteme işlenmeden hatırlatma giderse üye, ödediği tutar için
"ödemeniz gereken" e-postası alır. Yönetici isterse bir gün önce "yarın şu üyelere hatırlatma gidecek,
hesabı güncel tutun" e-postası alır; içinde her üyenin yarınki e-postada yazacak tutarı vardır.

- **Tercih sandık başınadır ve varsayılan kapalıdır** (`ManagerReminderPreference`, `WebUser.preferences`).
  Yalnızca o sandıkta işlem girme yetkisi olan (yönetici ya da yazma yetkili) kişi açabilir
  (`WebUser.get_managed_sandiks`). Sayfa: `/tercihlerim` ve e-postadaki `/tercih/<token>`.
- **Her üyenin günü farklı olabilir** (`ReminderPreference`): bugün, yarın kimin hangi hatırlatmayı
  alacağına `reminder.reminder_for_today(web_user, yarın)` ile bakılır. Yarın kimseye gitmiyorsa
  yöneticiye de e-posta gitmez. Mükerrer engeli üyelerdekiyle aynıdır: gün tam eşitlikle karşılaştırılır,
  kayıt tutulmaz.
- Tutarlar yarınki e-postayla **aynı fonksiyondan** (`reminder.collect_member_section`) gelir. Ayın son
  günü yarın yeni ay başlar ve o ayın aidatları henüz yoktur; `current_term` verilerek hesaplanır.
- Yönetici başına tek e-posta: yönettiği ve tercihi açık bütün sandıklar bölüm bölüm listelenir.

Ayrıca **bir kereye mahsus duyuru**: özelliğin eklendiği, bütün yöneticilere bir kez gönderilir
(`run_announcement`). Gönderilen kişiye `ManagerReminderPreference.ANNOUNCED_KEY` yazılır, ikinci kez
gitmez. Gecelik iş `ANNOUNCEMENT_LAST_DAY`e kadar dener (deploy'dan sonraki ilk gece gider); o günden
sonra adım kendiliğinden hiçbir şey yapmaz ve koddan kaldırılabilir.

Akış `reminder.py` ile aynıdır: veri `db_session` içinde düz sözlüklere çevrilir, gönderim oturum
kapalıyken yapılır; `render`/`send`/adres üreticileri dışarıdan verilir (testler Flask ve SMTP'siz).
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from time import sleep

from pony.orm import db_session

from sandik.auth import db as auth_db
from sandik.utils import period as period_utils
from sandik.utils import reminder
from sandik.utils.db_models import ManagerReminderPreference, Sandik, WebUser
from sandik.utils.sorting import turkish_sort_key

# Duyuru bu güne kadar (dahil) gecelik işte denenir; sonrasında gecelik iş duyuruya hiç bakmaz.
ANNOUNCEMENT_LAST_DAY = date(2026, 12, 31)

TR_DAY_NAMES = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]

KIND_TEXTS = {False: "Ay başı hatırlatması", True: "Ay sonu hatırlatması"}


def date_to_tr_text(day: date):
    """date(2026, 11, 22) -> '22 Kasım 2026 Pazar'."""
    return f"{day.day} {period_utils.TR_MONTH_NAMES[day.month - 1]} {day.year} {TR_DAY_NAMES[day.weekday()]}"


# --- Yarın kimlere hatırlatma gidecek? ----------------------------------------------------------

def collect_sandik_section(sandik: Sandik, reminder_day: date, url_builder=None):
    """Bu sandıkta `reminder_day` günü hatırlatma alacak üyeler. Kimse yoksa `None`.

    Üyenin hatırlatması bütün sandıklarını kapsayan tek bir e-postadır; burada yalnızca bu sandığın
    bölümü hesaplanır. Bu sandıkta ödemesi olmayan üyenin e-postasında bu sandık yer almaz, o yüzden
    listeye de girmez.
    """
    current_term = period_utils.date_to_period(reminder_day)
    rows = []
    for member in sandik.members_set.filter(lambda m: m.is_active):
        web_user = member.web_user_ref
        if web_user is None or not web_user.email_address:
            continue
        include_next_month = reminder.reminder_for_today(web_user=web_user, today=reminder_day)
        if include_next_month is None:
            continue
        section = reminder.collect_member_section(member=member, include_next_month=include_next_month,
                                                  url_builder=lambda _: None, current_term=current_term)
        if not section:
            continue
        rows.append({
            "member_id": member.id,
            "name_surname": web_user.name_surname,
            "kind_text": KIND_TEXTS[include_next_month],
            "include_next_month": include_next_month,
            "total": section["total"],
            "undistributed": section["undistributed"],
            "remaining": section["remaining"],
        })

    if not rows:
        return None

    rows.sort(key=lambda r: turkish_sort_key(r["name_surname"]))
    return {
        "sandik_id": sandik.id,
        "sandik_name": sandik.name,
        "currency": sandik.currency,
        "add_transaction_url": url_builder(sandik.id) if url_builder else None,
        "members": rows,
        "member_count": len(rows),
        "remaining_total": sum((r["remaining"] for r in rows if r["remaining"] > 0), Decimal(0)),
        "undistributed_member_count": sum(1 for r in rows if r["undistributed"] > 0),
    }


def collect_recipients(today: date = None, url_builder=None, preference_url_builder=None):
    """Bugün ön hatırlatma alacak yöneticiler. `db_session` içinde çağrılmalıdır.

    Aynı sandığın birden fazla yöneticisi olabilir; sandığın bölümü bir kez hesaplanır.
    """
    today = today or date.today()
    reminder_day = today + timedelta(days=1)
    section_cache = {}

    recipients = []
    for web_user in WebUser.select().order_by(WebUser.id):
        wanted = set(web_user.get_manager_reminder_sandik_ids())
        if not wanted or not web_user.email_address or not web_user.is_active:
            continue
        # Yetkisi sonradan alınmış sandık tercihte kalmış olabilir; yalnızca bugün yönettikleri.
        sandiks = [s for s in web_user.get_managed_sandiks() if s.id in wanted]

        sections = []
        for sandik in sandiks:
            if sandik.id not in section_cache:
                section_cache[sandik.id] = collect_sandik_section(sandik=sandik, reminder_day=reminder_day,
                                                                  url_builder=url_builder)
            if section_cache[sandik.id]:
                sections.append(section_cache[sandik.id])
        if not sections:
            continue

        recipients.append({
            "web_user_id": web_user.id,
            "email_address": web_user.email_address,
            "name_surname": web_user.name_surname,
            "preference_url": preference_url_builder(web_user) if preference_url_builder else None,
            "reminder_day": reminder_day,
            "reminder_day_text": date_to_tr_text(reminder_day),
            "sandiks": sections,
            "member_count": sum(s["member_count"] for s in sections),
        })
    return recipients


def build_subject(data):
    subject = f"⚠️ Hesap güncel mi? Yarın {data['member_count']} üyeye ödeme hatırlatması gidecek"
    if len(data["sandiks"]) == 1:
        subject += f" ({data['sandiks'][0]['sandik_name']})"
    return subject


# --- Duyuru (bir kereye mahsus) -----------------------------------------------------------------

def collect_announcement_recipients(preference_url_builder=None):
    """Duyuruyu henüz almamış, işlem girme yetkisi olan kişiler. `db_session` içinde çağrılmalıdır.

    Özelliği zaten açmış olan kişiye duyuru gönderilmez (biliyor).
    """
    recipients = []
    for web_user in WebUser.select().order_by(WebUser.id):
        preferences = web_user.preferences or {}
        if preferences.get(ManagerReminderPreference.ANNOUNCED_KEY):
            continue
        if not web_user.email_address or not web_user.is_active or web_user.get_manager_reminder_sandik_ids():
            continue
        sandiks = web_user.get_managed_sandiks()
        if not sandiks:
            continue
        recipients.append({
            "web_user_id": web_user.id,
            "email_address": web_user.email_address,
            "name_surname": web_user.name_surname,
            "preference_url": preference_url_builder(web_user) if preference_url_builder else None,
            "sandik_names": [s.name for s in sandiks],
        })
    return recipients


ANNOUNCEMENT_SUBJECT = "🔔 Yeni: Üyelerinize ödeme hatırlatması gitmeden bir gün önce haber alın"


# --- İş yürütme -----------------------------------------------------------------------------------

def _send_all(recipients, subject_of, render, send, dry_run, log, label, on_sent=None):
    result = {"sent": 0, "failed": 0, "recipients": len(recipients)}
    log(f"{label}{len(recipients)} kişiye gönderilecek")

    test_address = reminder.get_test_address()
    sleep_seconds = reminder.get_sleep_seconds()

    for index, data in enumerate(recipients):
        subject = subject_of(data)
        if test_address:
            subject = f"[TEST] {subject}"
        html = render(data)

        if dry_run:
            log(f"  - (kuru) {data['email_address']} <- {subject}")
            continue

        to_address = test_address or data["email_address"]
        try:
            send(to_address, subject, html)
        except Exception as e:
            result["failed"] += 1
            log(f"  ! {to_address} gönderilemedi: {type(e).__name__} -> {e}")
        else:
            result["sent"] += 1
            log(f"  - {to_address} gönderildi")
            if on_sent:
                on_sent(data)

        if sleep_seconds and index < len(recipients) - 1:
            sleep(sleep_seconds)

    log(f"{label}bitti: {result['sent']} gönderildi, {result['failed']} başarısız")
    return result


def run_manager_reminder(render, send, today: date = None, dry_run=False, log=print, url_builder=None,
                         preference_url_builder=None):
    """Bugün, yarın hatırlatma alacak üyeleri yöneticilere bildirir.

    Döner: `{"sent": int, "failed": int, "recipients": int}`
    """
    with db_session:
        recipients = collect_recipients(today=today, url_builder=url_builder,
                                        preference_url_builder=preference_url_builder)
    return _send_all(recipients=recipients, subject_of=build_subject, render=render, send=send,
                     dry_run=dry_run, log=log, label="[yönetici] ")


def run_announcement(render, send, today: date = None, dry_run=False, log=print, preference_url_builder=None,
                     force=False):
    """Özelliğin duyurusunu henüz almamış yöneticilere bir kez gönderir.

    `force` verilmezse yalnızca `ANNOUNCEMENT_LAST_DAY`e kadar çalışır (gecelik iş). Gönderilen kişi
    işaretlenir; kuru çalıştırma ve test adresine gönderim işaretlemez (gerçek kişiye gitmedi).
    """
    today = today or date.today()
    if not force and today > ANNOUNCEMENT_LAST_DAY:
        return {"sent": 0, "failed": 0, "recipients": 0}

    with db_session:
        recipients = collect_announcement_recipients(preference_url_builder=preference_url_builder)

    mark = None
    if not reminder.get_test_address():
        def mark(data):
            with db_session:
                auth_db.mark_manager_reminder_announced(web_user=WebUser[data["web_user_id"]], when=datetime.now())

    return _send_all(recipients=recipients, subject_of=lambda _: ANNOUNCEMENT_SUBJECT, render=render, send=send,
                     dry_run=dry_run, log=log, label="[duyuru] ", on_sent=mark)
