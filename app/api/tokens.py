"""Getting, listing and revoking personal access tokens; who am I."""
from flask import g, jsonify

from app import db
from app.user.models import User
from . import api_bp
from .auth import token_required, body
from .errors import ApiError, not_found
from .models import ApiToken, LoginFailure, TOKEN_DAYS
from .serialize import user_json, token_json


@api_bp.route('/tokens', methods=['POST'])
def create_token():
    """Sign in: {username, password, name?, days?} -> a new token, shown only this once."""
    data = body(required=('username', 'password'))
    username = str(data['username'])
    if LoginFailure.too_many(username):
        raise ApiError(429, 'too_many_attempts', 'Too many wrong passwords. Please wait 15 minutes and try again.')
    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(str(data['password'])):
        LoginFailure.record(username)
        raise ApiError(401, 'unauthorized', 'That username and password don\'t match.')
    if user.pw_man_reset:
        raise ApiError(403, 'password_change_required', 'This account\'s password was reset. Change it on the website first.')
    days = data.get('days', TOKEN_DAYS)
    if not isinstance(days, int) or not 1 <= days <= 365:
        raise ApiError(400, 'bad_request', '"days" must be a whole number from 1 to 365.')
    row, token = ApiToken.issue(user, str(data.get('name') or 'App'), days)
    out = token_json(row)
    out['token'] = token
    out['user'] = user_json(user)
    return jsonify(out), 201


@api_bp.route('/tokens', methods=['GET'])
@token_required()
def list_tokens():
    rows = ApiToken.query.filter_by(user_id=g.api_user.id).order_by(ApiToken.created.desc()).all()
    return jsonify(tokens=[token_json(r, current=r.id == g.api_token.id) for r in rows])


@api_bp.route('/tokens/<int:token_id>', methods=['DELETE'])
@token_required()
def revoke_token(token_id):
    row = db.session.get(ApiToken, token_id)
    if not row or row.user_id != g.api_user.id:
        raise not_found('That token')
    row.revoked = True
    db.session.commit()
    return '', 204


@api_bp.route('/tokens/current', methods=['DELETE'])
@token_required()
def sign_out():
    g.api_token.revoked = True
    db.session.commit()
    return '', 204


@api_bp.route('/me', methods=['GET'])
@token_required()
def me():
    return jsonify(user_json(g.api_user, full=True))
