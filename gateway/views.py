import requests
from django.shortcuts import render, redirect
from django.contrib import messages
from django.conf import settings

SERVICES = settings.SERVICES


# ── Helpers ───────────────────────────────────────────────────

def get_token(request):
    return request.session.get('access_token')

def auth_headers(request):
    return {'Authorization': f'Bearer {get_token(request)}'}

def is_logged_in(request):
    return bool(request.session.get('access_token'))

def is_admin(request):
    return request.session.get('role') == 'admin'


# ── Home ──────────────────────────────────────────────────────

def home(request):
    if not is_logged_in(request):
        return redirect('login')
    if is_admin(request):
        return redirect('admin_dashboard')
    return redirect('employee_dashboard')


# ── Auth ──────────────────────────────────────────────────────

def login_view(request):
    if is_logged_in(request):
        return redirect('home')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')

        response = requests.post(
            SERVICES['user_service'] + '/api/v1/auth/token/',
            json={'username': username, 'password': password}
        )

        if response.status_code == 200:
            data = response.json()
            request.session['access_token']  = data['access']
            request.session['refresh_token'] = data['refresh']
            request.session['username']      = username

            # get user role from user-service
            me = requests.get(
                SERVICES['user_service'] + '/api/v1/users/me/',
                headers=auth_headers(request)
            )
            if me.status_code == 200:
                request.session['role'] = me.json().get('role', 'employee')
                request.session['user_id'] = me.json().get('id')

            if request.session.get('role') == 'admin':
                return redirect('admin_dashboard')
            return redirect('employee_dashboard')

        return render(request, 'accounts/login.html', {
            'error': 'Invalid username or password.'
        })

    return render(request, 'accounts/login.html')


def logout_view(request):
    refresh = request.session.get('refresh_token')
    if refresh:
        requests.post(
            SERVICES['user_service'] + '/api/v1/users/logout/',
            json={'refresh': refresh},
            headers=auth_headers(request)
        )
    request.session.flush()
    return redirect('login')


def register_view(request):
    if is_logged_in(request):
        return redirect('home')

    if request.method == 'POST':
        payload = {
            'username':   request.POST.get('username', '').strip(),
            'email':      request.POST.get('email', '').strip(),
            'first_name': request.POST.get('first_name', '').strip(),
            'last_name':  request.POST.get('last_name', '').strip(),
            'password1':  request.POST.get('password1', ''),
            'password2':  request.POST.get('password2', ''),
        }
        response = requests.post(
            SERVICES['user_service'] + '/api/v1/users/register/',
            json=payload
        )
        if response.status_code == 201:
            return render(request, 'accounts/login.html', {
                'success': 'Account created! Please log in.'
            })
        errors = response.json()
        return render(request, 'accounts/register.html', {'errors': errors})

    return render(request, 'accounts/register.html')


def forgot_password_view(request):
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        response = requests.post(
            SERVICES['user_service'] + '/api/v1/users/forgot-password/',
            json={'email': email}
        )
        data = response.json()
        # dev only — in production token comes via email
        token = data.get('token')
        if token:
            return redirect('reset_password', token=token)
        return render(request, 'accounts/forgot_password.html', {
            'message': data.get('message')
        })
    return render(request, 'accounts/forgot_password.html')


def reset_password_view(request, token):
    if request.method == 'POST':
        payload = {
            'token':     token,
            'password1': request.POST.get('password1', ''),
            'password2': request.POST.get('password2', ''),
        }
        response = requests.post(
            SERVICES['user_service'] + '/api/v1/users/reset-password/',
            json=payload
        )
        if response.status_code == 200:
            return render(request, 'accounts/login.html', {
                'success': 'Password reset successful. Please log in.'
            })
        return render(request, 'accounts/reset_password.html', {
            'error': response.json().get('error'),
            'token': token
        })
    return render(request, 'accounts/reset_password.html', {'token': token})


# ── Employee Dashboard ────────────────────────────────────────

def employee_dashboard(request):
    if not is_logged_in(request):
        return redirect('login')

    response = requests.get(
        SERVICES['ngo_service'] + '/api/v1/ngos/',
        headers=auth_headers(request)
    )
    ngos = response.json().get('results', []) if response.status_code == 200 else []
    return render(request, 'employee_dashboard/list.html', {'ngos': ngos})


def employee_ngo_detail(request, ngo_id):
    if not is_logged_in(request):
        return redirect('login')

    response = requests.get(
        SERVICES['ngo_service'] + f'/api/v1/ngos/{ngo_id}/',
        headers=auth_headers(request)
    )
    ngo = response.json() if response.status_code == 200 else {}
    return render(request, 'employee_dashboard/detail.html', {'ngo': ngo})


# ── Admin Dashboard ───────────────────────────────────────────

def admin_dashboard(request):
    if not is_logged_in(request) or not is_admin(request):
        return redirect('login')

    response = requests.get(
        SERVICES['ngo_service'] + '/api/v1/ngos/',
        headers=auth_headers(request)
    )
    ngos = response.json().get('results', []) if response.status_code == 200 else []
    return render(request, 'admin_dashboard/list.html', {'ngos': ngos})


# ── Notification ──────────────────────────────────────────────

def broadcast_view(request):
    if not is_logged_in(request) or not is_admin(request):
        return redirect('login')

    if request.method == 'POST':
        requests.post(
            SERVICES['notification_service'] + '/api/v1/notifications/broadcasts/',
            json={'message': request.POST.get('message')},
            headers=auth_headers(request)
        )
        return redirect('broadcast')

    response = requests.get(
        SERVICES['notification_service'] + '/api/v1/notifications/broadcasts/',
        headers=auth_headers(request)
    )
    broadcasts = response.json().get('results', []) if response.status_code == 200 else []
    return render(request, 'notification/broadcast.html', {'broadcasts': broadcasts})


def notification_log_view(request):
    if not is_logged_in(request) or not is_admin(request):
        return redirect('login')

    response = requests.get(
        SERVICES['notification_service'] + '/api/v1/notifications/logs/',
        headers=auth_headers(request)
    )
    logs = response.json().get('results', []) if response.status_code == 200 else []
    return render(request, 'notification/log.html', {'logs': logs})


# ── Registration ──────────────────────────────────────────────

def registration_view(request):
    if not is_logged_in(request):
        return redirect('login')

    response = requests.get(
        SERVICES['registration_service'] + '/api/v1/registrations/my/',
        headers=auth_headers(request)
    )
    registration = response.json() if response.status_code == 200 else None
    return render(request, 'registration/list.html', {'registration': registration})


def register_activity(request, ngo_id):
    if not is_logged_in(request):
        return redirect('login')

    requests.post(
        SERVICES['registration_service'] + f'/api/v1/registrations/register/{ngo_id}/',
        headers=auth_headers(request)
    )
    return redirect('employee_dashboard')


def cancel_registration(request):
    if not is_logged_in(request):
        return redirect('login')

    requests.delete(
        SERVICES['registration_service'] + '/api/v1/registrations/cancel/',
        headers=auth_headers(request)
    )
    return redirect('employee_dashboard')


def switch_registration(request, ngo_id):
    if not is_logged_in(request):
        return redirect('login')

    requests.put(
        SERVICES['registration_service'] + f'/api/v1/registrations/switch/{ngo_id}/',
        headers=auth_headers(request)
    )
    return redirect('employee_dashboard')


# ── Checkin ───────────────────────────────────────────────────

def checkin_view(request):
    if not is_logged_in(request) or not is_admin(request):
        return redirect('login')

    response = requests.get(
        SERVICES['checkin_service'] + '/api/v1/checkins/live-monitor/',
        headers=auth_headers(request)
    )
    checkins = response.json().get('checkins', []) if response.status_code == 200 else []
    return render(request, 'checkin/list.html', {'checkins': checkins})


def generate_qr(request, ngo_id):
    if not is_logged_in(request) or not is_admin(request):
        return redirect('login')

    response = requests.get(
        SERVICES['checkin_service'] + f'/api/v1/checkins/generate-qr/{ngo_id}/',
        headers=auth_headers(request)
    )
    qr_data = response.json() if response.status_code == 200 else {}
    return render(request, 'checkin/qr.html', {
        'qr_code': qr_data.get('qr_code_base64'),
        'ngo_id':  ngo_id
    })


def scan_view(request):
    token = request.GET.get('token')
    if not token:
        return render(request, 'checkin/success.html', {'message': 'Invalid QR code.'})

    response = requests.post(
        SERVICES['checkin_service'] + '/api/v1/checkins/scan/',
        json={'token': token}
    )
    result = response.json()
    return render(request, 'checkin/success.html', {
        'message': result.get('message') or result.get('error')
    })