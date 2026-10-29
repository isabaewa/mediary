from datetime import datetime, time
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.http import JsonResponse, HttpResponseBadRequest
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Case, When, Value, IntegerField, DateField
from django.views.decorators.http import require_POST
from django.utils.http import url_has_allowed_host_and_scheme
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .services import sync_intakes
from .models import Medication, MedicationIntake, HealthEntry
from .forms import MedicationForm, HealthEntryForm, QuickIntakeForm

@login_required
def dashboard_view(request):
    """Главная страница приложения"""
    now = timezone.localtime(timezone.now())
    today = now.date()
    today_entry = HealthEntry.objects.filter(owner=request.user, date=today).first()
    today_intakes = list(MedicationIntake.objects.filter(medication__owner=request.user, date=today, medication__as_needed=False, is_extra=False, medication__start_date__lte=today, medication__end_date__gte=today).select_related('medication').order_by('medication_id', 'slot'))
    for intake in today_intakes:
        intake.scheduled_at = timezone.make_aware(datetime.combine(intake.date, intake.scheduled_time)) if intake.scheduled_time else None
    total_intakes = len(today_intakes)
    taken_intakes = sum(intake.taken for intake in today_intakes)
    
    context = {
        'today': today,
        'as_needed_medications': Medication.objects.filter(owner=request.user, as_needed=True),
        'as_needed_intakes': MedicationIntake.objects.filter(medication__owner=request.user, date=today, taken=True).filter(Q(is_extra=True) | Q(medication__as_needed=True)).select_related('medication'),
        'quick_form': QuickIntakeForm(user=request.user),
        'quick_medications_data': list(Medication.objects.filter(owner=request.user).values('id', 'dosage')),
        'today_entry': today_entry,
        'today_intakes': today_intakes,
        'total_intakes': total_intakes,
        'taken_intakes': taken_intakes,
        'intake_progress': round(taken_intakes * 100 / total_intakes) if total_intakes else 0,
    }
    return render(request, 'dashboard.html', context)

@login_required
def quick_intake_view(request):
    form = QuickIntakeForm(request.POST if request.method == 'POST' else None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        taken_at = timezone.localtime(form.cleaned_data['taken_at'])
        with transaction.atomic():
            if form.cleaned_data['mode'] == 'new':
                medication = Medication.objects.create(owner=request.user, name=form.cleaned_data['name'], dosage=form.cleaned_data['dosage'], as_needed=True)
            else:
                medication = Medication.objects.select_for_update().get(pk=form.cleaned_data['medication'].pk, owner=request.user)
            last = medication.intakes.filter(date=taken_at.date()).order_by('-slot').first()
            MedicationIntake.objects.create(medication=medication, date=taken_at.date(), slot=last.slot + 1 if last else 1, is_extra=True, taken=True, taken_at=taken_at, reason=form.cleaned_data['reason'])
        messages.success(request, f"Приём записан: {medication.name}")
        return redirect('dashboard')
    return render(request, 'quick_intake.html', {'quick_form': form, 'quick_medications_data': list(Medication.objects.filter(owner=request.user).values('id', 'dosage'))})

@require_POST
@login_required
def record_as_needed_view(request, pk):
    now = timezone.localtime()
    with transaction.atomic():
        medication = get_object_or_404(Medication.objects.select_for_update(), pk=pk, as_needed=True, owner=request.user)
        last = medication.intakes.filter(date=now.date()).order_by('-slot').first()
        MedicationIntake.objects.create(medication=medication, date=now.date(), slot=last.slot + 1 if last else 1, is_extra=True, taken=True, taken_at=now)
    messages.success(request, f"Приём записан: {medication.name}")
    return redirect('dashboard')

@require_POST
@login_required
def toggle_intake_status_view(request, pk):
    """Клик по круглой таблетке"""
    desired = request.POST.get('taken')
    if desired is not None and desired not in ('true', 'false'):
        return JsonResponse({'error': 'Некорректный статус приёма.'}, status=400)
    with transaction.atomic():
        intake = get_object_or_404(MedicationIntake.objects.select_for_update(), pk=pk, medication__owner=request.user)
        taken = desired == 'true' if desired is not None else not intake.taken
        if taken != intake.taken:
            intake.taken = taken
            intake.taken_at = timezone.now() if taken else None
            fields = ['taken', 'taken_at']
            if not taken:
                times = intake.medication.scheduled_times
                value = times[intake.slot - 1] if len(times) >= intake.slot else None
                scheduled = time.fromisoformat(value) if value else None
                if scheduled and intake.medication.intakes.filter(date=intake.date, scheduled_time=scheduled).exclude(pk=intake.pk).exists():
                    scheduled = None
                intake.scheduled_time = scheduled
                fields.append('scheduled_time')
            intake.save(update_fields=fields)
    if 'application/json' in request.headers.get('Accept', ''):
        return JsonResponse({
            'taken': intake.taken,
            'taken_at': timezone.localtime(intake.taken_at).strftime('%H:%M') if intake.taken_at else None,
        })
    if intake.taken:
        messages.success(request, f"✓ Вы приняли лекарство: {intake.medication.name}")
    else:
        messages.info(request, f"Отметка о приёме {intake.medication.name} снята.")
    return redirect('dashboard')

@login_required
def medication_list_view(request):
    medications = Medication.objects.filter(owner=request.user)
    section = request.session.get('medication_section', 'all')
    if section not in ('all', 'courses', 'occasional'):
        section = 'all'
    return render(request, 'medications/list.html', {
        'medications': medications,
        'courses': medications.filter(as_needed=False),
        'occasional_medications': medications.filter(as_needed=True),
        'selected_section': section,
    })

@require_POST
@login_required
def medication_section_view(request):
    section = request.POST.get('section')
    if section not in ('all', 'courses', 'occasional'):
        return HttpResponseBadRequest('Неизвестный раздел.')
    request.session['medication_section'] = section
    return redirect('medication_list')


@login_required
def medication_detail_view(request, pk):
    medication = get_object_or_404(Medication, pk=pk, owner=request.user)
    today = timezone.localdate()
    intakes = medication.intakes.annotate(
        future_group=Case(When(date__lte=today, then=Value(0)), default=Value(1), output_field=IntegerField()),
        history_date=Case(When(date__lte=today, then='date'), default=Value(None), output_field=DateField()),
    ).order_by('future_group', '-history_date', 'date', '-slot')
    page = Paginator(intakes, 20).get_page(request.GET.get('page'))
    return render(request, 'medications/detail.html', {'medication': medication, 'intakes': page, 'intake_page': page})

@login_required
def medication_create_view(request):
    """Добавление лекарства"""
    if request.method == 'POST':
        form = MedicationForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                medication = form.save(commit=False)
                medication.owner = request.user
                medication.save()
                sync_intakes(medication)
            messages.success(request, f"Курс «{medication.name}» добавлен!")
            return redirect('medication_list')
    else:
        today_str = timezone.localtime(timezone.now()).date().strftime('%Y-%m-%d')
        form = MedicationForm(initial={'start_date': today_str, 'end_date': today_str})
    return render(request, 'form.html', {'form': form, 'title': 'Добавление препарата'})

@login_required
def medication_update_view(request, pk):
    medication = get_object_or_404(Medication, pk=pk, owner=request.user)
    if request.method == 'POST':
        form = MedicationForm(request.POST, instance=medication)
        if form.is_valid():
            with transaction.atomic():
                medication = form.save(commit=False)
                medication.owner = request.user
                medication.save()
                sync_intakes(medication)
            messages.success(request, "Препарат успешно обновлен.")
            return redirect('medication_list')
    else:
        form = MedicationForm(instance=medication)
    return render(request, 'form.html', {'form': form, 'title': 'Редактирование препарата'})

@login_required
def medication_delete_view(request, pk):
    medication = get_object_or_404(Medication, pk=pk, owner=request.user)
    if request.method == 'POST':
        name = medication.name
        medication.delete()
        messages.success(request, f"Препарат «{name}» удален.")
        return redirect('medication_list')
    return render(request, 'medications/confirm_delete.html', {'medication': medication})

@login_required
def diary_list_view(request):
    entries = HealthEntry.objects.filter(owner=request.user).order_by('-date')
    return render(request, 'diary/list.html', {'entries': entries})

@login_required
def diary_detail_view(request, pk):
    entry = get_object_or_404(HealthEntry, pk=pk, owner=request.user)
    return render(request, 'diary/detail.html', {'entry': entry})

@login_required
def diary_create_view(request):
    """Создание записи в дневнике"""
    if request.method == 'POST':
        form = HealthEntryForm(request.POST, user=request.user)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.owner = request.user
            entry.save()
            messages.success(request, "Запись в дневнике сохранена!")
            return redirect('dashboard')
    else:
        today_str = timezone.localtime(timezone.now()).date().strftime('%Y-%m-%d')
        form = HealthEntryForm(initial={'date': today_str}, user=request.user)
    return render(request, 'form.html', {'form': form, 'title': 'Новая запись самочувствия'})

@login_required
def diary_update_view(request, pk):
    entry = get_object_or_404(HealthEntry, pk=pk, owner=request.user)
    if request.method == 'POST':
        form = HealthEntryForm(request.POST, instance=entry, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Изменения сохранены.")
            return redirect('dashboard')
    else:
        form = HealthEntryForm(instance=entry, user=request.user)
    return render(request, 'form.html', {'form': form, 'title': 'Редактирование записи'})

@login_required
def diary_delete_view(request, pk):
    entry = get_object_or_404(HealthEntry, pk=pk, owner=request.user)
    if request.method == 'POST':
        entry.delete()
        messages.success(request, "Запись удалена.")
        return redirect('dashboard')
    return render(request, 'diary/confirm_delete.html', {'entry': entry})

@login_required
def history_view(request):
    all_intakes = MedicationIntake.objects.filter(medication__owner=request.user, date__lte=timezone.localdate()).select_related('medication').order_by('-date', '-taken_at', '-scheduled_time', '-pk')
    all_entries = HealthEntry.objects.filter(owner=request.user).order_by('-date')
    context = {
        'all_intakes': all_intakes,
        'all_entries': all_entries,
    }
    return render(request, 'history.html', context)

