"""Именованные маршруты: аутентификация, препараты, приёмы и дневник."""

from django.contrib.auth.views import PasswordChangeView
from django.urls import path, reverse_lazy

from . import auth_views, views

urlpatterns = [
    # Аутентификация использует стандартные механизмы паролей и сессий Django.
    path(
        'accounts/password/change/',
        PasswordChangeView.as_view(
            template_name='registration/password_change.html',
            success_url=reverse_lazy('dashboard'),
        ),
        name='password_change',
    ),
    path('accounts/login/', auth_views.SignInView.as_view(), name='login'),
    path('accounts/signup/', auth_views.signup_view, name='signup'),
    path('accounts/logout/', auth_views.signout_view, name='logout'),
    path('medications/section/', views.medication_section_view, name='medication_section'),
    path('intake/add/', views.quick_intake_view, name='quick_intake'),
    # Главная
    path('', views.dashboard_view, name='dashboard'),
    # Лекарства CRUD
    path('medications/', views.medication_list_view, name='medication_list'),
    path('medications/add/', views.medication_create_view, name='medication_create'),
    path('medications/<int:pk>/', views.medication_detail_view, name='medication_detail'),
    path('medications/<int:pk>/edit/', views.medication_update_view, name='medication_update'),
    path('medications/<int:pk>/delete/', views.medication_delete_view, name='medication_delete'),
    path('medications/<int:pk>/take/', views.record_as_needed_view, name='record_as_needed'),
    # Изменение статуса выполняется только POST; один URL поддерживает HTML и JSON.
    path('intake/<int:pk>/toggle/', views.toggle_intake_status_view, name='toggle_intake'),
    # Дневник CRUD
    path('diary/', views.diary_list_view, name='diary_list'),
    path('diary/add/', views.diary_create_view, name='diary_create'),
    path('diary/<int:pk>/', views.diary_detail_view, name='diary_detail'),
    path('diary/<int:pk>/edit/', views.diary_update_view, name='diary_update'),
    path('diary/<int:pk>/delete/', views.diary_delete_view, name='diary_delete'),
    # История
    path('history/', views.history_view, name='history'),
]
