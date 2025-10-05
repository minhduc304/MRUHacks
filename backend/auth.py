"""
Authentication utilities for JWT-based user authentication
"""

import jwt
import bcrypt
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify
import os

# JWT Configuration
SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'your-secret-key-change-this-in-production')
ALGORITHM = 'HS256'
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours


def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt

    Args:
        password: Plain text password

    Returns:
        Hashed password as string
    """
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against its hash

    Args:
        plain_password: Plain text password to verify
        hashed_password: Hashed password to compare against

    Returns:
        True if password matches, False otherwise
    """
    return bcrypt.checkpw(
        plain_password.encode('utf-8'),
        hashed_password.encode('utf-8')
    )


def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    """
    Create a JWT access token

    Args:
        data: Dictionary containing user data to encode (typically user_id, email)
        expires_delta: Optional custom expiration time

    Returns:
        Encoded JWT token as string
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire, "iat": datetime.utcnow()})

    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> dict:
    """
    Decode and verify a JWT access token

    Args:
        token: JWT token string

    Returns:
        Decoded token payload as dictionary

    Raises:
        jwt.ExpiredSignatureError: If token has expired
        jwt.InvalidTokenError: If token is invalid
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise jwt.ExpiredSignatureError("Token has expired")
    except jwt.InvalidTokenError:
        raise jwt.InvalidTokenError("Invalid token")


def token_required(f):
    """
    Decorator to protect routes with JWT authentication

    Usage:
        @app.route('/protected')
        @token_required
        def protected_route(current_user):
            return jsonify({"user": current_user})

    The decorated function will receive current_user as the first argument,
    which contains the decoded token payload (user_id, email, etc.)
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None

        # Check for token in Authorization header
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                # Expected format: "Bearer <token>"
                token = auth_header.split(" ")[1]
            except IndexError:
                return jsonify({"error": "Invalid authorization header format"}), 401

        if not token:
            return jsonify({"error": "Authentication token is missing"}), 401

        try:
            # Decode token and get user data
            current_user = decode_access_token(token)

        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token has expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401
        except Exception as e:
            return jsonify({"error": f"Token validation failed: {str(e)}"}), 401

        # Pass current_user to the decorated function
        return f(current_user, *args, **kwargs)

    return decorated


def optional_token(f):
    """
    Decorator that makes authentication optional
    If token is present and valid, current_user is passed to the function
    If token is missing or invalid, current_user is None

    Usage:
        @app.route('/public-or-private')
        @optional_token
        def route(current_user):
            if current_user:
                return jsonify({"message": "Authenticated user"})
            else:
                return jsonify({"message": "Anonymous user"})
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        current_user = None

        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                token = auth_header.split(" ")[1]
                current_user = decode_access_token(token)
            except (IndexError, jwt.ExpiredSignatureError, jwt.InvalidTokenError):
                pass  # Ignore errors, treat as unauthenticated

        return f(current_user, *args, **kwargs)

    return decorated
