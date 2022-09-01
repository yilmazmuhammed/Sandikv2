from pony.orm import Set, Optional, Required
from pony.orm.core import EntityMeta, flush

from sandik.utils.db_models import Sandik, SandikAuthorityType, SandikRule, SmsPackage, WebUser, BankAccount, Member, \
    MoneyTransaction, BankTransaction, Notification, Share, Contribution, TrustRelationship, SubReceipt, Retracted, \
    PieceOfDebt, Log, Installment, Debt

DATABASE_TABLES_TO_BACKUP_WITH_ORDER = [
    Sandik, SandikAuthorityType, SandikRule, SmsPackage, WebUser, BankAccount, Member, MoneyTransaction,
    BankTransaction, Notification, Share, Contribution, TrustRelationship, SubReceipt, Debt, Installment, Retracted,
    PieceOfDebt, Log
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
    for row in db_table.select().order_by(lambda r: r.id):

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
            elif row[column] is not None and (
                    isinstance(column_attr, Optional) or isinstance(column_attr, Required)):
                if isinstance(column_attr.py_type, EntityMeta):
                    row[column] = column_attr.py_type[row[column]]
            else:
                pass
        print(table, row)

        if table.__name__ == 'WebUser':
            user = table.get(email_address=row["email_address"])
            if user and user.is_admin():
                print("before user.id:", user.id)
                user.id = row["id"]
                print("after user.id:", user.id)
                print("admin detected")
                continue

        table(**row)


def reset_database(database_tables):
    for table in database_tables:
        table.select().delete()
    flush()


def recalculate_is_fully_paid_for_all_payments():
    for c in Contribution.select():
        c.recalculate_is_fully_paid()
    for i in Installment.select():
        i.recalculate_is_fully_paid()
