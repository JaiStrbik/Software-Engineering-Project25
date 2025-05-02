from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import check_password_hash
import re
from datetime import datetime
from setup_db import User, Messages, engine, db_session
from query_db import add_user, get_user, get_user_by_id

app = Flask(__name__, template_folder='Templates')
app.secret_key = 'your_secret_key'  # Required for session and flash messages

@app.route('/')
def title_page():
    return render_template('title.html')

@app.route('/login', methods=["GET", "POST"])  
def login():
    if request.method == "POST":
        username = request.form.get('username')
        password = request.form.get('password')

        # Query user from the database
        user = get_user(username)

        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['joined_date'] = datetime.now().strftime("%Y-%m-%d")
            flash("Login successful! Welcome back, " + username, "success")
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid username or password", "error")
    
    return render_template('login.html')

@app.route('/signup', methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get('username')
        password = request.form.get('password')

        # Validate password requirements
        if not (re.search(r'[A-Za-z]', password) and  # At least one letter
                re.search(r'[0-9]', password) and      # At least one number
                re.search(r'[!@#$%^&*(),.?":{}|<>]', password)):  # At least one symbol
            flash("Password must contain at least one letter, one number, and one symbol", "error")
            return redirect(url_for('signup'))

        # Add user to the database
        try:
            add_user(username, password)
            flash("Account created successfully! Please log in.", "success")
            return redirect(url_for('login'))
        except Exception as e:
            if "UNIQUE constraint failed" in str(e):
                flash("Username already exists. Please choose another username.", "error")
            else:
                flash(str(e), "error")
            return redirect(url_for('signup'))
    
    return render_template('signup.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash("You need to log in to access the dashboard.", "error")
        return redirect(url_for('login'))
    
    # Get user info and messages
    user = get_user_by_id(session['user_id'])
    
    # Calculate days as member (mock data for now)
    days_member = 30
    
    # Format messages with timestamp
    messages = db_session.query(Messages).filter_by(user_id=session['user_id']).all()
    for message in messages:
        message.created_at = datetime.now()  # Mock timestamp
    
    return render_template('dashboard.html', 
                           username=session.get('username', 'User'),
                           days_member=days_member,
                           messages=messages)

@app.route('/create_message', methods=["POST"])
def create_message():
    if 'user_id' not in session:
        flash("You need to log in to create a message.", "error")
        return redirect(url_for('login'))
    
    message_text = request.form.get('name')
    
    if not message_text or len(message_text) < 1:
        flash("Message cannot be empty.", "error")
        return redirect(url_for('dashboard'))
    
    # Create new message
    new_message = Messages(name=message_text, user_id=session['user_id'])
    db_session.add(new_message)
    db_session.commit()
    
    flash("Message posted successfully!", "success")
    return redirect(url_for('dashboard'))

@app.route('/delete_message/<int:message_id>', methods=["POST"])
def delete_message(message_id):
    if 'user_id' not in session:
        flash("You need to log in to delete a message.", "error")
        return redirect(url_for('login'))
    
    # Get message and verify ownership
    message = db_session.query(Messages).filter_by(id=message_id, user_id=session['user_id']).first()
    
    if not message:
        flash("Message not found or you don't have permission to delete it.", "error")
        return redirect(url_for('dashboard'))
    
    # Delete message
    db_session.delete(message)
    db_session.commit()
    
    flash("Message deleted successfully!", "success")
    return redirect(url_for('dashboard'))

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out successfully.", "success")
    return redirect(url_for('title_page'))

@app.teardown_appcontext
def shutdown_session(exception=None):
    db_session.remove()

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)





