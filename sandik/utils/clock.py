from apscheduler.schedulers.blocking import BlockingScheduler

sched = BlockingScheduler()


@sched.scheduled_job('interval', seconds=1)
def timed_job():
    print('This job is run every 1 minutes.')


@sched.scheduled_job('cron', day_of_week='mon-sun', hour=14, minute=12)
def scheduled_job():
    print('This job is run every weekday at 5pm. 1')


@sched.scheduled_job('cron', day_of_week='mon-sun', hour=11, minute=12)
def scheduled_job2():
    print('This job is run every weekday at 5pm. 2')


@sched.scheduled_job('cron', day_of_week='mon-sun', hour=17, minute=12)
def scheduled_job3():
    print('This job is run every weekday at 5pm. 3')


sched.start()
