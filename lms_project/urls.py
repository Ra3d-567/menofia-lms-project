from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from lms_app import views

urlpatterns = [
    path('secret-uni-portal/logout/', views.user_logout, name='custom_admin_logout'),
    path('secret-uni-portal/', admin.site.urls),
    path('', include('lms_app.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
