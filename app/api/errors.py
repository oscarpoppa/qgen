"""Every API error is JSON: {"error": {"code": "...", "message": "...", "details": ...}}."""
from flask import jsonify
from werkzeug.exceptions import HTTPException

from . import api_bp


class ApiError(Exception):
    def __init__(self, status, code, message, details=None):
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details


def error_response(status, code, message, details=None, headers=None):
    body = {'error': {'code': code, 'message': message}}
    if details is not None:
        body['error']['details'] = details
    return jsonify(body), status, headers or {}


@api_bp.errorhandler(ApiError)
def _api_error(exc):
    headers = {'WWW-Authenticate': 'Bearer'} if exc.status == 401 else None
    return error_response(exc.status, exc.code, exc.message, exc.details, headers)


@api_bp.errorhandler(HTTPException)
def _http_error(exc):
    return error_response(exc.code, exc.name.lower().replace(' ', '_'), exc.description or exc.name)


def bad_request(message, details=None):
    return ApiError(400, 'bad_request', message, details)


def not_found(what='That'):
    return ApiError(404, 'not_found', '{} doesn\'t exist, or isn\'t yours.'.format(what))


def conflict(message):
    return ApiError(409, 'conflict', message)


def invalid(errors):
    """The request was understood but the content has problems (plain-language list)."""
    return ApiError(422, 'invalid', 'Please fix: ' + ' '.join(errors), errors)
