from django.urls import reverse
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

def is_employee(request):
    return request.session.get('role') == 'employee'


# ── Home ──────────────────────────────────────────────────────

def home(request):
    return render(request, 'home.html')

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
        try:
            requests.post(
                SERVICES['user_service'] + '/api/v1/users/logout/',
                json={'refresh': refresh},
                headers=auth_headers(request),
                timeout=3,
            )
        except Exception:
            pass   # logout API failure should never block the user from logging out
    
    request.session.flush()   # always clear session regardless
    return redirect('login')

def verify_email_view(request, token):
    """
    GET /verify-email/<token>/
    User clicks link from email → gateway calls user-service to activate.
    """
    res = requests.post(
        SERVICES['user_service'] + '/api/v1/users/verify-email/',
        json={'token': token}
    )

    if res.status_code == 200:
        return render(request, 'accounts/verify_success.html', {
            'message': 'Email verified! You can now log in.'
        })

    return render(request, 'accounts/verify_success.html', {
        'error': 'This verification link is invalid or has expired.'
    })

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
            email = payload['email']
            # ← redirect to the "check your inbox" page, pass email via query param
            return redirect(f"{reverse('register_sent')}?email={email}")
 
        errors = response.json()
        return render(request, 'accounts/register.html', {'errors': errors})
 
    return render(request, 'accounts/register.html')
 
 
def register_sent_view(request):
    email = request.GET.get('email', '')
    return render(request, 'accounts/verification_sent.html', {'email': email})


def forgot_password_view(request):
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        requests.post(
            SERVICES['user_service'] + '/api/v1/users/forgot-password/',
            json={'email': email}
        )
        # Always go to sent page regardless of response
        return redirect(f"{reverse('forgot_password_sent')}?email={email}")

    return render(request, 'accounts/forgot_password.html')


def forgot_password_sent_view(request):
    email = request.GET.get('email', '')
    return render(request, 'accounts/forgot_password_sent.html', {'email': email})


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
    if not is_employee(request):
        return redirect('home')

    # fetch NGO activities
    ngo_resp = requests.get(
        SERVICES['ngo_service'] + '/api/v1/activities/',
        headers=auth_headers(request)
    )
    ngo_raw = ngo_resp.json() if ngo_resp.status_code == 200 else {}
    ngos = ngo_raw.get('results', []) if isinstance(ngo_raw, dict) else []

    # fetch service types
    st_resp = requests.get(
        SERVICES['ngo_service'] + '/api/v1/employee/service-types/',
        headers=auth_headers(request)
    )
    st_raw = st_resp.json() if st_resp.status_code == 200 else []
    service_types = (
        st_raw.get('data') or st_raw.get('results') or []
        if isinstance(st_raw, dict) else st_raw
    )

    # fetch organizers
    org_resp = requests.get(
        SERVICES['ngo_service'] + '/api/v1/employee/organizers/',
        headers=auth_headers(request)
    )
    org_raw = org_resp.json() if org_resp.status_code == 200 else []
    organizers = (
        org_raw.get('data') or org_raw.get('results') or []
        if isinstance(org_raw, dict) else org_raw
    )

    # fetch registration
    try:
        reg_resp = requests.get(
            SERVICES['registration_service'] + '/api/v1/registrations/my/',
            headers=auth_headers(request),
            timeout=5,
        )
        registration = reg_resp.json() if reg_resp.status_code == 200 else None

        # normalize
        if registration and registration.get('registration') is None:
            registration = None

        if registration and registration.get('ngo_id'):
            ngo_detail_resp = requests.get(
                SERVICES['ngo_service'] + f'/api/v1/activities/{registration["ngo_id"]}/',
                headers=auth_headers(request)
            )
            if ngo_detail_resp.status_code == 200:
                registration['ngo'] = ngo_detail_resp.json()  # ← adds ngo object

    except Exception:
        registration = None

    # add computed fields
    for ngo in ngos:
        taken     = ngo.get('slots_taken', 0)
        max_slots = ngo.get('max_slots', 1)
        ngo['fill_pct']     = round(taken / max_slots * 100) if max_slots else 0
        ngo['status_label'] = {
            'open':        'open',
            'almost_full': 'almost',
            'full':        'full',
            'closed':      'closed',
            'inactive':    'inactive',
        }.get(ngo.get('status', ''), 'open')

    # ← KEY FIX: mark registered NGO
    if registration and registration.get('ngo_id'):
        registered_ngo_id = registration.get('ngo_id')
        for ngo in ngos:
            if ngo.get('id') == registered_ngo_id:
                ngo['status_label'] = 'registered'   # ← this makes Cancel show ✅
                break


    # ── render ────────────────────────────────────────── ← THEN RENDER

    return render(request, 'employee_dashboard/list.html', {
        'ngos':          ngos,
        'service_types': service_types,
        'organizers':    organizers,
        'registration':  registration,
    })


def employee_ngo_detail(request, ngo_id):
    if not is_logged_in(request):
        return redirect('login')
    if not is_employee(request):
        return redirect('home')

    ngo_resp = requests.get(
        SERVICES['ngo_service'] + f'/api/v1/activities/{ngo_id}/',
        headers=auth_headers(request)
    )
    ngo = ngo_resp.json() if ngo_resp.status_code == 200 else {}

    # ── split cutoff_datetime ──────────────────────────
    cutoff = ngo.get('cutoff_datetime', '')
    if cutoff:
        cutoff_clean       = cutoff[:19]
        ngo['cutoff_date'] = cutoff_clean[:10]    # "2026-05-08"
        ngo['cutoff_time'] = cutoff_clean[11:16]  # "23:59"
    else:
        ngo['cutoff_date'] = ''
        ngo['cutoff_time'] = ''

    # ── fix time format ────────────────────────────────
    ngo['start_time'] = ngo.get('start_time', '')[:5]
    ngo['end_time']   = ngo.get('end_time',   '')[:5]

    # ── fetch registration ─────────────────────────────
    try:
        reg_resp = requests.get(
            SERVICES['registration_service'] + '/api/v1/registrations/my/',
            headers=auth_headers(request),
            timeout=5,
        )
        registration = reg_resp.json() if reg_resp.status_code == 200 else None
    except Exception:
        registration = None

    return render(request, 'employee_dashboard/detail.html', {
        'ngo':          ngo,
        'registration': registration,
        'service_types': [],
    })

# ── Admin Dashboard ───────────────────────────────────────────

def admin_dashboard(request):
    if not is_logged_in(request):
        return redirect('login')
    if request.session.get('role') != 'admin':
        return redirect('home')

    # fetch stats
    stats_resp = requests.get(
        SERVICES['ngo_service'] + '/api/v1/ngos/dashboard/',
        headers=auth_headers(request)
    )
    stats_raw = stats_resp.json() if stats_resp.status_code == 200 else {}
    stats     = stats_raw.get('data', stats_raw) if isinstance(stats_raw, dict) else {}

    # fetch NGOs with optional filters
    params = {}
    if request.GET.get('search'):   params['search']  = request.GET['search']
    if request.GET.get('status'):   params['status']  = request.GET['status']

    ngos_resp = requests.get(
        SERVICES['ngo_service'] + '/api/v1/ngos/',
        headers=auth_headers(request),
        params=params
    )
    ngos_raw = ngos_resp.json() if ngos_resp.status_code == 200 else {}
    ngos = (
        ngos_raw.get('data', {}).get('results', [])   # {"success": True, "data": {"results": [...]}}
        or ngos_raw.get('results', [])                # {"results": [...]}
        or []
    ) if isinstance(ngos_raw, dict) else []

    # fetch service types
    st_resp = requests.get(
        SERVICES['ngo_service'] + '/api/v1/service-types/',
        headers=auth_headers(request)
    )
    st_raw        = st_resp.json() if st_resp.status_code == 200 else []
    service_types = (
        st_raw.get('data') or st_raw.get('results') or []
        if isinstance(st_raw, dict) else st_raw
    )

    # fetch organizers
    org_resp = requests.get(
        SERVICES['ngo_service'] + '/api/v1/organizers/',
        headers=auth_headers(request)
    )
    org_raw    = org_resp.json() if org_resp.status_code == 200 else []
    organizers = (
        org_raw.get('data') or org_raw.get('results') or []
        if isinstance(org_raw, dict) else org_raw
    )
    for ngo in ngos:
        taken     = ngo.get('slots_taken', 0)
        max_slots = ngo.get('max_slots', 1)
        ngo['fill_pct']     = round(taken / max_slots * 100) if max_slots else 0
        ngo['status_label'] = {
            'open':        'Open',
            'almost_full': 'Almost Full',
            'full':        'Full',
            'closed':      'Closed',
            'inactive':    'Inactive',
        }.get(ngo.get('status', ''), 'Unknown')

        # ── split cutoff_datetime into date and time for edit modal ──
        cutoff = ngo.get('cutoff_datetime', '')
        if cutoff:
            # handles both "2026-05-08T23:59:00+08:00" and "2026-05-08T23:59:00"
            cutoff_clean = cutoff[:19]  # take "2026-05-08T23:59:00"
            ngo['cutoff_date'] = cutoff_clean[:10]   # "2026-05-08"
            ngo['cutoff_time'] = cutoff_clean[11:16] # "23:59"
        else:
            ngo['cutoff_date'] = ''
            ngo['cutoff_time'] = ''

        # ── fix time format (remove seconds if present) ──
        start = ngo.get('start_time', '')
        end   = ngo.get('end_time', '')
        ngo['start_time_short'] = start[:5] if start else ''  # "08:00"
        ngo['end_time_short']   = end[:5]   if end   else ''  # "12:00"

    return render(request, 'admin_dashboard/list.html', {
        'stats':         stats,
        'ngos':          ngos,
        'service_types': service_types,
        'organizers':    organizers,
    })


def admin_ngo_detail(request, ngo_id):
    if not is_logged_in(request):
        return redirect('login')
    if request.session.get('role') != 'admin':
        return redirect('home')

    ngo_resp = requests.get(
        SERVICES['ngo_service'] + f'/api/v1/ngos/{ngo_id}/',
        headers=auth_headers(request)
    )
    if ngo_resp.status_code != 200:
        return redirect('admin_dashboard')

    ngo_raw = ngo_resp.json()
    ngo     = ngo_raw.get('data', ngo_raw)

    # ── split cutoff_datetime ──────────────────────────
    cutoff = ngo.get('cutoff_datetime', '')
    if cutoff:
        cutoff_clean       = cutoff[:19]
        ngo['cutoff_date'] = cutoff_clean[:10]
        ngo['cutoff_time'] = cutoff_clean[11:16]
    else:
        ngo['cutoff_date'] = ''
        ngo['cutoff_time'] = ''

    # ── fix time format ────────────────────────────────
    ngo['start_time'] = ngo.get('start_time', '')[:5]
    ngo['end_time']   = ngo.get('end_time',   '')[:5]

    # ── slot fill percentage ───────────────────────────
    taken     = ngo.get('slots_taken', 0)
    max_slots = ngo.get('max_slots', 1)
    ngo['fill_pct'] = round(taken / max_slots * 100) if max_slots else 0

    # ── status label ───────────────────────────────────
    status_label = {
        'open':        'Open',
        'almost_full': 'Almost Full',
        'full':        'Full',
        'closed':      'Closed',
        'inactive':    'Inactive',
    }.get(ngo.get('status', ''), 'Unknown')

    # ← wire registration service
    reg_resp = requests.get(
        SERVICES['registration_service'] + f'/api/v1/registrations/participants/{ngo_id}/',
        headers=auth_headers(request)
    )
    reg_data = reg_resp.json() if reg_resp.status_code == 200 else {}
    participants = reg_data.get('results', {}).get('participants', [])

    # enrich with user details
    registrations = []
    for p in participants:
        user_resp = requests.get(
            SERVICES['user_service'] + f'/api/v1/users/{p["employee_id"]}/',
            headers=auth_headers(request)
        )
        employee = user_resp.json() if user_resp.status_code == 200 else {
            'first_name': 'Unknown',
            'last_name': '',
            'username': f'user_{p["employee_id"]}',
            'email': '',
        }
        registrations.append({
            'employee': employee,
            'registered_at': p['registered_at'],
            'completed': p['completed'],
        })

    return render(request, 'admin_dashboard/detail.html', {
        'ngo':          ngo,
        'status_label': ngo.get('status_label', ''),
        'fill_pct':     ngo['fill_pct'],
        'registrations': registrations,    # ← now populated ✅
        'ngo':           ngo,
        'status_label':  status_label,
        'fill_pct':      ngo['fill_pct'],
        'registrations': [],
    })


def admin_create_ngo(request):
    if request.method != 'POST':
        return redirect('admin_dashboard')
    response = requests.post(
        SERVICES['ngo_service'] + '/api/v1/ngos/',
        json=request.POST.dict(),
        headers=auth_headers(request)
    )
    return redirect('admin_dashboard')


def admin_update_ngo(request, ngo_id):
    if request.method != 'POST':
        return redirect('admin_dashboard')
    requests.patch(
        SERVICES['ngo_service'] + f'/api/v1/ngos/{ngo_id}/',
        json=request.POST.dict(),
        headers=auth_headers(request)
    )
    return redirect('admin_dashboard')


def admin_delete_ngo(request, ngo_id):
    if request.method != 'POST':
        return redirect('admin_dashboard')
    requests.delete(
        SERVICES['ngo_service'] + f'/api/v1/ngos/{ngo_id}/',
        headers=auth_headers(request)
    )
    return redirect('admin_dashboard')


def admin_toggle_active(request, ngo_id):
    if request.method != 'POST':
        return redirect('admin_dashboard')
    requests.patch(
        SERVICES['ngo_service'] + f'/api/v1/ngos/{ngo_id}/toggle-active/',
        headers=auth_headers(request)
    )
    return redirect('admin_dashboard')


def admin_create_service_type(request):
    if request.method != 'POST':
        return redirect('admin_dashboard')
    requests.post(
        SERVICES['ngo_service'] + '/api/v1/service-types/',
        json={'name': request.POST.get('name', '')},
        headers=auth_headers(request)
    )
    return redirect('admin_dashboard')


def admin_delete_service_type(request, pk):
    if request.method != 'POST':
        return redirect('admin_dashboard')
    requests.delete(
        SERVICES['ngo_service'] + f'/api/v1/service-types/{pk}/',
        headers=auth_headers(request)
    )
    return redirect('admin_dashboard')


def admin_create_organizer(request):
    if request.method != 'POST':
        return redirect('admin_dashboard')

    description = request.POST.get('description', '').strip()

    payload = {
        'company_name': request.POST.get('company_name', '').strip(),
        'description':  description if description else 'No description provided.',
    }
    response = requests.post(
        SERVICES['ngo_service'] + '/api/v1/organizers/',
        json=payload,
        headers=auth_headers(request)
    )
    return redirect('admin_dashboard')


def admin_delete_organizer(request, pk):
    if request.method != 'POST':
        return redirect('admin_dashboard')
    requests.delete(
        SERVICES['ngo_service'] + f'/api/v1/organizers/{pk}/',
        headers=auth_headers(request)
    )
    return redirect('admin_dashboard')


# ── Notification ──────────────────────────────────────────────

def broadcast_view(request):
    if not is_logged_in(request):
        return redirect('login')
    if request.session.get('role') != 'admin':
        return redirect('home')

    if request.method == 'POST':
        subject  = request.POST.get('subject', '').strip()
        body     = request.POST.get('body', '').strip()
        target   = request.POST.get('target', 'all')
        ngo_ids  = request.POST.getlist('ngo_ids')

        response = requests.post(
            SERVICES['notification_service'] + '/api/v1/notifications/broadcasts/',
            json={
                'subject': subject,
                'body':    body,
                'target':  target,
                'ngo_ids': ngo_ids,
            },
            headers=auth_headers(request)
        )
        if response.status_code == 201:
            return redirect('broadcast')
        # handle error
        return render(request, 'notification/broadcast.html', {
            'error': response.json().get('detail', 'Failed to send broadcast.'),
        })

    # GET — fetch broadcast history
    history  = requests.get(
        SERVICES['notification_service'] + '/api/v1/notifications/broadcasts/',
        headers=auth_headers(request)
    )
    ngo_list = requests.get(
        SERVICES['ngo_service'] + '/api/v1/ngos/',
        headers=auth_headers(request)
    )
    return render(request, 'notification/broadcast.html', {
        'broadcast_history': history.json() if history.status_code == 200 else [],
        'ngo_list':          ngo_list.json().get('results', []) if ngo_list.status_code == 200 else [],
    })


def notification_log_view(request):
    if not is_logged_in(request):
        return redirect('login')
    if request.session.get('role') != 'admin':
        return redirect('home')

    filter_type = request.GET.get('type', '')
    params      = {'notification_type': filter_type} if filter_type else {}

    logs  = requests.get(
        SERVICES['notification_service'] + '/api/v1/notifications/logs/',
        headers=auth_headers(request),
        params=params
    )
    return render(request, 'notification/log.html', {
        'logs':        logs.json() if logs.status_code == 200 else [],
        'filter_type': filter_type,
    })


def notification_settings_view(request):
    if not is_logged_in(request):
        return redirect('login')
    if request.session.get('role') != 'admin':
        return redirect('home')

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add':
            requests.post(
                SERVICES['notification_service'] + '/api/v1/notifications/reminders/',
                json={'interval_days': request.POST.get('interval_days'), 'is_active': True},
                headers=auth_headers(request)
            )
        elif action == 'delete':
            requests.delete(
                SERVICES['notification_service'] + f'/api/v1/notifications/reminders/{request.POST.get("config_id")}/',
                headers=auth_headers(request)
            )
        elif action == 'toggle':
            requests.patch(
                SERVICES['notification_service'] + f'/api/v1/notifications/reminders/{request.POST.get("config_id")}/',
                json={},
                headers=auth_headers(request)
            )
        return redirect('notification_settings')

    configs = requests.get(
        SERVICES['notification_service'] + '/api/v1/notifications/reminders/',
        headers=auth_headers(request)
    )
    return render(request, 'notification/settings.html', {
        'configs':       configs.json() if configs.status_code == 200 else [],
        'quick_presets': [1, 3, 7, 14],
    })


# ── Registration ──────────────────────────────────────────────

def registration_view(request):
    if not is_logged_in(request):
        return redirect('login')
    
    if not is_employee(request):     
        return redirect('home')

    response = requests.get(
        SERVICES['registration_service'] + '/api/v1/registrations/my/',
        headers=auth_headers(request)
    )
    registration = response.json() if response.status_code == 200 else None
    return render(request, 'registration/list.html', {'registration': registration})


def register_activity(request, ngo_id):
    if not is_logged_in(request):
        return redirect('login')
    if not is_employee(request):     
        return redirect('home')

    requests.post(
        SERVICES['registration_service'] + f'/api/v1/registrations/register/{ngo_id}/',
        headers=auth_headers(request)
    )
    return redirect('employee_dashboard')


def cancel_registration(request):
    if not is_logged_in(request):
        return redirect('login')
    if not is_employee(request):     
        return redirect('home')

    requests.delete(
        SERVICES['registration_service'] + '/api/v1/registrations/cancel/',
        headers=auth_headers(request)
    )
    return redirect('employee_dashboard')


def switch_registration(request, ngo_id):
    if not is_logged_in(request):
        return redirect('login')
    if not is_employee(request):     
        return redirect('home')

    requests.put(
        SERVICES['registration_service'] + f'/api/v1/registrations/switch/{ngo_id}/',
        headers=auth_headers(request)
    )
    return redirect('employee_dashboard')

def participants_view(request, ngo_id):
    if not is_logged_in(request) or not is_admin(request):
        return redirect('login')

    response = requests.get(
        SERVICES['registration_service'] + f'/api/v1/registrations/participants/{ngo_id}/',
        headers=auth_headers(request)
    )
    data = response.json() if response.status_code == 200 else {}
    results = data.get('results', {})      # ← get results block first

    return render(request, 'registration/participants.html', {
        'participants': results.get('participants', []),   # ← fixed ✅
        'ngo_id': ngo_id,
        'count': data.get('count', 0),                    # ← count is at top level ✅
        'source': results.get('source', ''),              # ← fixed ✅
    })


# ── Checkin ───────────────────────────────────────────────────

def checkin_view(request, ngo_id):           # ← add ngo_id param
    if not is_logged_in(request) or not is_admin(request):
        return redirect('login')

    response = requests.get(
        SERVICES['checkin_service'] + f'/api/v1/checkins/live-monitor/{ngo_id}/',  # ← add ngo_id
        headers=auth_headers(request)
    )
    data = response.json() if response.status_code == 200 else {}
    return render(request, 'checkin/list.html', {
        'checkins': data.get('checkins', []),
        'checked_in_count': data.get('checked_in_count', 0),
        'ngo_id': ngo_id,
    })

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
    if not is_logged_in(request):
        return redirect('login')

    ngo_id = request.GET.get('ngo_id')
    if not ngo_id:
        return render(request, 'checkin/success.html', {'message': 'Invalid QR code.'})

    response = requests.post(
        SERVICES['checkin_service'] + '/api/v1/checkins/scan/',
        json={'ngo_id': int(ngo_id)},
        headers=auth_headers(request)   # ← employee JWT sent here
    )
    result = response.json()
    return render(request, 'checkin/success.html', {
        'message': result.get('message') or result.get('error')
    })