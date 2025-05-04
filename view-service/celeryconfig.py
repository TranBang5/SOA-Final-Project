from celery.schedules import crontab

beat_schedule = {
    'sync-view-counts': {
        'task': 'app.sync_view_counts',
        'schedule': 10.0,
    },
}
