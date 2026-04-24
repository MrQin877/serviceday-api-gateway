from django.urls import reverse
import requests
from django.shortcuts import render, redirect
from django.contrib import messages
from django.conf import settings
from django.utils.dateparse import parse_datetime

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

def fetch_all_ngos(headers):
    """Fetch all NGOs dynamically based on total count."""
    try:
        # Step 1 — get total count
        resp = requests.get(
            SERVICES['ngo_service'] + '/api/v1/ngos/',
            headers=headers,
            params={'page_size': 1}
        )
        if resp.status_code != 200:
            return []
        total = resp.json().get('data', {}).get('count', 0)
        if total == 0:
            return []

        # Step 2 — fetch all at once using total count
        resp = requests.get(
            SERVICES['ngo_service'] + '/api/v1/ngos/',
            headers=headers,
            params={'page_size': total}
        )
        return resp.json().get('data', {}).get('results', []) if resp.status_code == 200 else []
    except Exception:
        return []


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
    # fetch registration
    try:
        reg_resp = requests.get(
            SERVICES['registration_service'] + '/api/v1/registrations/my/',
            headers=auth_headers(request),
            timeout=5,
        )
        registration = reg_resp.json() if reg_resp.status_code == 200 else None

        # ← FIXED normalization
        if registration:
            if registration.get('registration') is None and 'ngo_id' not in registration:
                registration = None  # genuinely no registration

    except Exception:
        registration = None

    # fetch NGO name for banner
    if registration and registration.get('ngo_id'):
        try:
            ngo_detail_resp = requests.get(
                SERVICES['ngo_service'] + f'/api/v1/activities/{registration["ngo_id"]}/',
                headers=auth_headers(request)
            )
            if ngo_detail_resp.status_code == 200:
                registration['ngo'] = ngo_detail_resp.json()
        except Exception:
            pass

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

    # ← FIXED: mark registered NGO with int() conversion
    if registration and registration.get('ngo_id'):
        registered_ngo_id = int(registration.get('ngo_id'))   # ← int()
        for ngo in ngos:
            if int(ngo.get('id', 0)) == registered_ngo_id:    # ← int() both sides
                ngo['status_label'] = 'registered'
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

    # fix ngo id to int
    if ngo.get('id'):
        ngo['id'] = int(ngo['id'])

    # split cutoff_datetime
    cutoff = ngo.get('cutoff_datetime', '')
    if cutoff:
        cutoff_clean       = cutoff[:19]
        ngo['cutoff_date'] = cutoff_clean[:10]
        ngo['cutoff_time'] = cutoff_clean[11:16]
    else:
        ngo['cutoff_date'] = ''
        ngo['cutoff_time'] = ''

    ngo['start_time'] = ngo.get('start_time', '')[:5]
    ngo['end_time']   = ngo.get('end_time',   '')[:5]

    # fetch registration
    try:
        reg_resp = requests.get(
            SERVICES['registration_service'] + '/api/v1/registrations/my/',
            headers=auth_headers(request),
            timeout=5,
        )
        registration = reg_resp.json() if reg_resp.status_code == 200 else None

        # normalize
        if registration:
            if registration.get('registration') is None and 'ngo_id' not in registration:
                registration = None

        # ← ADD THIS — fetch ngo object for template comparison
        if registration and registration.get('ngo_id'):
            registration['ngo_id'] = int(registration['ngo_id'])  # ← fix type

            reg_ngo_resp = requests.get(
                SERVICES['ngo_service'] + f'/api/v1/activities/{registration["ngo_id"]}/',
                headers=auth_headers(request)
            )
            if reg_ngo_resp.status_code == 200:
                reg_ngo = reg_ngo_resp.json()
                reg_ngo['id'] = int(reg_ngo['id'])  # ← fix type
                registration['ngo'] = reg_ngo        # ← adds ngo.id for template

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
    print(f"STATUS: {reg_resp.status_code}")
    print(f"DATA: {reg_resp.json()}")
    reg_data     = reg_resp.json() if reg_resp.status_code == 200 else {}
    participants = reg_data.get('participants', [])
    print(f"PARTICIPANTS: {participants}")

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

        # ← parse ISO string into a real datetime so Django |date filter works
        raw_dt = p.get('registered_at', '')
        registered_at = parse_datetime(raw_dt) if raw_dt else None

        registrations.append({
            'employee':      employee,
            'registered_at': registered_at,   # ← now a datetime object
            'completed':     p['completed'],
        })
        return render(request, 'admin_dashboard/detail.html', {
            'ngo':           ngo,
            'status_label':  status_label, 
            'fill_pct':      ngo['fill_pct'],
            'registrations': registrations,
        })


def admin_create_ngo(request):
    if request.method != 'POST':
        return redirect('admin_dashboard')
    response = requests.post(
        SERVICES['ngo_service'] + '/api/v1/ngos/',
        json=request.POST.dict(),
        headers=auth_headers(request)
    )
    if response.status_code == 201:
        messages.success(request, 'NGO created successfully.')
    else:
        messages.error(request, 'Failed to create NGO.')
    return redirect('admin_dashboard')


def admin_update_ngo(request, ngo_id):
    if request.method != 'POST':
        return redirect('admin_dashboard')
    response = requests.patch(
        SERVICES['ngo_service'] + f'/api/v1/ngos/{ngo_id}/',
        json=request.POST.dict(),
        headers=auth_headers(request)
    )
    if response.status_code == 200:
        messages.success(request, 'NGO updated successfully.')
    else:
        messages.error(request, 'Failed to update NGO.')
    return redirect('admin_dashboard')


def admin_delete_ngo(request, ngo_id):
    if request.method != 'POST':
        return redirect('admin_dashboard')
    response = requests.delete(
        SERVICES['ngo_service'] + f'/api/v1/ngos/{ngo_id}/',
        headers=auth_headers(request)
    )
    if response.status_code == 200:
        messages.success(request, 'NGO deleted successfully.')
    else:
        messages.error(request, 'Failed to delete NGO.')
    return redirect('admin_dashboard')


def admin_toggle_active(request, ngo_id):
    if request.method != 'POST':
        return redirect('admin_dashboard')
    response = requests.patch(
        SERVICES['ngo_service'] + f'/api/v1/ngos/{ngo_id}/toggle-active/',
        headers=auth_headers(request)
    )
    if response.status_code == 200:
        messages.success(request, 'NGO status toggled successfully.')
    else:
        messages.error(request, 'Failed to toggle NGO status.')
    return redirect('admin_dashboard')


def admin_create_service_type(request):
    if request.method != 'POST':
        return redirect('admin_dashboard')
    response = requests.post(
        SERVICES['ngo_service'] + '/api/v1/service-types/',
        json={'name': request.POST.get('name', '')},
        headers=auth_headers(request)
    )
    if response.status_code == 201:
        messages.success(request, 'Service type created successfully.')
    else:
        error = response.json().get('errors', {})
        messages.error(request, f'Failed to create service type. {error}')
    return redirect('admin_dashboard')


def admin_delete_service_type(request, pk):
    if request.method != 'POST':
        return redirect('admin_dashboard')
    response = requests.delete(
        SERVICES['ngo_service'] + f'/api/v1/service-types/{pk}/',
        headers=auth_headers(request)
    )
    if response.status_code == 200:
        messages.success(request, 'Service type deleted successfully.')
    else:
        messages.error(request, 'Failed to delete service type. It may be in use by existing NGOs.')
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
    if response.status_code == 201:
        messages.success(request, 'Organizer created successfully.')
    else:
        messages.error(request, 'Failed to create organizer.')
    return redirect('admin_dashboard')


def admin_delete_organizer(request, pk):
    if request.method != 'POST':
        return redirect('admin_dashboard')
    response = requests.delete(
        SERVICES['ngo_service'] + f'/api/v1/organizers/{pk}/',
        headers=auth_headers(request)
    )
    if response.status_code == 200:
        messages.success(request, 'Organizer deleted successfully.')
    else:
        messages.error(request, 'Failed to delete organizer.')
    return redirect('admin_dashboard')


# ── Notification ──────────────────────────────────────────────

def broadcast_view(request):
    if not is_logged_in(request):
        return redirect('login')
    if request.session.get('role') != 'admin':
        return redirect('home')

    # fetch ALL NGOs dynamically
    all_ngos = fetch_all_ngos(auth_headers(request))

    # fetch registration counts — send as list
    ngo_ids_list = [str(n['id']) for n in all_ngos]
    try:
        counts_resp = requests.get(
            SERVICES['registration_service'] + '/api/v1/registrations/counts/',
            params=[('ngo_ids', ngo_id) for ngo_id in ngo_ids_list],
            headers=auth_headers(request)
        )
        counts = counts_resp.json() if counts_resp.status_code == 200 else {}
    except Exception:
        counts = {}

    # only keep NGOs with at least 1 registration
    ngo_list = []
    for ngo in all_ngos:
        count = counts.get(str(ngo['id']), counts.get(ngo['id'], 0))
        if count > 0:
            ngo['slots_taken'] = count
            ngo_list.append(ngo)

    # fetch broadcast history
    hist_resp = requests.get(
        SERVICES['notification_service'] + '/api/v1/notifications/broadcasts/',
        headers=auth_headers(request)
    )
    broadcast_history = hist_resp.json() if hist_resp.status_code == 200 else []

    if request.method == 'POST':
        subject = request.POST.get('subject', '').strip()
        body    = request.POST.get('body', '').strip()
        target  = request.POST.get('target', 'all')
        ngo_ids = request.POST.getlist('ngo_ids')

        payload = {
            'subject': subject,
            'body':    body,
            'target':  target,
        }
        if target == 'activity' and ngo_ids:
            payload['ngo_ids'] = ngo_ids

        response = requests.post(
            SERVICES['notification_service'] + '/api/v1/notifications/broadcasts/',
            json=payload,
            headers=auth_headers(request)
        )
        if response.status_code == 201:
            messages.success(request, 'Broadcast queued successfully!')
        else:
            try:
                error = response.json().get('detail', 'Failed to send broadcast.')
            except Exception:
                error = f'Failed. (Status {response.status_code})'
            messages.error(request, error)
        return redirect('broadcast')

    return render(request, 'notification/broadcast.html', {
        'ngo_list':          ngo_list,
        'broadcast_history': broadcast_history,
    })


def notification_log_view(request):
    if not is_logged_in(request):
        return redirect('login')
    if request.session.get('role') != 'admin':
        return redirect('home')

    filter_type = request.GET.get('type', '')
    params = {}
    if filter_type:
        params['notification_type'] = filter_type

    log_resp = requests.get(
        SERVICES['notification_service'] + '/api/v1/notifications/logs/',
        params=params,
        headers=auth_headers(request)
    )
    logs = log_resp.json() if log_resp.status_code == 200 else []

    # split sent_at into date and time
    for log in logs:
        sent_at = log.get('sent_at', '')
        if sent_at:
            clean = sent_at[:19]
            log['sent_date'] = clean[:10]    # "2026-04-24"
            log['sent_time'] = clean[11:16]  # "16:04"
        else:
            log['sent_date'] = ''
            log['sent_time'] = ''

    from datetime import datetime, timedelta
    seven_days_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

    total_sent  = len(logs)
    failed      = sum(1 for l in logs if not l.get('is_success'))
    recent_sent = sum(1 for l in logs if l.get('sent_date', '') >= seven_days_ago)  # ← fix l not log

    notification_types = [
        ('confirmation', 'Confirmation'),
        ('cancellation', 'Cancellation'),
        ('reminder',     'Reminder'),
        ('broadcast',    'Broadcast'),
        ('switch',       'Switch'),
        ('verification', 'Verification'),
    ]

    return render(request, 'notification/log.html', {
        'logs':               logs,
        'filter_type':        filter_type,
        'notification_types': notification_types,
        'stats': {
            'total_sent':  total_sent,
            'recent_sent': recent_sent,
            'failed':      failed,
        }
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

    response = requests.post(
        SERVICES['registration_service'] + f'/api/v1/registrations/register/{ngo_id}/',
        headers=auth_headers(request)
    )
    if response.status_code == 201:
        messages.success(request, 'Successfully registered for the activity!')
    else:
        error = response.json().get('error', 'Registration failed. Please try again.')
        messages.error(request, f'⚠️ {error}')
    return redirect('employee_dashboard')


def cancel_registration(request):
    if not is_logged_in(request):
        return redirect('login')
    if not is_employee(request):
        return redirect('home')

    response = requests.delete(
        SERVICES['registration_service'] + '/api/v1/registrations/cancel/',
        headers=auth_headers(request)
    )
    if response.status_code == 200:
        messages.success(request, 'Registration cancelled successfully.')
    else:
        messages.error(request, 'Failed to cancel registration.')
    return redirect('employee_dashboard')


def switch_registration(request, ngo_id):
    if not is_logged_in(request):
        return redirect('login')
    if not is_employee(request):
        return redirect('home')

    response = requests.put(
        SERVICES['registration_service'] + f'/api/v1/registrations/switch/{ngo_id}/',
        headers=auth_headers(request)
    )
    if response.status_code == 200:
        messages.success(request, 'Successfully switched to the new activity!')
    else:
        messages.error(request, 'Failed to switch activity. Please try again.')
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
        'participants': results.get('participants', []),   
        'ngo_id': ngo_id,
        'count': data.get('count', 0),                    
        'source': results.get('source', ''),              
    })


# ── Checkin ───────────────────────────────────────────────────

def checkin_view(request, ngo_id):
    if not is_logged_in(request) or not is_admin(request):
        return redirect('login')

    # fetch checkins
    response = requests.get(
        SERVICES['checkin_service'] + f'/api/v1/checkins/live-monitor/{ngo_id}/',
        headers=auth_headers(request)
    )
    data = response.json() if response.status_code == 200 else {}
    checkins = data.get('checkins', [])
    checked_in_count = data.get('checked_in_count', 0)

    # ← enrich checkins with user details
    enriched_checkins = []
    for checkin in checkins:
        user_resp = requests.get(
            SERVICES['user_service'] + f'/api/v1/users/{checkin["employee_id"]}/',
            headers=auth_headers(request)
        )
        if user_resp.status_code == 200:
            user = user_resp.json()
            checkin['employee_name'] = (
                f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
                or user.get('username', f"Employee #{checkin['employee_id']}")
            )
            checkin['username'] = user.get('username', '')
        else:
            checkin['employee_name'] = f"Employee #{checkin['employee_id']}"
            checkin['username'] = ''
        enriched_checkins.append(checkin)

    # fetch total registered
    reg_resp = requests.get(
        SERVICES['registration_service'] + f'/api/v1/registrations/participants/{ngo_id}/',
        headers=auth_headers(request)
    )
    reg_data = reg_resp.json() if reg_resp.status_code == 200 else {}
    total_registered = reg_data.get('count', 0)

    attendance_pct = round(
        checked_in_count / total_registered * 100
    ) if total_registered > 0 else 0

    # fetch ngo name
    ngo_resp = requests.get(
        SERVICES['ngo_service'] + f'/api/v1/ngos/{ngo_id}/',
        headers=auth_headers(request)
    )
    ngo = ngo_resp.json().get('data', {}) if ngo_resp.status_code == 200 else {}

    return render(request, 'checkin/list.html', {
        'checkins':         enriched_checkins,   # ← enriched
        'checked_in_count': checked_in_count,
        'total_registered': total_registered,
        'attendance_pct':   attendance_pct,
        'ngo':              ngo,
        'ngo_id':           ngo_id,
    })

def generate_qr(request, ngo_id):
    if not is_logged_in(request) or not is_admin(request):
        return redirect('login')

    # fetch QR from checkin service
    response = requests.get(
        SERVICES['checkin_service'] + f'/api/v1/checkins/generate-qr/{ngo_id}/',
        headers=auth_headers(request)
    )
    qr_data = response.json() if response.status_code == 200 else {}

    # ← fetch NGO details for template
    ngo_resp = requests.get(
        SERVICES['ngo_service'] + f'/api/v1/ngos/{ngo_id}/',
        headers=auth_headers(request)
    )
    ngo = ngo_resp.json().get('data', {}) if ngo_resp.status_code == 200 else {}

    return render(request, 'checkin/qr.html', {
        'qr_code': qr_data.get('qr_code_base64'),
        'ngo_id':  ngo_id,
        'ngo':     ngo,           # ← pass ngo object
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