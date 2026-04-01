from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from app import db
# Ensure all decorators are imported
from app.decorators import teacher_required, login_required
from werkzeug.utils import secure_filename
import traceback
import datetime
from datetime import timezone # Import timezone
import os

# Define the blueprint
assignments_bp = Blueprint(
    'assignments',
    __name__,
    template_folder='../templates/assignments'
)

# --- TEACHER'S "UPLOAD" PAGE (Local Upload, Due Date, WITH Notifications) ---
@assignments_bp.route('/upload', methods=['GET', 'POST'])
@teacher_required
def upload_assignment():
    teacher_user_id = session.get('user_id')

    try:
        # Fetch teacher's courses for the dropdown
        courses_ref = db.collection('courses').where('teacher_id', '==', teacher_user_id).stream()
        # Keep as list for the template loop in GET
        teacher_courses_list = [course.to_dict() | {'id': course.id} for course in courses_ref]
    except Exception as e:
        flash(f'Error fetching your courses: {e}', 'error')
        teacher_courses_list = []

    if request.method == 'POST':
        try:
            # Use .get() for safer access
            assignment_file = request.files.get('assignment_file')
            course_id = request.form.get('course_id')
            title = request.form.get('title')
            due_date_str = request.form.get('due_date')
            # Convert date string to a timezone-aware datetime object (end of day)
            due_date_dt = datetime.datetime.strptime(due_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59, tzinfo=timezone.utc) if due_date_str else None

            # --- More specific checks ---
            errors = []
            if not title:
                errors.append("Title is required.")
            if not course_id:
                errors.append("Course selection is required.")
            if not assignment_file or assignment_file.filename == '':
                errors.append("Assignment file is required.")

            if errors:
                for error in errors:
                    flash(error, 'error')
                # Return to the form, repopulating teacher courses
                today = datetime.date.today().strftime("%Y-%m-%d")
                return render_template('upload_assignment.html', teacher_courses=teacher_courses_list, today=today)
            # --- End checks ---

            # --- Proceed with saving file ---
            filename = secure_filename(assignment_file.filename)
            course_upload_dir = os.path.join(current_app.root_path, 'static/uploads', course_id)
            file_path = os.path.join(course_upload_dir, filename)
            os.makedirs(course_upload_dir, exist_ok=True)
            assignment_file.save(file_path)
            file_url = url_for('static', filename=f'uploads/{course_id}/{filename}')

            # Save assignment details to Firestore
            assignment_data = {
                'title': title,
                'course_id': course_id,
                'teacher_id': teacher_user_id,
                'file_url': file_url,
                'filename': filename,
                'uploaded_at': datetime.datetime.now(timezone.utc), # Use aware UTC
                'due_date': due_date_dt # Store aware due date
            }
            assignment_ref = db.collection('assignments').add(assignment_data)
            new_assignment_id = assignment_ref[1].id # Get the new assignment's ID

            # --- ## NOTIFICATION CODE ## ---
            try:
                course_doc = db.collection('courses').document(course_id).get()
                enrolled_students = []
                course_name = "Unknown Course"
                if course_doc.exists:
                     course_data = course_doc.to_dict()
                     enrolled_students = course_data.get('enrolled_students', [])
                     course_name = course_data.get('name', 'N/A')

                if enrolled_students:
                    notification_message = f"New assignment '{title}' uploaded for course '{course_name}'."
                    assignment_link = url_for('assignments.view_assignments', _external=True)
                    batch = db.batch()
                    notification_time = datetime.datetime.now(timezone.utc) # Use aware UTC
                    for student_id in enrolled_students:
                        notif_ref = db.collection('notifications').document()
                        notification_data = {
                            'student_id': student_id, 'message': notification_message,
                            'type': 'assignment', 'link': assignment_link,
                            'related_id': new_assignment_id,
                            'created_at': notification_time, 'is_read': False
                        }
                        batch.set(notif_ref, notification_data)
                    batch.commit()
                    print(f"--- Assignment notifications created for {len(enrolled_students)} students ---")
                else:
                     print(f"--- No students enrolled, no assignment notifications sent. ---")
            except Exception as notify_error:
                print(f"--- FAILED to create assignment notifications: {notify_error} ---")
                flash(f'Assignment uploaded, but failed to send notifications: {notify_error}', 'warning')
            # --- ## END NOTIFICATION CODE ## ---

            flash('Assignment uploaded successfully!', 'success')
            return redirect(url_for('dashboard.teacher_dashboard'))

        except ValueError:
             flash('Invalid date format for due date. Please use YYYY-MM-DD.', 'error')
        except Exception as e:
            flash(f'Error uploading assignment: {e}', 'error')
            traceback.print_exc() # Print full error to terminal

    # GET Request
    today = datetime.date.today().strftime("%Y-%m-%d")
    return render_template('upload_assignment.html', teacher_courses=teacher_courses_list, today=today)


# --- STUDENT'S "VIEW ASSIGNMENTS" PAGE ---
@assignments_bp.route('/view')
@login_required
def view_assignments():
    student_id = session.get('user_id')
    my_assignments = []
    submissions_map = {}
    today_date = datetime.date.today() # Get today's date for naive comparison in template

    try:
        # 1. Find enrolled courses
        courses_query = db.collection('courses').where('enrolled_students', 'array_contains', student_id).stream()
        my_course_ids = [course.id for course in courses_query]

        if my_course_ids:
            # 2. Find assignments for those courses, ordered by due date
            # Requires Index: course_id (IN), due_date (ASC)
            assignments_query = db.collection('assignments').where('course_id', 'in', my_course_ids).order_by('due_date').stream()
            for assignment in assignments_query:
                my_assignments.append(assignment.to_dict() | {'id': assignment.id})

            # 3. Find student's submissions
            submissions_query = db.collection('submissions').where('student_id', '==', student_id).stream()
            submissions_map = {sub.to_dict()['assignment_id']: sub.to_dict() for sub in submissions_query}
    except Exception as e:
        flash(f'Error fetching assignments: {e}. Check for Firebase index errors.', 'error')
        traceback.print_exc()

    return render_template('view_assignments.html',
                           assignments=my_assignments,
                           submissions_map=submissions_map,
                           today_date=today_date) # Pass today's date


# --- STUDENT'S "SUBMIT ASSIGNMENT" HANDLER (with Deadline Check) ---
@assignments_bp.route('/submit/<string:assignment_id>', methods=['POST'])
@login_required
def submit_assignment(assignment_id):
    student_id = session.get('user_id')
    try:
        submitted_file = request.files['submission_file']
        if not submitted_file or submitted_file.filename == '':
            flash('No file selected for submission.', 'error')
            return redirect(url_for('assignments.view_assignments'))

        filename = secure_filename(submitted_file.filename)
        assignment_ref = db.collection('assignments').document(assignment_id)
        assignment_doc = assignment_ref.get()
        if not assignment_doc.exists:
            flash('Assignment not found.', 'error')
            return redirect(url_for('assignments.view_assignments'))
        assignment = assignment_doc.to_dict()

        # --- DEADLINE CHECK ---
        due_date = assignment.get('due_date') # This is an aware datetime
        if due_date:
            now_utc = datetime.datetime.now(timezone.utc) # Get aware current time
            if now_utc > due_date:
                flash('Submission failed: The due date for this assignment has passed.', 'error')
                return redirect(url_for('assignments.view_assignments'))
        # --- END DEADLINE CHECK ---

        submission_dir = os.path.join(current_app.root_path, 'static/submissions', assignment['course_id'], assignment_id)
        os.makedirs(submission_dir, exist_ok=True)
        file_path = os.path.join(submission_dir, filename)
        submitted_file.save(file_path)
        file_url = url_for('static', filename=f'submissions/{assignment["course_id"]}/{assignment_id}/{filename}')

        submission_data = {
            'assignment_id': assignment_id, 'student_id': student_id,
            'course_id': assignment['course_id'], 'file_url': file_url,
            'filename': filename, 'submitted_at': datetime.datetime.now(timezone.utc) # Use aware UTC
        }
        doc_id = f"{assignment_id}_{student_id}"
        db.collection('submissions').document(doc_id).set(submission_data)
        flash('Assignment submitted successfully!', 'success')
    except Exception as e:
        flash(f'Error submitting assignment: {e}', 'error')
        traceback.print_exc()
    return redirect(url_for('assignments.view_assignments'))

# --- TEACHER: LIST MY ASSIGNMENTS ---
@assignments_bp.route('/teacher/list')
@teacher_required
def teacher_list():
    teacher_user_id = session.get('user_id')
    assignments = []
    course_names = {}
    try:
        courses_ref = db.collection('courses').where('teacher_id', '==', teacher_user_id).stream()
        course_names = {course.id: course.to_dict().get('name', 'N/A') for course in courses_ref}

        # Requires Index: teacher_id (ASC), uploaded_at (DESC)
        assign_query = db.collection('assignments') \
            .where('teacher_id', '==', teacher_user_id) \
            .order_by('uploaded_at', direction='DESCENDING') \
            .stream()
        for assign in assign_query:
            assign_data = assign.to_dict()
            assign_data['id'] = assign.id
            assign_data['course_name'] = course_names.get(assign_data.get('course_id'), 'Unknown Course')
            assignments.append(assign_data)
    except Exception as e:
        flash(f'Error fetching your assignments: {e}. Check for Firebase index errors.', 'error')
        traceback.print_exc()
    return render_template('teacher_assignment_list.html', assignments=assignments)


# --- TEACHER: EDIT ASSIGNMENT ---
@assignments_bp.route('/edit/<string:assignment_id>', methods=['GET', 'POST'])
@teacher_required
def edit_assignment(assignment_id):
    teacher_user_id = session.get('user_id')
    assignment_ref = db.collection('assignments').document(assignment_id)
    try:
        assignment = assignment_ref.get()
        if not assignment.exists or assignment.to_dict().get('teacher_id') != teacher_user_id:
            flash('Assignment not found or you do not have permission to edit it.', 'error')
            return redirect(url_for('assignments.teacher_list'))
        assignment_data = assignment.to_dict()
        courses_ref = db.collection('courses').where('teacher_id', '==', teacher_user_id).stream()
        teacher_courses = [course.to_dict() | {'id': course.id} for course in courses_ref]
    except Exception as e:
        flash(f'Error loading assignment data: {e}', 'error')
        traceback.print_exc()
        return redirect(url_for('assignments.teacher_list'))

    if request.method == 'POST':
        try:
            title = request.form.get('title')
            course_id = request.form.get('course_id')
            due_date_str = request.form.get('due_date')
            due_date_dt = datetime.datetime.strptime(due_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59, tzinfo=timezone.utc) if due_date_str else None
            new_assignment_file = request.files.get('assignment_file')
            update_payload = {'title': title, 'course_id': course_id, 'due_date': due_date_dt}

            if new_assignment_file and new_assignment_file.filename != '':
                old_file_path_part = assignment_data.get('file_url', '').split('/static/', 1)[-1]
                if old_file_path_part:
                    old_file_path = os.path.join(current_app.root_path, 'static', old_file_path_part.replace('/', os.sep))
                    if os.path.exists(old_file_path):
                        try: os.remove(old_file_path); print(f"--- Deleted old assignment file: {old_file_path} ---")
                        except OSError as e: print(f"--- Error deleting old file {old_file_path}: {e} ---")

                filename = secure_filename(new_assignment_file.filename)
                course_upload_dir = os.path.join(current_app.root_path, 'static/uploads', course_id)
                file_path = os.path.join(course_upload_dir, filename)
                os.makedirs(course_upload_dir, exist_ok=True)
                new_assignment_file.save(file_path)
                file_url = url_for('static', filename=f'uploads/{course_id}/{filename}')
                update_payload['file_url'] = file_url
                update_payload['filename'] = filename
            
            assignment_ref.update(update_payload)
            flash('Assignment updated successfully!', 'success')
            return redirect(url_for('assignments.teacher_list'))
        except ValueError:
             flash('Invalid date format for due date. Please use YYYY-MM-DD.', 'error')
        except Exception as e:
            flash(f'Error updating assignment: {e}', 'error')
            traceback.print_exc()

    return render_template('edit_assignment.html',
                           assignment=assignment_data,
                           assignment_id=assignment_id,
                           teacher_courses=teacher_courses)


# --- TEACHER: DELETE ASSIGNMENT ---
@assignments_bp.route('/delete/<string:assignment_id>', methods=['POST'])
@teacher_required
def delete_assignment(assignment_id):
    teacher_user_id = session.get('user_id')
    assignment_ref = db.collection('assignments').document(assignment_id)
    try:
        assignment = assignment_ref.get()
        if not assignment.exists or assignment.to_dict().get('teacher_id') != teacher_user_id:
            flash('Assignment not found or you do not have permission to delete it.', 'error')
            return redirect(url_for('assignments.teacher_list'))
        assignment_data = assignment.to_dict()
        file_path_part = assignment_data.get('file_url', '').split('/static/', 1)[-1]
        if file_path_part:
            file_path = os.path.join(current_app.root_path, 'static', file_path_part.replace('/', os.sep))
            if os.path.exists(file_path):
                try: os.remove(file_path); print(f"--- Deleted assignment file: {file_path} ---")
                except OSError as e: print(f"--- Error deleting file {file_path}: {e} ---")
        assignment_ref.delete()
        flash('Assignment deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting assignment: {e}', 'error')
        traceback.print_exc()
    return redirect(url_for('assignments.teacher_list'))


# --- TEACHER: VIEW SUBMISSIONS FOR AN ASSIGNMENT ---
@assignments_bp.route('/submissions/<string:assignment_id>')
@teacher_required
def view_submissions(assignment_id):
    teacher_user_id = session.get('user_id')
    try:
        assignment_ref = db.collection('assignments').document(assignment_id)
        assignment = assignment_ref.get()
        if not assignment.exists or assignment.to_dict().get('teacher_id') != teacher_user_id:
            flash('Assignment not found or you do not have permission to view it.', 'error')
            return redirect(url_for('assignments.teacher_list'))
        assignment_data = assignment.to_dict()

        course_id = assignment_data.get('course_id')
        course_doc = db.collection('courses').document(course_id).get()
        course_name = course_doc.to_dict().get('name', 'N/A') if course_doc.exists else 'Unknown Course'
        enrolled_student_ids = course_doc.to_dict().get('enrolled_students', []) if course_doc.exists else []
        
        submissions_query = db.collection('submissions').where('assignment_id', '==', assignment_id).stream()
        submissions_map = {sub.to_dict()['student_id']: sub.to_dict() | {'id': sub.id} for sub in submissions_query}

        students_with_submissions = []
        if enrolled_student_ids:
            student_refs = [db.collection('students').document(sid).get() for sid in enrolled_student_ids]
            for ref in student_refs:
                if ref.exists:
                    student_data = ref.to_dict()
                    student_data['id'] = ref.id
                    student_data['submission'] = submissions_map.get(ref.id, None)
                    students_with_submissions.append(student_data)
            students_with_submissions.sort(key=lambda x: x.get('name', ''))
            
    except Exception as e:
        flash(f'Error loading submissions: {e}. Check index errors.', 'error')
        traceback.print_exc()
        return redirect(url_for('assignments.teacher_list'))

    return render_template('assignment_submissions.html',
                           assignment=assignment_data,
                           assignment_id=assignment_id, # <-- Added this missing line
                           course_name=course_name,
                           students_with_submissions=students_with_submissions)

# --- TEACHER: SAVE GRADES FOR SUBMISSIONS ---
@assignments_bp.route('/submissions/<string:assignment_id>/save_grades', methods=['POST'])
@teacher_required
def save_grades(assignment_id):
    try:
        student_ids = request.form.getlist('student_ids')
        batch = db.batch()
        grades_saved_count = 0

        for student_id in student_ids:
            grade = request.form.get(f'grade-{student_id}')
            submission_doc_id = f"{assignment_id}_{student_id}"
            submission_ref = db.collection('submissions').document(submission_doc_id)
            
            if grade: 
                # Convert grade to number if possible
                try:
                    grade_value = float(grade)
                    batch.update(submission_ref, {'grade': grade_value})
                    grades_saved_count += 1
                except ValueError:
                    flash(f"Invalid grade '{grade}' for student {student_id}. Must be a number.", 'error')
            else:
                # If grade is blank, we can remove it (optional)
                # from google.cloud import firestore
                # batch.update(submission_ref, {'grade': firestore.DELETE_FIELD})
                pass 
        
        batch.commit()
        
        if grades_saved_count > 0:
            flash(f'Successfully saved {grades_saved_count} grade(s).', 'success')

    except Exception as e:
        flash(f'Error saving grades: {e}', 'error')
        traceback.print_exc()

    return redirect(url_for('assignments.view_submissions', assignment_id=assignment_id))