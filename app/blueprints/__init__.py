def create_app():
    app = Flask(__name__)
    
    # --- FIREBASE START ---
    import os
    import json
    import firebase_admin
    from firebase_admin import credentials

    firebase_config = os.environ.get('FIREBASE_CONFIG')

    if firebase_config:
        # Use Render's Environment Variable
        config_dict = json.loads(firebase_config)
        cred = credentials.Certificate(config_dict)
    else:
        # Local PC fallback
        cred = credentials.Certificate('serviceAccountKey.json')

    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    # --- FIREBASE END ---
    
    # ... rest of your code (Blueprints, etc.)
    return app