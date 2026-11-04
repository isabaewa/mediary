"""Личный кабинет, вход, регистрация и управление сессией Django Authentication."""

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.contrib.messages.views import SuccessMessageMixin
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_http_methods, require_POST

from .forms import ProfileForm, SignInForm, SignUpForm
from .selectors import account_summary_for


@login_required
@require_http_methods(['GET', 'HEAD', 'POST'])
def profile_view(request):
    """Кабинет без id в URL: форма всегда привязана к request.user."""
    form = ProfileForm(
        request.POST if request.method == 'POST' else None,
        instance=request.user,
    )
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, 'Данные профиля сохранены.')
            return redirect('profile')
        # ModelForm меняет instance при проверке; шапка должна показывать сохранённые данные.
        request.user.refresh_from_db()
    return render(
        request,
        'account/profile.html',
        {
            'form': form,
            'summary': account_summary_for(request.user),
        },
    )


class ProfilePasswordChangeView(SuccessMessageMixin, PasswordChangeView):
    """Стандартная смена пароля Django сохраняет текущую сессию."""

    template_name = 'registration/password_change.html'
    success_url = reverse_lazy('profile')
    success_message = 'Пароль изменён.'


class SignInView(LoginView):
    """Восстановить флажок из cookie; срок входа задать только после аутентификации."""

    template_name = 'registration/login.html'
    authentication_form = SignInForm
    redirect_authenticated_user = True

    def get_initial(self):
        initial = super().get_initial()
        initial['remember_me'] = self.request.COOKIES.get('mediary_remember') == '1'
        return initial

    def form_valid(self, form):
        response = super().form_valid(form)  # Django выполняет вход и меняет идентификатор сессии.
        remember = form.cleaned_data['remember_me']
        self.request.session.set_expiry(14 * 24 * 60 * 60 if remember else 0)
        # Cookie хранит только флажок; она не подтверждает вход и не содержит учётных данных.
        response.set_cookie(
            'mediary_remember',
            '1' if remember else '0',
            max_age=30 * 24 * 60 * 60,
            httponly=True,
            samesite='Lax',
            secure=self.request.is_secure(),
        )
        response.delete_cookie('mediary_compact')
        return response


def signup_view(request):
    """Создать аккаунт через UserCreationForm и направить пользователя на вход."""
    if request.user.is_authenticated:
        return redirect('dashboard')
    form = SignUpForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        form.save()  # UserCreationForm сохраняет хеш, а не исходный пароль.
        messages.success(request, 'Аккаунт создан. Войдите с вашим логином и паролем.')
        return redirect('login')
    return render(request, 'registration/signup.html', {'form': form})


@require_POST
def signout_view(request):
    """Завершить сессию только по POST, защищённому CSRF middleware."""
    logout(request)  # Удаляет состояние входа и данные текущей сессии.
    response = redirect('login')
    response.delete_cookie('mediary_compact')
    return response
