from functools import wraps
from flask import session, flash, redirect, url_for

def login_required(f):
    """
    Decorator to ensure a user is logged in.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """
    Decorator to ensure a user is logged in AND is an admin.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # First, check if they are logged in at all
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('auth.login'))

        # Then, check if their role is 'admin'
        if session.get('role') != 'admin':
            flash('You do not have permission to access this page.', 'error')
            return redirect(url_for('home')) # Redirect them to the home page

        return f(*args, **kwargs)
    return decorated_function


def teacher_required(f):
    """
    Decorator to ensure a user is a Teacher (or an Admin, who can do everything).
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('auth.login'))

        # Allow 'admin' OR 'teacher'
        if session.get('role') not in ('admin', 'teacher'):
            flash('This page is for teaching staff only.', 'error')
            return redirect(url_for('home'))

        return f(*args, **kwargs)
    return decorated_function