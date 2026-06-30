from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect


class AdminDeviceMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/secret-uni-portal/') and request.user.is_authenticated:
            # Check if user is staff/superuser
            if request.user.is_staff or request.user.is_superuser:
                # Exclude the logout path and register device path from checks
                if not request.path.startswith('/secret-uni-portal/logout/') and not request.path.startswith('/secret-uni-portal/register-device/'):
                    from lms_app.models import AdminDevice

                    # If the admin has no registered devices, we allow them to log in 
                    # so they can navigate to the registration URL.
                    trusted_devices = AdminDevice.objects.filter(user=request.user)
                    
                    if trusted_devices.exists():
                        cookie_token = request.COOKIES.get('admin_trusted_device')
                        
                        # Check if the cookie token matches ANY of their registered devices
                        valid_device = False
                        if cookie_token:
                            for device in trusted_devices:
                                if str(device.device_token) == cookie_token:
                                    valid_device = True
                                    break
                                    
                        if not valid_device:
                            try:
                                from lms_project.discord_alerts import \
                                    send_security_alert
                                ip = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0] if request.META.get('HTTP_X_FORWARDED_FOR') else request.META.get('REMOTE_ADDR')
                                send_security_alert(
                                    title="⚠️ Unauthorized Admin Access Attempt",
                                    description=f"**Username:** {request.user.username}\n**IP Address:** {ip}\nAttempted to access admin portal from an unregistered device.",
                                    color=16744192 # Orange
                                )
                            except Exception as e:
                                print(f"Error logging admin intrusion: {e}")
                                
                            logout(request)
                            messages.error(request, "Access Denied: Unrecognized Device. An alert has been sent to the administrators.")
                            return redirect('login')
                            
        response = self.get_response(request)
        return response

from django.conf import settings
from django.shortcuts import render


class LockdownMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        lockdown_file = settings.BASE_DIR / 'lockdown.flag'
        
        # If lockdown flag exists and user is not accessing admin portal
        if lockdown_file.exists() and not request.path.startswith('/secret-uni-portal/'):
            return render(request, 'maintenance.html', status=503)
            
        response = self.get_response(request)
        return response
