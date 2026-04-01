import firebase_admin
from firebase_admin import credentials, firestore
from flask import Flask, render_template
import os # Import os to generate a secret key

# Global database client instance
db = None

def create_app():
    global db

    app = Flask(__name__)

    # --- !!! CRITICAL SECURITY FIX !!! ---
    # Use environment variable for secret key in production, or generate a random one for development.
    # NEVER hardcode API keys or guessable strings here.
    app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24))
    # For simplicity in development, os.urandom(24) generates a new random key each time.
    # For production, set a fixed FLASK_SECRET_KEY environment variable.
    # --- END SECURITY FIX ---

    # --- Firebase Initialization ---
    if not firebase_admin._apps:
        try:
            cred = credentials.Certificate('serviceAccountKey.json')
            firebase_admin.initialize_app(cred, {
                # --- CORRECTED Storage Bucket URL (Use yours from Firebase Console) ---
                'storageBucket': 'studentmanagementsystem-204e6.firebasestorage.app'
                # --- Replace above with your actual bucket URL ending in .appspot.com ---
            })
            print("--- Firebase Admin SDK Initialized ---") # Debug print
        except Exception as e:
            print(f"!!! ERROR Initializing Firebase Admin SDK: {e} !!!")
            # Handle initialization error appropriately, maybe exit or raise
            raise e # Stop the app if Firebase can't init

    # --- Initialize Firestore Client ---
    try:
        db = firestore.client()
        print("--- Firestore Client Initialized ---") # Debug print
    except Exception as e:
         print(f"!!! ERROR Getting Firestore Client: {e} !!!")
         raise e # Stop the app if Firestore client fails

    # --- Register Blueprints (Consolidated into one block) ---
    with app.app_context():
        print("--- Registering Blueprints ---") # Debug print
        try:
            from .blueprints.auth_bp import auth_bp
            app.register_blueprint(auth_bp, url_prefix='/auth')

            from .blueprints.dashboard_bp import dashboard_bp
            app.register_blueprint(dashboard_bp, url_prefix='/dashboard')

            from .blueprints.students_bp import students_bp
            app.register_blueprint(students_bp, url_prefix='/students')

            from .blueprints.teachers_bp import teachers_bp
            app.register_blueprint(teachers_bp, url_prefix='/teachers')

            from .blueprints.courses_bp import courses_bp
            app.register_blueprint(courses_bp, url_prefix='/courses')

            from .blueprints.attendance_bp import attendance_bp
            app.register_blueprint(attendance_bp, url_prefix='/attendance')

            from .blueprints.assignments_bp import assignments_bp
            app.register_blueprint(assignments_bp, url_prefix='/assignments')

            from .blueprints.quizzes_bp import quizzes_bp
            app.register_blueprint(quizzes_bp, url_prefix='/quizzes')

            from .blueprints.finance_bp import finance_bp
            app.register_blueprint(finance_bp, url_prefix='/finance')

            from .blueprints.library_bp import library_bp
            app.register_blueprint(library_bp, url_prefix='/library')
            print("--- Blueprints Registered Successfully ---") # Debug print

            # --- ADD THESE TWO LINES ---
            from .blueprints.timetable_bp import timetable_bp
            app.register_blueprint(timetable_bp, url_prefix='/timetable')
            # ---------------------------

            from .blueprints.hostel_bp import hostel_bp
            app.register_blueprint(hostel_bp, url_prefix='/hostel')

        except Exception as e:
            print(f"!!! ERROR Registering Blueprints: {e} !!!")
            raise e # Stop if blueprints can't load


    # --- Main Route ---
    @app.route('/')
    def home():
        return render_template('index.html')

    print("--- Flask App Creation Complete ---") # Debug print
    return app