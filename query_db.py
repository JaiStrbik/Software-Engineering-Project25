from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from werkzeug.security import generate_password_hash
from setup_db import User

# Connect to the database
engine = create_engine('sqlite:///messages.db')
Session = sessionmaker(bind=engine)
session = Session()

# Function to add a user to the database
def add_user(username, password):
    hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
    new_user = User(username=username, password=hashed_password)
    session.add(new_user)
    session.commit()

# Function to get a user from the database by username
def get_user(username):
    return session.query(User).filter_by(username=username).first()

# Function to get a user from the database by ID
def get_user_by_id(user_id):
    return session.query(User).filter_by(id=user_id).first()