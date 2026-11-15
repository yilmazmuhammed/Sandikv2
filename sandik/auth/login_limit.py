"""
Giriş denemesi sınırı (süreç belleğinde).

Bu dosya `apartman`, `cuzdan`, `davetiye` ve `family_tree` uygulamalarında **birebir aynıdır** (hiçbir şey import
etmez, uygulamaya özel satırı yoktur); birinde yapılan değişiklik diğerlerine de taşınmalıdır. Denetim:
`cmp apartman/apartman/auth/login_limit.py cuzdan/cuzdan/auth/login_limit.py`.

* Aynı IP'den `LOCK_SECONDS` içinde `MAX_FAILED_PER_IP` hatalı denemeden sonra o IP'den giriş denenemez.
* Aynı e-posta adresine (hangi IP'den olursa olsun) `LOCK_SECONDS` içinde `MAX_FAILED_PER_ADDRESS` hatalı
  denemeden sonra o adresle giriş denenemez: IP değiştirerek tek hesaba parola denenmesin.
* Kayıtlı olmayan adres de sayılır ve kilit mesajı tektir: mesajdan hesabın var olup olmadığı anlaşılmaz.
* Kilitliyken doğru parola da reddedilir ve deneme sayılmaz (kilit uzamaz; süre ilk sayılan denemeden işler).
* Başarılı giriş o adresin sayacını ve o IP'nin **bu adres için** yaptığı hatalı denemeleri siler. IP'nin
  başka adreslere yaptığı denemeler silinmez: yoksa saldırgan arada kendi hesabıyla giriş yapıp IP sayacını
  sıfırlayarak çok sayıda hesaba parola deneyebilirdi.
* Süresi geçen kayıtlar her çağrıda o anahtar için, `SWEEP_SECONDS`te bir de bütün sözlükte temizlenir; bir
  anahtarda en fazla sınır kadar kayıt tutulur (kilitliyken yeni kayıt eklenmez). Sözlükler sınırsız büyümez.

Sayaçlar her işçi süreçte ayrıdır ve uygulama yeniden başlayınca sıfırlanır.
"""
import time
from threading import Lock

MAX_FAILED_PER_IP = 10
MAX_FAILED_PER_ADDRESS = 10
LOCK_SECONDS = 15 * 60
SWEEP_SECONDS = 60

LOCKED = f"Çok fazla hatalı giriş denemesi yapıldı. Lütfen {LOCK_SECONDS // 60} dakika sonra tekrar deneyiniz."

# ip -> [(zaman, adres), ...]; adres -> [zaman, ...]
_by_ip = {}
_by_address = {}
_lock = Lock()
_last_sweep = [0.0]


class LoginLocked(Exception):
    def __init__(self, message=LOCKED):
        super().__init__(message)


def _now() -> float:
    return time.time()


def _address_key(email_address) -> str:
    return (email_address or "").strip().lower()


def _fresh_ip(ip, now):
    entries = [entry for entry in _by_ip.get(ip, ()) if now - entry[0] < LOCK_SECONDS]
    if entries:
        _by_ip[ip] = entries
    else:
        _by_ip.pop(ip, None)
    return entries


def _fresh_address(address, now):
    moments = [moment for moment in _by_address.get(address, ()) if now - moment < LOCK_SECONDS]
    if moments:
        _by_address[address] = moments
    else:
        _by_address.pop(address, None)
    return moments


def _sweep(now):
    if now - _last_sweep[0] < SWEEP_SECONDS:
        return
    _last_sweep[0] = now
    for ip in list(_by_ip):
        _fresh_ip(ip, now)
    for address in list(_by_address):
        _fresh_address(address, now)


def is_locked(ip, email_address) -> bool:
    now = _now()
    address = _address_key(email_address)
    with _lock:
        _sweep(now)
        return (len(_fresh_ip(ip, now)) >= MAX_FAILED_PER_IP
                or len(_fresh_address(address, now)) >= MAX_FAILED_PER_ADDRESS)


def check(ip, email_address):
    """Kilitliyse `LoginLocked` fırlatır; parola denetlenmeden önce çağrılır"""
    if is_locked(ip, email_address):
        raise LoginLocked()


def record_failure(ip, email_address):
    now = _now()
    address = _address_key(email_address)
    with _lock:
        ip_entries = _fresh_ip(ip, now)
        if len(ip_entries) < MAX_FAILED_PER_IP:
            _by_ip[ip] = ip_entries + [(now, address)]
        address_moments = _fresh_address(address, now)
        if len(address_moments) < MAX_FAILED_PER_ADDRESS:
            _by_address[address] = address_moments + [now]


def record_success(ip, email_address):
    address = _address_key(email_address)
    with _lock:
        _by_address.pop(address, None)
        entries = [entry for entry in _by_ip.get(ip, ()) if entry[1] != address]
        if entries:
            _by_ip[ip] = entries
        else:
            _by_ip.pop(ip, None)


def reset():
    """Bütün sayaçları siler (testler için)"""
    with _lock:
        _by_ip.clear()
        _by_address.clear()
        _last_sweep[0] = 0.0
