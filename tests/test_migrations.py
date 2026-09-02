"""`sandik/utils/migrations` için testler.

Buradaki testlerin asıl derdi **MySQL'de tanımlayıcı yazımıdır**. Pony'nin MySQL sağlayıcısı
bütün adları küçük harfe çevirir (`normalize_name`), yani `WebUser` entity'sinin tablosu MySQL'de
`webuser`dır. Taşımalar tabloya adıyla eriştiği için aynı kuralı uygulamak zorundadır; uygulamadığı
sürece MySQL'de tablo "yok" görünür, işlemler sessizce atlanır ve taşıma uygulanmış işaretlenir —
sütun hiç eklenmediği için de uygulama `generate_mapping`de patlar.

Gerçek bir MySQL sunucusu gerekmesin diye SQL üretimi ve kontroller sahte bir backend ile
sınanır; sqlite yolu ise gerçek (geçici) bir dosya üzerinde uçtan uca çalıştırılır.
"""
import os
import sqlite3
import tempfile

import pytest

from sandik.utils import migrations
from sandik.utils.migrations.steps import MIGRATIONS
from sandik.utils.money import Currency


class FakeBackend(migrations.Backend):
    """Bağlantı açmadan yalnızca ad/SQL üretimini sınamak için."""

    def __init__(self, provider, tables=None):
        self.provider = provider
        self.params = {}
        self.connection = None
        self._tables = tables if tables is not None else {}
        self.executed = []

    def table_exists(self, table):
        return self.normalize(table) in self._tables

    def columns(self, table):
        return self._tables.get(self.normalize(table), [])

    def execute(self, sql, args=()):
        self.executed.append(sql)


# --- Tanımlayıcı yazımı ------------------------------------------------------------------------

@pytest.mark.parametrize("provider, expected", [
    ("mysql", "webuser"),      # Pony MySQL'de bütün adları küçük harfe çevirir
    ("postgres", "WebUser"),
    ("sqlite", "WebUser"),
])
def test_identifier_case_follows_pony(provider, expected):
    assert FakeBackend(provider).normalize("WebUser") == expected


def test_qname_quotes_with_the_right_case():
    assert FakeBackend("mysql").qname("WebUser") == "`webuser`"
    assert FakeBackend("postgres").qname("WebUser") == '"WebUser"'


def test_table_and_column_lookups_are_normalized():
    backend = FakeBackend("mysql", tables={"webuser": ["id", "preferences"]})
    assert backend.table_exists("WebUser") is True
    assert backend.column_exists("WebUser", "preferences") is True


# --- Üretilen SQL ------------------------------------------------------------------------------

def test_add_column_uses_the_normalized_table_name_on_mysql():
    backend = FakeBackend("mysql", tables={"webuser": ["id"]})
    operation = migrations.AddColumn("WebUser", "preferences", column_type={"mysql": "JSON NULL"})

    operation.apply(backend)

    assert backend.executed == ["ALTER TABLE `webuser` ADD COLUMN `preferences` JSON NULL"]


def test_add_column_is_skipped_when_the_table_is_missing():
    backend = FakeBackend("mysql", tables={})
    migrations.AddColumn("WebUser", "preferences", column_type={"mysql": "JSON NULL"}).apply(backend)
    assert backend.executed == []


# --- RunSql koruması ---------------------------------------------------------------------------

def test_run_sql_is_skipped_when_its_table_is_missing():
    """Sıfırdan kurulan veritabanında körlemesine çalışıp 'table doesn't exist' vermemeli."""
    backend = FakeBackend("mysql", tables={})
    operation = migrations.RunSql("UPDATE `webuser` SET x = 1", table="WebUser", only_for="mysql")

    result = operation.apply(backend)

    assert backend.executed == []
    assert "yok" in result


def test_run_sql_accepts_a_callable_so_identifiers_can_be_normalized():
    backend = FakeBackend("mysql", tables={"webuser": ["id"]})
    operation = migrations.RunSql(lambda b: f"UPDATE {b.qname('WebUser')} SET x = 1",
                                  table="WebUser", only_for="mysql")

    operation.apply(backend)

    assert backend.executed == ["UPDATE `webuser` SET x = 1"]


def test_every_run_sql_step_declares_its_table():
    """`steps.py`deki her RunSql tablo koruması taşımalı; yoksa sıfırdan kurulumda patlar."""
    for migration in MIGRATIONS:
        for operation in migration.operations:
            if isinstance(operation, migrations.RunSql):
                assert operation.table, f"{migration.name}: RunSql'e table verilmemiş"


def test_mysql_steps_generate_lowercase_identifiers():
    """steps.py'deki MySQL SQL'leri elle yazıldığı için ayrıca kontrol edilir."""
    backend = FakeBackend("mysql", tables={"webuser": ["id"]})
    for migration in MIGRATIONS:
        for operation in migration.operations:
            if isinstance(operation, migrations.RunSql) and callable(operation.sql):
                sql = operation.sql(backend)
                assert "`WebUser`" not in sql, f"{migration.name}: tablo adı küçük harf değil -> {sql}"


# --- sqlite'ta uçtan uca -----------------------------------------------------------------------

@pytest.fixture
def sqlite_db():
    path = os.path.join(tempfile.mkdtemp(), "t.sqlite")
    yield path


def test_migrations_apply_to_an_old_schema(sqlite_db):
    con = sqlite3.connect(sqlite_db)
    con.execute('CREATE TABLE "WebUser" ("id" INTEGER PRIMARY KEY, "email_address" TEXT NOT NULL)')
    con.execute('INSERT INTO "WebUser" ("email_address") VALUES (\'a@b.c\')')
    con.commit()
    con.close()

    migrations.run_migrations(provider="sqlite", params={"filename": sqlite_db})

    con = sqlite3.connect(sqlite_db)
    assert "preferences" in [c[1] for c in con.execute('PRAGMA table_info("WebUser")')]
    assert con.execute('SELECT preferences FROM "WebUser"').fetchone()[0] == "{}"
    con.close()


def test_migrations_are_idempotent(sqlite_db):
    con = sqlite3.connect(sqlite_db)
    con.execute('CREATE TABLE "WebUser" ("id" INTEGER PRIMARY KEY, "email_address" TEXT NOT NULL)')
    con.commit()
    con.close()

    migrations.run_migrations(provider="sqlite", params={"filename": sqlite_db})
    assert migrations.run_migrations(provider="sqlite", params={"filename": sqlite_db}) == []


def test_a_brand_new_database_skips_everything_and_marks_applied(sqlite_db):
    """Sıfırdan kurulumda hiçbir tablo yoktur; Pony'nin tabloları kurması beklenir."""
    migrations.run_migrations(provider="sqlite", params={"filename": sqlite_db})

    applied, pending = migrations.migration_status(provider="sqlite", params={"filename": sqlite_db})
    assert [m.name for m in applied] == [m.name for m in MIGRATIONS]
    assert pending == []


def test_currency_column_is_added_to_existing_sandiks(sqlite_db):
    """Var olan sandıklar taşımadan sonra TL (1) olmalı — modeldeki `default` ile aynı değer."""
    con = sqlite3.connect(sqlite_db)
    con.execute('CREATE TABLE "Sandik" ("id" INTEGER PRIMARY KEY, "name" TEXT NOT NULL, '
                '"type" INTEGER NOT NULL)')
    con.execute('INSERT INTO "Sandik" ("name", "type") VALUES (\'Eski sandık\', 1)')
    con.commit()
    con.close()

    migrations.run_migrations(provider="sqlite", params={"filename": sqlite_db})

    con = sqlite3.connect(sqlite_db)
    assert "currency" in [c[1] for c in con.execute('PRAGMA table_info("Sandik")')]
    assert con.execute('SELECT currency FROM "Sandik"').fetchone()[0] == Currency.TRY
    con.close()
