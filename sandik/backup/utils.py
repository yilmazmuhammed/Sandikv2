from sandik.auth import db as auth_db
from sandik.backup import db


def backup_database():
    backup_data = {}
    for table in db.DATABASE_TABLES_TO_BACKUP_WITH_ORDER:
        backup_data[table.__name__] = db.backup_table(table, included_relation_sets=db.INCLUDED_RELATION_SETS)

    return backup_data


def create_or_update_admin_users(admin_users_data):
    for user_data in admin_users_data:
        user = auth_db.get_web_user(email_address=user_data["email_address"])
        if user:
            auth_db.update_web_user(user, updated_by=auth_db.get_or_create_bot_user("backup_manager"),
                                    password_hash=user_data["password_hash"])
        else:
            auth_db.create_web_user(**user_data, created_by=auth_db.get_or_create_bot_user("backup_manager"))


def restore_database(backup_data):
    # TODO bütün satırlar import edildikten sonra before_insert gibi fonksiyonların çalışması lazım

    for table, relations in db.EXCLUDED_RELATIONS.items():
        for relation in relations:
            for row in backup_data[table.__name__]:
                row.pop(relation)

    admin_users = auth_db.get_admin_web_users()
    admin_users_data = [user.to_dict() for user in admin_users]

    db.reset_database(db.DATABASE_TABLES_TO_BACKUP_WITH_ORDER)

    for table in db.DATABASE_TABLES_TO_BACKUP_WITH_ORDER:
        db.restore_table(table=table, rows=backup_data[table.__name__])

    db.recalculate_is_fully_paid_for_all_payments()

    create_or_update_admin_users(admin_users_data=admin_users_data)
