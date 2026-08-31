"""
Şema taşıma (migration) altyapısı.

`family_tree/family_tree/utils/migrations/` ile aynı tasarımdır; her uygulama kendi klasörünün
dışına bağımlı olmadığı (ve Sandıkv2 ayrı bir submodule olduğu) için kod paylaşılmaz, kopyalanır.
Birinde düzeltilen bir hata diğerine de taşınmalıdır — iki dosya, yalnızca ortam değişkeni öneki
ve import yolu farkıyla aynı olmalıdır.

Pony `generate_mapping(create_tables=True)` ile eksik **tabloları** kendisi oluşturur ama var olan
tablolara **sütun eklemez**; modelde bir alan değiştiğinde uygulama eksik sütun yüzünden açılamaz.
Bu paket aradaki farkı kapatır ve **uygulama her açıldığında kendiliğinden** çalışır
(`sandik/utils/db_models.py` içinde, `db.bind()` ile `db.generate_mapping()` arasında).

Yapı:
  * `steps.py` — sırayla uygulanacak `Migration` listesi. **Yeni taşımalar buraya eklenir.**
  * bu dosya — taşımaları çalıştıran motor ve veritabanı işlemleri.

Uygulananlar `schema_migration` tablosunda tutulur, bu yüzden her taşıma bir kez çalışır. Ayrıca
her işlem kendi kontrolünü de yapar (sütun zaten varsa eklemez, tablo yoksa atlar); böylece
elle müdahale edilmiş ya da sıfırdan kurulmuş veritabanlarında da güvenle çalışır.

Sıfırdan kurulan veritabanında hiçbir tablo yoktur: bütün işlemler "tablo yok" diye atlanır,
taşımalar uygulanmış olarak işaretlenir ve tabloları Pony en güncel şemayla oluşturur.
"""
import os
import re
from datetime import datetime

MIGRATION_TABLE = "schema_migration"


# --------------------------------------------------------------------------------------
# Veritabanı arka uçları
# --------------------------------------------------------------------------------------

class Backend:
    """Taşımalar için ham (ORM'siz) veritabanı erişimi"""

    def __init__(self, provider, params):
        self.provider = provider
        self.params = params
        self.connection = None

    # -- bağlantı --------------------------------------------------------------------

    def connect(self):
        if self.provider == "sqlite":
            import sqlite3
            self.connection = sqlite3.connect(self.params["filename"])
        elif self.provider == "mysql":
            import pymysql
            self.connection = pymysql.connect(
                host=self.params["host"], user=self.params["user"],
                password=self.params["passwd"], database=self.params["db"], autocommit=False)
        elif self.provider == "postgres":
            import psycopg2
            self.connection = psycopg2.connect(self.params["dsn"])
        else:
            raise ValueError(f"Bilinmeyen veritabanı sağlayıcısı: {self.provider}")
        return self.connection

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    # -- sorgu -----------------------------------------------------------------------

    def execute(self, sql, args=()):
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql, args)
            return cursor
        finally:
            if self.provider != "sqlite":
                cursor.close()

    def fetchall(self, sql, args=()):
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql, args)
            return cursor.fetchall()
        finally:
            cursor.close()

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()

    @property
    def placeholder(self):
        return "?" if self.provider == "sqlite" else "%s"

    def quote(self, name):
        if self.provider == "mysql":
            return f"`{name}`"
        return f'"{name}"'

    def normalize(self, name):
        """Pony'nin bu sağlayıcıda kullandığı tanımlayıcı yazımı.

        **MySQL sağlayıcısı bütün tanımlayıcıları küçük harfe çevirir**
        (`pony/orm/dbproviders/mysql.py` → `normalize_name`), yani `WebUser` entity'sinin tablosu
        MySQL'de `webuser`dır; sqlite ve postgres'te ad olduğu gibi kalır. Taşımalar tabloya adıyla
        eriştiği için burada aynı kuralı uygulamak zorundayız — yoksa MySQL'de tablo "yok" görünür,
        işlemler sessizce atlanır ve taşıma uygulanmış işaretlenir.
        """
        return name.lower() if self.provider == "mysql" else name

    def qname(self, name):
        """Doğru yazımla tırnaklanmış tanımlayıcı. SQL üretilirken `quote` yerine bu kullanılır."""
        return self.quote(self.normalize(name))

    # -- şema bilgisi ----------------------------------------------------------------

    def table_exists(self, table) -> bool:
        table = self.normalize(table)
        if self.provider == "sqlite":
            rows = self.fetchall(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
        elif self.provider == "mysql":
            rows = self.fetchall(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = DATABASE() AND table_name = %s", (table,))
        else:
            rows = self.fetchall(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = current_schema() AND table_name = %s", (table,))
        return bool(rows)

    def columns(self, table):
        table = self.normalize(table)
        if self.provider == "sqlite":
            return [row[1] for row in self.fetchall(f'PRAGMA table_info("{table}")')]
        if self.provider == "mysql":
            rows = self.fetchall(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = DATABASE() AND table_name = %s", (table,))
        else:
            rows = self.fetchall(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = %s", (table,))
        return [row[0] for row in rows]

    def column_exists(self, table, column) -> bool:
        return self.normalize(column) in self.columns(table)

    def supports_drop_column(self) -> bool:
        """SQLite 3.35'ten önce ALTER TABLE ... DROP COLUMN yoktur"""
        if self.provider != "sqlite":
            return True
        import sqlite3
        version = tuple(int(part) for part in sqlite3.sqlite_version.split(".")[:2])
        return version >= (3, 35)

    # -- uygulanan taşımalar ---------------------------------------------------------

    def ensure_migration_table(self):
        self.execute(
            f'CREATE TABLE IF NOT EXISTS {self.quote(MIGRATION_TABLE)} ('
            f'{self.quote("name")} VARCHAR(100) NOT NULL PRIMARY KEY, '
            f'{self.quote("applied_time")} VARCHAR(30) NOT NULL)'
        )
        self.commit()

    def applied_migrations(self):
        rows = self.fetchall(f'SELECT {self.quote("name")} FROM {self.quote(MIGRATION_TABLE)}')
        return {row[0] for row in rows}

    def mark_applied(self, name):
        self.execute(
            f'INSERT INTO {self.quote(MIGRATION_TABLE)} '
            f'({self.quote("name")}, {self.quote("applied_time")}) '
            f'VALUES ({self.placeholder}, {self.placeholder})',
            (name, datetime.now().isoformat(timespec="seconds")),
        )


# --------------------------------------------------------------------------------------
# İşlemler
# --------------------------------------------------------------------------------------

class Operation:
    """Tek bir şema değişikliği. `apply` ne yapıldığını anlatan bir metin döndürür."""

    def apply(self, backend, dry_run=False):
        raise NotImplementedError


class AddColumn(Operation):
    """
    Var olan bir tabloya sütun ekler.

    `column_type` sağlayıcıdan bağımsız SQL tipidir ("INTEGER", "VARCHAR(20) NOT NULL"...). Tip
    sağlayıcıya göre değişiyorsa (ör. Pony `Json` -> mysql/sqlite `JSON`, postgres `JSONB`)
    `{"mysql": ..., "postgres": ..., "sqlite": ...}` sözlüğü de verilebilir; `default` için de aynısı
    geçerlidir (bir sağlayıcı sözlükte yoksa o sağlayıcıda DEFAULT yazılmaz — MySQL JSON sütununa
    DEFAULT kabul etmez, oraya NULL eklenip satırlar `RunSql` ile doldurulur).
    `default` verilirse DEFAULT eklenir; NOT NULL bir sütun eklenirken zorunludur.
    `references` yabancı anahtardır: yalnızca sqlite/postgres'te yazılır — MySQL'de ALTER TABLE
    ile satır içi REFERENCES yok sayılır, Pony de yabancı anahtar kısıtı aramadığı için
    sütunun kendisi yeterlidir.
    """

    def __init__(self, table, column, column_type, default=None, references=None,
                 on_delete="SET NULL"):
        self.table = table
        self.column = column
        self.column_type = column_type
        self.default = default
        self.references = references
        self.on_delete = on_delete

    def apply(self, backend, dry_run=False):
        if not backend.table_exists(self.table):
            return f"{self.table} tablosu yok, atlandı"
        if backend.column_exists(self.table, self.column):
            return f"{self.table}.{self.column} zaten var"

        column_type = (self.column_type.get(backend.provider) if isinstance(self.column_type, dict)
                       else self.column_type)
        if column_type is None:
            raise ValueError(f"{self.table}.{self.column} için {backend.provider} tipi tanımlı değil")
        default = (self.default.get(backend.provider) if isinstance(self.default, dict)
                   else self.default)

        definition = f"{backend.qname(self.column)} {column_type}"
        if default is not None:
            definition += f" DEFAULT {default}"
        if self.references and backend.provider != "mysql":
            table, column = self.references
            definition += (f" REFERENCES {backend.qname(table)} ({backend.qname(column)})"
                           f" ON DELETE {self.on_delete}")

        sql = f"ALTER TABLE {backend.qname(self.table)} ADD COLUMN {definition}"
        if dry_run:
            return f"eklenecek: {sql}"

        backend.execute(sql)
        return f"{self.table}.{self.column} eklendi"


class DropColumn(Operation):
    """
    Var olan bir tablodan sütun çıkarır.

    SQLite 3.35'ten önce `ALTER TABLE ... DROP COLUMN` yoktur; o durumda tablo SQLite'ın önerdiği
    yöntemle yeniden kurulur (yeni tablo -> veriyi kopyala -> eskisini sil -> adını değiştir).
    """

    def __init__(self, table, column):
        self.table = table
        self.column = column

    def apply(self, backend, dry_run=False):
        if not backend.table_exists(self.table):
            return f"{self.table} tablosu yok, atlandı"
        if not backend.column_exists(self.table, self.column):
            return f"{self.table}.{self.column} zaten yok"
        if dry_run:
            return f"çıkarılacak: {self.table}.{self.column}"

        if backend.supports_drop_column():
            backend.execute(
                f"ALTER TABLE {backend.qname(self.table)} DROP COLUMN {backend.qname(self.column)}")
            return f"{self.table}.{self.column} çıkarıldı"

        rebuild_sqlite_table_without_column(backend, self.table, self.column)
        return f"{self.table}.{self.column} çıkarıldı (tablo yeniden kuruldu)"


class RunSql(Operation):
    """
    Elle yazılmış SQL. `only_for` verilirse yalnızca o sağlayıcıda çalışır.

    `table` verilirse tablo yoksa atlanır. **Tablo adı geçen her `RunSql`de verilmelidir**: aksi
    hâlde sıfırdan kurulan veritabanında (henüz hiçbir tablo yokken) SQL körlemesine çalışır ve
    "table doesn't exist" ile patlar. `AddColumn`/`DropColumn` bu kontrolü kendiliğinden yapar.

    `sql`, backend alan bir fonksiyon da olabilir; tanımlayıcıları `backend.qname()` ile yazmak
    için gerekir (MySQL'de tablo/sütun adları küçük harftir, bkz. `Backend.normalize`).
    """

    def __init__(self, sql, description=None, only_for=None, table=None):
        self.sql = sql
        self.description = description or (sql if isinstance(sql, str) else "SQL")
        self.only_for = only_for
        self.table = table

    def apply(self, backend, dry_run=False):
        if self.only_for and backend.provider != self.only_for:
            return f"{self.only_for} dışında atlandı"
        if self.table and not backend.table_exists(self.table):
            return f"{self.table} tablosu yok, atlandı"
        if dry_run:
            return f"çalıştırılacak: {self.description}"
        backend.execute(self.sql(backend) if callable(self.sql) else self.sql)
        return self.description


def rebuild_sqlite_table_without_column(backend, table, column):
    """
    SQLite'da bir tabloyu belirtilen sütun olmadan yeniden kurar.

    Tablo tanımı `sqlite_master`dan okunur ve ilgili sütunun satırı çıkarılır; böylece UNIQUE
    kısıtları, yabancı anahtarlar ve tip bilgileri korunur (Pony tanımları her sütunu ayrı satıra
    yazdığı için satır bazlı ayıklama güvenlidir). Sonuç doğrulanır: beklenen sütunlar oluşmazsa
    istisna fırlatılır ve işlem geri alınır.
    """
    rows = backend.fetchall(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,))
    if not rows:
        raise RuntimeError(f"{table} tablosunun tanımı okunamadı")

    original_ddl = rows[0][0]
    expected_columns = [c for c in backend.columns(table) if c != column]
    new_ddl = _remove_column_from_ddl(original_ddl, table, column)
    temporary_table = f"{table}__migration"

    column_list = ", ".join(backend.quote(c) for c in expected_columns)

    # SQLite'ın önerdiği yöntem: yabancı anahtar denetimi ve tablo adı yeniden yazımı kapatılır
    backend.execute("PRAGMA foreign_keys=off")
    backend.execute("PRAGMA legacy_alter_table=on")
    try:
        backend.execute(new_ddl.replace(f'"{table}"', f'"{temporary_table}"', 1))
        backend.execute(f'INSERT INTO "{temporary_table}" ({column_list}) '
                        f'SELECT {column_list} FROM "{table}"')
        backend.execute(f'DROP TABLE "{table}"')
        backend.execute(f'ALTER TABLE "{temporary_table}" RENAME TO "{table}"')

        if backend.columns(table) != expected_columns:
            raise RuntimeError(
                f"{table} yeniden kurulduktan sonra sütunlar beklenenle uyuşmuyor: "
                f"{backend.columns(table)} != {expected_columns}")
    except Exception:
        backend.rollback()
        raise
    finally:
        backend.execute("PRAGMA legacy_alter_table=off")
        backend.execute("PRAGMA foreign_keys=on")


def _remove_column_from_ddl(ddl, table, column):
    """
    `CREATE TABLE` tanımından bir sütunun tanımını çıkarır.

    Satır bazlı ayıklama yapılamaz: `ALTER TABLE ... ADD COLUMN` ile eklenen sütunlar kendi
    satırlarına değil, var olan bir satırın sonuna yazılır. Bu yüzden sütun listesi gerçekten
    ayrıştırılır — tırnak içindeki metinler ve iç içe parantezler dikkate alınarak en dış
    seviyedeki virgüllerden bölünür. `CONSTRAINT`, `UNIQUE`, `PRIMARY KEY` gibi tablo kısıtları
    olduğu gibi korunur.
    """
    open_index = ddl.index("(")
    close_index = ddl.rindex(")")
    header = ddl[:open_index].rstrip()
    body = ddl[open_index + 1:close_index]

    items = _split_table_items(body)
    kept = [item for item in items if _item_column_name(item) != column]

    if len(kept) == len(items):
        raise RuntimeError(f"{table}.{column} sütununun tanımı bulunamadı:\n{ddl}")

    # SQLite `CREATE TABLE`'da bütün sütun tanımlarının tablo kısıtlarından ÖNCE gelmesini şart
    # koşar. `ALTER TABLE ADD COLUMN` ise yeni sütunu kapanış parantezinden hemen önce, yani
    # kısıtlardan SONRA yazar; tanımı olduğu gibi geri yazmak sözdizimi hatası verir.
    columns = [item for item in kept if _item_column_name(item) is not None]
    constraints = [item for item in kept if _item_column_name(item) is None]

    return header + " (\n  " + ",\n  ".join(columns + constraints) + "\n)"


def _split_table_items(body):
    """Sütun/kısıt tanımlarını en dış seviyedeki virgüllerden böler"""
    items, current, depth = [], [], 0
    in_single = in_double = False

    for char in body:
        if in_single:
            current.append(char)
            in_single = char != "'"
            continue
        if in_double:
            current.append(char)
            in_double = char != '"'
            continue

        if char == "'":
            in_single = True
        elif char == '"':
            in_double = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "," and depth == 0:
            items.append("".join(current).strip())
            current = []
            continue

        current.append(char)

    if "".join(current).strip():
        items.append("".join(current).strip())
    return items


# Sütun değil, tablo kısıtı olan tanımlar
TABLE_CONSTRAINT_KEYWORDS = ("constraint", "primary", "unique", "foreign", "check")


def _item_column_name(item):
    """Tanım bir sütunsa adını, tablo kısıtıysa None döndürür"""
    match = re.match(r'^\s*(?:"([^"]+)"|`([^`]+)`|\[([^\]]+)\]|(\w+))', item)
    if not match:
        return None

    name = next((group for group in match.groups() if group is not None), None)
    if name and name.lower() in TABLE_CONSTRAINT_KEYWORDS:
        return None
    return name


# --------------------------------------------------------------------------------------
# Çalıştırıcı
# --------------------------------------------------------------------------------------

class Migration:
    def __init__(self, name, description, operations):
        self.name = name
        self.description = description
        self.operations = operations


def database_target_from_env():
    """
    Ortam değişkenlerinden `(sağlayıcı, parametreler)` üretir.

    Hem `db.bind()` hem taşımalar aynı yeri kullansın diye burada: ikisinin farklı veritabanına
    bakması, "taşıma çalıştı ama uygulama hâlâ eski şemayı görüyor" gibi hatalara yol açardı.
    """
    provider = os.getenv("SANDIKv2_DATABASE_PROVIDER")

    if provider == "postgres":
        return "postgres", {"dsn": os.getenv("SANDIKv2_DATABASE_URL")}

    if provider == "mysql":
        return "mysql", {"host": os.getenv("SANDIKv2_DATABASE_HOST"), "user": os.getenv("SANDIKv2_DATABASE_USER"),
                         "passwd": os.getenv("SANDIKv2_DATABASE_PASSWORD"), "db": os.getenv("SANDIKv2_DATABASE_DB")}

    # Dosya yolu çalışma dizinine göre değil, bu dosyaya göre belirlenir (utils/database.sqlite)
    utils_directory = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return "sqlite", {"filename": os.path.join(utils_directory, "database.sqlite"), "create_db": True}


def migration_status(provider, params):
    """`(uygulananlar, bekleyenler)` listelerini döndürür"""
    from sandik.utils.migrations.steps import MIGRATIONS

    backend = Backend(provider=provider, params=params)
    backend.connect()
    try:
        backend.ensure_migration_table()
        applied = backend.applied_migrations()
    finally:
        backend.close()

    return ([m for m in MIGRATIONS if m.name in applied],
            [m for m in MIGRATIONS if m.name not in applied])


def is_enabled() -> bool:
    """`SANDIKv2_AUTO_MIGRATE='0'` ile açılışta otomatik taşıma kapatılabilir"""
    return (os.getenv("SANDIKv2_AUTO_MIGRATE") or "1").strip() not in ("0", "false", "False", "hayir")


def run_migrations(provider, params, dry_run=False, log=None):
    """
    Bekleyen taşımaları sırayla uygular ve yapılanların listesini döndürür.

    `db.bind()` ile `db.generate_mapping()` arasında çağrılır. Bir taşıma hata verirse istisna
    yukarı fırlatılır: uygulamanın yarım şemayla açılmaması gerekir.
    """
    from sandik.utils.migrations.steps import MIGRATIONS

    messages = []
    backend = Backend(provider=provider, params=params)
    backend.connect()
    try:
        backend.ensure_migration_table()
        applied = backend.applied_migrations()

        for migration in MIGRATIONS:
            if migration.name in applied:
                continue

            try:
                results = [operation.apply(backend, dry_run=dry_run)
                           for operation in migration.operations]
                if not dry_run:
                    backend.mark_applied(migration.name)
                    backend.commit()
            except Exception:
                backend.rollback()
                # Çok işçili sunucuda başka bir süreç aynı anda uygulamış olabilir; kayıt
                # düşülmüşse hatayı yutup devam ediyoruz, düşülmemişse gerçek bir hata var.
                if not dry_run and migration.name in backend.applied_migrations():
                    if log:
                        log(f"[{migration.name}] başka bir süreç uygulamış, atlandı")
                    continue
                raise

            message = f"[{migration.name}] {migration.description}: " + "; ".join(results)
            messages.append(message)
            if log:
                log(message)
    except Exception:
        backend.rollback()
        raise
    finally:
        backend.close()

    return messages
