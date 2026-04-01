import os
from app import create_app

app = create_app()

if __name__ == '__main__':
    # This line is the magic: it checks if Render gave us a Port. 
    # If not (on your PC), it uses 5000.
    port = int(os.environ.get("PORT", 5000))
    
    # host='0.0.0.0' allows Render to send people to your site
    app.run(host='0.0.0.0', port=port)