from django.conf import settings

def user_session(request):
    return {
        'user_id': request.session.get('user_id', ''),
    }

def services(request):
    return {
        "services": settings.SERVICES
    }