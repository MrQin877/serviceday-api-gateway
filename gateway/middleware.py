from django.utils.functional import SimpleLazyObject

class SessionUser:
    def __init__(self, request):
        self.username         = request.session.get('username', '')
        self.role             = request.session.get('role', '')
        self.is_authenticated = bool(request.session.get('access_token'))
        self.is_active        = self.is_authenticated
        self.is_staff         = False   # ← add this
        self.is_superuser     = False   # ← add this

    def __bool__(self):
        return self.is_authenticated


class GatewayAuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.user = SimpleLazyObject(lambda: SessionUser(request))
        return self.get_response(request)