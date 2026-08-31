# CLAUDE.md — Sandıkv2

Bu dosya, bu depoda çalışan Claude Code için rehberdir. **Yeni bir şey öğrenildiğinde/değiştiğinde
bu dosya güncel tutulmalıdır.**

Bu depo, `myilmaz_tr` ana deposunun bir git submodule'üdür. Ana deponun `CLAUDE.md` dosyasında
yönlendirme, ortam değişkenleri ve ortak kalıplar anlatılır; burada yalnızca Sandıkv2'ye özel
bilgiler var.

## Uygulama ne yapar?

Bir "sandık" (imece usulü ortak kasa) yönetim uygulamasıdır. Üyeler her ay **aidat** öder, biriken
paradan **borç** alır, borcu **taksitler** hâlinde geri öder.

## Alan modeli (`sandik/utils/db_models.py`)

Tüm entity'ler tek dosyadadır. Para alanlarının hepsi `Decimal`'dir.

```
Sandik ──< Member ──< Share ──< Contribution        (aidat, dönem = "YYYY-MM")
   │         │          └────< Debt ──< Installment (borç ve taksitleri)
   │         └───────< MoneyTransaction ──< SubReceipt
   │                                          │
   └─ SandikRule (kural formülleri)           └─ Retracted / PieceOfDebt
```

Kilit kavramlar:

- **MoneyTransaction**: üyenin para girişi (`TYPE.REVENUE`) veya çıkışı (`TYPE.EXPENSE`). Ham para
  hareketi; neye harcandığı **SubReceipt**'lerle belirlenir.
- **SubReceipt**: bir MoneyTransaction'ın bir aidata / taksite / borca / retracted'a dağıtılan
  parçası. Bir SubReceipt tam olarak **bir** referansa bağlı olmak zorundadır (`before_insert`).
- **"İşleme konmamış para" (undistributed)**: `mt.amount - Σ sub_receipt.amount`. Üyenin yatırdığı
  ama henüz bir ödemeye dağıtılmamış parası. `is_fully_distributed` bunun türevidir.
- **Retracted**: işleme konmamış paranın üyeye geri verilmesi. İki SubReceipt üretir (biri gider
  işleminde, biri asıl gelir işleminde).
- **PieceOfDebt**: güven bağlı sandıkta bir borcun "kimin parasından" verildiğini tutar.
- **Sandık tipleri**: `CLASSIC` (klasik) ve `WITH_TRUST_RELATIONSHIP` (güven bağlı). Borç limiti ve
  PieceOfDebt davranışı tipe göre değişir — yeni kod yazarken **iki tipi de** düşün.
- **SandikRule**: borç limiti / taksit sayısı / hisse sayısı formülleri. `cexprtk` ile değerlendirilir,
  `{uye_toplam_aidat}` gibi değişkenler içerir. Kural yoksa `NoValidRuleFound` atılır.
- **Log**: neredeyse her yazma işlemi `db.py` katmanında bir `Log` satırı da oluşturur.
- **`WebUser.preferences`**: kişiye ait tercihler, `Member.preferences` ile aynı kalıpta bir Json
  sütunu. Şimdilik yalnızca ödeme hatırlatma günlerini tutar; yeni tercihler için sütun/tablo
  eklemek gerekmez, Json'a anahtar eklenir. Anahtar adları ve doğrulama `ReminderPreference`
  sınıfındadır — **bu bir entity değildir**, yalnızca sabit ve yardımcı taşır. Açık/kapalı için
  ayrı anahtar **yoktur**: `0` = istemiyorum, `1`-`28` = ayın o günü. Anahtarı olmayan kullanıcı
  varsayılanları (1 ve 25) kullanır, yani mevcut ve yeni kullanıcılar baştan mail alır.
  Yazma yalnızca `auth/db.py` → `update_reminder_preference` üzerinden yapılır; o da
  `update_member_preferences` gibi Json'daki diğer anahtarlara dokunmaz.

## Modüller (`sandik/`)

| Modül | Yol öneki | İş |
|---|---|---|
| `auth` | `/` | Kayıt/giriş, `WebUser`, yetkiler |
| `general` | `/` | Ana sayfa, bildirimler, banka hesapları, loglar |
| `intro` | `/` | Herkese açık tanıtım sayfaları (tanıtım, kullanım kılavuzu, istatistikler) |
| `sandik` | `/sandik/` | Sandık, üye, hisse, güven bağı, kurallar |
| `transaction` | `/sandik/<id>/` | Para giriş/çıkışı, aidat, borç, taksit |
| `website_transaction` | `/websitesi-masraflari/` | Sitenin kendi gider kaydı |
| `backup` | `/yedek/` | Veritabanının JSON olarak dışa/içe aktarımı |
| `paw` | `/paw/` | PythonAnywhere: git pull + webapp reload |
| `bot` | — | E-posta (`email_bot.py`), SMS (NetGSM), Kuveyt Türk API |
| `bugfixs` | — | Tek seferlik veri düzeltme scriptleri (`.env`'i, yani **gerçek veritabanını** kullanır) |
| `blueprint_template` | — | Yeni modül açarken kopyalanacak iskelet |

`sandik/utils/clock.py`: **her gece 01:01'de** çalışıp biten zamanlanmış görev (PythonAnywhere
Tasks). Aidat oluşturur ve sırası gelen ödeme hatırlatma e-postalarını gönderir — bkz.
"Gecelik işler ve hatırlatma e-postaları". (Procfile'daki `clock` satırı Heroku dönemindendir;
PythonAnywhere Procfile'ı yok sayar.)

## Gecelik işler ve hatırlatma e-postaları

`sandik/utils/clock.py` PythonAnywhere'de zamanlanmış görev olarak **her gece 01:01'de** çalışır ve
biter. PythonAnywhere web uygulamalarında **thread desteklenmez** ve istek/yanıt döngüsünden uzun
yaşayan alt süreçler öldürülür; bu yüzden dönemsel işlerin yeri Flask sürecinin içi değil bu
betiktir. Betik her gece çalıştığı için "hangi işin sırası geldi" kararı da burada verilir.

| İş | Ne zaman | Nerede |
|---|---|---|
| Vadesi gelmiş aidatları oluşturma | her çalıştırmada (idempotent) | `clock.beginning_of_each_month` |
| Ay başı hatırlatması — bu ayın ödemeleri | kişinin seçtiği gün (varsayılan **1**) | `reminder.KIND_MONTH_START` |
| Ay sonu hatırlatması — bu ay + gelecek ay | kişinin seçtiği gün (varsayılan **25**) | `reminder.KIND_NEXT_MONTH` |

**Gün, kullanıcı tercihidir** (`ReminderPreference`); herkes iki hatırlatmayı da ayın istediği
gününde alabilir ya da hiç almayabilir. Tercihi olmayan kullanıcı varsayılanları kullanır, yani
sistem baştan herkese gönderir.

**Mükerrer gönderim, gün karşılaştırmasının tam eşitlik olmasıyla engellenir; veritabanında "bu
dönem gönderildi" kaydı tutulmaz.** Kişinin seçtiği gün ayda bir kez geldiği için iş o kişi için
ayda bir kez koşar. Karşılaştırma **aralığa çevrilmemelidir**: aralık, işin aynı ay içinde arka
arkaya birkaç gece koşması demektir ve o zaman kayıt tutmak zorunlu hâle gelir. Gün seçenekleri
**1-28** ile sınırlıdır (`ReminderPreference.MAX_DAY`): 29-31 seçilebilseydi o gün olmayan aylarda
hatırlatma hiç gitmezdi. İki hatırlatma aynı güne denk gelirse **tek e-posta** gönderilir (gelecek
ay dahil edilir).

Bunun bedeli, o gece görev hiç çalışmazsa o ayın hatırlatmasının kaçmasıdır. İki şey bu riski
küçültür: `clock.py` adımları birbirinden yalıtır (aidat oluşturma patlasa bile hatırlatma koşar,
bkz. `_step`) ve herhangi bir adım hata verince betik sıfırdan farklı çıkar — PythonAnywhere görev
çıktısını e-postayla gönderdiği için arıza görünür olur. Kaçan bir ay elle telafi edilir:
`python sandik/utils/clock.py --hatirlatma-ay-basi`.

**Görev saati gün sınırından uzak tutulmalıdır.** PythonAnywhere süreçleri UTC çalışır ve gün
kontrolü `date.today()` ile yapılır; 01:01 seçilmesi, görev birkaç dakika gecikse bile günün
değişmemesi içindir. `period_utils.current_period()` de aynı `date.today()`yi kullanır, böylece
e-postadaki "bu ay" üyenin sitede gördüğü "bu ay" ile aynı kalır.

### `sandik/utils/reminder.py`

- **Kişi başına tek e-posta.** Bir kişi birden fazla sandıkta üyeyse hepsi tek mailde bölüm bölüm
  listelenir (`general/utils.py` → `get_home_page_data` ile aynı yaklaşım).
- **Yalnızca ödemesi olan üyeye gönderilir.** `collect_reminder_data` hiç ödeme satırı bulamazsa
  `None` döner ve o kişi atlanır.
- Yeni sorgu yazılmaz: `transaction_utils.get_payments`, `member.total_of_undistributed_amount()`,
  `member.get_active_shares()` gibi mevcut yardımcılar kullanılır. `Member.web_user_ref`
  **`Optional`**'dır — `None` olan üyeler atlanmalıdır (`get_payments`'ın `order_by`'ı
  `p.member_ref.web_user_ref.name_surname` dereference eder ve patlar).
- **Gelecek ayın aidatı hesaplanır, veritabanına yazılmaz.** `create_due_contributions_for_share`
  aidatları yalnızca içinde bulunulan aya kadar oluşturur; ayın 25'inde gelecek ayın `Contribution`
  satırları henüz yoktur. Tutar `member.contribution_amount × aktif hisse` ile bulunur — bu,
  `transaction_db.create_contribution`'ın varsayılanıyla aynı formüldür, yani ayın 1'inde oluşacak
  kayıtla aynı sonucu verir. Kayıt zaten varsa (ör. elle oluşturulmuş) o hisse için satır üretilmez.
- Akış iki evrelidir: önce `db_session` içinde bütün veri **entity içermeyen düz sözlüklere**
  çevrilir (`collect_recipients`), sonra oturum kapalıyken şablon basılıp SMTP'ye çıkılır. Böylece
  `EmailBot`'un hata hâlindeki 60 sn'lik beklemeleri boyunca uzun bir veritabanı işlemi açık kalmaz.
- **`run_payment_reminder` kendisi mükerrer kontrolü yapmaz**, her çağrıldığında seçilen kişilere
  gönderir; engel `reminder_for_today()` içindeki tam gün eşitliğidir.
- İki kip vardır: `kind` verilmezse **gecelik kip** (`reminder_for_today`, herkesin kendi günü),
  verilirse **elle kip** (`reminder_for_kind`, günü yok sayar ama **kapatmış kullanıcıya yine
  göndermez**).
- E-postanın altındaki tercih bağlantısının adresi de `url_builder` gibi dışarıdan enjekte edilir
  (`preference_url_builder`); jeton üretmek uygulama bağlamı ister, testlerde `None` kalır.
- `render` ve `send` dışarıdan verilir; testler bu sayede Flask ve SMTP olmadan çalışır
  (`tests/test_payment_reminder.py`).

### E-posta gönderimi (`sandik/bot/email_bot.py`)

`SenderEmail`/`EmailBot` ham SMTP sarmalayıcısıdır; **aynı dosyanın sonundaki** modül seviyesi
yardımcılar (`create_email_bot_from_env`, `email_bot_session`, `send_html_email`,
`send_single_html_email`) uygulamanın tek kapısıdır. `SANDIKv2_EMAIL_BOT_*` anahtarları **başka
hiçbir yerde** `os.getenv` ile okunmaz.

- **Her mesajda tek alıcı.** `EmailBot.create_email_message` verilen adresleri virgülle `To:` başlığına
  dizer; toplu gönderimde bu bütün üyelerin adreslerini birbirine gösterirdi.
- Toplu iş için `email_bot_session()` / `_LazyEmailSender`: tek bağlantı açılır, hepsi onun üzerinden
  gider. Bağlantı **ilk gönderimde** açılır — betik her gece çalışıp çoğu gece hiç mail göndermez.
- Bir alıcıdaki hata döngüyü kesmez: kayda yazılıp sıradakine geçilir, sonuçta kaç tanesinin
  gönderilemediği raporlanır.

### Kullanıcı tercihi (`/tercihlerim`, `/tercih/<token>`)

Aynı formun iki giriş noktası vardır (`auth/page.py` → `_reminder_preference_page_base`):

| Yol | Kim | Kabuk |
|---|---|---|
| `/tercihlerim` | giriş yapmış kullanıcı (üst menü → "E-posta tercihlerim") | `utils/layout.html` |
| `/tercih/<token>` | e-postadaki bağlantı, **giriş gerektirmez** | `intro/_layout.html` |

- Jetonlu sayfa yönetim paneli kabuğunu kullanamaz (`utils/layout.html` `current_user` ister), bu
  yüzden tanıtım kabuğundan türer. Form gövdesi ikisinde ortaktır:
  `auth/parts/reminder_preference_form.html`. Genel form partial'ı (`utils/parts/form.html`)
  kullanılmaz, çünkü alanları "istiyorum + hangi gün" diye ikişerli gruplamak gerekiyor; iki kabuğun
  CSS'i ortak olmadığı için stiller o parçanın içindedir.
- **Jetonun süresi yoktur** (parola sıfırlamanın aksine): bağlantı kullanıcının posta kutusunda
  duruyor, aylar sonra da çalışmalı. Karşılığında yetkisi dardır — yalnızca hatırlatma günlerini
  değiştirir, hiçbir kişisel veri göstermez. Yükteki `email_address` doğrulanır, yani adres
  değişirse eski bağlantılar düşer (`auth/utils.py` → `get_web_user_from_reminder_preference_token`).
- **Adresler genel, etiketler geçici.** Sayfada bugün yalnızca hatırlatma günleri olduğu için
  kullanıcıya görünen etiketler ve fonksiyon adları ("E-posta ... tercihlerim",
  `reminder_preference_*`) e-postaya özeldir; **e-postayla ilgisi olmayan ilk tercih eklendiğinde**
  bunlar "Kullanıcı tercihlerim" / `preference_*` olarak yeniden adlandırılmalıdır. İkisi de ucuz.
  **Adresler ise (`/tercihlerim`, `/tercih/<token>`) bilerek baştan genel tutuldu, çünkü sonradan
  değiştirilemezler**: `/tercih/<token>` gönderilmiş e-postaların içinde, kullanıcıların posta
  kutusunda süresiz durur. Zorunlu kalınırsa eski adres kalıcı olarak yenisine yönlendirilmeli.
- **Veritabanında tek sayı, arayüzde iki seçenek.** Çeviri yalnızca `auth/forms.py` →
  `ReminderPreferenceForm.to_days()` / `fill_from_days()` içindedir; sayfa katmanı iki temsili
  birbirine karıştırmaz. Kutu işaretsizken gün seçici JS ile soluklaşıp `disabled` olur; gönderim
  anında tekrar açılır (disabled alan gönderilmez).
- **Bu sayfadaki göster/gizle JS'i bilerek jQuery değil, düz JavaScript'tir.** Depodaki alışılmış
  kalıp, sayfanın `js_block2` bloğunda jQuery ile `.toggle()` çağırmaktır (ör.
  `transaction/add_money_transaction_by_manager_page.html`), ama o kalıp burada kullanılamaz: form
  gövdesi iki kabukta paylaşılıyor ve **`intro/_layout.html` jQuery yüklemez** (yalnızca
  `utils/layout.html` yükler), dolayısıyla jQuery kullanılsa jetonlu sayfada sessizce çalışmazdı.
  Ortak, yeniden kullanılabilir bir göster/gizle yardımcısı `custom.js`'te yoktur.

### Şema taşımaları (`sandik/utils/migrations/`)

Pony eksik **tabloyu** oluşturur ama var olan tabloya **sütun eklemez**; dahası eksik sütunu görünce
`generate_mapping()`in **kendisi** `OperationalError: no such column` fırlatır. Bu çağrı `db_models`
import edilirken çalıştığı ve ana depodaki `app.py` dört uygulamayı da eager import ettiği için,
sütun eklenmeden kod güncellenirse **bütün site (myilmaz.tr dahil) açılmazdı**. Bu yüzden taşımalar
`db.bind()` ile `db.generate_mapping()` **arasında**, uygulama her açıldığında kendiliğinden çalışır:

```python
DATABASE_PROVIDER, DATABASE_PARAMS = migrations.database_target_from_env()
db.bind(provider=DATABASE_PROVIDER, **DATABASE_PARAMS)
if migrations.is_enabled():
    migrations.run_migrations(provider=DATABASE_PROVIDER, params=DATABASE_PARAMS, log=...)
db.generate_mapping(create_tables=True)
```

Böylece deploy **elle bir adım gerektirmez**: `/paw` → git pull → reload yeter.

- **Yeni taşıma `steps.py` listesinin sonuna eklenir**, var olanlar değiştirilmez. `db_models.py`
  içindeki model de güncellenmelidir: taşıma var olan veritabanlarını, model sıfırdan kurulanları
  belirler; ikisi aynı sonucu vermelidir.
- Uygulananlar `schema_migration` tablosunda tutulur, her taşıma bir kez çalışır. İşlemler ayrıca
  kendi kontrolünü de yapar (sütun varsa eklemez, tablo yoksa atlar), yani elle müdahale edilmiş
  veya sıfırdan kurulmuş veritabanlarında da güvenlidir.
- Çok işçili sunucuda iki süreç aynı anda taşıma denerse, kaybeden kaydı görüp sessizce atlar.
- Hata **yukarı fırlatılır**: uygulamanın yarım şemayla açılmaması gerekir.
- `database_target_from_env()` hem `db.bind()` hem taşımalar tarafından kullanılır; ikisinin farklı
  veritabanına bakması "taşıma çalıştı ama uygulama eski şemayı görüyor" hatasına yol açardı.
- **MySQL'de tablo/sütun adları küçük harftir.** Pony'nin MySQL sağlayıcısı bütün tanımlayıcıları
  `lower()`lar (`pony/orm/dbproviders/mysql.py` → `normalize_name`), yani `WebUser` entity'sinin
  tablosu MySQL'de `webuser`dır; sqlite ve postgres'te ad olduğu gibi kalır. Taşımalar tabloya
  adıyla eriştiği için `Backend.normalize()` / `qname()` aynı kuralı uygular ve **üretilen bütün
  SQL `qname()` ile yazılır**. Bu atlanırsa MySQL'de tablo "yok" görünür, işlemler sessizce
  atlanır, taşıma uygulanmış işaretlenir ve sütun hiç eklenmediği için uygulama
  `generate_mapping`de patlar. `steps.py`de elle SQL yazarken `RunSql`in fonksiyon biçimi
  kullanılmalıdır (`lambda b: ... b.qname("WebUser") ...`).
- **`RunSql`e `table=` verilmelidir.** `AddColumn`/`DropColumn` tablo yoksa kendiliğinden atlar ama
  `RunSql` körlemesine çalışır; sıfırdan kurulan veritabanında (henüz hiç tablo yokken) "table
  doesn't exist" ile patlar. `tests/test_migrations.py` her `RunSql` adımında bunu kontrol eder.
- `AddColumn`ın `column_type`/`default` alanları **sağlayıcıya göre sözlük** de alabilir. Pony `Json`
  mysql/sqlite'ta `JSON`, postgres'te `JSONB`'dir; ayrıca **MySQL JSON sütununa DEFAULT kabul etmez**,
  bu yüzden orada sütun NULL eklenip satırlar `RunSql` ile doldurulur ve sonra NOT NULL yapılır.
  (Bu iki eklenti `family_tree`deki sürümde yoktur.)
- Kapatmak için `SANDIKv2_AUTO_MIGRATE='0'`; o zaman elle: `python scripts/migrate.py`
  (`--durum` / `--kuru-calistir` seçenekleri vardır).
- **Testlerde kapalıdır**: `tests/conftest.py` `SANDIKv2_AUTO_MIGRATE=0` yazar. `Database.bind`
  yaması yalnızca Pony'nin bağlantısını yönlendirir; taşımalar kendi bağlantısını açar ve o,
  geliştiricinin gerçek `database.sqlite` dosyasına giderdi.

Paket `family_tree/family_tree/utils/migrations/` ile aynı tasarımdır. Her uygulama kendi klasörünün
dışına bağımlı olmadığı (ve Sandıkv2 ayrı bir submodule olduğu) için kod paylaşılmaz, **kopyalanır**;
birinde düzeltilen bir hata diğerine de taşınmalıdır.

### E-posta şablonları (`sandik/utils/templates/email/`)

Ortak kabuk **yalnızca `email/_layout.html`'de** tanımlıdır; yeni bir e-posta eklenirken kopyalanmaz,
`{% extends "email/_layout.html" %}` ile türetilip `email_content` bloğu doldurulur
(`intro/_layout.html` ile aynı kalıp). E-posta istemcilerinde harici CSS/JS ve
`url_for('static', ...)` çalışmadığı için: bütün stiller **satır içi**, düzen **tablo tabanlı**,
bağlantılar `_external=True` ile mutlaktır.

Tutarlar `tr_number_format` filtresiyle basılır; bu filtre `sandik/app.py` içinde tanımlı olduğu için
`clock.py` şablonu **kendi `create_app()` örneğinin app context'i içinde** basar. O örneğe
`SERVER_NAME` verilir (`_external=True` için gerekli) — web sürecine verilmez, yönlendirmeyi bozar.

### Elle çalıştırma

```bash
FLASK_DEBUG=1 ../venv/bin/python sandik/utils/clock.py --yardim
FLASK_DEBUG=1 ../venv/bin/python sandik/utils/clock.py --hatirlatma-ay-sonu --kuru --html=/tmp/onizleme.html
```

`--kuru` hiçbir şey göndermez ve **kapatma valfinden etkilenmez** (önizleme her zaman çalışsın diye);
`--html=<dosya>` üretilen e-postaların HTML'ini gözle kontrol için dosyaya yazar. Hatırlatma
seçenekleri (`--hatirlatma-ay-basi` / `--hatirlatma-ay-sonu`) gün kontrolünü atlar, yani ayın
herhangi bir gününde çalıştırılabilir — ama hatırlatmayı **kapatmış kullanıcılara yine gönderilmez**. `.env_debug`'da
`SANDIKv2_REMINDER_EMAIL_ENABLED="0"`dır: yerel çalıştırma yanlışlıkla gerçek üyelere mail atmasın.

### İlgili ortam değişkenleri

| Anahtar | Varsayılan | İş |
|---|---|---|
| `SANDIKv2_REMINDER_EMAIL_ENABLED` | `1` | Acil kapatma valfi (gerçek gönderimi durdurur) |
| `SANDIKv2_REMINDER_EMAIL_TEST_ADDRESS` | — | Doluysa bütün mailler bu adrese gider, konuya `[TEST]` eklenir |
| `SANDIKv2_REMINDER_EMAIL_SLEEP_SECONDS` | `2` | Gönderimler arası bekleme (Gmail hız sınırı) |
| `SANDIKv2_SERVER_NAME` | `sandikv2.myilmaz.tr` | `clock.py`'de mutlak adres üretmek için |
| `SANDIKv2_AUTO_MIGRATE` | `1` | `0` yapılırsa açılışta şema taşımaları çalışmaz (elle: `scripts/migrate.py`) |
| `SANDIKv2_EMAIL_BOT_SMTP_SERVER` | — | Boşsa adrese göre tahmin edilir (`SenderEmail.smtpserver_finder`) |

## Tanıtım sayfaları (`sandik/intro/`)

Giriş yapmadan görülebilen üç sayfa. Yönetim paneli düzenini (`utils/layout.html`) **kullanmazlar**;
kendi başına duran modern bir tanıtım sitesi görünümündeler.

| Yol | Şablon | İş |
|---|---|---|
| `/tanitim` | `about_page.html` | Sandık sistemi nedir, nasıl işler, kavramlar, sandık türleri |
| `/nasil-kullanilir` | `how_to_use_page.html` | Üye ve yönetici için adım adım kullanım kılavuzu + SSS |
| `/istatistikler` | `statistics_page.html` | Sistemin gerçek kullanım rakamları |

- **Ortak kabuk `templates/intro/_layout.html`'dedir**: `<head>`, üst menü, alt bilgi, renk
  değişkenleri ve bütün bileşen stilleri (kart, adım listesi, tablo, not kutusu, SSS akordiyonu,
  CTA) yalnızca orada tanımlıdır. Yeni bir tanıtım sayfası eklenirken bunlar kopyalanmaz;
  `{% extends "intro/_layout.html" %}` ile türetilip `hero_block` / `intro_content` (gerekiyorsa
  `intro_css_block`, `intro_js_block`) blokları doldurulur.
- **Tema:** açık palet `:root`, koyu palet `:root[data-theme="dark"]` altındadır; `data-theme`
  her zaman `<head>`'deki küçük script tarafından **ilk boyamadan önce** yazılır (kullanıcının
  seçimi varsa `localStorage["sandikv2-tema"]`, yoksa `prefers-color-scheme`). Bu yüzden CSS'te
  `prefers-color-scheme` medya sorgusu **yoktur** — koyu palet tek yerde durur, ikinci bir kopyayla
  senkron tutma derdi olmaz. Üst menüdeki `#theme-toggle` düğmesi temayı değiştirip seçimi
  `localStorage`a yazar; kullanıcı seçim yapmadıysa işletim sistemi teması anlık takip edilir
  (`matchMedia` change dinleyicisi). Düğmenin simgesi **basınca geçilecek** temayı gösterir
  (`.to-dark` / `.to-light`).
- Üzerine **beyaz yazı gelen dolu zeminler** (birincil düğme, logo kutusu) `--brand-2` değil
  `--brand-solid` kullanır: `--brand-2` karanlık temada açılır ve beyaz yazı okunmaz olur.
  `color-mix()` kullanılan yerlerde öncesine düz bir değer yazılır (desteklemeyen tarayıcıda kural
  tamamen düşer).
- **Sayfa geneli açık tonludur.** Hero ve CTA blokları koyu gradyan değil, `--hero-bg` ile tanımlı
  hafif renk yıkaması kullanır (karanlık temada koyu karşılığı); yazılar normal metin renginde.
  Bu yüzden koyu zemin için yazılmış `.btn-white` / `.btn-light` sınıfları **yoktur**; hero ve
  CTA düğmeleri de `.btn-primary` / `.btn-ghost` kullanır.
- Hero yüksekliği satır içi `style` ile değil sınıfla ayarlanır (`.hero-sm`, istatistik sayfasında
  `.stats-hero`): satır içi stil medya sorgularını ezip telefonda düzeltilemez hâle getiriyordu.
- **Giriş yapmamış ziyaretçi `/` adresinde giriş formu yerine `/tanitim`'e yönlendirilir**
  (`general/page.py` → `index_page`). Giriş/kayıt sayfalarının ve yönetim panelinin alt bilgisinde
  de üç sayfaya bağlantı vardır.
- Sayfalardaki metinler **son kullanıcıya** yazılmıştır: entity adları, ERRCODE mantığı gibi iç
  ayrıntılar anlatılmaz. Fiyat/ücret iddiası da yoktur (sistemde ödeme akışı yok, söz verilmesin).

### Mobil

**Siteye ağırlıklı olarak telefondan giriliyor; bu sayfalarda mobil görünüm birincil önceliktir.**
Bir değişiklikten sonra 375 px (ve tercihen 320 px) genişlikte kontrol edilmeli, sayfanın yatay
kaymadığı doğrulanmalıdır (`document.documentElement.scrollWidth == clientWidth`).

- Kırılım noktaları: `860px` (tek sütuna iner, üst menü hamburger olur) ve `700px` (telefon).
- **Tablolar telefonda yatay kaydırılmaz, satır satır dizilir** (`@media (max-width: 700px)` içinde
  `table.tbl` blok'a çevrilir, `thead` gizlenir). Başlık satırının anlamı kaybolmasın diye
  ikiden fazla sütunlu tablolarda hücrelere `data-label="Sütun adı"` yazılır; CSS bunu `::before`
  ile üstte küçük etiket olarak gösterir. İki sütunlu "anahtar → açıklama" tablolarında gerekmez.
- Telefonda hero ve CTA düğmeleri tam genişliğe yayılır, menü bağlantılarının dokunma alanı
  büyütülür; `code` etiketlerindeki `white-space: nowrap` kaldırılır (formül örnekleri taşıyordu).
- Tema düğmesi telefonda da hamburger menünün **içinde değil**, üst çubukta hamburgerin yanındadır
  (menüyü açmadan ulaşılsın diye). Menü telefonda `position: absolute` olduğu için akıştan çıkar;
  bu iki düğmeyi sağa yaslayan `margin-left: auto` bu yüzden `.theme-toggle` üzerindedir.

### İstatistiklerdeki "çöp veri" elemesi (`intro/utils.py`)

İstatistikler yalnızca **gerçekten kullanılan** sandıkları kapsar; deneme amacıyla açılıp bırakılmış
sandıklar ve hiçbir sandıkta üyeliği olmayan kullanıcılar sayılmaz. Ölçütler modül başındaki
sabitlerdedir ve **sayfanın altında kullanıcıya da açıklanır** — biri değişirse metin kendiliğinden
güncellenir (sabitler şablona veri olarak geçirilir), ama sabitin adı değişirse şablon da
güncellenmelidir.

| Sabit | Varsayılan | Anlamı |
|---|---|---|
| `MIN_ACTIVE_MEMBER_COUNT` | 3 | Sandığın en az bu kadar aktif üyesi olmalı |
| `MIN_MONEY_TRANSACTION_COUNT` | 20 | Sandıkta en az bu kadar para giriş/çıkışı olmalı |
| `RECENTLY_ACTIVE_MONTH_COUNT` | 6 | Son hareketi bu kadar ay içinde olan sandık "işleyen" sayılır |

Ayrıca sandığın `is_active` olması gerekir. Kullanıcı sayısı da bu sandıklara bağlıdır: yalnızca
elemeden geçen sandıkların en az birinde **aktif üyeliği olan** `WebUser`'lar sayılır.

- `collect_sandik_facts()` eleme için gereken üç sayımı sandığa göre gruplanmış üç sorguyla alır
  (sandık başına ayrı sorgu atmaz).
- `Debt` üzerinde tarih alanı yoktur; yıllara göre dağılımda borcun tarihi olarak
  `d.sub_receipt_ref.money_transaction_ref.date` kullanılır.
- Sonuç `STATISTICS_CACHE_DURATION` (15 dk) boyunca **süreç belleğinde** önbelleğe alınır; sayfa
  herkese açık olduğu için her istekte toplu sorgu çalışmasın diye. Önbellek her worker için
  ayrıdır. Site yöneticisi `?yenile=1` ile önbelleği atlayabilir. Dönen sözlük paylaşıldığı için
  **değiştirilmemelidir**.
- Sayfada kişiye ya da tek bir sandığa ait bilgi gösterilmez; hepsi toplam değerdir.

## Dikkat edilmesi gereken yerler

- **Para hesabında `int()`, `//`, `round()` kullanma.** Tutarlar `Decimal` ve kuruşlu olabilir.
  Bilinen sorunlu noktalar: `transaction/db.py` `create_piece_of_debts()` içindeki `//`,
  `db_models.py` `Debt.update_pieces_of_debt()` içindeki `int()`. Bunlar kuruşlu tutarlarda
  "ERRCODE 0017 / U-POD" hatalarına yol açabilir.
- **Silme sırası önemlidir.** Bir hisse veya üye kapatılırken iade edilecek tutar hesaplanmadan
  *önce* ödemesi tamamlanmamış aidatlar silinmelidir (`remove_unpaid_contributions`). Aksi hâlde
  kısmi ödenmiş bir aidata yatan para hem "ödenmiş aidat" hem de "işleme konmamış para" olarak iki
  kez iade edilir ve gider işlemi aşırı dağıtılıp **ERRCODE 0013** hatası alınır.
  (Bkz. `sandik/sandik/utils.py` → `remove_member_from_sandik`, `remove_share_from_member`.)
- **Invariant'lar**: bir işlem bittiğinde her MoneyTransaction için `get_undistributed_amount() >= 0`
  olmalı; sandıktan çıkarılan üyenin `get_balance()` değeri `0` olmalıdır. Yeni bir akış yazınca
  bunları kontrol et.
- **ERRCODE'lar** kullanıcıya gösterilen hata mesajlarında geçer; kodda `ERRCODE: 00xx` diye ara.
  `db_models.py` içinde bu kontrolleri susturmak için eklenmiş `return` satırları görürsen bunlar
  geçici çözümdür — kök nedeni bulup kaldır.
- `Sandikv2Exception.detect_caller_function_name()` `inspect.stack()` kullanır; frame'in kaynak
  kodu okunamazsa (`code_context is None`) gerçek hata maskelenebilir.
- **Entity hook'ları (`before_insert` / `after_insert`) yedekten geri yüklemede çalıştırılmaz.**
  Bu hook'lar "tek bir işlem yapılırken" geçerli iş kurallarını kontrol eder; geri yüklemede satırlar
  tamamlanmış bir anlık görüntü olarak yazıldığı için kurallar satır satır sağlanmaz. Örnek:
  `PieceOfDebt.before_insert` (ERRCODE 0018) borç verenin bakiyesinin verdiği borçtan büyük olmasını
  ister — borç geri ödendikten sonra bu doğru değildir, dolayısıyla geçmiş satır tekrar yazılamaz.
  `backup/db.py` → `entity_hooks_disabled()` bu yüzden vardır; türetilmiş alanlar yükleme sonrası
  `recalculate_derived_fields_for_all_rows()` ile topluca hesaplanır. Bu aşamada tutarsızlık
  bulunursa `InconsistentBackupData` fırlatılır ve **yükleme tamamen geri alınır**: tutarsız bir
  yedeği yükleyip uyarmaktansa hiç yüklememek tercih edilir. `backup/page.py` bu durumda
  `rollback()` çağırıp tutarsızlıkları ekranda listeler.
- **Kaynağa id ile erişen her yerde sandık kapsamı kontrol edilmelidir.** `requirement.py`
  dekoratörleri (`member_required`, `sandik_rule_required`, `money_transaction_required`,
  `contribution_required`) kaydı `sandik_ref=g.sandik` ile çeker; API'ler de `member` gibi query
  parametrelerini aynı şekilde daraltır. Aksi halde bir sandıkta yetkisi olan kullanıcı, adresteki
  sandık kendisininken başka sandığın kaydını okuyabilir/silebilir. Yeni bir dekoratör veya API
  yazarken bu filtreyi atlama.
- **Form alan adları entity sütun adlarıyla birebir aynı olmalıdır.** `page.py` katmanı
  `flask_form_to_dict()` çıktısını doğrudan entity'ye `**kwargs` olarak geçirir; uyuşmayan bir ad
  Pony'de `TypeError: Unknown attribute` (500) verir, eksik kalan `boolean_fields` anahtarı ise
  sessizce hep `False` olur. (`SandikAuthorityForm.is_admin` bu yüzden `is_primary` değildir.)
- **`Sandikv2UtilsException` türevlerinde `errcode` verilmezse** üst sınıftaki
  `0 < errcode < 1000` kontrolü asıl mesajı yok edip boş bir `ErrcodeException` fırlatır. Varsayılan
  bu nedenle `1`'dir; yeni istisna sınıflarında varsayılanı `0` bırakma.
- **Taksitlendirmede yuvarlama her adımda kalan tutar üzerinden yapılmalıdır**
  (`create_installments_of_debt`). Sabit bir taksit tutarı yukarı yuvarlanınca borç, son taksitlere
  sıra gelmeden bitebilir (ör. 100₺ / 30 taksit). Kural sıralamasında da (`raise/lower_order_of_
  sandik_rule`) komşu kural `order±1` ile aranmaz: silme sonrası boşluk kalabilir, komşu sıraya göre
  en yakın kayıt seçilir.
- **İstek başına değişen sözlükler modül seviyesinde tutulmamalı ya da kopyalanmalıdır.**
  `app.py` içindeki `HTTP_ERRORS` kopyalanmadan güncellenirse bir isteğin özel hata mesajı sonraki
  isteklere sızar.
- Pony ORM sorguları lambda içinde entity metodu çağırabilir (`c.get_unpaid_amount() > 0`); bunlar
  SQL'e çevrilir, dolayısıyla metot gövdesi SQL'e çevrilebilir olmalıdır.
- **Onay (yes/no) soruları için `window.confirm()` kullanılmaz.** Ortak tek bir Bootstrap 3 modal
  (`utils/parts/confirm_dialog.html`, `layout.html`'e include edilir; her sayfada tek örnek) ve
  `custom.js` → `showConfirmDialog(message, options)` kullanılır. `confirm()`'in aksine **asenkron**
  çalışır ve boolean değil, `CONFIRM_DIALOG_RESULT` içinden **üç** değerden biriyle çözülen bir
  Promise döndürür:
  - `CONFIRM` — onay düğmesi (varsayılan "Evet", `options.confirmText`)
  - `REJECT` — reddetme düğmesi (varsayılan "Vazgeç", `options.rejectText`)
  - `DISMISS` — X / Esc / karartılmış alan

  `REJECT` ile `DISMISS`'in ayrı olması bilinçlidir: bazı akışlarda "hayır" da bir işlem yapar,
  pencereyi kapatmak ise işlemi tamamen iptal eder. Bu yüzden reddetme düğmesinde `data-dismiss`
  **yoktur** (olsaydı X'ten ayırt edilemezdi) — kapatmayı `custom.js` yapar. İki seçenekli basit
  onaylarda `REJECT` ve `DISMISS` aynı şekilde ele alınır; kalıp `if (result === CONFIRM_DIALOG_
  RESULT.CONFIRM)` şeklinde yazılır (`if (result)` yazılmamalı, üç değer de truthy string'dir).

  İki kullanım kalıbı:
  - **Onaylı link** — `macros.html` → `button()` / `switch_button()` makrolarındaki `confirm_msg`
    parametresi hâlâ aynı şekilde kullanılır (bunlar `<a class="dialog-confirm"
    confirm-message="...">` üretir); `custom.js` bu linkin tıklamasını yakalayıp `preventDefault` +
    `showConfirmDialog()` ile yalnızca `CONFIRM` sonucunda `window.location.href` ile yönlendirir,
    `REJECT`/`DISMISS`'te hiçbir şey yapmaz. Yeni bir yerde onaylı link gerekiyorsa bu makrolar
    kullanılmalı, `confirm()`'e geri dönülmemeli.
  - **Onaya bağlı form submit'i** — bkz. `transaction/add_money_transaction_by_manager_page.html`
    (`askAndSubmit()`): iki düğme de formu gönderir (yalnızca gizli alanın `true` olup olmaması
    değişir), X ise formu **hiç göndermez**. `showConfirmDialog()` Promise döndüğü için submit
    handler'ında **soru sorulacağı anda** `e.preventDefault()` çağrılır, kullanıcı cevaplayınca
    `custom.js` → **`submitFormDirectly(form)`** ile (native, jQuery "submit" olayını tekrar
    tetiklemeden) gönderilir. Soru sorulmayan durumda `preventDefault` hiç çağrılmamalı ki
    `form_layout.html`'deki telefon alanı biçimlendirme gibi diğer submit handler'ları ve
    tarayıcının normal gönderimi eskisi gibi işlemeye devam etsin.

    **`form.submit()` ÇAĞRILMAZ, `submitFormDirectly(form)` kullanılır.** `CustomFlaskForm`
    türevlerinde alan adı `submit` olan bir `SubmitField` bulunur ve `utils/parts/form.html` bunu
    `name="submit"` ile render eder; HTML form elemanlarına alan adlarıyla da erişilebildiği ve
    alan adları metotları **gölgelediği** için `form.submit` metodu değil o input'u döndürür.
    `form.submit()` bu yüzden `TypeError: form.submit is not a function` verir — hata konsolda
    kalır, kullanıcıya yalnızca "hangi seçeneği seçersem seçeyim işlem tamamlanmıyor" olarak
    görünür. `submitFormDirectly()` metodu `HTMLFormElement.prototype`ten alır. Bu gönderim
    "submit" olayını tetiklemediği için tel alanı olan bir formda kullanılacaksa telefon
    biçimlendirmesi elle yapılmalıdır.

  **Soru metni yazarken:** iki seçeneğin de birer işlem yaptığı (yani reddetmenin "iptal" olmadığı)
  durumlarda soru "... yapılsın mı?" diye sorulup cevaplar "Evet/Hayır"a yüklenmez — bu, "Hayır ne
  yapıyor?" sorusunu doğurur ve dipnotla açıklamak gerekir. Bunun yerine soru **açık uçlu** sorulur
  ("Kalan para ile ne yapılsın?") ve iki seçenek `confirmText`/`rejectText` ile **düğmelerin üzerine**
  yazılır ("Vadesi gelmemiş ödemeler ödensin" / "Herhangi bir ödemeyle ilişkilendirilmeden dursun").
  Seçenekler düğmelerde yazınca iptalin nasıl yapılacağı görünmez kalır; bu yüzden `options.hint`
  ile "İşlemi hiç eklemek istemiyorsanız pencereyi (X) ile kapatınız." gibi bir satır eklenir.
  Uzun düğme yazıları Bootstrap'in `.btn { white-space: nowrap }` kuralıyla taşacağı için
  `confirm_dialog.html` içindeki stil bunları sarmalar ve dar ekranda alt alta dizer.
- **Form alanları ortak `utils/parts/form.html` ile render edilir**; alan tipine göre genel bir
  kalıp uygulanır. Tek bir sayfada bir alanı zenginleştirmek (yanına tuş koymak, placeholder'ı
  duruma göre değiştirmek) gerekiyorsa bu ortak partial değiştirilmez; sayfanın `js_block2`
  bloğunda jQuery ile yapılır. Örnek: `transaction/add_money_transaction_by_manager_page.html`
  seçilen üye + işlem türüne göre `#amount` placeholder'ını günceller, alanı `input-group` içine alıp
  hızlı doldurma tuşu ekler ve form altındaki bilgi satırlarından yalnızca ilgili olanı gösterir.
  Bootstrap **3** kullanılır; tuş gizlenirken `input-group` sınıfı da kaldırılmalıdır, aksi hâlde
  alanın köşe yuvarlaklığı bozulur.
- `MoneyTransaction.TYPE.REVENUE` **0** olduğu için JS'te işlem türü karşılaştırmaları katı (`===`)
  ve string üzerinden yapılmalıdır: seçim yapılmamış `<select>` boş string döndürür ve `"" == 0`
  JavaScript'te doğrudur — gevşek karşılaştırmada "türü seçilmemiş" durum "para girişi" sanılır.
- `DecimalField` tarayıcıda `<input type="number">` olarak render edilir. Bu alanlara JS ile değer
  veya placeholder yazarken **binlik ayraçsız, noktalı ondalıklı** biçim kullanılmalıdır (`1249.5`);
  gösterim için kullanılan Türkçe biçim (`1.249,50`) ne alana yazılabilir ne de sunucuda
  ayrıştırılabilir.
- Hesaplanan bir ipucunu (placeholder/öneri) "anlamsız" diye tamamen gizlemek yerine 0'a sıkıştırıp
  göstermek yeğlenir: değer beklenmedik şekilde 0/negatif çıktığında ipucunun hiç görünmemesi
  "özellik çalışmıyor" gibi algılanıyor.
- Veri değiştiren döngülerden sonra sorgu yapmadan önce `flush()` çağırmak güvenlidir.
- **Alfabetik sıralama `sandik/utils/sorting.py` → `turkish_sort_key` ile yapılır.** Python'un
  varsayılan sıralaması kod noktasına baktığı için türkçe harfleri (ç, ğ, ı, ö, ş, ü) listenin
  sonuna atar ("Zeytin" < "Çınar"); `str.lower()` de türkçe bilmez (`"IŞIK".lower()` → "işik",
  `"İZMİR".lower()` → "i̇zmi̇r" yani i + birleşik nokta), bu yüzden `turkish_lower()` I/İ harflerini
  önce elle çevirir. Anahtar büyük/küçük harf ayrımı yapmaz; noktalama ve rakamı harflerden önce,
  türkçede olmayan q/w/x'i latin sıralarında, şapkalı harfleri (â, î, û) aksansız hâllerinin
  yanında sıralar. Sandık listelerinin hepsi buradan geçer: `db_models.py` →
  `WebUser.my_sandiks()` (üst menü + ana sayfa), `general/utils.py` → ana sayfa tabloları,
  `sandik/db.py` → `sandiks_form_choices()` (üyelik başvurusu formu). Şablonda
  `| sort(attribute="name")` gibi bir filtre eklenirse bu sıra bozulur (jinja'nın `sort`u türkçe
  bilmez); sıralama python tarafında yapılmalıdır. **Üye adları hâlâ SQL'de sıralanıyor**
  (`order_by(lambda m: m.web_user_ref.name_surname.lower())`), sıraları veritabanı collation'ına
  bağlıdır; tablolardaki istemci tarafı (footable) sıralama da türkçe bilmez. Testler:
  `tests/test_turkish_sorting.py`.

## Yerelde çalıştırma ve test

```bash
FLASK_DEBUG=1 ../venv/bin/python run.py
```

`FLASK_DEBUG` ile `.env_debug` yüklenir. `SANDIKv2_DATABASE_PROVIDER` `postgres`/`mysql` değilse
sqlite kullanılır ve dosya `sandik/utils/database.sqlite` olur.

### Otomatik testler (`tests/`)

Yavaş yavaş büyütülen bir pytest paketi var (2026-08'de başladı). Kurulum ve çalıştırma:

```bash
../venv/bin/pip install -r requirements-dev.txt   # yalnızca pytest; üretime kurulmaz
../venv/bin/python -m pytest
```

- `tests/conftest.py`: `db_models`'ın normalde `sandik/utils/database.sqlite` dosyasına bağlandığı
  import-anı yan etkisini (bkz. "Alan modeli") ilk import'tan önce `Database.bind`'ı yamalayarak
  bellek-içi (`:memory:`) bir sqlite'a yönlendirir — gerçek/geliştirme veritabanına asla dokunmaz.
  `generate_mapping()` süreç başına yalnızca bir kez çalışabildiği için testler arası izolasyon her
  testten sonra tüm tabloları boşaltıp yeniden oluşturarak sağlanır (`drop_all_tables` +
  `create_tables`, `_clean_database` autouse fixture'ı).
- `tests/factories.py`: sandık/üye/hisse/aidat/para hareketi kurmak için ince yardımcı fonksiyonlar.
  Ham `Entity(...)` yerine gerçek `sandik/*/db.py` içindeki `create_*` fonksiyonlarını sarar (Log
  oluşturma dahil), böylece testler uygulamanın gerçek yoluna yakın kalır. Yeni bir senaryo
  kurarken önce burada uygun bir fabrika olup olmadığına bak, yoksa ekle.
- Testler `@db_session` dekoratörüyle yazılır (Pony sorguları bir session içinde olmalı).
- **Dış dünyaya çıkan işleri enjekte edilebilir yaz.** `reminder.run_payment_reminder` şablon basma
  (`render`), gönderme (`send`) ve adres üretme (`url_builder`) işlerini parametre olarak alır;
  `tests/test_payment_reminder.py` bu sayede Flask ve SMTP olmadan koşar. Yeni bir dış bağımlılık
  eklerken aynı kalıbı izle.
- Yeni bir modülü test ederken bu kalıbı izle: `tests/test_<modül>.py`, `factories`'ten fabrika
  kullan/gerekirse ekle, `assert` ile Decimal değerleri doğrudan karşılaştır (`==`, `int()`/`round()`
  kullanma — bkz. "Dikkat edilmesi gereken yerler").
- Bu paket dışında, tek seferlik bir akışı elle doğrulamak için hâlâ yukarıdaki yöntem (geçici
  script + `Database.bind` yaması) kullanılabilir; ama kalıcı değeri olan bir doğrulamaysa
  `tests/`'e eklemek tercih edilir.

## Veri onarım scriptleri (`sandik/bugfixs/`)

Bunlar `.env` üzerinden **gerçek veritabanına** bağlanır. Çalıştırmadan önce yedek al.

| Script | İş |
|---|---|
| `bugfix_1_redistribute_pods.py` | `PieceOfDebt` tutarsızlıklarını düzeltir |
| `bugfix_2_check_member_removal_consistency.py` | **Salt okunur.** Aşırı dağıtılmış/negatif para işlemleri, pasif ama bakiyesi sıfır olmayan üyeler, yarıda kalmış silmeler |
| `bugfix_3_fix_broken_member_removal.py` | Yarıda kalmış üye silmelerinin bıraktığı fazla iadeyi ve negatif para çıkışını onarır. Varsayılan kuru çalışmadır; yazmak için `--fix` gerekir, invariant'lar sağlanmazsa kendini geri alır |

## TODO.txt

Depo kökündeki `TODO.txt` serbest biçimli yapılacaklar listesidir; bilinen eksikler orada.
