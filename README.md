# Full-Stack Student Management System (SMS)

This is a comprehensive, role-based web application built with Python (Flask) and Firebase to manage all core academic, administrative, and financial operations of an educational institution. The system features distinct dashboards and permissions for Admins, Teachers, and Students.

![Admin Dashboard Screenshot](ss.PNG)

---

## 🚀 Key Features

* [cite_start]**Role-Based Access Control (RBAC):** Secure, distinct dashboards and functionalities for three user roles: **Admin**, **Teacher**, and **Student** [cite: 3-4].
* [cite_start]**Authentication:** Secure, token-based login (Email & Password) using **Firebase Authentication** and the Firebase JavaScript SDK [cite: 5-6].
* [cite_start]**Student Management (Admin):** Full CRUD (Create, Read, Update, Delete) for student profiles, including linking student accounts to their profiles [cite: 7-9].
* [cite_start]**Teacher Management (Admin):** Full CRUD for teacher profiles, including linking them to their registered user accounts [cite: 10-12].
* [cite_start]**Course Management (Admin):** Full CRUD for courses, including enrolling students and assigning teachers to subjects [cite: 13-15].

### Academic Modules
* **Attendance:** Teachers can mark daily attendance for their courses. [cite_start]Students can view their attendance percentage on their dashboard, which is color-coded for performance [cite: 18-20].
* [cite_start]**Assignments:** Teachers can upload assignment files (with due dates) to local server storage[cite: 22]. [cite_start]Students can download and submit their work, which is also saved locally [cite: 23-24].
* [cite_start]**Quizzes & Results:** Teachers can create dynamic quizzes (MCQs) with deadlines[cite: 26]. Students can take quizzes only once, which are **auto-graded** upon submission. [cite_start]Results are displayed on the student's results page and dashboard [cite: 27-28, 30-31].

### Finance Module
* [cite_start]**Fee Management:** Admins can assign fees and track payment status (Paid, Unpaid, Partially Paid) for all students [cite: 33-34].
* [cite_start]**Receipts:** Students can view their fee status and upload payment receipts (as images/PDFs)[cite: 35].
* [cite_start]**Challan & Reporting:** Admins can generate a clean, printable **HTML fee challan** and export a full finance report to **Excel (.xlsx)** [cite: 36-38].

### Library Management
* **Book Catalog:** Admins can manage the library's book catalog (CRUD).
* **Issue/Return:** Admins can issue books to students and mark them as returned. [cite_start]This logic automatically updates the available quantities [cite: 50-51].
* **Penalties:** The system automatically calculates and displays late-fee penalties for overdue books on both the Admin and Student dashboards.

### Timetable & Notifications
* [cite_start]**Timetable:** Admins can create timetables and manage weekly class schedules, assigning subjects, teachers, and rooms [cite: 59-61].
* **Personalized Schedules:** Teacher and Student dashboards automatically display *only* their own personal schedule for the week.
* [cite_start]**Dynamic Notification Bell 🔔:** A real-time notification system (using JavaScript/Fetch) alerts students with a badge on a bell icon [cite: 39-41].
* **Notification Triggers:** Students are automatically notified of new assignments, new quizzes, and fee updates.

### Analytics
* [cite_start]**Chart.js Integration:** The Admin and Teacher dashboards feature dynamic charts to visualize data, including a pie chart for student fee status and bar charts for course attendance percentages [cite: 47-48].

![Teacher Dashboard Screenshot](cc.PNG)

---

## 🛠️ Technologies Used

* **Backend:** Python, Flask, Flask Blueprints
* **Database & Auth:** Google Firebase (Firestore, Firebase Authentication)
* **Frontend:** HTML, CSS, Bootstrap 5, JavaScript (Fetch API, DOM)
* **Reporting:** Chart.js, **openpyxl** (for .xlsx), `fpdf2` (for .pdf generation - *Note: Switched to HTML/CSS for challan*)
* **File Storage:** Local server-side storage (using `os` and `werkzeug` for secure uploads)

---

## ⚙️ How to Run

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git](https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git)
    cd YOUR_REPO_NAME
    ```
2.  **Create and activate a virtual environment:**
    ```bash
    # Windows
    python -m venv venv
    .\venv\Scripts\activate
    ```
3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Add Firebase Credentials:**
    * Go to your Firebase Project Settings -> Service Accounts.
    * Generate a new private key.
    * Rename the downloaded JSON file to `serviceAccountKey.json` and place it in the root of the project folder.
5.  **Add Firebase Web Config:**
    * Go to Firebase Project Settings -> General.
    * Find your Web App (or create one).
    * Copy the `firebaseConfig` object.
    * Paste your config into `app/templates/auth/login.html` in the designated `<script>` section.
6.  **Create Local Storage Folders:**
    * Inside the `app/static/` directory, create three empty folders: `uploads`, `submissions`, and `receipts`.
7.  **Run the application:**
    ```bash
    python run.py
    ```

---

## ⚖️ License

Copyright (c) 2025 [Muhammad Usman]. This project is licensed under the **MIT License**. See the `LICENSE` file for details.