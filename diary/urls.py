from django.urls import path
from . import views

urlpatterns = [
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
    # Переключение статуса приема
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
