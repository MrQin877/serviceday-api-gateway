import requests
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.conf import settings

SERVICES = settings.SERVICES


# ── Home ──────────────────────────────────────────────
def home(request):
    return render(request, 'home.html')


# ── Auth ──────────────────────────────────────────────
def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        response = requests.post(
            SERVICES['user_service'] + '/api/v1/auth/token/',
            json={'username': username, 'password': password}
        )

        if response.status_code == 200:
            data = response.json()
            # save token in session
            request.session['access_token'] = data['access']
            request.session['username']     = username
            return redirect('employee_dashboard')
        else:
            return render(request, 'accounts/login.html', {
                'error': 'Invalid username or password.'
            })

    return render(request, 'accounts/login.html')


def logout_view(request):
    request.session.flush()
    return redirect('login')


# ── NGO Service ───────────────────────────────────────
def employee_dashboard(request):
    token    = request.session.get('access_token')
    response = requests.get(
        SERVICES['ngo_service'] + '/api/v1/activities/',
        headers={'Authorization': f'Bearer {token}'}
    )
    activities = response.json().get('results', []) if response.status_code == 200 else []
    return render(request, 'employee_dashboard/list.html', {
        'activities': activities
    })


def admin_dashboard(request):
    token    = request.session.get('access_token')
    response = requests.get(
        SERVICES['ngo_service'] + '/api/v1/ngos/',
        headers={'Authorization': f'Bearer {token}'}
    )
    ngos = response.json().get('results', []) if response.status_code == 200 else []
    return render(request, 'admin_dashboard/list.html', {
        'ngos': ngos
    })


# ── Notification Service ──────────────────────────────
def broadcast_view(request):
    token    = request.session.get('access_token')
    response = requests.get(
        SERVICES['notification_service'] + '/api/v1/notifications/broadcasts/',
        headers={'Authorization': f'Bearer {token}'}
    )
    broadcasts = response.json().get('results', []) if response.status_code == 200 else []
    return render(request, 'notification/broadcast.html', {
        'broadcasts': broadcasts
    })


def notification_log_view(request):
    token    = request.session.get('access_token')
    response = requests.get(
        SERVICES['notification_service'] + '/api/v1/notifications/logs/',
        headers={'Authorization': f'Bearer {token}'}
    )
    logs = response.json().get('results', []) if response.status_code == 200 else []
    return render(request, 'notification/log.html', {
        'logs': logs
    })


# ── Registration Service ──────────────────────────────
def registration_view(request):
    token = request.session.get('access_token')
    response = requests.get(
        SERVICES['registration_service'] + '/api/v1/registrations/my/',  # ← fix URL to match your service
        headers={'Authorization': f'Bearer {token}'}
    )
    registration = response.json() if response.status_code == 200 else None
    return render(request, 'registration/list.html', {
        'registration': registration
    })


def register_activity(request, ngo_id):
    token = request.session.get('access_token')
    response = requests.post(
        SERVICES['registration_service'] + f'/api/v1/registrations/register/{ngo_id}/',
        headers={'Authorization': f'Bearer {token}'}
    )
    return redirect('employee_dashboard')


def cancel_registration(request):
    token = request.session.get('access_token')
    response = requests.delete(
        SERVICES['registration_service'] + '/api/v1/registrations/cancel/',
        headers={'Authorization': f'Bearer {token}'}
    )
    return redirect('employee_dashboard')


def switch_registration(request, ngo_id):
    token = request.session.get('access_token')
    response = requests.put(
        SERVICES['registration_service'] + f'/api/v1/registrations/switch/{ngo_id}/',
        headers={'Authorization': f'Bearer {token}'}
    )
    return redirect('employee_dashboard')


# ── Checkin Service ───────────────────────────────────
def checkin_view(request):
    token = request.session.get('access_token')
    response = requests.get(
        SERVICES['checkin_service'] + '/api/v1/checkins/live-monitor/',
        headers={'Authorization': f'Bearer {token}'}
    )
    checkins = response.json().get('checkins', []) if response.status_code == 200 else []
    return render(request, 'checkin/list.html', {
        'checkins': checkins
    })


def generate_qr(request, ngo_id):
    token = request.session.get('access_token')
    response = requests.get(
        SERVICES['checkin_service'] + f'/api/v1/checkins/generate-qr/{ngo_id}/',
        headers={'Authorization': f'Bearer {token}'}
    )
    qr_data = response.json() if response.status_code == 200 else {}
    return render(request, 'checkin/qr.html', {
        'qr_code': qr_data.get('qr_code_base64'),
        'ngo_id': ngo_id
    })


# ← ADD THIS NEW ONE
def scan_view(request):
    token = request.GET.get('token')   # comes from QR URL ?token=xxx

    if not token:
        return render(request, 'checkin/success.html', {
            'message': 'Invalid QR code.'
        })

    response = requests.post(
        SERVICES['checkin_service'] + '/api/v1/checkins/scan/',
        json={'token': token}
    )

    result = response.json()
    return render(request, 'checkin/success.html', {
        'message': result.get('message') or result.get('error')
    })