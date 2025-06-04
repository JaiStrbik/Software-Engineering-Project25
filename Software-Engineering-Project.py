from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import check_password_hash
import re
from datetime import datetime
import pytz
from setup_db import User, Messages, engine, db_session
from query_db import add_user, get_user, get_user_by_id
from openai import OpenAI
import os
from difflib import get_close_matches
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__, template_folder='Templates')
app.secret_key = os.getenv("FLASK_SECRET_KEY", "default_fallback_secret")

# Define a jinja filter for timezone conversion
@app.template_filter('aest_time')
def aest_time(utc_dt):
    """Convert UTC datetime to Australian Eastern Standard Time"""
    if utc_dt is None:
        return ""
    aest = pytz.timezone('Australia/Sydney')
    aest_dt = utc_dt.replace(tzinfo=pytz.UTC).astimezone(aest)
    return aest_dt.strftime('%B %d, %Y at %I:%M %p')

client = OpenAI()

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
    ],
    "Informal Conversation": [
        "Low level issues where a conversation reminds the student of College expectations and resets behaviour"
    ]

 
}

def clean_teacher_input(text):
    return re.sub(r'[^\w\s]', '', text).lower().strip()

def categorize_message(subcategory=None, category=None):
    if category and category in ["positive", "negative"]:
        return category
    positive_subcategories = ["Affirmation", "Merit", "Merit/Record of Achievement"]
    negative_subcategories = ["Informal Conversation", "Challenge", "White Card", "Friday Detention"]
    if subcategory in positive_subcategories:
        return "positive"
    elif subcategory in negative_subcategories:
        return "negative"
    else:
        return "negative"

def get_severity_level(subcategory):
    if subcategory in ["Friday Detention"]:
        return "extremely serious"
    elif subcategory in {"White Card"}:
        return "serious"
    elif subcategory in {"Challenge"}:
        return "moderate"
    elif subcategory in {"Informal Conversation"}:
        return "low level"
    else:
        return "positive"

def find_closest_behavior(user_input, subcategory):
    behaviors = BEHAVIOR_GUIDE.get(subcategory, [])
    cleaned_input = clean_teacher_input(user_input)
    
    # Try to get the closest match from the subcategory with a very low cutoff
    matches = get_close_matches(cleaned_input, behaviors, n=1, cutoff=0.01)
    
    if matches:
        return matches[0]
    
    # If no match and the subcategory has behaviors, return the first one
    if behaviors:
        return behaviors[0]
    
    # As a last resort, return the first behavior from any non-empty category
    for category_behaviors in BEHAVIOR_GUIDE.values():
        if category_behaviors:
            return category_behaviors[0]
    
    # Fallback if somehow everything is empty (shouldn't happen)
    return "Inappropriate classroom behaviour"

def generate_ai_message(behavior, subcategory):
    if os.getenv("OPENAI_API_KEY") is None:
        return "AI message generation is currently unavailable. Please check API settings."

    severity = get_severity_level(subcategory)

    prompt = (
    f"You are a teacher writing a professional, concise pastoral care message for a student based on the behavior: '{behavior}'. "
    f"This incident is categorized under '{subcategory}', which is considered a {severity} concern. "
    f"Do not use slang or casual phrases. Avoid terms like 'clowning around' or 'messing about'. "
    f"Use the exact behavior phrase '{behavior}' from the College behavior guide. Keep the message neutral, clear, and 2–3 sentences long. "
    f"Tone:\n"
    f"- Positive: warm and encouraging.\n"
    f"- Moderate: constructive but firm.\n"
    f"- Serious: clear, professional, and direct."
    )

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a professional school communication assistant."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=150,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"OpenAI error: {e}")
        return "Unable to generate message at this time."

@app.route('/standardize_message', methods=["POST"])
def standardize_message_api():
    message_text = request.form.get('name')
    category = request.form.get('category', 'negative')
    subcategory = request.form.get('subcategory')  # Add this line to capture subcategory
    
    if not message_text:
        return jsonify({"error": "Missing message text"}), 400

    try:
        # Pass subcategory to the function
        standardized_message = standardize_message_with_openai(message_text, category, subcategory)
        return jsonify({"standardized_message": standardized_message})
    except Exception as e:
        return jsonify({"error": str(e), "standardized_message": "An error occurred processing your message."}), 500


def standardize_message_with_openai(message_text, category, subcategory=None):
    if os.getenv("OPENAI_API_KEY") is None:
        return "AI message standardization is currently unavailable. Please check API settings."

    # Step 1: Clean the input
    cleaned_input = clean_teacher_input(message_text)
    
    # Step 2: Ensure category is correctly identified based on subcategory
    if category is None or category == "":
        category = categorize_message(subcategory)
    
    # Step 3: Get valid behaviors for the subcategory
    subcategory_behaviors = BEHAVIOR_GUIDE.get(subcategory, [])
    
    # Step 4: Find closest match from behavior guide - only for the correct category type
    matched_behavior = find_closest_behavior(cleaned_input, subcategory)
    
    # Get severity level for more specific prompting
    severity_level = get_severity_level(subcategory)
    
    # Step 5: Construct prompt
    system_prompt = (
        "You are a pastoral care assistant writing professional, concise school messages to parents. "
        "Your message must include: "
        "1. A clear statement of the specific positive behavior using formal language "
        "2. Why this behavior is beneficial for the classroom environment "
        "3. A brief encouragement to continue this positive behavior "
        "4. A brief indication that you as the teacher remains committed to supporting the student's growth "
        "Messages should be formal, respectful, and 2-3 sentences."
    ) if category == "positive" else (
        "You are a pastoral care assistant writing professional, concise school messages to parents. "
        "Your message must include: "
        "1. A clear statement of the specific behavior concern using formal language "
        "2. Why this behavior is problematic for the classroom environment "
        "3. A brief constructive suggestion for improvement "
        "4. A brief indication that you as the teacher remains committed to supporting the student's growth "
        "Messages should be formal, respectful, and 2-3 sentences."
    )

    tone_instruction = (
        "Write it warmly and encouragingly. This is positive feedback about excellent student behavior." if category == "positive"
        else f"Write it with a calm, firm, professional tone. This is a {severity_level} behavioral concern."
    )

    # Modify prompt based on category
    if category == "positive":
        user_prompt = (
            f"Teacher input: '{message_text}'\n"
            f"Subcategory: {subcategory}\n"
            f"Matched positive behavior from guide: '{matched_behavior}'\n\n"
            f"{tone_instruction} You must reference the specific positive behavior '{matched_behavior}' and include encouraging feedback. "
            f"End with a brief indication that you, as the teacher, remain committed to supporting the student's continued growth. "
            "Keep it professional and concise (2-3 sentences)."
        )
    else:
        user_prompt = (
            f"Teacher input: '{message_text}'\n"
            f"Subcategory: {subcategory}\n"
            f"Severity level: {severity_level}\n"
            f"Matched behavior from guide: '{matched_behavior}'\n\n"
            f"{tone_instruction} You must reference the specific behavior '{matched_behavior}' and include constructive feedback. "
            f"End with a brief indication that you, as the teacher, remain committed to supporting the student's growth. "
            "Keep it professional and concise (2-3 sentences)."
        )

    # Step 6: Generate AI message
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=150,
            temperature=0.6
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"OpenAI error during standardization: {e}")
        return "An error occurred while processing the message."




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
    
    # Get filter parameter
    filter_type = request.args.get('filter', None)
    
    positive_messages = db_session.query(Messages).filter_by(user_id=session['user_id'], severity="positive").all()
    negative_messages = db_session.query(Messages).filter_by(user_id=session['user_id'], severity="negative").all()
    
    if filter_type == 'positive':
        messages = positive_messages
    elif filter_type == 'negative':
        messages = negative_messages
    else:
        messages = positive_messages + negative_messages

    return render_template('dashboard.html',
                           username=session.get('username', 'User'),
                           positive_messages=positive_messages,
                           negative_messages=negative_messages,
                           messages=messages,
                           active_filter=filter_type,
                           pastoral_message="Enter pastoral message here")

@app.route('/create_message', methods=["POST"])
def create_message():
    if 'user_id' not in session:
        flash("You need to log in to create a message.", "error")
        return redirect(url_for('login'))

    message_text = request.form.get('name')
    subcategory = request.form.get('subcategory')
    category = request.form.get('category')
    standardized_message = request.form.get('standardized_message')

    if not message_text or not subcategory:
        flash("Message and subcategory are required.", "error")
        return redirect(url_for('dashboard'))

    severity = categorize_message(subcategory, category)

    if not standardized_message:
        standardized_message = standardize_message_with_openai(message_text, severity)

    new_message = Messages(
        name=message_text,
        user_id=session['user_id'],
        severity=severity,
        standardized_message=standardized_message,
        subcategory=subcategory
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

    # Add a print statement for debugging
    print(f"Deleting message {message_id} for user {session['user_id']}")
    
    db_session.delete(message)
    db_session.commit()

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




