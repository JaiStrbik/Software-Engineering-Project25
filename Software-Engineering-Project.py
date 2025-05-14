from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import check_password_hash
import re
from datetime import datetime
from setup_db import User, Messages, engine, db_session
from query_db import add_user, get_user, get_user_by_id
from openai import OpenAI
import os
from dotenv import load_dotenv
from difflib import get_close_matches
load_dotenv()

# Initialize Flask application
app = Flask(__name__, template_folder='Templates')
app.secret_key = 'your_secret_key'  # Replace in production

# Helper functions for message categorization and behavior matching
def categorize_message(subcategory):
    positive_subcategories = ["Affirmation", "Merit", "Merit/Record of Achievement"]
    negative_subcategories = ["Informal Conversation", "Challenge", "White Card", "Friday Detention"]

    if subcategory in positive_subcategories:
        return "positive"
    elif subcategory in negative_subcategories:
        return "negative"
    else:
        return "negative"  # default to negative if uncertain

# Define behavior guide dictionary
BEHAVIOR_GUIDE = {
    "White Card": [
        "Repeated disrespect toward staff member",
        "Repeated organisational issues",
        "Repeated low level misconduct",
        "Inappropriate classroom behaviour - disrupting the learning of students",
        "Significant disruption to the learning of others",
        "Disrespectful &/or offensive behaviour towards peers",
        "Challenging a teacher",
        "Chewing gum",
        "Swearing",
        "Breaking phone policy",
        "Making a purchase from a vending machine on or after the bell",
        "Disruptive during College assembly/Mass",
        "Irresponsible use of technology"
    ],
    "Challenge": [
        "Disrespectful toward staff member",
        "Late to class",
        "Shift untucked after verbal warning",
        "Entering a room without permission",
        "Rowdy classroom entry after being asked to settle",
        "Eating or drinking in the classroom without permission",
        "No equipment",
        "Talking over the teacher",
        "Talking over other students",
        "Distracting others from learning",
        "No attempt of set task",
        "Interfering with another student's belongings"
    ],
    "Affirmation": [
        "Going the extra mile",
        "Cleaning up the classroom without being asked",
        "Volunteers for prayer at the beginning/end of class",
        "Assisting a peer without being asked",
        "Assisting a teacher without being asked",
        "Impressive behaviour in public",
        "Picking up rubbish without being asked",
        "Sustained effort over a month",
        "Outstanding result in an assessment",
        "Positive use of character strengths",
        "Being an upstander to inappropriate behaviour"
    ],
    "Friday Detention": [
        "Defiance",
        "Truancy",
        "Leaving the classroom without permission",
        "Ongoing disrespect after White Card has been issued",
        "Breaking hands-off rule",
        "Damage to classroom or belongings due to reckless behaviour"
    ],
    "Merit / Record of Achievement": [
        "Sustained effort over a month",
        "Fulfils the basic expectation of an Augustinian student",
        "Outstanding result in an assessment task",
        "Positive use of character strengths",
        "Being an upstander by challenging inappropriate behaviour towards peers and/or teacher"
    ]
}

def find_closest_behavior(user_input, subcategory):
    behaviors = BEHAVIOR_GUIDE.get(subcategory, [])
    matches = get_close_matches(user_input, behaviors, n=1, cutoff=0.4)
    return matches[0] if matches else "general behavior issue"

# OpenAI client initialization with API key from environment variable
api_key = os.getenv("OPENAI_API_KEY")
# If no environment variable, use the hardcoded key (not recommended for production)
if not api_key:
    api_key = "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"
client = OpenAI(api_key=api_key)

def generate_ai_message(behavior, subcategory):
    prompt = f"Write a professional, concise pastoral care message for a student based on the following behavior: '{behavior}'. The incident is categorized as '{subcategory}'."
    
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a pastoral assistant that creates professional and compassionate messages."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=150,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"OpenAI error: {e}")
        return "Unable to generate message at this time."

# Define the standardize_message_with_openai function
def standardize_message_with_openai(message_text, category):
    try:
        if category == "positive":
            prompt = f"Transform this message into a standardized positive pastoral message: '{message_text}'"
        else:
            prompt = f"Transform this message into a standardized pastoral message that addresses concerns: '{message_text}'"

        response = client.chat.completions.create(
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
        return "The message could not be processed at this time."

# Route for the standardize_message API endpoint
@app.route('/standardize_message', methods=["POST"])
def standardize_message_api():
    print("Request received at standardize_message endpoint")
    print("Form data:", request.form)
    
    # Try to get message from form data
    message_text = request.form.get('name')
    category = request.form.get('category')
    
    print(f"message_text: {message_text}")
    print(f"category: {category}")

    if not message_text or not category:
        print("Error: Missing message or category")
        return jsonify({"error": "Missing message or category"}), 400

    standardized_message = standardize_message_with_openai(message_text, category)
    print(f"Generated standardized_message: {standardized_message}")
    return jsonify({"standardized_message": standardized_message})

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
    subcategory = request.form.get('subcategory')
    standardized_message = request.form.get('standardized_message')

    if not message_text or not subcategory:
        flash("Message and subcategory are required.", "error")
        return redirect(url_for('dashboard'))

    severity = categorize_message(subcategory)

    if not standardized_message:
        standardized_message = standardize_message_with_openai(message_text, severity)

    new_message = Messages(
        name=message_text,
        user_id=session['user_id'],
        severity=severity,
        standardized_message=standardized_message,
        subcategory=subcategory  # make sure your model has this
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



@app.teardown_appcontext
def shutdown_session(exception=None):
    db_session.remove()


@app.route('/generate_message', methods=['GET', 'POST'])
def generate_message():
    ai_message = ""
    if request.method == 'POST':
        user_input = request.form['message']
        subcategory = request.form['subcategory']
        behavior = find_closest_behavior(user_input, subcategory)
        ai_message = generate_ai_message(behavior, subcategory)
    return render_template('generate_message.html', ai_message=ai_message)


if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)