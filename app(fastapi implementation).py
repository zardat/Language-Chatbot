import os
import sqlite3
import bcrypt
from flask import Flask, request, jsonify, session as flask_session, redirect, url_for
from flask import render_template  # if you want to use templates
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain.memory import ConversationBufferMemory
# from langchain.chat_models import ChatOpenAI
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, AIMessage

# ---------------------- Configuration ----------------------
# Set your OpenAI API key here.
os.environ["OPENAI_API_KEY"] = "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"

# Initialize Flask
app = Flask(__name__)
app.secret_key = "your_secret_key_here"  # Replace with a secure key in production

# ---------------------- Database Functions ----------------------
def create_tables():
    conn = sqlite3.connect("chatbot.db")
    cursor = conn.cursor()
    # Users table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL
    )""")
    # Sessions table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        learning_language TEXT NOT NULL,
        known_language TEXT NOT NULL,
        proficiency_level TEXT NOT NULL,
        current_module TEXT DEFAULT 'Module 1',
        current_submodule TEXT DEFAULT 'Submodule 1',
        start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )""")
    # Conversations table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        session_id INTEGER,
        user_response TEXT NOT NULL,
        tutor_response TEXT NOT NULL,
        performance_score INTEGER DEFAULT 0,
        next_submodule_or_review TEXT DEFAULT '',
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (session_id) REFERENCES sessions(id)
    )""")
    # Mistakes table (with module/submodule info)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS mistakes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER,
        conversation_id INTEGER,
        module TEXT,
        submodule TEXT,
        error_type TEXT,
        incorrect_response TEXT,
        correct_response TEXT,
        FOREIGN KEY (session_id) REFERENCES sessions(id),
        FOREIGN KEY (conversation_id) REFERENCES conversations(id)
    )""")
    conn.commit()
    conn.close()

create_tables()

def signup_db(username: str, password: str):
    conn = sqlite3.connect("chatbot.db")
    cursor = conn.cursor()
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    try:
        cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_password))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return False
    conn.close()
    return True

def login_db(username: str, password: str):
    conn = sqlite3.connect("chatbot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, password FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()
    if user and bcrypt.checkpw(password.encode('utf-8'), user[1]):
        return user[0]
    return None

def get_user_session(user_id: int):
    conn = sqlite3.connect("chatbot.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, learning_language, known_language, proficiency_level, current_module, current_submodule
        FROM sessions WHERE user_id = ? ORDER BY start_time DESC LIMIT 1
    """, (user_id,))
    result = cursor.fetchone()
    conn.close()
    if result:
        return {
            "session_id": result[0],
            "learning_language": result[1],
            "known_language": result[2],
            "proficiency_level": result[3],
            "current_module": result[4],
            "current_submodule": result[5]
        }
    return None

def create_user_session_db(user_id: int, learning_language: str, known_language: str, proficiency_level: str):
    conn = sqlite3.connect("chatbot.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO sessions (user_id, learning_language, known_language, proficiency_level)
        VALUES (?, ?, ?, ?)
    """, (user_id, learning_language, known_language, proficiency_level))
    conn.commit()
    conn.close()

def save_conversation_db(user_id: int, session_id: int, user_response: str, tutor_response: str):
    conn = sqlite3.connect("chatbot.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO conversations (user_id, session_id, user_response, tutor_response)
        VALUES (?, ?, ?, ?)
    """, (user_id, session_id, user_response, tutor_response))
    conn.commit()
    conv_id = cursor.lastrowid
    conn.close()
    return conv_id

def save_mistake_db(session_id: int, conversation_id: int, error_type: str, incorrect: str, correct: str, module: str, submodule: str):
    conn = sqlite3.connect("chatbot.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO mistakes (session_id, conversation_id, module, submodule, error_type, incorrect_response, correct_response)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (session_id, conversation_id, module, submodule, error_type, incorrect, correct))
    conn.commit()
    conn.close()

def update_user_session_in_db(session_id: int, new_module: str, new_submodule: str):
    conn = sqlite3.connect("chatbot.db")
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE sessions 
        SET current_module = ?, current_submodule = ?
        WHERE id = ?
    """, (new_module, new_submodule, session_id))
    conn.commit()
    conn.close()

# ---------------------- AI Tutor Setup and Templates ----------------------
# Initialize our LLM and conversation memory
llm = ChatOpenAI(model_name="gpt-3.5-turbo", temperature=0.7)
memory = ConversationBufferMemory(return_messages=True, memory_key="chat_history", input_key="user_response")

# Define prompt templates (for teaching, testing, evaluation, and mistake summary)
teaching_template = PromptTemplate(
    input_variables=["learning_language", "current_module", "current_submodule", "chat_history"],
    template="""You are a language tutor teaching a student learning {learning_language}.

Current Lesson: **Module:** {current_module} → **Submodule:** {current_submodule}

**Teaching Phase:**  
Explain the concept clearly with examples and include written pronunciation guides.
For context, here is a summary of previous interactions:
{chat_history}

Please present the lesson without asking any questions.
"""
)

testing_template = PromptTemplate(
    input_variables=["learning_language", "current_module", "current_submodule", "chat_history"],
    template="""You are a language tutor helping a student learn {learning_language}.

Current Lesson: **Module:** {current_module} → **Submodule:** {current_submodule}

**Testing Phase:**  
Based on the lesson, ask a simple, direct text-based question that the student can answer using the provided information.
For context, here is a summary of the lesson so far:
{chat_history}

Please ask your question now.
"""
)

evaluation_template = PromptTemplate(
    input_variables=["learning_language", "current_module", "current_submodule", "user_response", "chat_history"],
    template="""You are a language tutor evaluating a student's written answer in {learning_language}.

Current Lesson: **Module:** {current_module} → **Submodule:** {current_submodule}

**User Response:** {user_response}

**Evaluation Phase:**  
If the answer is correct, include "Great job" in your feedback.
If incorrect, specify the error (e.g., pronunciation, vocabulary, grammar) and provide the correct answer.
For context, here is a summary of previous interactions:
{chat_history}

Please provide your evaluation.
"""
)

mistake_summary_template = PromptTemplate(
    input_variables=["learning_language", "current_module", "current_submodule", "mistakes_text"],
    template="""You are a language tutor reviewing common mistakes made in this submodule while teaching {learning_language}.

Current Lesson: **Module:** {current_module} → **Submodule:** {current_submodule}

The following mistakes were observed:
{mistakes_text}

**Revision Phase:**  
Provide a concise summary of these mistakes with revision tips to help the student improve.
"""
)

teaching_response_func = teaching_template | llm | StrOutputParser()
testing_response_func = testing_template | llm | StrOutputParser()
evaluation_response_func = evaluation_template | llm | StrOutputParser()
mistake_summary_response_func = mistake_summary_template | llm | StrOutputParser()

def summarize_chat_history(chat_history_str: str) -> str:
    max_length = 1000
    if len(chat_history_str) > max_length:
        summary_prompt = f"Summarize the following conversation in one concise paragraph:\n{chat_history_str}"
        summary = llm.invoke(summary_prompt)
        return summary
    return chat_history_str

def update_progress(session: dict, cycle_count: int, correct_answer_count: int):
    THRESHOLD_CYCLES = 5
    if cycle_count >= THRESHOLD_CYCLES:
        submodule_num = int(session["current_submodule"].split()[1])
        module_num = int(session["current_module"].split()[1])
        if submodule_num < 3:
            new_submodule = f"Submodule {submodule_num + 1}"
            new_module = session["current_module"]
        else:
            new_module = f"Module {module_num + 1}"
            new_submodule = "Submodule 1"
        session["current_module"] = new_module
        session["current_submodule"] = new_submodule
        update_user_session_in_db(session["session_id"], new_module, new_submodule)
        cycle_count = 0
        correct_answer_count = 0
        print(f"Advanced to {new_module} → {new_submodule}")
    return session, cycle_count, correct_answer_count

# Global counters for simplicity; in production, track per session
cycle_count = 0
correct_answer_count = 0

# ---------------------- Flask Routes ----------------------
@app.route("/")
def home():
    return "Welcome to the Intelligent Language Tutor!"

@app.route("/signup", methods=["POST"])
def api_signup():
    data = request.json
    username = data.get("username")
    password = data.get("password")
    if signup_db(username, password):
        return jsonify({"message": "Signup successful"}), 200
    return jsonify({"message": "Username already exists"}), 400

@app.route("/login", methods=["POST"])
def api_login():
    data = request.json
    username = data.get("username")
    password = data.get("password")
    user_id = login_db(username, password)
    if user_id:
        flask_session["user_id"] = user_id
        return jsonify({"message": "Login successful", "user_id": user_id}), 200
    return jsonify({"message": "Invalid credentials"}), 401

@app.route("/create_session", methods=["POST"])
def api_create_session():
    data = request.json
    user_id = flask_session.get("user_id")
    if not user_id:
        return jsonify({"message": "User not logged in"}), 401
    learning_language = data.get("learning_language")
    known_language = data.get("known_language")
    proficiency_level = data.get("proficiency_level")
    create_user_session_db(user_id, learning_language, known_language, proficiency_level)
    new_session = get_user_session(user_id)
    return jsonify(new_session), 200

@app.route("/chat", methods=["POST"])
def api_chat():
    global cycle_count, correct_answer_count
    data = request.json
    user_id = flask_session.get("user_id")
    if not user_id:
        return jsonify({"message": "User not logged in"}), 401
    session_data = get_user_session(user_id)
    if not session_data:
        return jsonify({"message": "No active session. Create a session first."}), 400
    
    # Load and format conversation history
    history_messages = memory.load_memory_variables({}).get("chat_history", [])
    formatted_history = "\n".join(
        f"{'User' if isinstance(msg, HumanMessage) else 'Tutor'}: {msg.content}"
        for msg in history_messages
    ) if history_messages else "No previous conversation."
    summarized_history = summarize_chat_history(formatted_history)
    
    # Teaching Phase
    teaching_output = teaching_response_func.invoke({
        "learning_language": session_data["learning_language"],
        "current_module": session_data["current_module"],
        "current_submodule": session_data["current_submodule"],
        "chat_history": summarized_history
    })
    
    # Testing Phase
    testing_output = testing_response_func.invoke({
        "learning_language": session_data["learning_language"],
        "current_module": session_data["current_module"],
        "current_submodule": session_data["current_submodule"],
        "chat_history": summarized_history
    })
    
    # If no user input provided, return teaching and testing output
    user_input = data.get("user_input", "")
    if not user_input:
        return jsonify({
            "teaching": teaching_output,
            "testing": testing_output,
            "message": "Waiting for user response."
        }), 200
    
    # Evaluation Phase
    conversation_id = save_conversation_db(user_id, session_data["session_id"], user_input, "")
    evaluation_output = evaluation_response_func.invoke({
        "learning_language": session_data["learning_language"],
        "current_module": session_data["current_module"],
        "current_submodule": session_data["current_submodule"],
        "user_response": user_input,
        "chat_history": summarized_history
    })
    print("Evaluation Output:", evaluation_output)
    
    if "Great job" in evaluation_output:
        correct_answer_count += 1
    else:
        correct_answer_count = max(correct_answer_count - 1, 0)
    
    for line in evaluation_output.split("\n"):
        if "→" in line:
            try:
                parts = line.split("→")
                if len(parts) < 2:
                    continue
                left_side = parts[0]
                if ":" not in left_side:
                    continue
                error_type = left_side.split(":")[0].strip()
                incorrect = left_side.split(":")[1].strip()
                correct_ans = parts[1].strip()
                if incorrect and correct_ans:
                    save_mistake_db(session_data["session_id"], conversation_id, error_type, incorrect, correct_ans,
                                     module=session_data["current_module"], submodule=session_data["current_submodule"])
                    print(f"Logged mistake: {error_type} - {incorrect} → {correct_ans}")
            except Exception as e:
                print("Error parsing mistake line:", e)
    
    save_conversation_db(user_id, session_data["session_id"], user_input, evaluation_output)
    cycle_count += 1
    
    revision_summary = None
    if cycle_count >= 5:
        conn = sqlite3.connect("chatbot.db")
        cursor = conn.cursor()
        cursor.execute("""
            SELECT error_type, incorrect_response, correct_response 
            FROM mistakes 
            WHERE session_id = ? AND module = ? AND submodule = ?
        """, (session_data["session_id"], session_data["current_module"], session_data["current_submodule"]))
        mistakes_rows = cursor.fetchall()
        conn.close()
        if mistakes_rows:
            mistakes_text = "\n".join(
                f"{row[0]} - {row[1]} → {row[2]}" for row in mistakes_rows
            )
            revision_summary = mistake_summary_response_func.invoke({
                "learning_language": session_data["learning_language"],
                "current_module": session_data["current_module"],
                "current_submodule": session_data["current_submodule"],
                "mistakes_text": mistakes_text
            })
        else:
            revision_summary = "No mistakes detected in these 5 cycles. Great job!"
        session_data, cycle_count, correct_answer_count = update_progress(session_data, cycle_count, correct_answer_count)
    
    memory.save_context({"user_response": user_input}, {"output": evaluation_output})
    
    return jsonify({
        "teaching": teaching_output,
        "testing": testing_output,
        "evaluation": evaluation_output,
        "revision_summary": revision_summary
    }), 200

if __name__ == "__main__":
    app.run(debug=True)
