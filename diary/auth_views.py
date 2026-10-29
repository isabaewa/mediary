from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
from .forms import SignUpForm, SignInForm


class SignInView(LoginView):
    template_name = 'registration/login.html'
    authentication_form = SignInForm
    redirect_authenticated_user = True

    def get_initial(self):
        initial = super().get_initial()
        initial['remember_me'] = self.request.COOKIES.get('mediary_remember') == '1'
        return initial

    def form_valid(self, form):
        response = super().form_valid(form)  # authenticate/login and session key rotation by Django.
        remember = form.cleaned_data['remember_me']
        self.request.session.set_expiry(14*24*60*60 if remember else 0)
        # Separate, non-sensitive cookie: only the preference of the checkbox.
        response.set_cookie('mediary_remember', '1' if remember else '0',
                            max_age=30*24*60*60, httponly=True, samesite='Lax',
                            secure=self.request.is_secure())
        response.delete_cookie('mediary_compact')
        return response


def signup_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    form = SignUpForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        form.save()  # UserCreationForm hashes the password; raw passwords are never saved.
        messages.success(request, 'Аккаунт создан. Войдите с вашим логином и паролем.')
        return redirect('login')
    return render(request, 'registration/signup.html', {'form': form})


@require_POST
def signout_view(request):
    logout(request)  # Clears the authenticated session and its stored preferences.
    response = redirect('login')
    response.delete_cookie('mediary_compact')
    return response
