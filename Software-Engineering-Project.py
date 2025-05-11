from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import check_password_hash
import re
from datetime import datetime
from setup_db import User, Messages, engine, db_session
from query_db import add_user, get_user, get_user_by_id
import openai
import os
from dotenv import load_dotenv  # ✅ Load environment variables

# Load .env variables
load_dotenv()

# Configure OpenAI key from .env
openai.api_key = os.getenv("OPENAI_API_KEY")

# Flag for OpenAI availability
OPENAI_AVAILABLE = True

# Test OpenAI connection on startup
try:
    response = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "system", "content": "Connection test"}],
        max_tokens=5,
        temperature=0.5
    )
    print("✅ OpenAI API connected successfully.")
except Exception as e:
    print(f"⚠️ Warning: OpenAI API initialization error: {e}")
    OPENAI_AVAILABLE = False

DEFAULT_FALLBACK = "The message could not be processed at this time."

app = Flask(__name__, template_folder='Templates')
app.secret_key = 'your_secret_key'  # Replace in production


@app.route('/')
def title_page():
    return render_template('title.html')


@app.route('/login', methods=["GET", "POST"])  
def login():
    if request.method == "POST":
        username = request.form.get('username')
        password = request.form.get('password')

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

        if not (re.search(r'[A-Za-z]', password) and re.search(r'[0-9]', password) and re.search(r'[!@#$%^&*(),.?":{}|<>]', password)):
            flash("Password must contain at least one letter, one number, and one symbol", "error")
            return redirect(url_for('signup'))

        try:
            add_user(username, password)
            flash("Account created successfully! Please log in.", "success")
            return redirect(url_for('login'))
        except Exception as e:
            if "UNIQUE constraint failed" in str(e):
                flash("Username already exists. Please choose another username.", "error")
            else:
                flash(str(e), "error")
    
    return render_template('signup.html')


@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash("You need to log in to access the dashboard.", "error")
        return redirect(url_for('login'))

    user = get_user_by_id(session['user_id'])

    positive_messages = db_session.query(Messages).filter_by(user_id=session['user_id'], severity="positive").all()
    negative_messages = db_session.query(Messages).filter_by(user_id=session['user_id'], severity="negative").all()
    messages = positive_messages + negative_messages

    return render_template('dashboard.html',
                           username=session.get('username', 'User'),
                           positive_messages=positive_messages,
                           negative_messages=negative_messages,
                           messages=messages,
                           pastoral_message="Enter pastoral message here")


@app.route('/create_message', methods=["POST"])
def create_message():
    if 'user_id' not in session:
        flash("You need to log in to create a message.", "error")
        return redirect(url_for('login'))

    message_text = request.form.get('name')
    severity = request.form.get('severity')
    standardized_message = request.form.get('standardized_message')

    if not message_text or len(message_text) < 1:
        flash("Message cannot be empty.", "error")
        return redirect(url_for('dashboard'))

    if severity not in ["positive", "negative"]:
        flash("Invalid severity selected.", "error")
        return redirect(url_for('dashboard'))

    if not standardized_message:
        standardized_message = standardize_message_with_openai(message_text, severity)

    new_message = Messages(
        name=message_text,
        user_id=session['user_id'],
        severity=severity,
        standardized_message=standardized_message
    )
    db_session.add(new_message)
    db_session.commit()

    flash("Message posted successfully!", "success")
    return redirect(url_for('dashboard'))


@app.route('/delete_message/<int:message_id>', methods=["POST"])
def delete_message(message_id):
    if 'user_id' not in session:
        flash("You need to log in to delete a message.", "error")
        return redirect(url_for('login'))

    message = db_session.query(Messages).filter_by(id=message_id, user_id=session['user_id']).first()

    if not message:
        flash("Message not found or you don't have permission to delete it.", "error")
        return redirect(url_for('dashboard'))

    db_session.delete(message)
    db_session.commit()

    flash("Message deleted successfully!", "success")
    return redirect(url_for('dashboard'))


@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out successfully.", "success")
    return redirect(url_for('title_page'))


@app.route('/standardize_message', methods=["POST"])
def standardize_message_api():
    message_text = request.form.get('message')
    category = request.form.get('category')

    if not message_text or not category:
        return jsonify({"error": "Missing message or category"}), 400

    standardized_message = standardize_message_with_openai(message_text, category)
    return jsonify({"standardized_message": standardized_message})


def standardize_message_with_openai(message_text, category):
    if OPENAI_AVAILABLE:
        try:
            if category == "positive":
                prompt = f"Transform this message into a standardized positive pastoral message: '{message_text}'"
            else:
                prompt = f"Transform this message into a standardized pastoral message that addresses concerns: '{message_text}'"

            response = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a pastoral assistant that rephrases messages to be professional and compassionate."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=150,
                temperature=0.7
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"OpenAI error: {e}")

    return local_standardize_message(message_text, category)


def local_standardize_message(message_text, category):
    if category == "positive":
        return "I'd like to highlight a positive development we've recently observed and appreciate the progress."
    else:
        return "There are a few concerns that may be worth discussing to support improvement."


@app.teardown_appcontext
def shutdown_session(exception=None):
    db_session.remove()


if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)

