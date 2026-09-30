"""The original /api/v1 endpoints. They now need a teacher's personal access
token (Authorization: Bearer qg_...), the same as /api/v2."""
from functools import wraps

from app.api.auth import token_required
from app.api.errors import ApiError, error_response


def teacher_token(view):
    """flask_restful handles errors itself, so turn sign-in failures into JSON here."""
    guarded = token_required(teacher=True)(view)

    @wraps(view)
    def inner(*args, **kwargs):
        try:
            return guarded(*args, **kwargs)
        except ApiError as exc:
            #a finished Response, which flask_restful passes through untouched
            body, status, headers = error_response(exc.status, exc.code, exc.message, exc.details,
                                                   {'WWW-Authenticate': 'Bearer'} if exc.status == 401 else None)
            body.status_code = status
            body.headers.extend(headers)
            return body
    return inner
