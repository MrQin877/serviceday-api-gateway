from django.urls import reverse
import requests
import jwt as pyjwt
from django.shortcuts import render, redirect
from django.contrib import messages
from django.conf import settings
from django.utils.dateparse import parse_datetime
from django.http import JsonResponse

SERVICES = settings.SERVICES


# ── Helpers ───────────────────────────────────────────────────

def get_token(request):
    return request.session.get('access_token')

def is_token_expired(token):
    if not token:
        return True
    try:
        pyjwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
        return False
    except pyjwt.ExpiredSignatureError:
        return True
    except Exception:
        return True

def refresh_access_token(request):
    refresh_token = request.session.get('refresh_token', '')
    if not refresh_token:
        return None
    try:
        response = requests.post(
            SERVICES['user_service'] + '/api/v1/auth/token/refresh/',
            json={'refresh': refresh_token},
            timeout=5
        )
        if response.status_code == 200:
            new_access = response.json().get('access')
            request.session['access_token'] = new_access
            return new_access
    except Exception:
        pass
    return None

def check_auth(request):
    """
    Returns headers dict if valid.
    Returns redirect if expired or not logged in.

    Usage in every view:
        headers = check_auth(request)
        if not isinstance(headers, dict):
            return headers
    """
    if not is_logged_in(request):
        return redirect('login')

    token = get_token(request)
    if is_token_expired(token):
        new_token = refresh_access_token(request)
        if new_token:
            return {
                'Authorization': f'Bearer {new_token}',
                'Content-Type':  'application/json',
            }
        request.session.flush()
        messages.error(request, 'Your session has expired. Please log in again.')
        return redirect('login')

    return {
        'Authorization': f'Bearer {token}',
        'Content-Type':  'application/json',
    }

def handle_service_response(response, request):
    """Returns redirect if 401/403, else None."""
    if response.status_code in [401, 403]:
        request.session.flush()
        messages.error(request, 'Your session has expired. Please log in again.')
        return redirect('login')
    return None

def auth_headers(request):
    return {'Authorization': f'Bearer {get_token(request)}'}

def is_logged_in(request):
    return bool(request.session.get('access_token'))

def is_admin(request):
    return request.session.get('role') == 'admin'

def is_employee(request):
    return request.session.get('role') == 'employee'

def fetch_all_ngos(headers):
    try:
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

            me = requests.get(
                SERVICES['user_service'] + '/api/v1/users/me/',
                headers={'Authorization': f'Bearer {data["access"]}'}
            )
            
            print("=== DEBUG LOGIN ===")                    # 👈 add
            print(f"me status: {me.status_code}")           # 👈 add
            print(f"me response: {me.json()}")              # 👈 add
            
            if me.status_code == 200:
                request.session['role']    = me.json().get('role', 'employee')
                request.session['user_id'] = me.json().get('id')
                
                print(f"user_id saved: {request.session['user_id']}")   # 👈 add
                print(f"role saved: {request.session['role']}")         # 👈 add
                print("===================")         

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
            pass
    request.session.flush()
    return redirect('login')


def verify_email_view(request, token):
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
    headers = check_auth(request)
    if not isinstance(headers, dict):
        return headers
    if not is_employee(request):
        return redirect('home')

    ngo_resp = requests.get(
        SERVICES['ngo_service'] + '/api/v1/activities/',
        headers=headers
    )
    expired = handle_service_response(ngo_resp, request)
    if expired:
        return expired

    ngo_raw = ngo_resp.json() if ngo_resp.status_code == 200 else {}
    ngos    = ngo_raw.get('results', []) if isinstance(ngo_raw, dict) else []

    st_resp = requests.get(
        SERVICES['ngo_service'] + '/api/v1/employee/service-types/',
        headers=headers
    )
    st_raw        = st_resp.json() if st_resp.status_code == 200 else []
    service_types = (
        st_raw.get('data') or st_raw.get('results') or []
        if isinstance(st_raw, dict) else st_raw
    )

    org_resp   = requests.get(
        SERVICES['ngo_service'] + '/api/v1/employee/organizers/',
        headers=headers
    )
    org_raw    = org_resp.json() if org_resp.status_code == 200 else []
    organizers = (
        org_raw.get('data') or org_raw.get('results') or []
        if isinstance(org_raw, dict) else org_raw
    )

    try:
        reg_resp     = requests.get(
            SERVICES['registration_service'] + '/api/v1/registrations/my/',
            headers=headers,
            timeout=5,
        )
        registration = reg_resp.json() if reg_resp.status_code == 200 else None
        if registration:
            if registration.get('registration') is None and 'ngo_id' not in registration:
                registration = None
    except Exception:
        registration = None

    if registration and registration.get('ngo_id'):
        try:
            ngo_detail_resp = requests.get(
                SERVICES['ngo_service'] + f'/api/v1/activities/{registration["ngo_id"]}/',
                headers=headers
            )
            if ngo_detail_resp.status_code == 200:
                registration['ngo'] = ngo_detail_resp.json()
        except Exception:
            pass

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

    if registration and registration.get('ngo_id'):
        registered_ngo_id = int(registration.get('ngo_id'))
        for ngo in ngos:
            if int(ngo.get('id', 0)) == registered_ngo_id:
                ngo['status_label'] = 'registered'
                break

    return render(request, 'employee_dashboard/list.html', {
        'ngos':          ngos,
        'service_types': service_types,
        'organizers':    organizers,
        'registration':  registration,
    })


def employee_ngo_detail(request, ngo_id):
    headers = check_auth(request)
    if not isinstance(headers, dict):
        return headers
    if not is_employee(request):
        return redirect('home')

    ngo_resp = requests.get(
        SERVICES['ngo_service'] + f'/api/v1/activities/{ngo_id}/',
        headers=headers
    )
    expired = handle_service_response(ngo_resp, request)
    if expired:
        return expired

    ngo = ngo_resp.json() if ngo_resp.status_code == 200 else {}
    if ngo.get('id'):
        ngo['id'] = int(ngo['id'])

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

    try:
        reg_resp     = requests.get(
            SERVICES['registration_service'] + '/api/v1/registrations/my/',
            headers=headers,
            timeout=5,
        )
        registration = reg_resp.json() if reg_resp.status_code == 200 else None
        if registration:
            if registration.get('registration') is None and 'ngo_id' not in registration:
                registration = None
        if registration and registration.get('ngo_id'):
            registration['ngo_id'] = int(registration['ngo_id'])
            reg_ngo_resp = requests.get(
                SERVICES['ngo_service'] + f'/api/v1/activities/{registration["ngo_id"]}/',
                headers=headers
            )
            if reg_ngo_resp.status_code == 200:
                reg_ngo        = reg_ngo_resp.json()
                reg_ngo['id']  = int(reg_ngo['id'])
                registration['ngo'] = reg_ngo
    except Exception:
        registration = None

    return render(request, 'employee_dashboard/detail.html', {
        'ngo':           ngo,
        'registration':  registration,
        'service_types': [],
    })


# ── Admin Dashboard ───────────────────────────────────────────

def admin_dashboard(request):
    headers = check_auth(request)
    if not isinstance(headers, dict):
        return headers
    if not is_admin(request):
        return redirect('home')

    stats_resp = requests.get(
        SERVICES['ngo_service'] + '/api/v1/ngos/dashboard/',
        headers=headers
    )
    expired = handle_service_response(stats_resp, request)
    if expired:
        return expired

    stats_raw = stats_resp.json() if stats_resp.status_code == 200 else {}
    stats     = stats_raw.get('data', stats_raw) if isinstance(stats_raw, dict) else {}

    page      = request.GET.get('page', 1)
    params    = {'page': page, 'page_size': 5}
    if request.GET.get('search'): params['search'] = request.GET['search']
    if request.GET.get('status'): params['status'] = request.GET['status']

    ngos_resp = requests.get(
        SERVICES['ngo_service'] + '/api/v1/ngos/',
        headers=headers,
        params=params
    )
    expired = handle_service_response(ngos_resp, request)
    if expired:
        return expired

    ngos_raw    = ngos_resp.json() if ngos_resp.status_code == 200 else {}
    ngo_data    = ngos_raw.get('data', {}) if isinstance(ngos_raw, dict) else {}
    ngos        = ngo_data.get('results', [])
    total       = ngo_data.get('count', 0)
    next_page   = ngo_data.get('next')
    prev_page   = ngo_data.get('previous')
    page        = int(page)
    page_size   = 5
    total_pages = (total + page_size - 1) // page_size
    page_range  = range(max(1, page - 2), min(total_pages + 1, page + 3))

    st_resp = requests.get(
        SERVICES['ngo_service'] + '/api/v1/service-types/',
        headers=headers
    )
    st_raw        = st_resp.json() if st_resp.status_code == 200 else []
    service_types = st_raw.get('data') or st_raw.get('results') or [] if isinstance(st_raw, dict) else st_raw

    org_resp   = requests.get(
        SERVICES['ngo_service'] + '/api/v1/organizers/',
        headers=headers
    )
    org_raw    = org_resp.json() if org_resp.status_code == 200 else []
    organizers = org_raw.get('data') or org_raw.get('results') or [] if isinstance(org_raw, dict) else org_raw

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

        cutoff = ngo.get('cutoff_datetime', '')
        if cutoff:
            cutoff_clean       = cutoff[:19]
            ngo['cutoff_date'] = cutoff_clean[:10]
            ngo['cutoff_time'] = cutoff_clean[11:16]
        else:
            ngo['cutoff_date'] = ''
            ngo['cutoff_time'] = ''

        start = ngo.get('start_time', '')
        end   = ngo.get('end_time', '')
        ngo['start_time_short'] = start[:5] if start else ''
        ngo['end_time_short']   = end[:5]   if end   else ''

    return render(request, 'admin_dashboard/list.html', {
        'stats':         stats,
        'ngos':          ngos,
        'service_types': service_types,
        'organizers':    organizers,
        'total':         total,
        'page':          page,
        'total_pages':   total_pages,
        'page_range':    page_range,
        'has_next':      next_page is not None,
        'has_prev':      prev_page is not None,
    })


def admin_ngo_detail(request, ngo_id):
    headers = check_auth(request)
    if not isinstance(headers, dict):
        return headers
    if not is_admin(request):
        return redirect('home')

    ngo_resp = requests.get(
        SERVICES['ngo_service'] + f'/api/v1/ngos/{ngo_id}/',
        headers=headers
    )
    expired = handle_service_response(ngo_resp, request)
    if expired:
        return expired
    if ngo_resp.status_code != 200:
        return redirect('admin_dashboard')

    ngo_raw = ngo_resp.json()
    ngo     = ngo_raw.get('data', ngo_raw)

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

    taken     = ngo.get('slots_taken', 0)
    max_slots = ngo.get('max_slots', 1)
    ngo['fill_pct'] = round(taken / max_slots * 100) if max_slots else 0

    status_label = {
        'open':        'Open',
        'almost_full': 'Almost Full',
        'full':        'Full',
        'closed':      'Closed',
        'inactive':    'Inactive',
    }.get(ngo.get('status', ''), 'Unknown')

    reg_resp     = requests.get(
        SERVICES['registration_service'] + f'/api/v1/registrations/participants/{ngo_id}/',
        headers=headers
    )
    reg_data     = reg_resp.json() if reg_resp.status_code == 200 else {}
    participants = reg_data.get('participants', [])

    registrations = []
    for p in participants:
        user_resp = requests.get(
            SERVICES['user_service'] + f'/api/v1/users/{p["employee_id"]}/',
            headers=headers
        )
        employee = user_resp.json() if user_resp.status_code == 200 else {
            'first_name': 'Unknown', 'last_name': '',
            'username':   f'user_{p["employee_id"]}', 'email': '',
        }
        raw_dt        = p.get('registered_at', '')
        registered_at = parse_datetime(raw_dt) if raw_dt else None
        registrations.append({
            'employee':      employee,
            'registered_at': registered_at,
            'completed':     p['completed'],
        })

    return render(request, 'admin_dashboard/detail.html', {
        'ngo':           ngo,
        'status_label':  status_label,
        'fill_pct':      ngo['fill_pct'],
        'registrations': registrations,
    })


def admin_create_ngo(request):
    headers = check_auth(request)
    if not isinstance(headers, dict):
        return headers
    if request.method != 'POST':
        return redirect('admin_dashboard')
    response = requests.post(
        SERVICES['ngo_service'] + '/api/v1/ngos/',
        json=request.POST.dict(),
        headers=headers
    )
    if response.status_code == 201:
        messages.success(request, 'NGO created successfully.')
    else:
        messages.error(request, 'Failed to create NGO.')
    return redirect('admin_dashboard')


def admin_update_ngo(request, ngo_id):
    headers = check_auth(request)
    if not isinstance(headers, dict):
        return headers
    if request.method != 'POST':
        return redirect('admin_dashboard')
    response = requests.patch(
        SERVICES['ngo_service'] + f'/api/v1/ngos/{ngo_id}/',
        json=request.POST.dict(),
        headers=headers
    )
    if response.status_code == 200:
        messages.success(request, 'NGO updated successfully.')
    else:
        messages.error(request, 'Failed to update NGO.')
    return redirect('admin_dashboard')


def admin_delete_ngo(request, ngo_id):
    headers = check_auth(request)
    if not isinstance(headers, dict):
        return headers
    if request.method != 'POST':
        return redirect('admin_dashboard')
    response = requests.delete(
        SERVICES['ngo_service'] + f'/api/v1/ngos/{ngo_id}/',
        headers=headers
    )
    if response.status_code == 200:
        messages.success(request, 'NGO deleted successfully.')
    else:
        messages.error(request, 'Failed to delete NGO.')
    return redirect('admin_dashboard')


def admin_toggle_active(request, ngo_id):
    headers = check_auth(request)
    if not isinstance(headers, dict):
        return headers
    if request.method != 'POST':
        return redirect('admin_dashboard')
    response = requests.patch(
        SERVICES['ngo_service'] + f'/api/v1/ngos/{ngo_id}/toggle-active/',
        headers=headers
    )
    if response.status_code == 200:
        messages.success(request, 'NGO status toggled successfully.')
    else:
        messages.error(request, 'Failed to toggle NGO status.')
    return redirect('admin_dashboard')


def admin_create_service_type(request):
    headers = check_auth(request)
    if not isinstance(headers, dict):
        return headers
    if request.method != 'POST':
        return redirect('admin_dashboard')
    response = requests.post(
        SERVICES['ngo_service'] + '/api/v1/service-types/',
        json={'name': request.POST.get('name', '')},
        headers=headers
    )
    if response.status_code == 201:
        messages.success(request, 'Service type created successfully.')
    else:
        error = response.json().get('errors', {})
        messages.error(request, f'Failed to create service type. {error}')
    return redirect('admin_dashboard')


def admin_delete_service_type(request, pk):
    headers = check_auth(request)
    if not isinstance(headers, dict):
        return headers
    if request.method != 'POST':
        return redirect('admin_dashboard')
    response = requests.delete(
        SERVICES['ngo_service'] + f'/api/v1/service-types/{pk}/',
        headers=headers
    )
    if response.status_code == 200:
        messages.success(request, 'Service type deleted successfully.')
    else:
        messages.error(request, 'Failed to delete service type.')
    return redirect('admin_dashboard')


def admin_create_organizer(request):
    headers = check_auth(request)
    if not isinstance(headers, dict):
        return headers
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
        headers=headers
    )
    if response.status_code == 201:
        messages.success(request, 'Organizer created successfully.')
    else:
        messages.error(request, 'Failed to create organizer.')
    return redirect('admin_dashboard')


def admin_delete_organizer(request, pk):
    headers = check_auth(request)
    if not isinstance(headers, dict):
        return headers
    if request.method != 'POST':
        return redirect('admin_dashboard')
    response = requests.delete(
        SERVICES['ngo_service'] + f'/api/v1/organizers/{pk}/',
        headers=headers
    )
    if response.status_code == 200:
        messages.success(request, 'Organizer deleted successfully.')
    else:
        messages.error(request, 'Failed to delete organizer.')
    return redirect('admin_dashboard')


# ── Notification ──────────────────────────────────────────────

def broadcast_view(request):
    headers = check_auth(request)
    if not isinstance(headers, dict):
        return headers
    if not is_admin(request):
        return redirect('home')

    all_ngos     = fetch_all_ngos(headers)
    ngo_ids_list = [str(n['id']) for n in all_ngos]
    try:
        counts_resp = requests.get(
            SERVICES['registration_service'] + '/api/v1/registrations/counts/',
            params=[('ngo_ids', ngo_id) for ngo_id in ngo_ids_list],
            headers=headers
        )
        counts = counts_resp.json() if counts_resp.status_code == 200 else {}
    except Exception:
        counts = {}

    ngo_list = []
    for ngo in all_ngos:
        count = counts.get(str(ngo['id']), counts.get(ngo['id'], 0))
        if count > 0:
            ngo['slots_taken'] = count
            ngo_list.append(ngo)

    hist_resp         = requests.get(
        SERVICES['notification_service'] + '/api/v1/notifications/broadcasts/',
        headers=headers
    )
    broadcast_history = hist_resp.json() if hist_resp.status_code == 200 else []

    for b in broadcast_history:
        sent_at        = b.get('sent_at', '')
        b['sent_date'] = sent_at[:10]   if sent_at else ''
        b['sent_time'] = sent_at[11:16] if sent_at else ''

    if request.method == 'POST':
        subject = request.POST.get('subject', '').strip()
        body    = request.POST.get('body', '').strip()
        target  = request.POST.get('target', 'all')
        ngo_ids = request.POST.getlist('ngo_ids')
        payload = {'subject': subject, 'body': body, 'target': target}
        if target == 'activity' and ngo_ids:
            payload['ngo_ids'] = ngo_ids
        response = requests.post(
            SERVICES['notification_service'] + '/api/v1/notifications/broadcasts/',
            json=payload,
            headers=headers
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


def broadcast_progress_view(request, broadcast_id):
    if not is_logged_in(request):
        return JsonResponse({'error': 'Not logged in'}, status=401)
    token = get_token(request)
    if is_token_expired(token):
        return JsonResponse({'error': 'Session expired'}, status=401)
    response = requests.get(
        SERVICES['notification_service'] + f'/api/v1/notifications/broadcasts/{broadcast_id}/progress/',
        headers=auth_headers(request)
    )
    if response.status_code == 200:
        return JsonResponse(response.json())
    return JsonResponse({'error': 'Failed'}, status=response.status_code)


def notification_log_view(request):
    headers = check_auth(request)
    if not isinstance(headers, dict):
        return headers
    if not is_admin(request):
        return redirect('home')

    filter_type = request.GET.get('type', '')
    page        = int(request.GET.get('page', 1))
    page_size   = 5
    params      = {'page': page, 'page_size': page_size}
    if filter_type:
        params['notification_type'] = filter_type

    log_resp = requests.get(
        SERVICES['notification_service'] + '/api/v1/notifications/logs/',
        params=params,
        headers=headers
    )
    expired = handle_service_response(log_resp, request)
    if expired:
        return expired

    data  = log_resp.json() if log_resp.status_code == 200 else {}
    logs  = data.get('results', []) if isinstance(data, dict) else []
    total = data.get('count', 0)

    for log in logs:
        sent_at = log.get('sent_at', '')
        if sent_at:
            clean            = sent_at[:19]
            log['sent_date'] = clean[:10]
            log['sent_time'] = clean[11:16]
        else:
            log['sent_date'] = ''
            log['sent_time'] = ''

    total_pages = (total + page_size - 1) // page_size
    page_range  = range(max(1, page - 2), min(total_pages + 1, page + 3))

    from datetime import datetime, timedelta
    seven_days_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

    return render(request, 'notification/log.html', {
        'logs':               logs,
        'filter_type':        filter_type,
        'notification_types': [
            ('confirmation', 'Confirmation'),
            ('cancellation', 'Cancellation'),
            ('reminder',     'Reminder'),
            ('broadcast',    'Broadcast'),
            ('switch',       'Switch'),
            ('verification', 'Verification'),
        ],
        'stats': {
            'total_sent':  total,
            'recent_sent': sum(1 for l in logs if l.get('sent_date', '') >= seven_days_ago),
            'failed':      sum(1 for l in logs if not l.get('is_success')),
        },
        'page':        page,
        'total_pages': total_pages,
        'page_range':  page_range,
        'has_next':    page < total_pages,
        'has_prev':    page > 1,
        'total':       total,
    })


def notification_settings_view(request):
    headers = check_auth(request)
    if not isinstance(headers, dict):
        return headers
    if not is_admin(request):
        return redirect('home')

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add':
            requests.post(
                SERVICES['notification_service'] + '/api/v1/notifications/reminders/',
                json={'interval_days': request.POST.get('interval_days'), 'is_active': True},
                headers=headers
            )
        elif action == 'delete':
            requests.delete(
                SERVICES['notification_service'] + f'/api/v1/notifications/reminders/{request.POST.get("config_id")}/',
                headers=headers
            )
        elif action == 'toggle':
            requests.patch(
                SERVICES['notification_service'] + f'/api/v1/notifications/reminders/{request.POST.get("config_id")}/',
                json={},
                headers=headers
            )
        return redirect('notification_settings')

    configs = requests.get(
        SERVICES['notification_service'] + '/api/v1/notifications/reminders/',
        headers=headers
    )
    return render(request, 'notification/settings.html', {
        'configs':       configs.json() if configs.status_code == 200 else [],
        'quick_presets': [1, 3, 7, 14],
    })


# ── Registration ──────────────────────────────────────────────

def registration_view(request):
    headers = check_auth(request)
    if not isinstance(headers, dict):
        return headers
    if not is_employee(request):
        return redirect('home')

    response     = requests.get(
        SERVICES['registration_service'] + '/api/v1/registrations/my/',
        headers=headers
    )
    registration = response.json() if response.status_code == 200 else None
    return render(request, 'registration/list.html', {'registration': registration})


def register_activity(request, ngo_id):
    headers = check_auth(request)
    if not isinstance(headers, dict):
        return headers
    if not is_employee(request):
        return redirect('home')

    response = requests.post(
        SERVICES['registration_service'] + f'/api/v1/registrations/register/{ngo_id}/',
        headers=headers
    )
    if response.status_code == 201:
        messages.success(request, 'Successfully registered for the activity!')
    else:
        error = response.json().get('error', 'Registration failed. Please try again.')
        messages.error(request, f'⚠️ {error}')
    return redirect('employee_dashboard')


def cancel_registration(request):
    headers = check_auth(request)
    if not isinstance(headers, dict):
        return headers
    if not is_employee(request):
        return redirect('home')

    response = requests.delete(
        SERVICES['registration_service'] + '/api/v1/registrations/cancel/',
        headers=headers
    )
    if response.status_code == 200:
        messages.success(request, 'Registration cancelled successfully.')
    else:
        messages.error(request, 'Failed to cancel registration.')
    return redirect('employee_dashboard')


def switch_registration(request, ngo_id):
    headers = check_auth(request)
    if not isinstance(headers, dict):
        return headers
    if not is_employee(request):
        return redirect('home')

    response = requests.put(
        SERVICES['registration_service'] + f'/api/v1/registrations/switch/{ngo_id}/',
        headers=headers
    )
    if response.status_code == 200:
        messages.success(request, 'Successfully switched to the new activity!')
    else:
        messages.error(request, 'Failed to switch activity. Please try again.')
    return redirect('employee_dashboard')


def participants_view(request, ngo_id):
    headers = check_auth(request)
    if not isinstance(headers, dict):
        return headers
    if not is_admin(request):
        return redirect('home')

    response = requests.get(
        SERVICES['registration_service'] + f'/api/v1/registrations/participants/{ngo_id}/',
        headers=headers
    )
    data    = response.json() if response.status_code == 200 else {}
    results = data.get('results', {})
    return render(request, 'registration/participants.html', {
        'participants': results.get('participants', []),
        'ngo_id':       ngo_id,
        'count':        data.get('count', 0),
        'source':       results.get('source', ''),
    })


# ── Checkin ───────────────────────────────────────────────────

def checkin_view(request, ngo_id):
    headers = check_auth(request)
    if not isinstance(headers, dict):
        return headers
    if not is_admin(request):
        return redirect('home')

    response         = requests.get(
        SERVICES['checkin_service'] + f'/api/v1/checkins/live-monitor/{ngo_id}/',
        headers=headers
    )
    data             = response.json() if response.status_code == 200 else {}
    checkins         = data.get('checkins', [])
    checked_in_count = data.get('checked_in_count', 0)

    enriched_checkins = []
    for checkin in checkins:
        user_resp = requests.get(
            SERVICES['user_service'] + f'/api/v1/users/{checkin["employee_id"]}/',
            headers=headers
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
            checkin['username']      = ''
        enriched_checkins.append(checkin)

    reg_resp         = requests.get(
        SERVICES['registration_service'] + f'/api/v1/registrations/participants/{ngo_id}/',
        headers=headers
    )
    reg_data         = reg_resp.json() if reg_resp.status_code == 200 else {}
    total_registered = reg_data.get('count', 0)
    attendance_pct   = round(checked_in_count / total_registered * 100) if total_registered > 0 else 0

    ngo_resp = requests.get(
        SERVICES['ngo_service'] + f'/api/v1/ngos/{ngo_id}/',
        headers=headers
    )
    ngo = ngo_resp.json().get('data', {}) if ngo_resp.status_code == 200 else {}

    return render(request, 'checkin/list.html', {
        'checkins':         enriched_checkins,
        'checked_in_count': checked_in_count,
        'total_registered': total_registered,
        'attendance_pct':   attendance_pct,
        'ngo':              ngo,
        'ngo_id':           ngo_id,
    })


def generate_qr(request, ngo_id):
    headers = check_auth(request)
    if not isinstance(headers, dict):
        return headers
    if not is_admin(request):
        return redirect('home')

    response = requests.get(
        SERVICES['checkin_service'] + f'/api/v1/checkins/generate-qr/{ngo_id}/',
        headers=headers
    )
    qr_data  = response.json() if response.status_code == 200 else {}
    ngo_resp = requests.get(
        SERVICES['ngo_service'] + f'/api/v1/ngos/{ngo_id}/',
        headers=headers
    )
    ngo = ngo_resp.json().get('data', {}) if ngo_resp.status_code == 200 else {}

    return render(request, 'checkin/qr.html', {
        'qr_code': qr_data.get('qr_code_base64'),
        'ngo_id':  ngo_id,
        'ngo':     ngo,
    })


def scan_view(request):
    headers = check_auth(request)
    if not isinstance(headers, dict):
        return headers

    ngo_id = request.GET.get('ngo_id')
    if not ngo_id:
        return render(request, 'checkin/success.html', {'message': 'Invalid QR code.'})

    response = requests.post(
        SERVICES['checkin_service'] + '/api/v1/checkins/scan/',
        json={'ngo_id': int(ngo_id)},
        headers=headers
    )
    result = response.json()
    return render(request, 'checkin/success.html', {
        'message': result.get('message') or result.get('error')
    })