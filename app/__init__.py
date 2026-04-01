import firebase_admin
from firebase_admin import credentials, firestore
from flask import Flask, render_template
import os 
import json # Added for Environment Variable parsing

# Global database client instance
db = None

def create_app():
    global db

    app = Flask(__name__)

    # --- SECURITY FIX ---
    app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24))

    # --- Firebase Initialization (UPDATED FOR RENDER) ---
    if not firebase_admin._apps:
        try:
            # 1. Check if we are on Render (Environment Variable)
            firebase_config = os.environ.get('FIREBASE_CONFIG')

            if firebase_config:
                # Use the JSON text from Render Dashboard
                config_dict = json.loads(firebase_config)
                cred = credentials.Certificate(config_dict)
                print("--- Firebase Initialized via Environment Variable ---")
            else:
                # Use the local file on your PC
                cred = credentials.Certificate('serviceAccountKey.json')
                print("--- Firebase Initialized via local file ---")

            firebase_admin.initialize_app(cred, {
                'storageBucket': 'studentmanagementsystem-204e6.firebasestorage.app'
            })
            
        except Exception as e:
            print(f"!!! ERROR Initializing Firebase Admin SDK: {e} !!!")
            raise e 

    # --- Initialize Firestore Client ---
    try:
        db = firestore.client()
        print("--- Firestore Client Initialized ---")
    except Exception as e:
         print(f"!!! ERROR Getting Firestore Client: {e} !!!")
         raise e 

    # --- Register Blueprints ---
    with app.app_context():
        print("--- Registering Blueprints ---")
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

            from .blueprints.timetable_bp import timetable_bp
            app.register_blueprint(timetable_bp, url_prefix='/timetable')

            from .blueprints.hostel_bp import hostel_bp
            app.register_blueprint(hostel_bp, url_prefix='/hostel')
            
            print("--- Blueprints Registered Successfully ---")

        except Exception as e:
            print(f"!!! ERROR Registering Blueprints: {e} !!!")
            raise e

    # --- Main Route ---
    @app.route('/')
    def home():
        return render_template('index.html')

    print("--- Flask App Creation Complete ---")
    return app