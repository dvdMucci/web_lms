from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm, PasswordChangeForm
from django.contrib.auth import authenticate
from django.utils import timezone
from .models import CustomUser, StudentRegistrationToken
import pyotp # Necesario para la verificación de OTP, aunque TOTPDevice lo maneja directamente

class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    user_type = forms.ChoiceField(choices=CustomUser.USER_TYPES, required=True)
    
    class Meta:
        model = CustomUser
        fields = ('username', 'email', 'first_name', 'last_name', 'user_type')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].label = 'Contraseña'
        self.fields['password2'].label = 'Repetir contraseña'
        self.fields['password1'].help_text = 'Ingresá una contraseña segura.'
        self.fields['password2'].help_text = 'Volvé a ingresar la contraseña para confirmarla.'

        for field_name in ['password1', 'password2']:
            self.fields[field_name].widget.attrs['class'] = 'form-control'
            self.fields[field_name].widget.attrs['autocomplete'] = 'new-password'

        self.fields['password1'].widget.attrs['placeholder'] = 'Ingresá la contraseña'
        self.fields['password2'].widget.attrs['placeholder'] = 'Repetí la contraseña'

        self.fields['password2'].error_messages['required'] = 'Debes repetir la contraseña.'
        self.error_messages['password_mismatch'] = 'Las contraseñas no coinciden. Verificalas e intentá de nuevo.'
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
        return user


class StudentRegistrationForm(UserCreationForm):
    class Meta:
        model = CustomUser
        fields = ('username', 'first_name', 'last_name')
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].label = 'Contraseña'
        self.fields['password2'].label = 'Repetir contraseña'
        self.fields['password1'].help_text = 'Ingresá una contraseña segura.'
        self.fields['password2'].help_text = 'Volvé a ingresar la contraseña para confirmarla.'

        for field_name in ['password1', 'password2']:
            self.fields[field_name].widget.attrs['class'] = 'form-control'
            self.fields[field_name].widget.attrs['autocomplete'] = 'new-password'

        self.fields['password1'].widget.attrs['placeholder'] = 'Ingresá tu contraseña'
        self.fields['password2'].widget.attrs['placeholder'] = 'Repetí tu contraseña'

        # Mensajes claros en español para el flujo de confirmación de contraseña.
        self.fields['password2'].error_messages['required'] = 'Debes repetir la contraseña.'
        self.error_messages['password_mismatch'] = 'Las contraseñas no coinciden. Verificalas e intentá de nuevo.'

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = ''
        user.user_type = 'student'
        if commit:
            user.save()
        return user


class StudentRegistrationTokenCreateForm(forms.ModelForm):
    starts_at = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'})
    )
    expires_at = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'})
    )

    class Meta:
        model = StudentRegistrationToken
        fields = ('description', 'starts_at', 'expires_at', 'max_uses')
        widgets = {
            'description': forms.TextInput(attrs={'class': 'form-control'}),
            'max_uses': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
        }

    def clean(self):
        cleaned_data = super().clean()
        starts_at = cleaned_data.get('starts_at')
        expires_at = cleaned_data.get('expires_at')
        if starts_at and timezone.is_naive(starts_at):
            starts_at = timezone.make_aware(starts_at, timezone.get_current_timezone())
            cleaned_data['starts_at'] = starts_at
        if expires_at and timezone.is_naive(expires_at):
            expires_at = timezone.make_aware(expires_at, timezone.get_current_timezone())
            cleaned_data['expires_at'] = expires_at
        if starts_at and expires_at and expires_at <= starts_at:
            raise forms.ValidationError('La fecha de expiración debe ser posterior al inicio.')
        return cleaned_data

class CustomUserChangeForm(UserChangeForm):
    class Meta:
        model = CustomUser
        fields = ('username', 'email', 'first_name', 'last_name', 'user_type', 'is_active')

class ProfileForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ['first_name', 'last_name', 'email', 'telegram_chat_id']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'telegram_chat_id': forms.TextInput(attrs={'class': 'form-control'}),
        }

class ChangePasswordForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Opcional: Añadir clases CSS a los campos para estilizar con Bootstrap, por ejemplo
        for field_name in self.fields:
            self.fields[field_name].widget.attrs['class'] = 'form-control'

class LoginForm(forms.Form):
    username = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )
    otp_token = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Código 2FA (opcional)'})
    )
    
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
    
    def clean(self):
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')
        otp_token = self.cleaned_data.get('otp_token')
        
        if username and password:
            self.user_cache = authenticate(
                self.request, 
                username=username, 
                password=password
            )
            
            if self.user_cache is None:
                raise forms.ValidationError("Credenciales inválidas")
            
            if not self.user_cache.is_active:
                raise forms.ValidationError("Esta cuenta está desactivada")
            
            # Verificar 2FA si está habilitado
            if self.user_cache.is_2fa_enabled:
                if not otp_token:
                    raise forms.ValidationError("Se requiere código 2FA")
                
                # Usar django-otp para verificar el token
                device = self.user_cache.totpdevice_set.filter(confirmed=True).first()
                if device and not device.verify_token(otp_token):
                    raise forms.ValidationError("Código 2FA inválido")
        
        return self.cleaned_data
    
    def get_user(self):
        return getattr(self, 'user_cache', None)