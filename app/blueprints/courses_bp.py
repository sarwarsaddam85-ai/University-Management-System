from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app import db
from app.decorators import admin_required

# Define the blueprint
courses_bp = Blueprint(
    'courses', 
    __name__, 
    template_folder='../templates/courses'
)

def get_all_teachers():
    """Helper function to fetch all teachers for dropdowns."""
    teachers_list = []
    try:
        teachers_ref = db.collection('teachers').stream()
        for teacher in teachers_ref:
            teachers_list.append({
                'id': teacher.id,
                'name': teacher.to_dict().get('name', 'Unnamed Teacher')
            })
    except Exception as e:
        flash(f'Error fetching teachers list: {e}', 'error')
    return teachers_list

# Route to list all courses (READ)
@courses_bp.route('/')
@admin_required
def index():
    courses_list = []
    try:
        courses_ref = db.collection('courses').stream()
        for course in courses_ref:
            course_data = course.to_dict()
            course_data['id'] = course.id
            
            # Fetch the assigned teacher's name
            teacher_id = course_data.get('teacher_id')
            if teacher_id:
                teacher_doc = db.collection('teachers').document(teacher_id).get()
                if teacher_doc.exists:
                    course_data['teacher_name'] = teacher_doc.to_dict().get('name', 'N/A')
                else:
                    course_data['teacher_name'] = 'Teacher Not Found'
            else:
                course_data['teacher_name'] = 'Not Assigned'
                
            courses_list.append(course_data)
            
    except Exception as e:
        flash(f'Error fetching courses: {e}', 'error')
        
    return render_template('course_list.html', courses=courses_list)

# Route for adding a new course (CREATE)
@courses_bp.route('/add', methods=['GET', 'POST'])
@admin_required
def add_course():
    if request.method == 'POST':
        try:
            data = {
                'name': request.form['name'],
                'course_code': request.form['course_code'],
                'department': request.form['department'],
                'teacher_id': request.form['teacher_id'] # Store the teacher's UID
            }
            db.collection('courses').add(data)
            flash('Course added successfully!', 'success')
            return redirect(url_for('courses.index'))
            
        except Exception as e:
            flash(f'Error adding course: {e}', 'error')
            
    # GET request: Fetch teachers for the form
    teachers = get_all_teachers()
    return render_template('course_form.html', form_action='add', course={}, teachers=teachers)

# Route for editing a course (UPDATE)
@courses_bp.route('/edit/<string:course_id>', methods=['GET', 'POST'])
@admin_required
def edit_course(course_id):
    course_ref = db.collection('courses').document(course_id)
    
    if request.method == 'POST':
        try:
            updated_data = {
                'name': request.form['name'],
                'course_code': request.form['course_code'],
                'department': request.form['department'],
                'teacher_id': request.form['teacher_id']
            }
            course_ref.update(updated_data)
            flash('Course updated successfully!', 'success')
            return redirect(url_for('courses.index'))
            
        except Exception as e:
            flash(f'Error updating course: {e}', 'error')
    
    # GET request: Fetch course data and teachers list
    try:
        course = course_ref.get()
        if not course.exists:
            flash('Course not found.', 'error')
            return redirect(url_for('courses.index'))
            
        teachers = get_all_teachers()
        return render_template('course_form.html', 
                               form_action='edit', 
                               course=course.to_dict(), 
                               course_id=course_id,
                               teachers=teachers)
                               
    except Exception as e:
        flash(f'Error fetching course: {e}', 'error')
        return redirect(url_for('courses.index'))

# Route for deleting a course (DELETE)
@courses_bp.route('/delete/<string:course_id>', methods=['GET'])
@admin_required
def delete_course(course_id):
    try:
        db.collection('courses').document(course_id).delete()
        flash('Course deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting course: {e}', 'error')
        
    return redirect(url_for('courses.index'))

# Route for enrolling students in a course
@courses_bp.route('/enroll/<string:course_id>', methods=['GET', 'POST'])
@admin_required
def enroll_students(course_id):
    course_ref = db.collection('courses').document(course_id)
    
    try:
        course = course_ref.get()
        if not course.exists:
            flash('Course not found.', 'error')
            return redirect(url_for('courses.index'))
        
        course_data = course.to_dict()

        if request.method == 'POST':
            # Get the list of student IDs from the form's checkboxes
            enrolled_ids = request.form.getlist('student_ids')
            
            # Update the course document with this list of student IDs
            course_ref.update({
                'enrolled_students': enrolled_ids
            })
            
            flash('Student enrollment updated successfully!', 'success')
            return redirect(url_for('courses.index'))

        # --- GET Request Logic ---
        # 1. Get all students from the 'students' collection
        all_students = []
        students_ref = db.collection('students').stream()
        for student in students_ref:
            student_data = student.to_dict()
            student_data['id'] = student.id
            all_students.append(student_data)
        
        # 2. Get the list of students already enrolled
        enrolled_student_ids = course_data.get('enrolled_students', [])
        
        return render_template('enroll_students.html', 
                               course=course_data, 
                               all_students=all_students,
                               enrolled_student_ids=enrolled_student_ids)

    except Exception as e:
        flash(f'An error occurred: {e}', 'error')
        return redirect(url_for('courses.index'))