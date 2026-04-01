from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app, make_response
from app import db
from app.decorators import admin_required
import datetime
from werkzeug.utils import secure_filename
import os
import face_recognition
import pickle
import traceback
from openpyxl import Workbook
import openpyxl.styles
import io
# We need this import for the delete_student function (to remove from rooms)
from google.cloud import firestore

# Define the blueprint
students_bp = Blueprint(
    'students',
    __name__,
    template_folder='../templates/students'
)

def get_student_users():
    """Helper function to fetch all users with the role 'student'."""
    users_list = []
    try:
        users_ref = db.collection('users').where('role', '==', 'student').stream()
        for user in users_ref:
            users_list.append(user.to_dict())
    except Exception as e:
        flash(f'Error fetching student users: {e}', 'error')
    return users_list

def get_all_timetables():
    """Helper function to fetch all timetable names and IDs."""
    timetables = []
    try:
        tt_ref = db.collection('timetables').order_by('name').stream()
        timetables = [{'id': tt.id, 'name': tt.to_dict().get('name', 'N/A')} for tt in tt_ref]
    except Exception as e:
        flash(f'Error fetching timetables list: {e}', 'error')
    return timetables

# --- ## ADDED HELPER FOR HOSTEL ROOMS ## ---
def get_available_rooms():
    """Helper function to fetch all hostel rooms with available space."""
    available_rooms = []
    try:
        rooms_ref = db.collection('hostel_rooms').order_by('room_number').stream()
        for room in rooms_ref:
            room_data = room.to_dict()
            room_data['id'] = room.id
            occupancy = len(room_data.get('students_assigned', []))
            if occupancy < room_data.get('capacity', 0):
                room_data['occupancy'] = occupancy
                available_rooms.append(room_data)
    except Exception as e:
        flash(f'Error fetching available rooms: {e}. Check index errors.', 'error')
    return available_rooms
# --- ## END HELPER ## ---

# Route to list all students (READ - Updated for Timetable)
@students_bp.route('/')
@admin_required
def index():
    students_list = []
    all_timetables_dict = {tt['id']: tt['name'] for tt in get_all_timetables()}
    try:
        students_ref = db.collection('students').stream()
        for student in students_ref:
            student_data = student.to_dict()
            student_data['id'] = student.id # This is the user_id
            
            user_id = student_data.get('user_id')
            if user_id:
                user_doc = db.collection('users').document(user_id).get()
                student_data['email'] = user_doc.to_dict().get('email', 'N/A') if user_doc.exists else 'User not found'
            else:
                student_data['email'] = 'Not Linked'
                
            # Get timetable name for display
            timetable_id = student_data.get('timetable_id')
            student_data['timetable_name'] = all_timetables_dict.get(timetable_id, 'N/A') if timetable_id else 'N/A'
            
            students_list.append(student_data)
            
    except Exception as e:
        flash(f'Error fetching students: {e}', 'error')
        
    return render_template('student_list.html', students=students_list)

# Route for adding a new student (CREATE - Updated for Timetable & Hostel)
@students_bp.route('/add', methods=['GET', 'POST'])
@admin_required
def add_student():
    if request.method == 'POST':
        try:
            student_id = request.form['user_id']
            hostel_room_id = request.form.get('hostel_room_id') or None
            
            data = {
                'name': request.form['name'],
                'user_id': student_id,
                'roll_no': request.form['roll_no'],
                'department': request.form['department'],
                'semester': request.form['semester'],
                'contact_info': request.form['contact_info'],
                'timetable_id': request.form.get('timetable_id') or None,
                'hostel_room_id': hostel_room_id # <-- Add hostel ID
            }
            student_ref = db.collection('students').document(student_id)
            student_ref.set(data)
            
            # --- Update Room Occupancy ---
            if hostel_room_id:
                room_ref = db.collection('hostel_rooms').document(hostel_room_id)
                room_ref.update({
                    'students_assigned': firestore.ArrayUnion([student_id])
                })
            # --- End Update ---

            flash('Student added and linked successfully!', 'success')
            return redirect(url_for('students.index'))
        except Exception as e:
            flash(f'Error adding student: {e}', 'error')
            
    # GET: Fetch all data for dropdowns
    student_users = get_student_users()
    all_timetables = get_all_timetables()
    available_rooms = get_available_rooms()
    
    return render_template('student_form.html',
                           form_action='add', student={},
                           student_users=student_users,
                           all_timetables=all_timetables,
                           available_rooms=available_rooms) # <-- Pass rooms

# Route for editing a student (UPDATE - Updated for Timetable & Hostel)
@students_bp.route('/edit/<string:student_id>', methods=['GET', 'POST'])
@admin_required
def edit_student(student_id):
    student_ref = db.collection('students').document(student_id)
    
    # Get current student data first to see old room assignment
    try:
        student_doc = student_ref.get()
        if not student_doc.exists:
            flash('Student not found.', 'error')
            return redirect(url_for('students.index'))
        student_data = student_doc.to_dict()
        old_room_id = student_data.get('hostel_room_id')
    except Exception as e:
        flash(f'Error fetching student: {e}', 'error')
        return redirect(url_for('students.index'))

    if request.method == 'POST':
        try:
            new_room_id = request.form.get('hostel_room_id') or None
            updated_data = {
                'name': request.form['name'],
                'user_id': request.form['user_id'],
                'roll_no': request.form['roll_no'],
                'department': request.form['department'],
                'semester': request.form['semester'],
                'contact_info': request.form['contact_info'],
                'timetable_id': request.form.get('timetable_id') or None,
                'hostel_room_id': new_room_id
            }
            student_ref.update(updated_data)

            # --- Update Room Occupancy (Handle room change) ---
            if old_room_id != new_room_id:
                # Remove from old room
                if old_room_id:
                    old_room_ref = db.collection('hostel_rooms').document(old_room_id)
                    old_room_ref.update({
                        'students_assigned': firestore.ArrayRemove([student_id])
                    })
                # Add to new room
                if new_room_id:
                    new_room_ref = db.collection('hostel_rooms').document(new_room_id)
                    new_room_ref.update({
                        'students_assigned': firestore.ArrayUnion([student_id])
                    })
            # --- End Update ---

            flash('Student updated successfully!', 'success')
            return redirect(url_for('students.index'))
        except Exception as e:
            flash(f'Error updating student: {e}', 'error')
            traceback.print_exc()

    # GET request
    try:
        student_users = get_student_users()
        all_timetables = get_all_timetables()
        available_rooms = get_available_rooms()
        
        # Add the student's *current* room to the list if it's "full"
        if old_room_id and old_room_id not in [r['id'] for r in available_rooms]:
             current_room_doc = db.collection('hostel_rooms').document(old_room_id).get()
             if current_room_doc.exists:
                current_room_data = current_room_doc.to_dict()
                current_room_data['id'] = current_room_doc.id
                current_room_data['occupancy'] = len(current_room_data.get('students_assigned', []))
                available_rooms.append(current_room_data)

        return render_template('student_form.html', 
                               form_action='edit', 
                               student=student_data, 
                               student_id=student_id,
                               student_users=student_users,
                               all_timetables=all_timetables,
                               available_rooms=available_rooms)
    except Exception as e:
        flash(f'Error fetching student: {e}', 'error')
        return redirect(url_for('students.index'))

# Route for deleting a student (DELETE - Updated to POST)
@students_bp.route('/delete/<string:student_id>', methods=['POST']) # Changed to POST
@admin_required
def delete_student(student_id):
    # The student_id is the user's UID
    if request.method == 'POST':
        try:
            # --- Remove student from hostel room before deleting ---
            student_doc = db.collection('students').document(student_id).get()
            if student_doc.exists:
                old_room_id = student_doc.to_dict().get('hostel_room_id')
                if old_room_id:
                    old_room_ref = db.collection('hostel_rooms').document(old_room_id)
                    old_room_ref.update({
                        'students_assigned': firestore.ArrayRemove([student_id])
                    })
            # --- End hostel removal ---

            db.collection('students').document(student_id).delete()
            flash('Student deleted successfully!', 'success')
        except Exception as e:
            flash(f'Error deleting student: {e}', 'error')
            traceback.print_exc()
    else:
        flash('Invalid request method for delete.', 'error')

    return redirect(url_for('students.index'))

# --- ADMIN: MANAGE STUDENT FACE DATA ---
@students_bp.route('/manage_faces/<string:student_id>', methods=['GET', 'POST'])
@admin_required
def manage_faces(student_id):
    student_ref = db.collection('students').document(student_id)
    training_dir = os.path.join(current_app.root_path, 'static/training_images', student_id)
    os.makedirs(training_dir, exist_ok=True)

    if request.method == 'POST':
        uploaded_files = request.files.getlist('face_images')
        if not uploaded_files or uploaded_files[0].filename == '':
            flash('No files selected.', 'error')
            return redirect(request.url)
        file_count = 0
        try:
            for file in uploaded_files:
                if file and file.filename != '':
                    filename = secure_filename(file.filename)
                    file_path = os.path.join(training_dir, filename)
                    file.save(file_path)
                    file_count += 1
            flash(f'{file_count} new image(s) uploaded successfully!', 'success')
            return redirect(request.url)
        except Exception as e:
            flash(f'Error uploading images: {e}', 'error')

    # GET Request
    try:
        student = student_ref.get()
        if not student.exists:
            flash('Student not found.', 'error')
            return redirect(url_for('students.index'))
        student_data = student.to_dict()

        existing_images = []
        if os.path.exists(training_dir):
            for filename in os.listdir(training_dir):
                if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                    file_url = url_for('static', filename=f'training_images/{student_id}/{filename}')
                    existing_images.append(file_url)
    except Exception as e:
        flash(f'Error loading page: {e}', 'error')
        return redirect(url_for('students.index'))

    return render_template('manage_faces.html', 
                           student=student_data, 
                           student_id=student_id,
                           existing_images=existing_images)

# --- ADMIN: TRAIN FACE RECOGNITION MODEL ---
@students_bp.route('/train_faces')
@admin_required
def train_faces():
    print("--- Starting Face Training Process ---")
    training_images_dir = os.path.join(current_app.root_path, 'static/training_images')
    encodings_file_path = os.path.join(current_app.root_path, 'static/encodings.dat')
    known_encodings = []
    known_student_ids = []
    try:
        if not os.path.exists(training_images_dir):
             flash('Training images directory not found. Upload images first.', 'error')
             return redirect(url_for('dashboard.admin_dashboard'))

        for student_id_folder in os.listdir(training_images_dir):
            student_dir_path = os.path.join(training_images_dir, student_id_folder)
            if not os.path.isdir(student_dir_path): continue
            print(f"--- Training on student ID: {student_id_folder} ---")
            for image_name in os.listdir(student_dir_path):
                image_path = os.path.join(student_dir_path, image_name)
                try:
                    image = face_recognition.load_image_file(image_path)
                    face_encodings = face_recognition.face_encodings(image)
                    if face_encodings:
                        encoding = face_encodings[0]
                        known_encodings.append(encoding)
                        known_student_ids.append(student_id_folder)
                        print(f"    ... processed {image_name}")
                    else:
                        print(f"    ... WARNING: No face found in {image_name}")
                except Exception as e:
                    print(f"    ... ERROR processing {image_name}: {e}")

        print(f"--- Training complete. Found {len(known_encodings)} total encodings. Saving... ---")
        data_to_save = {"encodings": known_encodings, "student_ids": known_student_ids}
        with open(encodings_file_path, 'wb') as f:
            pickle.dump(data_to_save, f)
        print(f"--- Encodings saved to {encodings_file_path} ---")
        flash(f'Face recognition training complete! Processed {len(known_encodings)} images.', 'success')
    except Exception as e:
        flash(f'An error occurred during training: {e}', 'error')
        print(f"---!!! TRAINING FAILED: {e} !!!---")
        traceback.print_exc()
    return redirect(url_for('dashboard.admin_dashboard'))


# --- ADMIN: EXPORT STUDENT LIST TO EXCEL ---
@students_bp.route('/export/excel')
@admin_required
def export_students_excel():
    try:
        # 1. Fetch timetables to map IDs to Names
        all_timetables_dict = {tt['id']: tt['name'] for tt in get_all_timetables()}

        # 2. Fetch all student data
        students_list = []
        students_ref = db.collection('students').order_by('name').stream()
        for student in students_ref:
            student_data = student.to_dict()
            student_data['id'] = student.id
            user_id = student_data.get('user_id')
            if user_id:
                user_doc = db.collection('users').document(user_id).get()
                student_data['email'] = user_doc.to_dict().get('email', 'N/A') if user_doc.exists else 'User not found'
            else:
                student_data['email'] = 'Not Linked'
            timetable_id = student_data.get('timetable_id')
            student_data['timetable_name'] = all_timetables_dict.get(timetable_id, 'N/A') if timetable_id else 'N/A'
            students_list.append(student_data)

        # 3. Create Excel workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Student List"
        headers = ["Name", "Linked Email", "Roll No.", "Department", "Semester", "Assigned Timetable", "Contact"]
        ws.append(headers)
        for cell in ws["1:1"]:
            cell.font = openpyxl.styles.Font(bold=True)

        # Write Data
        for student in students_list:
            row = [
                student.get('name', 'N/A'), student.get('email', 'N/A'),
                student.get('roll_no', 'N/A'), student.get('department', 'N/A'),
                student.get('semester', 'N/A'), student.get('timetable_name', 'N/A'),
                student.get('contact_info', 'N/A')
            ]
            ws.append(row)

        # Adjust widths
        for col in ws.columns:
            max_length = 0; column = col[0].column_letter
            for cell in col:
                try:
                    if len(str(cell.value)) > max_length: max_length = len(str(cell.value))
                except: pass
            adjusted_width = (max_length + 2)
            ws.column_dimensions[column].width = adjusted_width

        # 4. Save to memory buffer
        virtual_workbook = io.BytesIO()
        wb.save(virtual_workbook)
        excel_data = virtual_workbook.getvalue()

        # 5. Create Response
        response = make_response(excel_data)
        filename = f"Student_List_{datetime.date.today().strftime('%Y%m%d')}.xlsx"
        response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        return response

    except Exception as e:
        flash(f'Error generating Excel report: {e}', 'error')
        traceback.print_exc()
        return redirect(url_for('students.index'))