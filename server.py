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
# Custom filter function to parse string to datetime
def parse_datetime(value, format='%Y-%m-%d %H:%M:%S'):
    from datetime import datetime
    try:
        parsed_datetime = datetime.strptime(value, format)
        return parsed_datetime.strftime('%b %d %Y - %H:%M')
    except ValueError:
        # Fallback behavior: Return the original value
        return value
# Register the custom filter
app.template_filter('parse_datetime')(parse_datetime)
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
                return func(*args, **kwargs, user_credentials=user_credentials)
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
            # Fetch posts, default should be based on recent posts
            user_info['username'] = user_info.get('email', '').split('@')[0]
            sort_option = request.args.get('sort_by', 'recent')
            page = int(request.args.get('page', 0))
            fetch_count = (10 * (page + 1))
            exists_more = True;

            posts = fetch_posts(self_id=user_info.get('oid'), sort_by=sort_option, limit=fetch_count+1)
            
            print(fetch_count, " : ", len(posts))
            if fetch_count >= len(posts):
                exists_more = False

            return render_template('index.html', _self=user_info, email=user_email, posts=posts, sort_by=sort_option, exists_more=exists_more, page=page)
        else:
            session.clear()
            error_message = "Unauthorized email domain. Access is restricted to @student.bth.se emails."
            return render_template('index.html', error=error_message)

    return send_from_directory('web/static', "index.html")


# Get post from user
@app.route('/user/<username>/post/<int:post_id>', methods=['GET'])
@middleware_authentication # Check if logged in
def get_user_post(username, post_id, user_credentials): # The user_credentials is sent from middleware_authentication
    user_credentials['username'] = user_credentials.get('email', '').split('@')[0]
    # Retrieve the post from the database and join with the user that posted to recieve info

    post = fetch_posts(self_id=user_credentials.get('oid'), post_id=post_id, limit=1)
    if post is None:
        abort(404)

    comments = query_db('''
        SELECT comments.*, 
            users.name, 
            users.username, 
            COUNT(l.like_id) as like_count,
            CASE WHEN EXISTS (SELECT 1 FROM likes WHERE comment_id = comments.comment_id AND user_id = ?) THEN 1 ELSE 0 END as is_liked
        FROM comments
        JOIN users ON comments.user_id = users.user_id
        LEFT JOIN likes l ON comments.comment_id = l.comment_id
        WHERE comments.post_id = ?
        GROUP BY comments.comment_id
    ''', [user_credentials.get('oid'), post_id])

    
    return render_template('posts/post.html', _self=user_credentials, post=post, comments=comments)

# Get specific user page
@app.route('/user/<username>', methods=['GET'])
@middleware_authentication # Check if logged in
def get_user(username, user_credentials): # The user_credentials is sent from middleware_authentication
    user_credentials['username'] = user_credentials.get('email', '').split('@')[0]

    user = query_db('SELECT * FROM users WHERE username = ?', [username], one=True)
    if user is None:
        abort(404)
    # Query posts for the user from the database
    # posts = fetch_posts(self_id=user_credentials.get('oid'))
    posts = fetch_posts(self_id=user_credentials.get('oid'), user_id=user['user_id'])
    
    return render_template('users/user.html', _self=user_credentials, user=user, posts=posts)

@app.route('/search', methods=['GET'])
@middleware_authentication # Check if logged in
def search(user_credentials):
    user_credentials['username'] = user_credentials.get('email', '').split('@')[0]
    search_query = request.args.get('q');

    # Check if query contains '@' symbol for username search instead of name search
    if search_query[0] == '@':
        # Search by username
        search_query = search_query[1:];
        print(search_query);
        user = query_db('SELECT * FROM users WHERE username = ?', [search_query], one=True)

        return render_template('search/search_results.html', _self=user_credentials, users=[user] if user else [])
    else:
        # Search by name (matching partial names)
        users = query_db("SELECT * FROM users WHERE name LIKE ? OR username LIKE ?", [f'%{search_query}%', f'%{search_query}%'])
        
        return render_template('search/search_results.html', _self=user_credentials, users=users if users else [])

@app.route('/logout', methods=['GET'])
def logout():
    # Clear session data
    session.clear()
    return redirect(url_for('index'))


# === POST Requests ===

@app.route('/', methods=['POST'])
@middleware_authentication # Check if logged in
def index_post(user_credentials):
    sort_by = request.form.get('sort_by')

    # Redirect to the index page with the sorting preference as a query parameter
    return redirect(url_for('index', sort_by=sort_by))

@app.route('/create-post', methods=['POST'])
def create_post():
    if 'user' in session:
        user = session['user']
        user_id = user.get('oid')
        title = request.form.get('title')
        content = request.form.get('body')
        # Get the current date and format it
        created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Insert the post into the database
        query_db("INSERT INTO posts (title, body ,user_id, created_at) VALUES (?, ?, ?, ?)", [title, content, user_id, created_at], False, True)

        return redirect(url_for('index'))

@app.route('/post/<int:post_id>/create-comment', methods=['POST'])
def create_comment(post_id):
    if 'user' in session:
        user = session['user']
        user_id = user.get('oid')
        title = request.form.get('title')
        content = request.form.get('body')
        # Get the current date and format it
        created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Insert the post into the database
        query_db("INSERT INTO comments (title, body, user_id, post_id, created_at) VALUES (?, ?, ?, ?, ?)", [title, content, user_id, post_id, created_at], False, True)
        # Return JSON response indicating success
        return jsonify(success=True)
    else:
        # Handle case where user is not logged in
        return jsonify(success=False, error='User not logged in')


@app.route('/likepost/<int:post_id>/<action>', methods=['POST'])
@middleware_authentication
def like_post(post_id, action, user_credentials):
    user_id = user_credentials.get('oid')
    success = False
    
    # Check if the user has already liked the post
    existing_like = query_db("SELECT * FROM likes WHERE post_id = ? AND user_id = ?", [post_id, user_id], one=True)

    if existing_like and action == 'like':
        # User has already liked the post, prevent re-liking
        success = False
    else:
        if action == 'like':
            # Insert a new row into the likes table
            query_db("INSERT INTO likes (post_id, user_id) VALUES (?, ?)", [post_id, user_id], False, True)
            success = True
        elif action == 'unlike':
            # Delete the row from the likes table
            query_db("DELETE FROM likes WHERE post_id = ? AND user_id = ?", [post_id, user_id], False, True)
            success = True

    return jsonify(success=success)

@app.route('/likecomment/<int:comment_id>/<action>', methods=['POST'])
@middleware_authentication
def like_comment(comment_id, action, user_credentials):
    user_id = user_credentials.get('oid')
    success = False
    
    # Check if the user has already liked the post
    existing_like = query_db("SELECT * FROM likes WHERE comment_id = ? AND user_id = ?", [comment_id, user_id], one=True)

    if existing_like and action == 'like':
        # User has already liked the post, prevent re-liking
        success = False
    else:
        if action == 'like':
            # Insert a new row into the likes table
            query_db("INSERT INTO likes (comment_id, user_id) VALUES (?, ?)", [comment_id, user_id], False, True)
            success = True
        elif action == 'unlike':
            # Delete the row from the likes table
            query_db("DELETE FROM likes WHERE comment_id = ? AND user_id = ?", [comment_id, user_id], False, True)
            success = True

    return jsonify(success=success)

@app.route('/delete-post/<int:post_id>', methods=['POST'])
@middleware_authentication
def delete_post(post_id, user_credentials):
    user_id = user_credentials.get('oid')
    success = False

    existing_post = query_db("SELECT * FROM posts WHERE post_id = ? AND user_id = ?", [post_id, user_id], one=True)

    if existing_post:
        try:
            # Due to enabled ON DELETE CASCADING on the likes and comments related to this post_id, everything will be deleted correctly when deleting the post itself
            query_db("DELETE FROM posts WHERE post_id = ?", [post_id], False, True)
            success = True
        except Exception as e:
            print("An error occurred while deleting the post and associated data:", e)

    return jsonify(success=success)

# === USER DEFINED FUNCTIONS ===
def fetch_posts(self_id, sort_by=None, limit=10, post_id=None, user_id=None):
    query = '''
        SELECT p.*, u.name, u.username, 
               COUNT(DISTINCT l.like_id) as like_count, 
               COUNT(DISTINCT c.comment_id) as comment_count,
               CASE WHEN EXISTS (SELECT 1 FROM likes WHERE post_id = p.post_id AND user_id = ?) THEN 1 ELSE 0 END as is_liked
        FROM posts p
        JOIN users u ON p.user_id = u.user_id
        LEFT JOIN likes l ON p.post_id = l.post_id
        LEFT JOIN comments c ON p.post_id = c.post_id
    '''
    params = [self_id] if self_id else []

    # Add WHERE clause if post_id is provided
    if post_id is not None:
        query += ' WHERE p.post_id = ?'
        params.append(post_id)
    if user_id is not None:
        query += ' WHERE u.user_id = ?'
        params.append(user_id)

    query += ' GROUP BY p.post_id, u.user_id'

    # Fetch data from the database based on the sort_by parameter
    if sort_by == 'recent':
        query += ' ORDER BY p.created_at DESC'
    elif sort_by == 'likes':
        query += ' ORDER BY like_count DESC'
    else:
        pass  # Default sorting

    # Add LIMIT clause
    if limit == 1:
        query += ' LIMIT 1'
        result = query_db(query, params, one=True)
    else:
        query += ' LIMIT ?'
        params.append(limit)
        result = query_db(query, params)

    return result





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