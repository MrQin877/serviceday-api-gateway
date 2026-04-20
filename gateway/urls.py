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
    path('registration/',           views.registration_view,    name='registration'),
    path('checkin/',                views.checkin_view,         name='checkin'),
]