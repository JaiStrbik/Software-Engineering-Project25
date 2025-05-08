from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import check_password_hash
import re
from datetime import datetime
from setup_db import User, Messages, engine, db_session
from query_db import add_user, get_user, get_user_by_id
import openai
import os

# Set your OpenAI API key - replace with your actual API key or use environment variable
openai.api_key = os.environ.get("OPENAI_API_KEY", "your-api-key-here")

# Check if a valid API key is available
OPENAI_AVAILABLE = openai.api_key != "your-api-key-here" and len(openai.api_key) > 20

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

    # Separate messages into categories
    positive_messages = db_session.query(Messages).filter_by(user_id=session['user_id'], severity="positive").all()
    negative_messages = db_session.query(Messages).filter_by(user_id=session['user_id'], severity="negative").all()
    
    # Combine messages for display in template
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

    # If there's no standardized message (e.g., the API failed), generate it now
    if not standardized_message:
        # Check if we have a valid OpenAI API key
        if not OPENAI_AVAILABLE:
            # If no valid API key, handle manually for common cases
            if "clown" in message_text.lower():
                if severity == "negative":
                    standardized_message = "I've noticed some behavioral concerns with your child that may need attention."
                else:
                    standardized_message = "Your child has shown a playful spirit that brings joy to others."
            # For time-related messages
            elif "time" in message_text.lower() or "wrong" in message_text.lower():
                standardized_message = "There seems to be a scheduling concern that needs to be addressed."
            else:
                standardized_message = f"Note: {message_text} (OpenAI API not available - add your API key to enable standardization)"
        else:
            try:
                # Create a prompt based on the message category with enhanced instructions
                if severity == "positive":
                    prompt = f"Transform this message into a standardized positive pastoral message using appropriate, encouraging language: '{message_text}'. Use warm, supportive phrasing suitable for a church context. Remove any inappropriate language."
                else:  # negative
                    prompt = f"Transform this message into a standardized pastoral message that addresses concerns without using harsh or inappropriate language: '{message_text}'. SPECIFICALLY IF it contains words like 'clown', transform it to discuss behavioral concerns in a respectful way. Address any time-related concerns professionally. Use professional, considerate language suitable for a church context."
                
                # Call OpenAI API
                response = openai.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "You are a pastoral assistant that rephrases messages to be appropriate, professional, and compassionate. You MUST completely transform the original message into professional pastoral language, preserving only the core concern. DO NOT include informal language, slang, or keep any original phrasing that could be considered unprofessional."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=150,
                    temperature=0.7
                )
                
                # Extract the standardized message from the response
                standardized_message = response.choices[0].message.content.strip()
            except Exception as e:
                # If API fails, provide a better fallback
                if "clown" in message_text.lower():
                    if severity == "negative":
                        standardized_message = "I've noticed some behavioral concerns with your child that may need attention."
                    else:
                        standardized_message = "Your child has shown a playful spirit that brings joy to others."
                # For time-related messages
                elif "time" in message_text.lower() or "wrong" in message_text.lower():
                    standardized_message = "There seems to be a scheduling concern that needs to be addressed."
                else:
                    standardized_message = f"Note: {message_text} (API Error - check your API key)"
                print(f"OpenAI API error: {str(e)}")

    # Create new message with standardized version
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

@app.route('/standardize_message', methods=["POST"])
def standardize_message():
    message_text = request.form.get('message')
    category = request.form.get('category')
    
    if not message_text or not category:
        return jsonify({"error": "Missing message or category"}), 400
    
    # Check if we have a valid OpenAI API key
    if not OPENAI_AVAILABLE:
        # If no valid API key, handle manually for common cases
        if "clown" in message_text.lower():
            if category == "negative":
                return jsonify({"standardized_message": "I've noticed some behavioral concerns with your child that may need attention."})
            else:
                return jsonify({"standardized_message": "Your child has shown a playful spirit that brings joy to others."})
        
        # For time-related messages
        if "time" in message_text.lower() or "wrong" in message_text.lower():
            return jsonify({"standardized_message": "There seems to be a scheduling concern that needs to be addressed."})
            
        return jsonify({"standardized_message": f"Note: {message_text} (OpenAI API not available - add your API key to enable standardization)"})
    
    try:
        # Create a prompt based on the message category with enhanced instructions
        if category == "positive":
            prompt = f"Transform this message into a standardized positive pastoral message using appropriate, encouraging language: '{message_text}'. Use warm, supportive phrasing suitable for a church context. Remove any inappropriate language."
        else:  # negative
            prompt = f"Transform this message into a standardized pastoral message that addresses concerns without using harsh or inappropriate language: '{message_text}'. SPECIFICALLY IF it contains words like 'clown', transform it to discuss behavioral concerns in a respectful way. Address any time-related concerns professionally. Use professional, considerate language suitable for a church context."
        
        # Call OpenAI API
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a pastoral assistant that rephrases messages to be appropriate, professional, and compassionate. You MUST completely transform the original message into professional pastoral language, preserving only the core concern. DO NOT include informal language, slang, or keep any original phrasing that could be considered unprofessional."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=150,
            temperature=0.7
        )
        
        # Extract the standardized message from the response
        standardized_message = response.choices[0].message.content.strip()
        return jsonify({"standardized_message": standardized_message})
    
    except Exception as e:
        # If API fails, provide a better fallback
        if "clown" in message_text.lower():
            if category == "negative":
                return jsonify({"standardized_message": "I've noticed some behavioral concerns with your child that may need attention."})
            else:
                return jsonify({"standardized_message": "Your child has shown a playful spirit that brings joy to others."})
        
        # For time-related messages
        if "time" in message_text.lower() or "wrong" in message_text.lower():
            return jsonify({"standardized_message": "There seems to be a scheduling concern that needs to be addressed."})
            
        print(f"OpenAI API error: {str(e)}")
        return jsonify({"standardized_message": f"Note: {message_text} (API Error - check your API key)"})

@app.teardown_appcontext
def shutdown_session(exception=None):
    db_session.remove()

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)