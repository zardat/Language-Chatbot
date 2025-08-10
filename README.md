# Intelligent Language Tutor System 🤖💬

An interactive, AI-driven platform designed to teach any language through a structured, adaptive, and personalized course. This system uses a powerful language model to create dynamic lessons, track user progress, and provide targeted feedback on common mistakes.

## ✨ Features

-   **Adaptive Learning:** Automatically adjusts lesson difficulty based on the learner's proficiency level (Beginner, Intermediate, Advanced).
-   **Structured Curriculum:** Organizes learning into a clear `Module > Submodule` structure, ensuring steady and logical progression.
-   **Interactive Cycles:** Engages users in a three-phase loop for each concept:
    1.  **Teaching:** Presents new content with examples.
    2.  **Testing:** Asks a relevant question to gauge understanding.
    3.  **Evaluation:** Provides instant, corrective feedback.
-   **Personalized Revision:** Logs every mistake a user makes. If a pattern of errors emerges, the system initiates a targeted revision session before moving on to new material.
-   **Multi-language Support:** The architecture is designed to support learning any language, with the user's native language used for initial setup and clarification.

## 🛠️ Architecture & Tech Stack

The system is built with a modular architecture to separate concerns and ensure scalability.

-   **Frontend:** A dynamic web interface for user interaction.
    -   React | HTML5 | CSS3 | JavaScript
-   **Backend:** A RESTful API server to manage application logic.
    -   Flask / FastAPI | Python
-   **AI & Language Processing:** The core intelligence of the tutor.
    -   OpenAI GPT-3.5-turbo | LangChain
-   **Database:** A lightweight and reliable database for data persistence.
    -   SQLite

## ⚙️ How It Works

The system follows a state machine to guide the learner's journey. The core interaction is a cycle that ensures concepts are mastered before progression.

```mermaid
graph TD
    A[Start Submodule] --> B{Teaching Phase};
    B --> C{Testing Phase};
    C --> D{Evaluation Phase};
    D --> E{Mistake Logged?};
    E -- Yes --> F[Increment Mistake Counter];
    E -- No --> G[Increment Correct Counter];
    F --> H{5 Cycles Complete?};
    G --> H;
    H -- Yes --> I{Mistakes Were Made?};
    H -- No --> B;
    I -- Yes --> J[Provide Revision Summary];
    I -- No --> K[Advance to Next Submodule/Module];
    J --> K;

    style A fill:#28a745,color:#fff
    style K fill:#28a745,color:#fff
    style J fill:#ffc107,color:#333
