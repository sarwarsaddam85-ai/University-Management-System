from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app, make_response
from app import db
from app.decorators import admin_required
import datetime
from werkzeug.utils import secure_filename
import os
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

# Route to list all students
@students_bp.route('/')
@admin_required
def index():
    students_list = []
    all_timetables_dict = {tt['id']: tt['name'] for tt in get_all_timetables()}
    try:
        students_ref = db.collection('students').stream()
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
            
    except Exception as e:
        flash(f'Error fetching students: {e}', 'error')
        
    return render_template('student_list.html', students=students_list)

# Route for adding a new student
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
                'hostel_room_id': hostel_room_id
            }
            student_ref = db.collection('students').document(student_id)
            student_ref.set(data)
            
            if hostel_room_id:
                room_ref = db.collection('hostel_rooms').document(hostel_room_id)
                room_ref.update({
                    'students_assigned': firestore.ArrayUnion([student_id])
                })

            flash('Student added and linked successfully!', 'success')
            return redirect(url_for('students.index'))
        except Exception as e:
            flash(f'Error adding student: {e}', 'error')
            
    student_users = get_student_users()
    all_timetables = get_all_timetables()
    available_rooms = get_available_rooms()
    
    return render_template('student_form.html',
                           form_action='add', student={},
                           student_users=student_users,
                           all_timetables=all_timetables,
                           available_rooms=available_rooms)

# Route for editing a student
@students_bp.route('/edit/<string:student_id>', methods=['GET', 'POST'])
@admin_required
def edit_student(student_id):
    student_ref = db.collection('students').document(student_id)
    
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

            if old_room_id != new_room_id:
                if old_room_id:
                    old_room_ref = db.collection('hostel_rooms').document(old_room_id)
                    old_room_ref.update({
                        'students_assigned': firestore.ArrayRemove([student_id])
                    })
                if new_room_id:
                    new_room_ref = db.collection('hostel_rooms').document(new_room_id)
                    new_room_ref.update({
                        'students_assigned': firestore.ArrayUnion([student_id])
                    })

            flash('Student updated successfully!', 'success')
            return redirect(url_for('students.index'))
        except Exception as e:
            flash(f'Error updating student: {e}', 'error')
            traceback.print_exc()

    student_users = get_student_users()
    all_timetables = get_all_timetables()
    available_rooms = get_available_rooms()
    
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

# Route for deleting a student
@students_bp.route('/delete/<string:student_id>', methods=['POST'])
@admin_required
def delete_student(student_id):
    if request.method == 'POST':
        try:
            student_doc = db.collection('students').document(student_id).get()
            if student_doc.exists:
                old_room_id = student_doc.to_dict().get('hostel_room_id')
                if old_room_id:
                    old_room_ref = db.collection('hostel_rooms').document(old_room_id)
                    old_room_ref.update({
                        'students_assigned': firestore.ArrayRemove([student_id])
                    })

            db.collection('students').document(student_id).delete()
            flash('Student deleted successfully!', 'success')
        except Exception as e:
            flash(f'Error deleting student: {e}', 'error')
            traceback.print_exc()
    else:
        flash('Invalid request method for delete.', 'error')

    return redirect(url_for('students.index'))

# Route for exporting student list to Excel
@students_bp.route('/export/excel')
@admin_required
def export_students_excel():
    try:
        all_timetables_dict = {tt['id']: tt['name'] for tt in get_all_timetables()}
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

        wb = Workbook()
        ws = wb.active
        ws.title = "Student List"
        headers = ["Name", "Linked Email", "Roll No.", "Department", "Semester", "Assigned Timetable", "Contact"]
        ws.append(headers)
        for cell in ws["1:1"]:
            cell.font = openpyxl.styles.Font(bold=True)

        for student in students_list:
            row = [
                student.get('name', 'N/A'), student.get('email', 'N/A'),
                student.get('roll_no', 'N/A'), student.get('department', 'N/A'),
                student.get('semester', 'N/A'), student.get('timetable_name', 'N/A'),
                student.get('contact_info', 'N/A')
            ]
            ws.append(row)

        for col in ws.columns:
            max_length = 0; column = col[0].column_letter
            for cell in col:
                try:
                    if len(str(cell.value)) > max_length: max_length = len(str(cell.value))
                except: pass
            adjusted_width = (max_length + 2)
            ws.column_dimensions[column].width = adjusted_width

        virtual_workbook = io.BytesIO()
        wb.save(virtual_workbook)
        excel_data = virtual_workbook.getvalue()

        response = make_response(excel_data)
        filename = f"Student_List_{datetime.date.today().strftime('%Y%m%d')}.xlsx"
        response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        return response

    except Exception as e:
        flash(f'Error generating Excel report: {e}', 'error')
        traceback.print_exc()
        return redirect(url_for('students.index'))