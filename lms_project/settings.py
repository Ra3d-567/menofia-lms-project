"""
Essential Django settings for the LMS project.
"""

from pathlib import Path
import os
from dotenv import load_dotenv

# السطر ده هو اللي هيخلي بايثون يقرأ ملف الـ .env
load_dotenv()
from datetime import timedelta
import dj_database_url

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-dummy-key-replace-in-production'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = 'RENDER' not in os.environ
ALLOWED_HOSTS = ['*']

# Application definition
INSTALLED_APPS = [
    # Custom apps
    'lms_app',
    'jazzmin',
    
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'cloudinary_storage',
'cloudinary',
    
    # Security
    'axes',
]

AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesBackend',
    'django.contrib.auth.backends.ModelBackend',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'lms_app.middleware.LockdownMiddleware',
    'lms_app.middleware.AdminDeviceMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'axes.middleware.AxesMiddleware',
]

ROOT_URLCONF = 'lms_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'lms_app.context_processors.active_announcement',
                'lms_app.context_processors.user_notifications',
            ],
        },
    },
]

WSGI_APPLICATION = 'lms_project.wsgi.application'

# Database
DATABASES = {
    'default': dj_database_url.config(
        default='sqlite:///' + str(BASE_DIR / 'db.sqlite3'),
        conn_max_age=600
    )
}

# CRUCIAL LMS CONFIGURATION: Use our custom User model
AUTH_USER_MODEL = 'lms_app.User'

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Global Authentication Routing
LOGIN_URL = '/login/'
LOGOUT_REDIRECT_URL = '/login/'

# Media files (Uploaded materials)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Session Security
SESSION_COOKIE_AGE = 1800  # 30 minutes
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# Axes Brute Force Protection
AXES_FAILURE_LIMIT = 10
AXES_COOLOFF_TIME = timedelta(minutes=10)
AXES_LOCKOUT_CALLABLE = 'lms_app.views.custom_lockout_response'
AXES_RESET_ON_SUCCESS = True

# PRODUCTION SECURITY SETTINGS
# DEBUG = False
# ALLOWED_HOSTS = ['*']
# SECURE_BROWSER_XSS_FILTER = True
# X_FRAME_OPTIONS = 'DENY'
# SECURE_CONTENT_TYPE_NOSNIFF = True
# CSRF_COOKIE_SECURE = True
# SESSION_COOKIE_SECURE = True
# تعطيل نظام الحماية لو إحنا في وضع التطوير (Local) عشان نعرف نجرب براحتنا
AXES_ENABLED = True

JAZZMIN_SETTINGS = {
    "site_title": "إدارة المنصة",
    "site_header": "كلية التربية النوعية",
    "site_brand": "جامعة المنوفية",
    "site_logo": "images/logo_nav.png", # Ensure this matches the existing logo in static
    "login_logo": None,
    "login_logo_dark": None,
    "site_logo_classes": "img-circle",
    "site_icon": None,
    "welcome_sign": "Admin Panel | لوحة تحكم الأدمن",
    "copyright": "جامعة المنوفية",
    "search_model": ["auth.User", "lms_app.User"],
    "user_avatar": None,
    "site_url": False,
    "topmenu_links": [
        {"name": "الرئيسية",  "url": "admin:index", "permissions": ["auth.view_user"]},
        {"name": "استيراد ملف الطلاب (CSV)", "url": "/management/import-students/", "icon": "fas fa-file-csv", "permissions": ["auth.add_user"]}
    ],
    "show_sidebar": True,
    "navigation_expanded": True,
    "hide_apps": [],
    "hide_models": [],
    "order_with_respect_to": ["auth", "lms_app"],
    "icons": {
        "auth": "fas fa-users-cog",
        "auth.user": "fas fa-user",
        "auth.Group": "fas fa-users",
        "lms_app.User": "fas fa-user-graduate",
        "lms_app.Subject": "fas fa-book",
        "lms_app.SubjectSection": "fas fa-chalkboard-teacher",
        "lms_app.Assignment": "fas fa-tasks",
        "lms_app.Submission": "fas fa-file-upload",
        "lms_app.AdminDevice": "fas fa-laptop-code",
        "lms_app.AttendanceSession": "fas fa-calendar-check",
    },
    "default_icon_parents": "fas fa-chevron-circle-right",
    "default_icon_children": "fas fa-circle",
    "related_modal_active": False,
    "custom_css": "css/jazzmin_custom.css",
    "custom_js": None,
    "use_google_fonts_cdn": True,
    "show_ui_builder": True, # Allows admin to customize theme live
    "changeform_format": "horizontal_tabs",
    "language_chooser": False,
}

JAZZMIN_UI_TWEAKS = {
    "navbar_small_text": False,
    "footer_small_text": False,
    "body_small_text": False,
    "brand_small_text": False,
    "brand_colour": "navbar-dark",
    "accent": "accent-primary",
    "navbar": "navbar-dark",
    "no_navbar_border": False,
    "navbar_fixed": False,
    "layout_boxed": False,
    "footer_fixed": False,
    "sidebar_fixed": True,
    "sidebar": "sidebar-dark-primary",
    "sidebar_nav_small_text": False,
    "sidebar_disable_expand": False,
    "sidebar_nav_child_indent": False,
    "sidebar_nav_compact_style": False,
    "sidebar_nav_legacy_style": False,
    "sidebar_nav_flat_style": False,
    "theme": "darkly",
    "dark_mode_theme": "darkly",
    "button_classes": {
        "primary": "btn-primary",
        "secondary": "btn-secondary",
        "info": "btn-info",
        "warning": "btn-warning",
        "danger": "btn-danger",
        "success": "btn-success"
    }
}

DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1520526985229631700/k8j6dS1IWIJbW7ujOav_vcMvQZdlpN0Y3lZyi7dKfAKG4En0QuLG8-h8Cdp56ooFmHns"
DISCORD_SECURITY_WEBHOOK_URL = "https://discord.com/api/webhooks/1520529604002054165/pdRk3ONaakP4BdWlIB7gmwDYz-iM7E5XCy7LfHLcP3ti2dikC6Ib9Wr179fuJNNsGFVH"
DISCORD_ACTIVITY_WEBHOOK_URL = "https://discord.com/api/webhooks/1520529429506425063/6S5NuSxlcQC7unT_cTT2e-_vbWzMUyVFfMfZet6-a-xznHIxxDacM_p2GEa_c0KDWtYL"
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'discord': {
            'level': 'ERROR',
            'class': 'lms_project.discord_logger.DiscordExceptionHandler',
            'formatter': 'verbose',
        },
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'discord'],
            'level': 'INFO',
            'propagate': True,
        },
        'django.request': {
            'handlers': ['discord', 'console'],
            'level': 'ERROR',
            'propagate': False,
        },
    },
}
DISCORD_BOT_TOKEN = os.environ.get('DISCORD_BOT_TOKEN', '')
DISCORD_OWNER_ID = "1086107264961753098"
DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL', '')
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'
DEFAULT_FILE_STORAGE = 'cloudinary_storage.storage.MediaCloudinaryStorage'