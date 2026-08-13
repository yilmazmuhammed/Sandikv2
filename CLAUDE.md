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

## Modüller (`sandik/`)

| Modül | Yol öneki | İş |
|---|---|---|
| `auth` | `/` | Kayıt/giriş, `WebUser`, yetkiler |
| `general` | `/` | Ana sayfa, bildirimler, banka hesapları, loglar |
| `sandik` | `/sandik/` | Sandık, üye, hisse, güven bağı, kurallar |
| `transaction` | `/sandik/<id>/` | Para giriş/çıkışı, aidat, borç, taksit |
| `website_transaction` | `/websitesi-masraflari/` | Sitenin kendi gider kaydı |
| `backup` | `/yedek/` | Veritabanının JSON olarak dışa/içe aktarımı |
| `paw` | `/paw/` | PythonAnywhere: git pull + webapp reload |
| `bot` | — | E-posta (`email_bot.py`), SMS (NetGSM), Kuveyt Türk API |
| `bugfixs` | — | Tek seferlik veri düzeltme scriptleri (`.env`'i, yani **gerçek veritabanını** kullanır) |
| `blueprint_template` | — | Yeni modül açarken kopyalanacak iskelet |

`sandik/utils/clock.py`: her ayın başında çalışacak iş (aidat oluşturma). Procfile'da `clock`
process'i olarak tanımlı.

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

## Yerelde çalıştırma ve test

```bash
FLASK_DEBUG=1 ../venv/bin/python run.py
```

`FLASK_DEBUG` ile `.env_debug` yüklenir. `SANDIKv2_DATABASE_PROVIDER` `postgres`/`mysql` değilse
sqlite kullanılır ve dosya `sandik/utils/database.sqlite` olur.

Otomatik test paketi **yoktur**. Bir akışı doğrulamak için `db_models`'ı import etmeden önce
`pony.orm.Database.bind`'ı geçici bir sqlite dosyasına yönlendiren tek kullanımlık bir script yazmak
pratik bir yöntemdir (import anında bind edildiği için sonradan değiştirilemez).

## Veri onarım scriptleri (`sandik/bugfixs/`)

Bunlar `.env` üzerinden **gerçek veritabanına** bağlanır. Çalıştırmadan önce yedek al.

| Script | İş |
|---|---|
| `bugfix_1_redistribute_pods.py` | `PieceOfDebt` tutarsızlıklarını düzeltir |
| `bugfix_2_check_member_removal_consistency.py` | **Salt okunur.** Aşırı dağıtılmış/negatif para işlemleri, pasif ama bakiyesi sıfır olmayan üyeler, yarıda kalmış silmeler |
| `bugfix_3_fix_broken_member_removal.py` | Yarıda kalmış üye silmelerinin bıraktığı fazla iadeyi ve negatif para çıkışını onarır. Varsayılan kuru çalışmadır; yazmak için `--fix` gerekir, invariant'lar sağlanmazsa kendini geri alır |

## TODO.txt

Depo kökündeki `TODO.txt` serbest biçimli yapılacaklar listesidir; bilinen eksikler orada.
