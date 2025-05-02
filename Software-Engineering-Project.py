from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import check_password_hash
import re
from query_db import add_user, get_user

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Required for session and flash messages

@app.route('/')
def title_page():
    return render_template('title_page.html')

@app.route('/login', methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        username = request.form.get('username')
        password = request.form.get('password')

        # Query user from the database
        user = get_user(username)

        if user and check_password_hash(user[2], password):  # user[2] is the hashed password
            session['user_id'] = user[0]  # user[0] is the user ID
            flash("Login successful!", "info")
            return redirect(url_for('title_page'))
        else:
            flash("Invalid username or password", "error")
    
    return render_template('login_page.html')

@app.route('/signup', methods=["GET", "POST"])
def signup_page():
    if request.method == "POST":
        username = request.form.get('username')
        password = request.form.get('password')

        # Validate password requirements
        if not (re.search(r'[A-Za-z]', password) and  # At least one letter
                re.search(r'[0-9]', password) and      # At least one number
                re.search(r'[!@#$%^&*(),.?":{}|<>]', password)):  # At least one symbol
            flash("Password must contain at least one letter, one number, and one symbol", "error")
            return redirect(url_for('signup_page'))

        # Add user to the database
        try:
            add_user(username, password)
            flash("Account created successfully!", "info")
            return redirect(url_for('login_page'))
        except Exception as e:
            flash(str(e), "error")
    
    return render_template('signup_page.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash("You need to log in to access the dashboard.", "error")
        return redirect(url_for('login_page'))
    return render_template('dashboard.html')

if __name__ == "__main__":
    app.run(debug=True)





