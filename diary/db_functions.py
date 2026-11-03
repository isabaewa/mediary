"""Unicode-регистр для поиска: стандартный LOWER SQLite обрабатывает только ASCII."""

from django.db.models.functions import Lower


def register_sqlite_text_functions(sender, connection, **kwargs):
    if connection.vendor == 'sqlite':
        connection.connection.create_function(
            'mediary_lower',
            1,
            lambda value: value.lower() if isinstance(value, str) else value,
            deterministic=True,
        )


class UnicodeLower(Lower):
    """На SQLite используем Python lower; на других СУБД — штатный LOWER."""

    def as_sqlite(self, compiler, connection, **extra_context):
        return self.as_sql(compiler, connection, function='mediary_lower', **extra_context)
