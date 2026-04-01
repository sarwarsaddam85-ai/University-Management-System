from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify # <-- Added jsonify
from firebase_admin import auth, firestore
import google.auth.exceptions
from app import db # Import the db instance from __init__.py

# Define the blueprint
auth_bp = Blueprint('auth', __name__, template_folder='../templates/auth')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    # --- Check if user is already logged in ---
    if session.get('user_id'):
        flash('You are already logged in. Please log out to register a new account.', 'info')
        if session.get('role') == 'admin':
            return redirect(url_for('dashboard.admin_dashboard'))
        elif session.get('role') == 'teacher':
            return redirect(url_for('dashboard.teacher_dashboard'))
        else:
            return redirect(url_for('dashboard.student_dashboard'))
    # --- End of check ---

    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        role = request.form['role'] # Student, Teacher, Admin

        try:
            # 1. Create user in Firebase Authentication
            user = auth.create_user(
                email=email,
                password=password
            )

            # 2. Store user role and other details in Firestore
            user_data = {
                'email': email,
                'role': role,
                'uid': user.uid
            }
            db.collection('users').document(user.uid).set(user_data)

            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('auth.login'))

        except auth.EmailAlreadyExistsError:
            flash('Email already exists. Please login.', 'error')
        except Exception as e:
            flash(f'An error occurred: {e}', 'error')

    return render_template('register.html')


# --- UPDATED LOGIN FUNCTION (Verify ID Token) ---
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    # --- Check if already logged in (Redirects GET requests) ---
    if session.get('user_id'):
        if request.method == 'GET':
             flash('You are already logged in.', 'info')
             if session.get('role') == 'admin': return redirect(url_for('dashboard.admin_dashboard'))
             elif session.get('role') == 'teacher': return redirect(url_for('dashboard.teacher_dashboard'))
             else: return redirect(url_for('dashboard.student_dashboard'))
        # Allow POST requests even if logged in, JS handles flow

    # --- Handle POST request (from JavaScript with ID Token) ---
    if request.method == 'POST':
        try:
            # 1. Get the ID token from JSON body
            id_token = request.json.get('idToken')
            if not id_token:
                return jsonify({'success': False, 'message': 'ID token missing.'}), 400

            # 2. Verify the ID token using Firebase Admin SDK
            decoded_token = auth.verify_id_token(id_token)
            uid = decoded_token['uid'] # Verified user ID

            # 3. Get user data (role) from Firestore
            user_doc = db.collection('users').document(uid).get()
            if user_doc.exists:
                user_info = user_doc.to_dict()

                # 4. Store user info in Flask session
                session.clear() # Clear old session
                session['user_id'] = uid
                session['email'] = user_info.get('email', decoded_token.get('email'))
                session['role'] = user_info.get('role', 'student')

                # 5. Determine redirect URL
                if session['role'] == 'admin':
                    redirect_url = url_for('dashboard.admin_dashboard')
                elif session['role'] == 'teacher':
                    redirect_url = url_for('dashboard.teacher_dashboard')
                else:
                    redirect_url = url_for('dashboard.student_dashboard')

                # 6. Send success response back to JavaScript
                return jsonify({'success': True, 'redirectUrl': redirect_url})
            else:
                # User authenticated but no record in Firestore 'users' collection
                return jsonify({'success': False, 'message': 'User data not found. Please contact admin.'}), 404

        # --- Error Handling ---
        except auth.InvalidIdTokenError as e:
            return jsonify({'success': False, 'message': f'Invalid login session: {e}'}), 401
        except auth.ExpiredIdTokenError as e:
             return jsonify({'success': False, 'message': f'Login session expired: {e}'}), 401
        except google.auth.exceptions.RefreshError as e:
             print(f"!!! Firebase Admin SDK Error: {e}")
             return jsonify({'success': False, 'message': 'Server configuration error.'}), 500
        except Exception as e:
            print(f"!!! Login Error: {e}")
            return jsonify({'success': False, 'message': f'An unexpected error occurred: {e}'}), 500

    # --- Handle GET request (Show the login page) ---
    return render_template('login.html')

# --- Logout function (No changes needed) ---
@auth_bp.route('/logout')
def logout():
    session.clear() # Clear the user session
    flash('You have been logged out.', 'success')
    return redirect(url_for('auth.login'))