import os
import json
import firebase_admin
from firebase_admin import credentials

# 1. Try to get the config from the Render Environment Variable
firebase_config = os.environ.get('FIREBASE_CONFIG')

if firebase_config:
    # We are on Render! Use the data from the Environment Variable
    try:
        config_dict = json.loads(firebase_config)
        cred = credentials.Certificate(config_dict)
    except Exception as e:
        print(f"!!! ERROR Parsing FIREBASE_CONFIG: {e} !!!")
        raise e
else:
    # We are on your PC! Use the local file
    if os.path.exists('serviceAccountKey.json'):
        cred = credentials.Certificate('serviceAccountKey.json')
    else:
        print("!!! ERROR: No serviceAccountKey.json found locally !!!")
        raise FileNotFoundError("serviceAccountKey.json not found")

# 2. Initialize the app only if it hasn't been started yet
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)