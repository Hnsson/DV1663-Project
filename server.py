from flask import Flask, render_template, request, abort, jsonify, send_from_directory, redirect, session, url_for
from functools import wraps
from msal import ConfidentialClientApplication
import os
import uuid

# MSAL Configurations
CLIENT_ID = '0e3eed48-d269-4631-989f-5b25f0f0c54b'
CLIENT_SECRET = 'f7d9652b-a97f-4db4-b2bd-aba6ed181c58'
AUTHORITY = 'https://login.microsoftonline.com/fc13d152-2331-488a-bda5-b8a82c098338'
REDIRECT_PATH = '/getAToken'
SCOPE = ["User.Read", "email"]
SESSION_TYPE = "filesystem"  # Ensures that the session is stored on the server-side

from database import query_db, init_db

import random
import bcrypt

app = Flask(__name__, template_folder='web/templates')
app.secret_key = os.urandom(24)  # You can also use a more permanent secret key
app.config['SESSION_TYPE'] = SESSION_TYPE

msal_app = ConfidentialClientApplication(
    CLIENT_ID, authority=AUTHORITY, client_credential=CLIENT_SECRET
)

init_db(app)

@app.route('/login')
def login():
    state = str(uuid.uuid4())  # Generate a new state value for each authentication request
    auth_url = msal_app.get_authorization_request_url(SCOPE, state=state, redirect_uri="https://localhost:8080/getAToken")
    session['state'] = state  # Store state in session for later validation
    return redirect(auth_url)

@app.route('/getAToken')
def authorized():
    # Check the state returned to ensure this request is not a result of a CSRF attack
    if request.args.get('state') != session.get("state"):
        return "State mismatch error", 400
    code = request.args.get('code')
    result = msal_app.acquire_token_by_authorization_code(code, scopes=SCOPE, redirect_uri="https://localhost:8080/getAToken")
    if "access_token" in result:
        # Success
        session['user'] = result.get('id_token_claims')
        return redirect(url_for('index'))
    else:
        # Error
        return "Authentication failed", 500


# === GET Requests ===

def middleware_authentication(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        print("YO2")
        if 'user' not in session:
            return redirect(url_for('login'))
        return func(*args, **kwargs)
    return wrapper

@app.route('/', methods=['GET'])
def index():
    user_info = session.get('user', {})
    if user_info:
        return render_template('index.html', user=user_info)
    return send_from_directory('web/static', "index.html")

@app.route('/home', methods=['GET'])
@middleware_authentication # Check if logged in
def home():
    # This is where (when logged in) all the posts is gonna be dispalyed
    return "Home";

@app.route('/users', methods=['GET']) # Will be removed when fininshed
def get_users():
    return render_template('users/users.html', users=query_db('SELECT * FROM users'))

# Get post from user
@app.route('/user/<username>/post/<int:post_id>', methods=['GET'])
def get_user_post(username, post_id):
    post = query_db('SELECT * FROM posts WHERE post_id = ?', [post_id], one=True)
    if post is None:
        abort(404)

    comments = query_db('SELECT * FROM comments WHERE post_id = ?', [post_id])

    return render_template('posts/post.html', post=post, comments=comments, username=username)

# Get specific user page
@app.route('/user/<username>', methods=['GET'])
def get_user(username):
    user = query_db('SELECT * FROM users WHERE username = ?', [username], one=True)
    if user is None:
        abort(404)
    # Query posts for the user from the database
    posts = query_db('SELECT * FROM posts WHERE user_id = ?', [user['user_id']])
    
    return render_template('users/user.html', user=user, posts=posts)

@app.route('/search', methods=['GET'])
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




# === POST Requests ===

@app.route('/create-post', methods=['POST'])
def create_post():
    pass;

@app.route('/post/<post_id>/create-comment', methods=['POST'])
def create_comment(post_id):
    pass;








# === TEMPORARY Test ===
@app.route('/create-random-user', methods=['POST'])
def create_random_user():
    try:
        # Generate random user information
        username, password, name, age = generate_random_user()
        # Hash the password using Bcrypt
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        
        # Insert the user into the database
        query_db("INSERT INTO users (username, password_hash, name, age) VALUES (?, ?, ?, ?)", [username, hashed_password.decode('utf-8'), name, age], False, True);

        # Return success response
        return jsonify({'success': True, 'message': f"User created: Username - {username}, Password - {password}, Age - {age}"}), 201
    except Exception as e:
        # Return error response
        print(e);
        return jsonify({'success': False, 'error': str(e)}), 500

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

def generate_random_user():
    # List of random names
    names = ['Alice', 'Bob', 'Charlie', 'David', 'Emma', 'Frank', 'Grace', 'Henry', 'Ivy', 'Jack']
    
    # Generate random username, password, and age
    name = random.choice(names)
    username = name[0].lower() + name[-1].lower() + str(random.randint(100, 999))
    password = ''.join(random.choices('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=8))
    age = random.randint(18, 54)
    
    return username, password, name, age


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
    app.run(debug=True, port=8080)
