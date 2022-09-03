# from apscheduler.schedulers.blocking import BlockingScheduler
import os
import sys

from dotenv import load_dotenv

current = os.path.dirname(os.path.realpath(__file__))
parent = os.path.dirname(current)
root = os.path.dirname(parent)

sys.path.append(root)

project_folder = os.path.expanduser(root)  # adjust as appropriate
load_dotenv(os.path.join(project_folder, '.env'))

from pony.orm import db_session

from sandik.auth import db as auth_db
from sandik.transaction import utils as transaction_utils


# scheduler = BlockingScheduler()


# @scheduler.scheduled_job('cron', day=1, hour=0, minute=1)
def beginning_of_each_month():
    # TODO Aidatları ve taksitleri öde
    with db_session:
        # TODO sadece bu ayın aidatlarını oluştur
        transaction_utils.create_due_contributions_for_all_sandiks(
            created_by=auth_db.get_or_create_bot_user(which="clock"),
            created_from="clock.beginning_of_each_month"
        )


# scheduler.start()

if __name__ == '__main__':
    beginning_of_each_month()
