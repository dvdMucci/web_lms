
from datetime import timedelta
from pathlib import Path
import environ
import os
import sys

# Inicializar entorno
env = environ.Env()


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Leer archivo .env
environ.Env.read_env(os.path.join(BASE_DIR, '../.env'))


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/3.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
#
# Sin default a proposito: si falta DJANGO_SECRET_KEY, django-environ lanza
# ImproperlyConfigured y el contenedor no arranca. Antes habia un default hardcodeado
# que ademas esta publicado en el repo de GitHub, asi que un despliegue sin .env
# arrancaba silenciosamente con una clave conocida (sesiones y tokens firmados
# falsificables).
#   Generar una nueva:
#   python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
SECRET_KEY = env('DJANGO_SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
# Produccion: DJANGO_DEBUG=False en .env del host (Compose). Desarrollo: DJANGO_DEBUG=True.
DEBUG = env.bool('DJANGO_DEBUG', default=False)

# Pantalla de mantenimiento (503). Activar con MAINTENANCE_MODE=True en .env
MAINTENANCE_MODE = env.bool('MAINTENANCE_MODE', default=False)

# Sin '*': con el comodin, Django aceptaba cualquier cabecera Host. Eso permitia
# envenenar los links absolutos que arma request.build_absolute_uri(), en particular
# el mail de verificacion de cuenta (accounts/views.py), haciendolos apuntar al
# dominio de un atacante para robar el token firmado.
ALLOWED_HOSTS = env.list(
    'DJANGO_ALLOWED_HOSTS',
    default=['marinaojeda.ar', 'www.marinaojeda.ar', 'localhost', '127.0.0.1'],
)

# Configuraci?n CSRF para dominios confiables
CSRF_TRUSTED_ORIGINS = [
    'https://marinaojeda.ar',
    'https://www.marinaojeda.ar',
    'http://localhost:5801',
    'http://127.0.0.1:5801',
]

# Configuracion para proxy reverso (Traefik / Cloudflare)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True

# Cookies solo por HTTPS; SameSite Lax reduce riesgo CSRF en navegaciones cruzadas.
# En produccion (Brasil/Traefik) definir SESSION_COOKIE_DOMAIN=.marinaojeda.ar y CSRF_COOKIE_DOMAIN igual.
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_DOMAIN = env('SESSION_COOKIE_DOMAIN', default=None)
CSRF_COOKIE_DOMAIN = env('CSRF_COOKIE_DOMAIN', default=None)

# Traefik ya redirige 80 -> 443, pero esto cubre el caso de que algo llegue por HTTP
# directo al contenedor. Funciona junto con SECURE_PROXY_SSL_HEADER de mas arriba.
SECURE_SSL_REDIRECT = env.bool('DJANGO_SECURE_SSL_REDIRECT', default=True)

# HSTS: el navegador recuerda por un ano que este dominio es solo HTTPS.
# include_subdomains queda en False a proposito: no todos los subdominios del VPS
# estan detras de Traefik con TLS. Subirlo requiere verificarlos uno por uno.
SECURE_HSTS_SECONDS = env.int('DJANGO_HSTS_SECONDS', default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

# Application definition

INSTALLED_APPS = [
    'rest_framework',
    'accounts',
    'courses',
    'attendance',
    'grades',
    'units',
    'materials',
    'assignments',
    'quizzes',
    'forums',
    'notifications',
    'core',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_otp',
    'django_otp.plugins.otp_totp',
    'django_otp.plugins.otp_static',
    'axes',
]

AUTH_USER_MODEL = 'accounts.CustomUser'  # Usar el modelo de usuario personalizado

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'core.middleware.MaintenanceModeMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    # accounts.middleware.StudentEmailVerificationMiddleware se quito el 2026-07-21:
    # su __call__ era `return self.get_response(request)`, o sea no verificaba nada.
    # La verificacion real de email se hace en las vistas de accounts.
    'core.middleware.StudentViewMiddleware',
    'django_otp.middleware.OTPMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # Debe ir al final, despues de AuthenticationMiddleware.
    'axes.middleware.AxesMiddleware',
]

# django-axes: freno de fuerza bruta en el login. Antes no habia ninguno y 2FA es
# opcional (is_2fa_enabled default False), asi que la mayoria de las cuentas dependen
# solo de la contrasena.
AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',
    'django.contrib.auth.backends.ModelBackend',
]
# Se bloquea la combinacion usuario+IP, no la IP sola: en una escuela muchos alumnos
# comparten la misma IP publica y bloquear por IP dejaria a todo un curso afuera.
AXES_LOCKOUT_PARAMETERS = [['username', 'ip_address']]
AXES_FAILURE_LIMIT = env.int('AXES_FAILURE_LIMIT', default=8)
AXES_COOLOFF_TIME = timedelta(minutes=env.int('AXES_COOLOFF_MINUTES', default=30))
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_TEMPLATE = 'accounts/lockout.html'

ROOT_URLCONF = 'web.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.student_view',
                'notifications.context_processors.notifications_processor',
            ],
        },
    },
]



WSGI_APPLICATION = 'web.wsgi.application'


# Database
# https://docs.djangoproject.com/en/3.2/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': env('DB_NAME'),
        'USER': env('DB_USER'),
        'PASSWORD': env('DB_PASSWORD'),
        # Nombre del servicio Compose (db) o IP si el DNS falla en multi-red.
        'HOST': env('DB_HOST', default='db'),
        'PORT': env('DB_PORT'),
        'OPTIONS': {
            'sql_mode': 'traditional', # Modo SQL para compatibilidad
            'charset': 'utf8mb4',
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES', character_set_connection=utf8mb4, collation_connection=utf8mb4_unicode_ci",
            'use_unicode': True,
        },
        # Reutilizar la conexion 60 s. Estaba en 0 (conexion nueva en cada request,
        # o sea handshake + autenticacion contra MariaDB por cada pagina) por un
        # problema de autenticacion viejo que ya no aplica con mysqlclient 2.2.8.
        'CONN_MAX_AGE': env.int('DB_CONN_MAX_AGE', default=60),
        'ATOMIC_REQUESTS': True,  # Transacciones automaticas
    }
}

# Configuraci?n de conexi?n a la base de datos
DB_CONNECTION_TIMEOUT = 20
DB_READ_TIMEOUT = 30
DB_WRITE_TIMEOUT = 30


# Password validation
# https://docs.djangoproject.com/en/3.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/3.2/topics/i18n/

LANGUAGE_CODE = 'es-es'
TIME_ZONE = 'America/Argentina/Buenos_Aires'
USE_I18N = True
USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.2/howto/static-files/

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
# Django 5.x: usar STORAGES en lugar del deprecado STATICFILES_STORAGE.
# El comentario de antes decia "nombres hasheados (cache-bust automatico)" pero el
# backend configurado era CompressedStaticFilesStorage, que comprime pero NO hashea:
# el cache-busting no estaba funcionando. Ver core/storage_backends.py.
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'core.storage_backends.ResilientManifestStaticFilesStorage',
    },
}
MEDIA_URL = '/media/'
# MEDIA_ROOT apunta al bucket de Oracle OCI montado.
# OJO: /media/ NO se sirve como ruta publica (ver web/urls.py). Todo archivo sale por
# una vista con permisos. MEDIA_URL queda definido solo porque Django lo requiere.
MEDIA_ROOT = '/home/ubuntu/marinaOjedaS3/media'

# Cache compartido entre workers de gunicorn.
# El default (LocMemCache) es por proceso: con varios workers cada uno tenia su propia
# copia del uso de almacenamiento y el escaneo del bucket se repetia N veces.
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
        # En disco local del contenedor, NUNCA sobre el mount s3fs.
        'LOCATION': env('DJANGO_CACHE_DIR', default='/tmp/django_cache'),
        'TIMEOUT': 300,
    }
}

# Default primary key field type
# https://docs.djangoproject.com/en/3.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/accounts/login/'
# OTP Settings
OTP_TOTP_ISSUER = 'Marina Ojeda LMS' # Nombre del emisor para la aplicaci?n 2FA
OTP_LOGIN_URL = '/accounts/login/' # URL de login para OTP

# Configuraci?n de Mailgun (notificaciones)
MAILGUN_API_KEY = env('MAILGUN_API_KEY', default='')
MAILGUN_DOMAIN = env('MAILGUN_DOMAIN', default='')
MAILGUN_BASE_URL = env('MAILGUN_BASE_URL', default='https://api.mailgun.net')
MAILGUN_FROM_EMAIL = env('MAILGUN_FROM_EMAIL', default='')
MAILGUN_TIMEOUT = env.int('MAILGUN_TIMEOUT', default=10)
MAILGUN_ENABLED = bool(MAILGUN_API_KEY and MAILGUN_DOMAIN and MAILGUN_FROM_EMAIL)

# Verificacion de email
EMAIL_VERIFICATION_MAX_AGE_SECONDS = env.int('EMAIL_VERIFICATION_MAX_AGE_SECONDS', default=172800)
EMAIL_VERIFICATION_COOLDOWN_SECONDS = env.int('EMAIL_VERIFICATION_COOLDOWN_SECONDS', default=300)


# --- Ajustes exclusivos de la suite de tests -------------------------------
# Estos dos settings de produccion rompen al test client de Django, no porque la
# configuracion este mal sino porque el cliente de tests no simula ni HTTPS ni el
# ciclo real de login.
TESTING = 'test' in sys.argv

if TESTING:
    # Client.login() llama a authenticate() sin pasar el request, y AxesBackend lo
    # exige. En produccion el login pasa siempre por LoginForm, que si lo pasa.
    AXES_ENABLED = False
    # El test client hace peticiones HTTP: con el redirect activo, toda vista
    # respondia 301 en lugar de la respuesta esperada.
    SECURE_SSL_REDIRECT = False
    # Sin esto la suite solo pasa si el sitio NO esta en mantenimiento: el middleware
    # devolvia 503 a todo y los tests fallaban por una razon que no tiene que ver con
    # el codigo que se esta probando.
    MAINTENANCE_MODE = False
