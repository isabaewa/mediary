from django.apps import AppConfig
from django.db.backends.signals import connection_created


class DiaryConfig(AppConfig):
    name = 'diary'

    def ready(self):
        from .db_functions import register_sqlite_text_functions

        # Регистрируем и для рабочей БД, и для новых соединений тестового сервера.
        connection_created.connect(
            register_sqlite_text_functions,
            dispatch_uid='diary.sqlite_text_functions',
        )
