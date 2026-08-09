from contextlib import contextmanager
from datetime import datetime, date

from pony.orm import Set, Optional, Required
from pony.orm.core import EntityMeta, flush

from sandik.utils.db_models import Sandik, SandikAuthorityType, SandikRule, SmsPackage, WebUser, BankAccount, Member, \
    MoneyTransaction, BankTransaction, Notification, Share, Contribution, TrustRelationship, SubReceipt, Retracted, \
    PieceOfDebt, Log, Installment, Debt, WebsiteTransaction

# DATABASE_TABLES_TO_BACKUP_WITH_ORDER liste sıralaması önemlidir
DATABASE_TABLES_TO_BACKUP_WITH_ORDER = [
    Sandik, SandikAuthorityType, SandikRule, SmsPackage, WebUser, BankAccount, Member, MoneyTransaction,
    BankTransaction, Notification, Share, Contribution, TrustRelationship, SubReceipt, Debt, Installment, Retracted,
    PieceOfDebt, WebsiteTransaction, Log
]

INCLUDED_RELATION_SETS = {
    WebUser: ["applied_sandiks_set", "sandik_authority_types_set", "sms_packages_set"],
    Installment: ["sub_receipts_set"]
}

EXCLUDED_RELATIONS = {
    SubReceipt: ["debt_ref", "installment_ref", "revenue_retracted_ref", "expense_retracted_ref"]
}


ENTITY_HOOK_NAMES = ["before_insert", "after_insert", "before_update", "after_update",
                     "before_delete", "after_delete"]


@contextmanager
def entity_hooks_disabled(tables):
    """
    Geri yükleme süresince entity hook'larını (before_insert vb.) devre dışı bırakır.

    Bu hook'lar "normal kullanımda tek bir işlem yapılırken" sağlanması gereken iş kurallarını
    kontrol eder. Geri yüklemede ise satırlar tek tek işlem olarak değil, tamamlanmış bir anlık
    görüntü olarak yazılır; kurallar satır satır sağlanmaz:

    - `PieceOfDebt.before_insert` (ERRCODE 0018) borç veren üyenin bakiyesinin verdiği borçtan
      büyük olmasını ister. Bu yalnızca borç VERİLİRKEN doğrudur: borç geri ödendikten sonra o
      tutar üyenin bakiyesinde ayrılmış olarak durmaz, dolayısıyla geçmiş satır tekrar yazılırken
      kural kaçınılmaz olarak ihlal edilir.
    - `SubReceipt.before_insert` (ERRCODE 0012) tam olarak bir bağlantı ister; ancak alt makbuzun
      borç/taksit/geri-alınmış bağlantıları daha sonraki tablolar yazılırken kurulur.
    - `SubReceipt.after_insert` türetilmiş alanları (is_fully_paid, is_fully_distributed) yeniden
      hesaplar; bunlar yükleme bittikten sonra topluca hesaplanır.
    """
    saved_hooks = {}
    for table in tables:
        for hook_name in ENTITY_HOOK_NAMES:
            if hook_name in table.__dict__:
                saved_hooks[(table, hook_name)] = table.__dict__[hook_name]
                setattr(table, hook_name, lambda self: None)
    try:
        yield
    finally:
        for (table, hook_name), hook in saved_hooks.items():
            setattr(table, hook_name, hook)


def backup_table(db_table, included_relation_sets):
    rows = []
    for row in db_table.select().order_by(db_table._pk_):

        with_collections = False
        if db_table in included_relation_sets:
            with_collections = True

        row_data = row.to_dict(with_collections=with_collections)
        row_data = {key: row_data[key] for key in row_data if
                    not isinstance(row_data[key], list) or key in included_relation_sets[db_table]}

        rows.append(row_data)

    return rows


def restore_table(table, rows):
    for row in rows:
        for column, value in row.items():
            column_attr = getattr(table, column)

            if isinstance(column_attr, Set):
                reverse_entity = column_attr.reverse.entity
                row[column] = [reverse_entity[i] for i in row[column]]
            elif row[column] is not None and isinstance(column_attr, (Optional, Required)):
                if isinstance(column_attr.py_type, EntityMeta):
                    row[column] = column_attr.py_type[row[column]]
                elif column_attr.py_type in [date, datetime]:
                    try:
                        row[column] = datetime.strptime(row[column], "%a, %d %b %Y %H:%M:%S %Z")
                    except ValueError:
                        pass
            else:
                if row[column] is not None:
                    # Buraya girmesi beklenmiyor
                    pass
        table(**row)


def reset_database(database_tables):
    tables = database_tables[:]
    tables.reverse()
    for table in tables:
        table.select().delete()
    flush()


def recalculate_derived_fields_for_all_rows():
    """
    Hook'lar kapalıyken yüklenen satırların türetilmiş alanlarını yeniden hesaplar ve bulunan
    tutarsızlıkları liste olarak döndürür. Liste boş değilse çağıran taraf geri yüklemeyi iptal
    eder (bkz. backup/utils.py -> restore_database).

    Bayraklar `<= 0` ile hesaplanır, `== 0` ile değil. Fazla ödenmiş bir aidat/taksit veya aşırı
    dağıtılmış bir para işlemi "tamamlanmamış" işaretlenirse otomatik ödeme mantığı onu tekrar ele
    alır ve negatif tutarlı alt makbuz üretebilir.
    """
    inconsistencies = []

    for c in Contribution.select():
        unpaid_amount = c.get_unpaid_amount()
        c.is_fully_paid = unpaid_amount <= 0
        if unpaid_amount < 0:
            inconsistencies.append(f"Aidat#{c.id} ({c.term}) fazla ödenmiş: {unpaid_amount}")

    for i in Installment.select():
        unpaid_amount = i.get_unpaid_amount()
        i.is_fully_paid = unpaid_amount <= 0
        if unpaid_amount < 0:
            inconsistencies.append(f"Taksit#{i.id} ({i.term}) fazla ödenmiş: {unpaid_amount}")

    for mt in MoneyTransaction.select():
        undistributed_amount = mt.get_undistributed_amount()
        mt.is_fully_distributed = undistributed_amount <= 0
        if undistributed_amount < 0:
            member = mt.member_ref
            inconsistencies.append(
                f"Para işlemi#{mt.id} ({mt.date}, "
                f"{member.web_user_ref.name_surname if member.web_user_ref else f'#{member.id}'}, "
                f"{member.sandik_ref.name}) aşırı dağıtılmış: {undistributed_amount}")

    return inconsistencies
