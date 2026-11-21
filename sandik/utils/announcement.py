"""Yeni özellik duyuruları: her duyuru, hedef kitlesindeki her kişiye **bir kez** e-postayla gider.

Kullanıcı istedi: yeni özellikler için ara ara duyuru atılacak, ama her duyuru için ayrı, kalıcı kod
istenmedi. Bu yüzden altyapı genel, duyuru ise veridir:

- Bir duyuru = `ANNOUNCEMENTS` listesine bir `Announcement` satırı + `email/duyurular/<anahtar>.html` şablonu.
- Gecelik iş (`clock.py`) son günü geçmemiş bütün duyuruları dener; kişi başına "gönderildi" işareti
  `WebUser.preferences["announcements"][<anahtar>]`a yazıldığı için ikinci kez gitmez. Deploy'dan sonraki ilk
  gece gider; yeni yetki alan biri son güne kadar o gece alır.
- Son gün geçince duyuru hiçbir şey yapmaz; listeden satırı ve şablonu silmek temizliktir (işaretler zararsız
  kalır). **Anahtar sonradan değiştirilmez**: değişirse herkese ikinci kez gider.

Hedef kitleler (`AUDIENCES`) yeniden kullanılır; kişiye göre ilgili sandıkların listesini döner, boşsa o kişiye
gönderilmez. "İşleyen sandık" istatistik sayfasının ölçütüdür (`intro/utils.py → collect_sandik_facts`: etkin,
en az 3 aktif üye, en az 20 para hareketi, son 6 ayda hareket): açılıp hiç kullanılmamış deneme sandıklarının
yöneticilerine duyuru gitmesin diye.

Gönderim `reminder.py` ile aynı kalıptadır: kapatma valfi ve test adresi ortaktır (`SANDIKv2_REMINDER_EMAIL_*`),
`render`/`send` dışarıdan verilir, veri `db_session` içinde düz sözlüklere çevrilir. Başarısız gönderim ve test
adresine gönderim işaretlenmez (gerçek kişiye gitmedi).
"""
from dataclasses import dataclass
from datetime import date, datetime
from time import sleep
from typing import Callable, Optional

from pony.orm import db_session

from sandik.auth import db as auth_db
from sandik.utils import reminder
from sandik.utils.db_models import WebUser
from sandik.utils.sorting import turkish_sort_key


# --- Hedef kitleler -------------------------------------------------------------------------------
# Her biri `(web_user, context) -> [sandık, ...]`; `context` bir çalıştırma boyunca paylaşılan önbellektir.

def _running_sandik_ids(context):
    if "running_sandik_ids" not in context:
        from sandik.intro import utils as intro_utils
        context["running_sandik_ids"] = {f["sandik"].id for f in intro_utils.collect_sandik_facts()
                                         if f["is_recently_active"]}
    return context["running_sandik_ids"]


def managers_of_running_sandiks(web_user, context):
    """İşleyen sandıklarda işlem girme yetkisi (yönetici ya da yazma yetkili) olanlar."""
    running = _running_sandik_ids(context)
    return [s for s in web_user.get_managed_sandiks() if s.id in running]


def members_of_running_sandiks(web_user, context):
    """İşleyen sandıklarda etkin üyeliği olanlar."""
    running = _running_sandik_ids(context)
    sandiks = {m.sandik_ref for m in web_user.members_set if m.is_active and m.sandik_ref.id in running}
    return sorted(sandiks, key=lambda s: turkish_sort_key(s.name))


AUDIENCES = {
    "isleyen_sandik_yoneticileri": managers_of_running_sandiks,
    "isleyen_sandik_uyeleri": members_of_running_sandiks,
}


# --- Duyurular ------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Announcement:
    key: str  # kalıcı kimlik; "gönderildi" işareti bununla tutulur, değiştirilmez
    subject: str
    audience: str  # AUDIENCES anahtarı
    last_day: date  # bu güne kadar (dahil) gecelik iş dener
    # İsteğe bağlı: True dönerse kişi atlanır (ör. özelliği zaten açmış)
    skip: Optional[Callable[[WebUser], bool]] = None

    @property
    def template(self):
        return f"email/duyurular/{self.key}.html"


ANNOUNCEMENTS = (
    Announcement(
        key="yonetici_on_hatirlatmasi",
        subject="🔔 Yeni: Üyelerinize ödeme hatırlatması gitmeden bir gün önce haber alın",
        audience="isleyen_sandik_yoneticileri",
        last_day=date(2026, 12, 31),
        skip=lambda web_user: bool(web_user.get_manager_reminder_sandik_ids()),
    ),
)

SENT_KEY = "announcements"


def get(key):
    return next((a for a in ANNOUNCEMENTS if a.key == key), None)


def active_announcements(today: date = None):
    today = today or date.today()
    return [a for a in ANNOUNCEMENTS if today <= a.last_day]


def was_sent(web_user, key):
    sent = (web_user.preferences or {}).get(SENT_KEY)
    return isinstance(sent, dict) and key in sent


def collect_recipients(announcement: Announcement, preference_url_builder=None):
    """Duyuruyu henüz almamış hedef kişiler. `db_session` içinde çağrılmalıdır."""
    audience = AUDIENCES[announcement.audience]
    context = {}
    recipients = []
    for web_user in WebUser.select().order_by(WebUser.id):
        if not web_user.email_address or not web_user.is_active or was_sent(web_user, announcement.key):
            continue
        if announcement.skip and announcement.skip(web_user):
            continue
        sandiks = audience(web_user, context)
        if not sandiks:
            continue
        recipients.append({
            "web_user_id": web_user.id,
            "email_address": web_user.email_address,
            "name_surname": web_user.name_surname,
            "sandik_names": [s.name for s in sandiks],
            "preference_url": preference_url_builder(web_user) if preference_url_builder else None,
        })
    return recipients


def run_announcement(announcement: Announcement, render, send, dry_run=False, log=print,
                     preference_url_builder=None):
    """Bir duyuruyu henüz almamış hedef kişilere gönderir. Döner: `{"sent", "failed", "recipients"}`."""
    with db_session:
        recipients = collect_recipients(announcement, preference_url_builder=preference_url_builder)

    label = f"[duyuru: {announcement.key}] "
    result = {"sent": 0, "failed": 0, "recipients": len(recipients)}
    log(f"{label}{len(recipients)} kişiye gönderilecek")

    test_address = reminder.get_test_address()
    sleep_seconds = reminder.get_sleep_seconds()
    for index, data in enumerate(recipients):
        subject = f"[TEST] {announcement.subject}" if test_address else announcement.subject
        html = render(data, template=announcement.template)

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
            if not test_address:
                with db_session:
                    auth_db.mark_announcement_sent(web_user=WebUser[data["web_user_id"]], key=announcement.key,
                                                   when=datetime.now())

        if sleep_seconds and index < len(recipients) - 1:
            sleep(sleep_seconds)

    log(f"{label}bitti: {result['sent']} gönderildi, {result['failed']} başarısız")
    return result


def run_announcements(render, send, today: date = None, dry_run=False, log=print, preference_url_builder=None):
    """Gecelik iş: son günü geçmemiş bütün duyurular."""
    for announcement in active_announcements(today):
        run_announcement(announcement, render=render, send=send, dry_run=dry_run, log=log,
                         preference_url_builder=preference_url_builder)
