import os
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def assign_existing_records(apps, schema_editor):
    Medication = apps.get_model('diary', 'Medication')
    HealthEntry = apps.get_model('diary', 'HealthEntry')
    alias = schema_editor.connection.alias
    if not Medication.objects.using(alias).filter(owner__isnull=True).exists() and not HealthEntry.objects.using(alias).filter(owner__isnull=True).exists():
        return
    username = os.environ.get('MEDIARY_LEGACY_OWNER')
    User = apps.get_model(*settings.AUTH_USER_MODEL.split('.'))
    owner = User.objects.using(alias).filter(username=username).first() if username else None
    if owner is None:
        raise RuntimeError('Для переноса существующей базы задайте MEDIARY_LEGACY_OWNER с логином созданного аккаунта. База и записи не удалены.')
    Medication.objects.using(alias).filter(owner__isnull=True).update(owner_id=owner.pk)
    HealthEntry.objects.using(alias).filter(owner__isnull=True).update(owner_id=owner.pk)


class Migration(migrations.Migration):
    dependencies = [('diary', '0007_healthentry_owner_medication_owner_and_more')]
    operations = [
        migrations.RunPython(assign_existing_records, migrations.RunPython.noop),
        migrations.AlterField(model_name='medication', name='owner', field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='medications', to=settings.AUTH_USER_MODEL, verbose_name='Владелец')),
        migrations.AlterField(model_name='healthentry', name='owner', field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='health_entries', to=settings.AUTH_USER_MODEL, verbose_name='Владелец')),
    ]
