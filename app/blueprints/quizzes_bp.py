from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app import db
# --- Ensure all decorators are imported ---
from app.decorators import teacher_required, login_required, admin_required
import datetime
from google.cloud.firestore_v1.base_query import FieldFilter # Needed for fetching questions

# Define the blueprint
quizzes_bp = Blueprint(
    'quizzes',
    __name__,
    template_folder='../templates/quizzes'
)

# --- TEACHER'S "QUIZ LIST" PAGE ---
@quizzes_bp.route('/list')
@teacher_required
def list_quizzes():
    teacher_user_id = session.get('user_id')
    my_quizzes = []
    course_names = {} # To store course names for display

    try:
        # Fetch teacher's courses first to get names
        courses_ref = db.collection('courses').where('teacher_id', '==', teacher_user_id).stream()
        course_names = {course.id: course.to_dict().get('name', 'N/A') for course in courses_ref}

        # Fetch quizzes created by this teacher
        query = db.collection('quizzes').where('teacher_id', '==', teacher_user_id).order_by('created_at', direction='DESCENDING').stream()
        for quiz in query:
            quiz_data = quiz.to_dict()
            quiz_data['id'] = quiz.id
            # Add course name using the map
            quiz_data['course_name'] = course_names.get(quiz_data.get('course_id'), 'Unknown Course')
            my_quizzes.append(quiz_data)

    except Exception as e:
        flash(f'Error fetching quizzes: {e}. You may need to create a Firebase index.', 'error')

    return render_template('quiz_list.html', quizzes=my_quizzes)


# --- TEACHER'S "CREATE QUIZ" PAGE ---
@quizzes_bp.route('/create', methods=['GET', 'POST'])
@teacher_required
def create_quiz():
    teacher_user_id = session.get('user_id')

    # Get this teacher's courses for the dropdown
    try:
        courses_ref = db.collection('courses').where('teacher_id', '==', teacher_user_id).stream()
        teacher_courses = [course.to_dict() | {'id': course.id} for course in courses_ref]
    except Exception as e:
        flash(f'Error fetching your courses: {e}', 'error')
        teacher_courses = []

    if request.method == 'POST':
        try:
            course_id = request.form['course_id']
            title = request.form['title']
            # --- Get the deadline from the form ---
            deadline_str = request.form['deadline']
            # Convert the string YYYY-MM-DD to a datetime object for Firestore
            deadline_dt = datetime.datetime.strptime(deadline_str, '%Y-%m-%d') if deadline_str else None
            # --- End deadline handling ---

            quiz_data = {
                'title': title,
                'course_id': course_id,
                'teacher_id': teacher_user_id,
                'created_at': datetime.datetime.utcnow(),
                'deadline': deadline_dt, # <-- Store the deadline
                'question_count': 0
            }
            quiz_ref = db.collection('quizzes').add(quiz_data)
            new_quiz_id = quiz_ref[1].id

            flash('Quiz created successfully! Now, add questions to it.', 'success')
            return redirect(url_for('quizzes.add_questions', quiz_id=new_quiz_id))

        except ValueError:
             flash('Invalid date format for deadline. Please use YYYY-MM-DD.', 'error')
        except Exception as e:
            flash(f'Error creating quiz: {e}', 'error')

    # Get today's date for the default value in the form
    today = datetime.date.today().strftime("%Y-%m-%d")
    return render_template('create_quiz.html', teacher_courses=teacher_courses, today=today)


# --- TEACHER'S "ADD QUESTIONS" PAGE ---
@quizzes_bp.route('/add_questions/<string:quiz_id>', methods=['GET', 'POST'])
@teacher_required
def add_questions(quiz_id):
    teacher_user_id = session.get('user_id')

    # Fetch the specific quiz
    try:
        quiz_ref = db.collection('quizzes').document(quiz_id)
        quiz = quiz_ref.get()
        if not quiz.exists or quiz.to_dict().get('teacher_id') != teacher_user_id:
            flash('Quiz not found or you do not have permission to edit it.', 'error')
            return redirect(url_for('quizzes.list_quizzes'))
        quiz_data = quiz.to_dict()

        # Fetch existing questions for this quiz
        questions = []
        questions_query = quiz_ref.collection('questions').order_by('order').stream()
        questions = [q.to_dict() | {'id': q.id} for q in questions_query]

    except Exception as e:
        flash(f'Error fetching quiz details: {e}', 'error')
        return redirect(url_for('quizzes.list_quizzes'))

    # --- HANDLE ADDING A NEW QUESTION (POST) ---
    if request.method == 'POST':
        try:
            question_text = request.form['question_text']
            option_a = request.form['option_a']
            option_b = request.form['option_b']
            option_c = request.form['option_c']
            option_d = request.form['option_d']
            correct_answer = request.form['correct_answer']

            if not all([question_text, option_a, option_b, option_c, option_d, correct_answer]):
                 flash('All fields are required for the question.', 'error')
                 return redirect(request.url)

            current_count = len(questions)
            new_order = current_count + 1

            question_data = {
                'text': question_text,
                'options': {'A': option_a, 'B': option_b, 'C': option_c, 'D': option_d},
                'correct_answer': correct_answer,
                'order': new_order
            }
            quiz_ref.collection('questions').add(question_data)
            quiz_ref.update({'question_count': new_order})

            flash('Question added successfully!', 'success')
            return redirect(url_for('quizzes.add_questions', quiz_id=quiz_id))

        except Exception as e:
            flash(f'Error adding question: {e}', 'error')

    # --- SHOW THE PAGE (GET) ---
    return render_template('add_questions.html', quiz=quiz_data, quiz_id=quiz_id, questions=questions)

# --- STUDENT'S "VIEW QUIZZES" PAGE (Includes check for submitted quizzes) ---
@quizzes_bp.route('/student/list')
@login_required
def student_quiz_list():
    student_id = session.get('user_id')
    available_quizzes = []
    course_names = {}
    submitted_quiz_ids = set() # <-- For checking completion status

    try:
        # 1. Find courses student is enrolled in
        courses_query = db.collection('courses').where('enrolled_students', 'array_contains', student_id).stream()
        my_course_ids = []
        for course in courses_query:
            my_course_ids.append(course.id)
            course_names[course.id] = course.to_dict().get('name', 'N/A')

        if my_course_ids:
            # 2. Find quizzes for those courses
            quizzes_query = db.collection('quizzes').where('course_id', 'in', my_course_ids).order_by('deadline').stream()
            for quiz in quizzes_query:
                quiz_data = quiz.to_dict()
                quiz_data['id'] = quiz.id
                quiz_data['course_name'] = course_names.get(quiz_data.get('course_id'), 'Unknown Course')
                available_quizzes.append(quiz_data)

        # 3. Fetch IDs of submitted quizzes
        submissions_query = db.collection('quiz_submissions').where('student_id', '==', student_id).stream()
        for sub in submissions_query:
            submitted_quiz_ids.add(sub.to_dict().get('quiz_id'))

    except Exception as e:
        flash(f'Error fetching quizzes: {e}. Check for Firebase index errors.', 'error')

    return render_template('student_quiz_list.html',
                           available_quizzes=available_quizzes,
                           submitted_quiz_ids=submitted_quiz_ids) # Pass submitted IDs


# --- STUDENT'S "TAKE QUIZ" PAGE (Includes check for existing submission) ---
@quizzes_bp.route('/take/<string:quiz_id>', methods=['GET', 'POST'])
@login_required
def take_quiz(quiz_id):
    student_id = session.get('user_id')

    # --- Check for existing submission ---
    submission_doc_id = f"{quiz_id}_{student_id}"
    submission_ref = db.collection('quiz_submissions').document(submission_doc_id)
    existing_submission = submission_ref.get()
    if existing_submission.exists:
        flash('You have already submitted this quiz.', 'info')
        return redirect(url_for('quizzes.student_quiz_list'))
    # --- End check ---

    # --- Fetch Quiz and Questions ---
    try:
        quiz_ref = db.collection('quizzes').document(quiz_id)
        quiz = quiz_ref.get()
        if not quiz.exists:
            flash('Quiz not found.', 'error')
            return redirect(url_for('quizzes.student_quiz_list'))
        quiz_data = quiz.to_dict()

        # Check enrollment
        course_doc = db.collection('courses').document(quiz_data['course_id']).get()
        if not course_doc.exists or student_id not in course_doc.to_dict().get('enrolled_students', []):
            flash('You are not enrolled in the course for this quiz.', 'error')
            return redirect(url_for('quizzes.student_quiz_list'))
        course_name = course_doc.to_dict().get('name', 'N/A')

        # Fetch questions
        questions_query = quiz_ref.collection('questions').order_by('order').stream()
        questions = [q.to_dict() | {'id': q.id} for q in questions_query]

    except Exception as e:
        flash(f'Error loading quiz: {e}', 'error')
        return redirect(url_for('quizzes.student_quiz_list'))

    # --- HANDLE QUIZ SUBMISSION (POST) ---
    if request.method == 'POST':
        try:
            student_answers = {}
            score = 0
            total_questions = len(questions)
            submitted_question_ids = request.form.getlist('question_ids')

            for question in questions:
                 q_id = question['id']
                 if q_id in submitted_question_ids:
                    selected_option = request.form.get(f'answer_{q_id}')
                    student_answers[q_id] = selected_option
                    if selected_option == question['correct_answer']:
                        score += 1

            submission_data = {
                'quiz_id': quiz_id,
                'student_id': student_id,
                'course_id': quiz_data['course_id'],
                'answers': student_answers,
                'score': score,
                'total_questions': total_questions,
                'submitted_at': datetime.datetime.utcnow()
            }
            db.collection('quiz_submissions').document(submission_doc_id).set(submission_data)

            flash(f'Quiz submitted successfully! Your score: {score}/{total_questions}', 'success')
            return redirect(url_for('quizzes.student_quiz_list'))

        except Exception as e:
            flash(f'Error submitting quiz: {e}', 'error')

    # --- SHOW THE QUIZ PAGE (GET) ---
    return render_template('take_quiz.html',
                           quiz=quiz_data,
                           quiz_id=quiz_id,
                           questions=questions,
                           course_name=course_name)


# --- TEACHER'S "VIEW SUBMISSIONS" PAGE ---
@quizzes_bp.route('/submissions/<string:quiz_id>')
@teacher_required
def view_submissions(quiz_id):
    teacher_user_id = session.get('user_id')
    submissions = []

    try:
        # 1. Fetch quiz & verify owner
        quiz_ref = db.collection('quizzes').document(quiz_id)
        quiz = quiz_ref.get()
        if not quiz.exists or quiz.to_dict().get('teacher_id') != teacher_user_id:
            flash('Quiz not found or you do not have permission to view its submissions.', 'error')
            return redirect(url_for('quizzes.list_quizzes'))
        quiz_data = quiz.to_dict()
        course_name = db.collection('courses').document(quiz_data['course_id']).get().to_dict().get('name', 'N/A')

        # 2. Fetch submissions
        submissions_query = db.collection('quiz_submissions').where('quiz_id', '==', quiz_id).stream()

        # 3. Fetch student details (with caching)
        student_cache = {}
        for sub in submissions_query:
            submission_data = sub.to_dict()
            student_id = submission_data.get('student_id')
            if student_id not in student_cache:
                student_doc = db.collection('students').document(student_id).get()
                student_cache[student_id] = student_doc.to_dict() if student_doc.exists else {'name': 'Unknown', 'roll_no': 'N/A'}

            submission_data['student_name'] = student_cache[student_id].get('name')
            submission_data['student_roll_no'] = student_cache[student_id].get('roll_no')
            submissions.append(submission_data)

        submissions.sort(key=lambda x: x.get('student_name', ''))

    except Exception as e:
        flash(f'Error fetching submissions: {e}. Check for Firebase index errors.', 'error')
        return redirect(url_for('quizzes.list_quizzes'))

    return render_template('view_submissions.html',
                           quiz=quiz_data,
                           submissions=submissions,
                           course_name=course_name)

# --- ADMIN'S "VIEW SUBMISSIONS" PAGE ---
@quizzes_bp.route('/admin/submissions', methods=['GET'])
@admin_required
def admin_view_submissions():
    all_quizzes = []
    submissions = []
    selected_quiz_id = request.args.get('quiz_id')
    selected_quiz_title = ""
    course_names = {}
    student_cache = {}

    try:
        # 1. Fetch courses for names
        courses_ref = db.collection('courses').stream()
        for course in courses_ref:
            course_names[course.id] = course.to_dict().get('name', 'N/A')

        # 2. Fetch all quizzes
        quizzes_ref = db.collection('quizzes').order_by('created_at', direction='DESCENDING').stream()
        for quiz in quizzes_ref:
             quiz_data = quiz.to_dict()
             quiz_data['id'] = quiz.id
             quiz_data['course_name'] = course_names.get(quiz_data.get('course_id'), 'Unknown')
             all_quizzes.append(quiz_data)

        # 3. Fetch submissions if quiz selected
        if selected_quiz_id:
            selected_quiz = next((q for q in all_quizzes if q['id'] == selected_quiz_id), None)
            if selected_quiz:
                selected_quiz_title = selected_quiz['title']
                submissions_query = db.collection('quiz_submissions').where('quiz_id', '==', selected_quiz_id).stream()

                for sub in submissions_query:
                    submission_data = sub.to_dict()
                    student_id = submission_data.get('student_id')
                    if student_id not in student_cache:
                        student_doc = db.collection('students').document(student_id).get()
                        student_cache[student_id] = student_doc.to_dict() if student_doc.exists else {'name': 'Unknown', 'roll_no': 'N/A'}

                    submission_data['student_name'] = student_cache[student_id].get('name')
                    submission_data['student_roll_no'] = student_cache[student_id].get('roll_no')
                    submissions.append(submission_data)
                submissions.sort(key=lambda x: x.get('student_name', ''))

    except Exception as e:
        flash(f'Error fetching data: {e}. Check for Firebase index errors.', 'error')

    return render_template('admin_submissions.html',
                           all_quizzes=all_quizzes,
                           submissions=submissions,
                           selected_quiz_id=selected_quiz_id,
                           selected_quiz_title=selected_quiz_title)


# --- STUDENT'S "VIEW RESULTS" PAGE ---
@quizzes_bp.route('/student/results')
@login_required
def student_results():
    student_id = session.get('user_id')
    results = []
    quiz_cache = {}
    course_cache = {}

    try:
        # 1. Fetch student's submissions
        submissions_query = db.collection('quiz_submissions').where('student_id', '==', student_id).order_by('submitted_at', direction='DESCENDING').stream()

        # 2. Fetch details for each submission
        for sub in submissions_query:
            submission_data = sub.to_dict()
            quiz_id = submission_data.get('quiz_id')
            course_id = submission_data.get('course_id')

            # Fetch quiz title (cached)
            if quiz_id not in quiz_cache:
                quiz_doc = db.collection('quizzes').document(quiz_id).get()
                quiz_cache[quiz_id] = quiz_doc.to_dict().get('title', 'N/A') if quiz_doc.exists else 'N/A'

            # Fetch course name (cached)
            if course_id not in course_cache:
                course_doc = db.collection('courses').document(course_id).get()
                course_cache[course_id] = course_doc.to_dict().get('name', 'N/A') if course_doc.exists else 'N/A'

            submission_data['quiz_title'] = quiz_cache.get(quiz_id)
            submission_data['course_name'] = course_cache.get(course_id)
            results.append(submission_data)

    except Exception as e:
        flash(f'Error fetching results: {e}. Check for Firebase index errors.', 'error')

    return render_template('student_results.html', results=results)