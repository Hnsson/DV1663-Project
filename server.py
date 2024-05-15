from flask import Flask, render_template, request, abort, jsonify, send_from_directory, redirect, session, url_for
from msal import ConfidentialClientApplication
import os
import uuid

from functools import wraps
from datetime import datetime

# MSAL Configurations
CLIENT_ID = '0e3eed48-d269-4631-989f-5b25f0f0c54b'
CLIENT_SECRET = 'Ie48Q~Hu21oGeLikTEijYtseHTPNVbWsw4UFGcbp'
AUTHORITY = 'https://login.microsoftonline.com/fc13d152-2331-488a-bda5-b8a82c098338'
REDIRECT_PATH = '/getAToken'
SCOPE = ["User.Read", "email"]
SESSION_TYPE = "filesystem"  # Ensures that the session is stored on the server-side

from database import query_db, init_db

import random
import bcrypt



app = Flask(__name__, template_folder='web/templates')
app.secret_key = '127347567897'
app.config['SESSION_TYPE'] = SESSION_TYPE
app.config['SESSION_FILE_DIR'] = '/path/to/your/sessions'  # Specify your directory
os.makedirs(app.config['SESSION_FILE_DIR'], exist_ok=True)  # Create the directory if it doesn't exist
app.config.update(
    SESSION_COOKIE_SAMESITE='None',
    SESSION_COOKIE_SECURE= True
)
# app.config['SESSION_COOKIE_HTTPONLY'] = True

app.config['SESSION_COOKIE_SAMESITE'] = 'None'  # Consider 'Lax' or 'Strict' based on need


msal_app = ConfidentialClientApplication(
    CLIENT_ID, authority=AUTHORITY, client_credential=CLIENT_SECRET
)

init_db(app)

@app.route('/login')
def login():
    state = str(uuid.uuid4())  # Generate a new state value for each authentication request
    session['state'] = state  # Store state in session for later validation
    print("Saved state:", state)
    auth_url = msal_app.get_authorization_request_url(SCOPE, state=state, redirect_uri="https://127.0.0.1:8080/getAToken")
    return redirect(auth_url)

@app.route('/getAToken')
def authorized():
    received_state = request.args.get('state')
    saved_state = session.get("state")
    print("Log - Received state:", received_state)  # Debug log
    print("Log - Expected state from session:", saved_state)  # Debug log
    # Check the state returned to ensure this request is not a result of a CSRF attack
    if request.args.get('state') != session.get("state"):
        return "State mismatch error", 400
    code = request.args.get('code')
    result = msal_app.acquire_token_by_authorization_code(code, scopes=SCOPE, redirect_uri="https://127.0.0.1:8080/getAToken")
    if "access_token" in result:
        # Success
        id_token_claims = result.get('id_token_claims')
        print(id_token_claims)
        # Check if the user's email ends with '@student.bth.se'
        if id_token_claims.get('email', '').endswith('@student.bth.se'):
            # Check if the user already exists in the database
            user_exists = query_db("SELECT * FROM users WHERE user_id = ?", [id_token_claims.get('oid')], one=True)
            if not user_exists:
                oid = str(id_token_claims.get('oid'))
                name = str(id_token_claims.get('name'))
                email = str(id_token_claims.get('email'))
                username = email.split('@')[0]

                # Insert the user into the database
                query_db("INSERT INTO users (user_id, name, username, email) VALUES (?, ?, ?, ?)", [oid, name, username, email], False, True)
        session['user'] = id_token_claims
        return redirect(url_for('index'))
    else:
        # Error
        print("Error acquiring token:", result.get("error"), result.get("error_description"))
        return "Authentication failed", 500
    # code = request.args.get('code')
    # result = msal_app.acquire_token_by_authorization_code(code, scopes=SCOPE, redirect_uri="https://localhost:8080/getAToken")
    # session['user'] = result.get('id_token_claims')
    # received_user = request.args.get('state')
    # return redirect(url_for('index'))


# === GET Requests ===
# Authentication middleware
def middleware_authentication(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        user_credentials = session.get('user', {})
        if user_credentials:
            if user_credentials.get('email', '').endswith('@student.bth.se'):
                return func(*args, **kwargs)
            else:
                return redirect(url_for('index'))
        else:
            return render_template('error/error.html', title='303 - Invalid credentials.', code=303, message="You need to login."), 303
    return wrapper


@app.route('/', methods=['GET'])
def index():
    user_info = session.get('user', {})
    if user_info:
        user_email = user_info.get('email', 'No email found')
        if user_email and user_email.endswith('@student.bth.se'):
            return render_template('index.html', user=user_info, email=user_email, username=user_email.split('@')[0])
        else:
            session.clear()
            error_message = "Unauthorized email domain. Access is restricted to @student.bth.se emails."
            return render_template('index.html', error=error_message)

    return send_from_directory('web/static', "index.html")


@app.route('/users', methods=['GET']) # Will be removed when fininshed
def get_users():
    # return render_template('users/users.html', users=query_db('SELECT * FROM users'))
    return "Expired path..."

# Get post from user
@app.route('/user/<username>/post/<int:post_id>', methods=['GET'])
@middleware_authentication # Check if logged in
def get_user_post(username, post_id):
    post_query = '''
        SELECT p.*, u.username AS user_username, u.name AS user_name 
        FROM posts p
        JOIN users u ON p.user_id = u.user_id
        WHERE p.post_id = ?
    '''
    post = query_db(post_query, [post_id], one=True)
    if post is None:
        abort(404)

    comments = query_db('''
        SELECT comments.*, users.name, users.username
        FROM comments
        JOIN users ON comments.user_id = users.user_id
        WHERE comments.post_id = ?
    ''', [str(post_id)])

    user = {'username': post['user_username'], 'name': post['user_name']}  # Create user dictionary
    
    return render_template('posts/post.html', post=post, comments=comments, user=user, username=username)


# Get specific user page
@app.route('/user/<username>', methods=['GET'])
@middleware_authentication # Check if logged in
def get_user(username):
    user = query_db('SELECT * FROM users WHERE username = ?', [username], one=True)
    if user is None:
        abort(404)
    # Query posts for the user from the database
    posts = query_db('SELECT * FROM posts WHERE user_id = ?', [user['user_id']])
    
    return render_template('users/user.html', user=user, posts=posts)

@app.route('/search', methods=['GET'])
@middleware_authentication # Check if logged in
def search():
    search_query = request.args.get('q');

    print(search_query);
    # Check if query contains '@' symbol for username search instead of name search
    if search_query[0] == '@':
        # Search by username
        search_query = search_query[1:];
        print(search_query);
        user = query_db('SELECT * FROM users WHERE username = ?', [search_query], one=True)

        return render_template('search/search_results.html', users=[user] if user else [])
    else:
        # Search by name (matching partial names)
        users = query_db("SELECT * FROM users WHERE name LIKE ? OR username LIKE ?", [f'%{search_query}%', f'%{search_query}%'])
        
        return render_template('search/search_results.html', users=users if users else [])

@app.route('/logout', methods=['GET'])
def logout():
    # Clear session data
    session.clear()
    return redirect(url_for('index'))


# === POST Requests ===

@app.route('/create-post', methods=['POST'])
def create_post():
    if 'user' in session:
        user = session['user']
        user_id = user.get('oid')
        title = request.form.get('title')
        content = request.form.get('body')
        # Get the current date and format it
        created_at = datetime.now().strftime('%Y-%m-%d')

        # Insert the post into the database
        query_db("INSERT INTO posts (title, body ,user_id, created_at) VALUES (?, ?, ?, ?)", [title, content, user_id, created_at], False, True)

        return redirect(url_for('index'))

@app.route('/post/<post_id>/create-comment', methods=['POST'])
def create_comment(post_id):
    if 'user' in session:
        user = session['user']
        user_id = user.get('oid')
        title = request.form.get('title')
        content = request.form.get('body')
        # Get the current date and format it
        created_at = datetime.now().strftime('%Y-%m-%d')

        # Insert the post into the database
        query_db("INSERT INTO comments (title, body, user_id, post_id, created_at) VALUES (?, ?, ?, ?, ?)", [title, content, user_id, post_id, created_at], False, True)
        # Return JSON response indicating success
        return jsonify(success=True)
    else:
        # Handle case where user is not logged in
        return jsonify(success=False, error='User not logged in')


@app.route('/delete-user/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    try:
        # Perform deletion of the user with the specified user_id
        # Assuming you have a function named delete_user_from_db to handle this operation
        query_db("DELETE FROM users WHERE user_id = ?", [user_id], False, True);

        # Return success response
        return jsonify({'success': True, 'message': f"User with ID {user_id} deleted successfully"}), 200
    except Exception as e:
        # Return error response
        return jsonify({'success': False, 'error': str(e)}), 500


# === Helper Functions ===


# === DEFAULT Routing ===

# Route to serve the static HTML file
@app.route('/<path:filename>', methods=['GET'])
def serve_static_html(filename):
    return send_from_directory('web/static', filename + ".html")

# Route to serve CSS files
@app.route('/css/<path:filename>')
def serve_css(filename):
    return send_from_directory('web/css', filename)


# === ERROR Handling ===

@app.errorhandler(404)
def page_not_found(error):
    print(error);
    return render_template('error/error.html', title='404 - Page not found.', code=404, message=error), 404




# Start app
if __name__ == '__main__':
    app.run(debug=True, port=8080, ssl_context=('cert.pem', 'key.pem'))