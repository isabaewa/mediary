from django.contrib import admin

from .models import HealthEntry, Medication, MedicationIntake


@admin.register(Medication)
class MedicationAdmin(admin.ModelAdmin):
    list_display = ('name', 'purpose', 'dosage', 'daily_doses', 'start_date', 'end_date')
    search_fields = ('name', 'purpose')


@admin.register(MedicationIntake)
class MedicationIntakeAdmin(admin.ModelAdmin):
    list_display = ('medication', 'date', 'slot', 'scheduled_time', 'taken', 'taken_at')
    list_filter = ('taken', 'date')


@admin.register(HealthEntry)
class HealthEntryAdmin(admin.ModelAdmin):
    list_display = ('date', 'condition', 'mood', 'pain_intensity')
    list_filter = ('condition', 'mood')
