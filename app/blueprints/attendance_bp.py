from flask import Blueprint, render_template, request, redirect, url_for, session, flash, make_response, current_app, jsonify
from app import db
from app.decorators import teacher_required, admin_required, login_required
from datetime import date, datetime, timezone
import io
import csv
import face_recognition
import pickle
import numpy as np
import cv2
import os
import traceback # <-- This line is now included

# Define the blueprint
attendance_bp = Blueprint(
    'attendance', 
    __name__, 
    template_folder='../templates/attendance'
)

# --- TEACHER'S PAGE ---
@attendance_bp.route('/mark', methods=['GET', 'POST'])
@teacher_required
def mark_attendance():
    teacher_user_id = session.get('user_id')
    
    # Find all courses assigned to this logged-in teacher
    try:
        courses_ref = db.collection('courses').where('teacher_id', '==', teacher_user_id).stream()
        teacher_courses = [course.to_dict() | {'id': course.id} for course in courses_ref]
    except Exception as e:
        flash(f'Error fetching your courses: {e}', 'error')
        teacher_courses = []

    # --- SAVE ATTENDANCE (POST) ---
    if request.method == 'POST':
        try:
            course_id = request.form['course_id']
            attendance_date = request.form['attendance_date']
            
            # Create a unique ID for this attendance sheet
            sheet_id = f"{course_id}_{attendance_date}"
            
            # Get all student IDs and their status
            student_statuses = {}
            for key, value in request.form.items():
                if key.startswith('status_'):
                    student_id = key.split('_')[1]
                    student_statuses[student_id] = value # 'present' or 'absent'

            # Save the data to Firestore
            attendance_data = {
                'course_id': course_id,
                'date': attendance_date,
                'students': student_statuses
            }
            db.collection('attendance').document(sheet_id).set(attendance_data)
            
            flash('Attendance saved successfully!', 'success')
            # Redirect to the main manual attendance page
            return redirect(url_for('attendance.mark_attendance'))
            
        except Exception as e:
            flash(f'Error saving attendance: {e}', 'error')

    # --- SHOW PAGE (GET) ---
    selected_course_id = request.args.get('course_id')
    student_list = []
    course_name = ""
    today = date.today().strftime("%Y-%m-%d")

    if selected_course_id:
        try:
            # 1. Get the course
            course_doc = db.collection('courses').document(selected_course_id).get()
            if not course_doc.exists:
                flash('Course not found.', 'error')
                return redirect(url_for('attendance.mark_attendance'))
            
            course_data = course_doc.to_dict()
            course_name = course_data.get('name')
            
            # 2. Get enrolled students
            enrolled_ids = course_data.get('enrolled_students', [])
            if enrolled_ids:
                # Fetch all students in the list
                student_refs = [db.collection('students').document(sid).get() for sid in enrolled_ids]
                for ref in student_refs:
                    if ref.exists:
                        student_list.append(ref.to_dict() | {'id': ref.id})
            
        except Exception as e:
            flash(f'Error fetching students: {e}', 'error')

    return render_template('mark_attendance.html', 
                           teacher_courses=teacher_courses, 
                           student_list=student_list,
                           selected_course_id=selected_course_id,
                           course_name=course_name,
                           today=today)


# --- ADMIN'S REPORT PAGE ---
@attendance_bp.route('/report', methods=['GET'])
@admin_required
def view_report():
    try:
        # Get all courses for the dropdown
        all_courses_ref = db.collection('courses').stream()
        all_courses = [course.to_dict() | {'id': course.id} for course in all_courses_ref]
        
        # Get all students and map ID to Name for the report
        students_ref = db.collection('students').stream()
        students_map = {s.id: s.to_dict().get('name', 'N/A') for s in students_ref}
        
    except Exception as e:
        flash(f'Error fetching data: {e}', 'error')
        all_courses = []
        students_map = {}

    selected_course_id = request.args.get('course_id')
    attendance_records = []
    course_name = ""

    if selected_course_id:
        try:
            # Get course name
            course_name = db.collection('courses').document(selected_course_id).get().to_dict().get('name', '')
            
            # Get all attendance for this course, ordered by date
            records_ref = db.collection('attendance').where('course_id', '==', selected_course_id).order_by('date', direction='DESCENDING').stream()
            for record in records_ref:
                attendance_records.append(record.to_dict())
                
        except Exception as e:
            flash(f'Error fetching report: {e}', 'error')

    return render_template('view_report.html',
                           all_courses=all_courses,
                           attendance_records=attendance_records,
                           selected_course_id=selected_course_id,
                           course_name=course_name,
                           students_map=students_map)

# --- ADMIN'S DOWNLOAD REPORT ROUTE ---
@attendance_bp.route('/report/download/<string:course_id>')
@admin_required
def download_report(course_id):
    try:
        # 1. Get Course Name
        course = db.collection('courses').document(course_id).get()
        if not course.exists:
            flash('Course not found.', 'error')
            return redirect(url_for('attendance.view_report'))
        course_name = course.to_dict().get('name', 'Report')

        # 2. Get Student Map (ID -> Name, Roll No)
        students_ref = db.collection('students').stream()
        students_map = {s.id: s.to_dict() for s in students_ref}

        # 3. Get Attendance Records
        records_ref = db.collection('attendance').where('course_id', '==', course_id).order_by('date', direction='DESCENDING').stream()
        attendance_records = [record.to_dict() for record in records_ref]

        # 4. Create CSV in memory
        si = io.StringIO()
        writer = csv.writer(si)

        # Write Header
        writer.writerow(['Date', 'Student Name', 'Roll No.', 'Status'])

        # Write Data
        for record in attendance_records:
            date = record.get('date')
            for student_id, status in record.get('students', {}).items():
                student_info = students_map.get(student_id, {})
                student_name = student_info.get('name', 'Unknown Student')
                student_roll = student_info.get('roll_no', 'N/A')
                writer.writerow([date, student_name, student_roll, status])

        # 5. Prepare and send the response
        output = make_response(si.getvalue())
        filename = f"{course_name.replace(' ', '_')}_attendance_report.csv"
        output.headers["Content-Disposition"] = f"attachment; filename={filename}"
        output.headers["Content-type"] = "text/csv"
        return output

    except Exception as e:
        flash(f'Error generating report: {e}', 'error')
        return redirect(url_for('attendance.view_report'))

# --- STUDENT'S "VIEW MY ATTENDANCE" PAGE (per course) ---
@attendance_bp.route('/my_attendance/<string:course_id>')
@login_required
def view_my_attendance(course_id):
    student_id = session.get('user_id')
    attendance_data = []
    course_name = "Course Not Found"
    now_aware = datetime.now(timezone.utc) # Get timezone-aware time

    try:
        # 1. Verify student enrollment and get course name
        course_doc = db.collection('courses').document(course_id).get()
        if not course_doc.exists or student_id not in course_doc.to_dict().get('enrolled_students', []):
            flash('You are not enrolled in this course or the course does not exist.', 'error')
            return redirect(url_for('dashboard.student_dashboard'))
        course_name = course_doc.to_dict().get('name', 'N/A')

        # 2. Fetch all attendance records for this course
        records_ref = db.collection('attendance').where('course_id', '==', course_id).order_by('date', direction='DESCENDING').stream()

        # 3. Extract this student's status from each record
        for record in records_ref:
            record_data = record.to_dict()
            student_status = record_data.get('students', {}).get(student_id, 'N/A') # Get status or 'N/A'
            attendance_data.append({
                'date': record_data.get('date'),
                'status': student_status
            })

    except Exception as e:
        flash(f'Error fetching your attendance: {e}. Check for Firebase index errors.', 'error')
        pass 

    return render_template('student_attendance_report.html',
                           attendance_data=attendance_data,
                           course_name=course_name)

# --- TEACHER: AUTO ATTENDANCE PAGE (GET) ---
@attendance_bp.route('/auto_attend')
@teacher_required
def auto_attend_page():
    teacher_user_id = session.get('user_id')
    
    # Fetch all courses assigned to this logged-in teacher
    try:
        courses_ref = db.collection('courses').where('teacher_id', '==', teacher_user_id).stream()
        teacher_courses = [course.to_dict() | {'id': course.id} for course in courses_ref]
    except Exception as e:
        flash(f'Error fetching your courses: {e}', 'error')
        teacher_courses = []

    return render_template('auto_attendance.html', teacher_courses=teacher_courses)


# --- TEACHER: AUTO ATTENDANCE (RECOGNIZE FACES - POST) ---
@attendance_bp.route('/recognize', methods=['POST'])
@teacher_required
def recognize_faces():
    print("--- Received request for face recognition ---") # Debug
    try:
        # 1. Load the "known faces" encodings we saved
        encodings_file_path = os.path.join(current_app.root_path, 'static/encodings.dat')
        if not os.path.exists(encodings_file_path):
            print("--- ERROR: encodings.dat file not found. Run training. ---")
            return jsonify({'error': 'Face recognition model is not trained. Please contact admin.'}), 500

        with open(encodings_file_path, 'rb') as f:
            known_data = pickle.load(f)
        known_encodings = known_data['encodings']
        known_student_ids = known_data['student_ids']
        print(f"--- Loaded {len(known_encodings)} known encodings ---") # Debug

        # 2. Get the image file sent from JavaScript
        file_storage = request.files.get('classroom_snapshot')
        if not file_storage:
            print("--- ERROR: No snapshot image received ---")
            return jsonify({'error': 'No snapshot image received.'}), 400

        # Read the image file into an OpenCV format
        filestr = file_storage.read()
        npimg = np.frombuffer(filestr, np.uint8)
        unknown_image = cv2.imdecode(npimg, cv2.IMREAD_COLOR)
        # Convert from BGR (OpenCV default) to RGB (face_recognition default)
        rgb_unknown_image = cv2.cvtColor(unknown_image, cv2.COLOR_BGR2RGB)
        print("--- Snapshot loaded successfully ---") # Debug

        # 3. Find all faces and encodings in the classroom snapshot
        face_locations = face_recognition.face_locations(rgb_unknown_image)
        face_encodings = face_recognition.face_encodings(rgb_unknown_image, face_locations)
        print(f"--- Found {len(face_encodings)} faces in the snapshot ---") # Debug

        recognized_student_ids = set() # Use a set to avoid duplicates

        # 4. Compare each found face to the known encodings
        for face_encoding in face_encodings:
            matches = face_recognition.compare_faces(known_encodings, face_encoding, tolerance=0.6)
            face_distances = face_recognition.face_distance(known_encodings, face_encoding)
            best_match_index = np.argmin(face_distances) 

            if matches[best_match_index]:
                student_id = known_student_ids[best_match_index]
                recognized_student_ids.add(student_id)
        
        print(f"--- Recognized student IDs: {recognized_student_ids} ---") # Debug

        # 5. Fetch student names from the recognized IDs
        recognized_students_list = []
        if recognized_student_ids:
            for student_id in recognized_student_ids:
                student_doc = db.collection('students').document(student_id).get()
                if student_doc.exists:
                    student_data = student_doc.to_dict()
                    recognized_students_list.append({
                        'id': student_id,
                        'name': student_data.get('name', 'N/A'),
                        'roll_no': student_data.get('roll_no', 'N/A')
                    })
        
        # 6. Return the list of recognized students as JSON
        return jsonify({'success': True, 'students': recognized_students_list})

    except Exception as e:
        print(f"---!!! RECOGNITION FAILED: {e} !!!---")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500