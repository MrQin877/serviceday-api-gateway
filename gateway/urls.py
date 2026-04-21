from django.urls import path
from . import views

urlpatterns = [
    path('',                        views.home,                 name='home'),
    path('login/',                  views.login_view,           name='login'),
    path('logout/',                 views.logout_view,          name='logout'),
    path('employee/dashboard/',     views.employee_dashboard,   name='employee_dashboard'),
    path('admin/dashboard/',        views.admin_dashboard,      name='admin_dashboard'),
    path('notification/broadcast/', views.broadcast_view,       name='broadcast'),
    path('notification/log/',       views.notification_log_view,name='notification_log'),
    path('registration/register/<int:ngo_id>/',  views.register_activity,    name='register_activity'),
    path('registration/cancel/',                 views.cancel_registration,   name='cancel_registration'),
    path('registration/switch/<int:ngo_id>/',    views.switch_registration,   name='switch_registration'),
    path('checkin/qr/<int:ngo_id>/',             views.generate_qr,           name='generate_qr'),
    path('checkin/scan/', views.scan_view, name='scan_checkin'),
]