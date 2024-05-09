from flask import Flask, render_template, request, abort, jsonify, send_from_directory
from database import query_db, init_db

import random
import bcrypt

app = Flask(__name__, template_folder='web/templates')
init_db(app)


# GET REQUESTS
@app.route('/', methods=['GET'])
def hello_world():
    return send_from_directory('web/static', "index.html")

@app.route('/users', methods=['GET'])
def get_users():
    return render_template('users/users.html', users=query_db('SELECT * FROM users'))

@app.route('/user/<username>', methods=['GET'])
def get_user(username):
    user = query_db('SELECT * FROM users WHERE username = ?', [username], one=True)
    if user is None:
        return "No such user"

    return username + ', age ' + str(user['age'])









# POST REQUESTS
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


# This will handle all 404 errors
@app.errorhandler(404)
def page_not_found(error):
    print(error);
    return render_template('error/error.html', title='404 - Page not found.', code=404, message=error), 404





# Helper functions
def generate_random_user():
    # List of random names
    names = ['Alice', 'Bob', 'Charlie', 'David', 'Emma', 'Frank', 'Grace', 'Henry', 'Ivy', 'Jack']
    
    # Generate random username, password, and age
    name = random.choice(names)
    username = name[0].lower() + name[-1].lower() + str(random.randint(100, 999))
    password = ''.join(random.choices('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=8))
    age = random.randint(18, 54)
    
    return username, password, name, age





# Route to serve the static HTML file
@app.route('/<path:filename>', methods=['GET'])
def serve_static_html(filename):
    return send_from_directory('web/static', filename + ".html")

# Route to serve CSS files
@app.route('/css/<path:filename>')
def serve_css(filename):
    return send_from_directory('web/css', filename)





# Start app
if __name__ == '__main__':
    app.run(debug=True, port=8080)
