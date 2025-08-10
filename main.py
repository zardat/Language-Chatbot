import os
os.environ["OPENAI_API_KEY"] = "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"

import sqlite3
import bcrypt
from fastapi import FastAPI, HTTPException, Depends, Request, Form
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.requests import Request
from starlette.responses import RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

# Import your tutoring modules and LangChain integration
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain.memory import ConversationBufferMemory
# from langchain_community.chat_models import ChatOpenAI
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, AIMessage


# Initialize FastAPI app
app = FastAPI()

# Optional: Enable CORS if your frontend is separate
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

def signup(username: str, password: str):
    conn = sqlite3.connect("chatbot.db")
    cursor = conn.cursor()
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    try:
        cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_password))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Username already exists")
    conn.close()
    return {"message": "Signup successful"}

def login(username: str, password: str):
    conn = sqlite3.connect("chatbot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, password FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()
    if user and bcrypt.checkpw(password.encode('utf-8'), user[1]):
        return user[0]
    raise HTTPException(status_code=401, detail="Invalid username or password")

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

def create_user_session(user_id: int, learning_language: str, known_language: str, proficiency_level: str):
    conn = sqlite3.connect("chatbot.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO sessions (user_id, learning_language, known_language, proficiency_level)
        VALUES (?, ?, ?, ?)
    """, (user_id, learning_language, known_language, proficiency_level))
    conn.commit()
    conn.close()

def save_conversation(user_id: int, session_id: int, user_response: str, tutor_response: str):
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

def save_mistake(session_id: int, conversation_id: int, error_type: str, incorrect: str, correct: str, module: str, submodule: str):
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

# ---------------------- FastAPI Models ----------------------
class SignupModel(BaseModel):
    username: str
    password: str

class SessionModel(BaseModel):
    learning_language: str
    known_language: str
    proficiency_level: str

class ChatModel(BaseModel):
    user_id: int
    user_input: str

# ---------------------- AI Tutor Setup and Templates ----------------------
# Initialize our LLM and memory
llm = ChatOpenAI(model_name="gpt-3.5-turbo", temperature=0.7)
memory = ConversationBufferMemory(return_messages=True, memory_key="chat_history", input_key="user_response")

# Define prompt templates (you can include different ones based on proficiency)
# For brevity, we include a single set here (you can conditionally select for beginner vs non-beginner)
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
If the answer is correct, include "Great job" in your feedback. If incorrect, specify the error (e.g., pronunciation, vocabulary, grammar) and provide the correct answer.
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

# ---------- Module Progression ----------
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

# Initialize counters (global for simplicity; in production, track per session)
cycle_count = 0
correct_answer_count = 0

# ---------- FastAPI Endpoints ----------
@app.get("/")
def read_root():
    return {"message": "Welcome to the Intelligent Language Tutor API"}

@app.post("/signup")
def api_signup(data: SignupModel):
    return signup(data.username, data.password)

@app.post("/login")
def api_login(form_data: OAuth2PasswordRequestForm = Depends()):
    user_id = login(form_data.username, form_data.password)
    return {"user_id": user_id}

@app.post("/create_session")
def api_create_session(session_data: SessionModel, user_id: int):
    # Assume user_id is provided in the request (or through a dependency)
    create_user_session(user_id, session_data.learning_language, session_data.known_language, session_data.proficiency_level)
    new_session = get_user_session(user_id)
    return new_session

@app.post("/chat")
def api_chat(chat_data: ChatModel):
    global cycle_count, correct_answer_count

    user_id = chat_data.user_id
    session = get_user_session(user_id)
    if not session:
        raise HTTPException(status_code=400, detail="No active session found. Please create a session first.")

    # Load and format conversation history from memory
    history_messages = memory.load_memory_variables({}).get("chat_history", [])
    formatted_history = "\n".join(
        f"{'User' if isinstance(msg, HumanMessage) else 'Tutor'}: {msg.content}"
        for msg in history_messages
    ) if history_messages else "No previous conversation."
    summarized_history = summarize_chat_history(formatted_history)

    # The conversation flow: teaching, testing, evaluation are triggered sequentially.
    # For demonstration, we assume that this /chat endpoint handles one cycle.
    # In production, you might design separate endpoints or a websocket for real-time conversation.
    
    # 1. Teaching phase
    teaching_output = teaching_response_func.invoke({
        "learning_language": session["learning_language"],
        "current_module": session["current_module"],
        "current_submodule": session["current_submodule"],
        "chat_history": summarized_history
    })

    # 2. Testing phase
    testing_output = testing_response_func.invoke({
        "learning_language": session["learning_language"],
        "current_module": session["current_module"],
        "current_submodule": session["current_submodule"],
        "chat_history": summarized_history
    })

    # In a web API, you would now return the testing question to the client.
    # The client would then send the user's answer in a subsequent request.
    # For demonstration, we'll assume the user's answer is sent along with the /chat request.
    # So, we add a field "user_input" to ChatModel if needed. Here we assume chat_data.user_input exists.
    user_input = chat_data.user_input  if hasattr(chat_data, "user_input") else ""
    if not user_input:
        return {"teaching": teaching_output, "testing": testing_output, "message": "Waiting for user response."}

    # 3. Evaluation phase (once user responds)
    # First, save the conversation (assume save_conversation returns conversation_id)
    conversation_id = save_conversation(user_id, session["session_id"], user_input, "")
    evaluation_output = evaluation_response_func.invoke({
        "learning_language": session["learning_language"],
        "current_module": session["current_module"],
        "current_submodule": session["current_submodule"],
        "user_response": user_input,
        "chat_history": summarized_history
    })

    # Update correct answer counter based on evaluation
    if "Great job" in evaluation_output:
        correct_answer_count += 1
    else:
        correct_answer_count = max(correct_answer_count - 1, 0)
    
    # Parse evaluation output for mistakes and store them in the database
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
                    save_mistake(session["session_id"], conversation_id, error_type, incorrect, correct_ans,
                                 module=session["current_module"], submodule=session["current_submodule"])
            except Exception as e:
                print("Error parsing mistake line:", e)

    # Save evaluation output in conversation
    save_conversation(user_id, session["session_id"], user_input, evaluation_output)
    
    # Increase cycle count for the submodule
    cycle_count += 1

    # After 5 cycles, return a revision summary if mistakes exist and update progress
    revision_summary = None
    if cycle_count >= 5:
        conn = sqlite3.connect("chatbot.db")
        cursor = conn.cursor()
        cursor.execute("""
            SELECT error_type, incorrect_response, correct_response 
            FROM mistakes 
            WHERE session_id = ? AND module = ? AND submodule = ?
        """, (session["session_id"], session["current_module"], session["current_submodule"]))
        mistakes_rows = cursor.fetchall()
        conn.close()
        if mistakes_rows:
            mistakes_text = "\n".join(
                f"{row[0]} - {row[1]} → {row[2]}" for row in mistakes_rows
            )
            revision_summary = mistake_summary_response_func.invoke({
                "learning_language": session["learning_language"],
                "current_module": session["current_module"],
                "current_submodule": session["current_submodule"],
                "mistakes_text": mistakes_text
            })
        else:
            revision_summary = "No mistakes detected in these 5 cycles. Great job!"
        session, cycle_count, correct_answer_count = update_progress(session, cycle_count, correct_answer_count)

    # Save conversation context in memory for future context.
    memory.save_context({"user_response": user_input}, {"output": evaluation_output})
    
    return {
        "teaching": teaching_output,
        "testing": testing_output,
        "evaluation": evaluation_output,
        "revision_summary": revision_summary
    }

# Run the app with: uvicorn main:app --reload
