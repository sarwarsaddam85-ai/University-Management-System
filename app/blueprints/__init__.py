from flask import Flask


def create_app():
    app = Flask(__name__)
    
    import os
    import json
    import firebase_admin
    from firebase_admin import credentials

    # Logic to choose between Render (variable) and Local (file)
    firebase_config = os.environ.get('FIREBASE_CONFIG')

    if firebase_config:
        # Use the Environment Variable we set in Render Dashboard
        config_dict = json.loads(firebase_config)
        cred = credentials.Certificate(config_dict)
    else:
        # Only use the file if we are on your local computer
        cred = credentials.Certificate('serviceAccountKey.json')

    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)

    # ... (rest of your app logic)
    return app