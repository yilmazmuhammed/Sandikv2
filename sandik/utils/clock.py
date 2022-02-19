from apscheduler.schedulers.blocking import BlockingScheduler
from pony.orm import db_session

from sandik.auth import db as auth_db
from sandik.transaction import utils as transaction_utils

scheduler = BlockingScheduler()


@scheduler.scheduled_job('cron', day=1, hour=0, minute=1)
def beginning_of_each_month():
    # TODO Aidatları ve taksitleri öde
    with db_session:
        # TODO sadece bu ayın aidatlarını oluştur
        transaction_utils.create_due_contributions_for_all_sandiks(
            created_by=auth_db.get_or_create_bot_user(which="clock"),
            created_from="scheduler.beginning_of_each_month"
        )


scheduler.start()
