from datetime import datetime

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
                elif column_attr.py_type is datetime:
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


def recalculate_is_fully_paid_for_all_payments():
    for c in Contribution.select():
        c.recalculate_is_fully_paid()
    for i in Installment.select():
        i.recalculate_is_fully_paid()
