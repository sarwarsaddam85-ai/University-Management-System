from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app import db
from app.decorators import admin_required # Only admins manage timetables
import datetime
import traceback
from datetime import timezone

# Define the blueprint
timetable_bp = Blueprint(
    'timetable',
    __name__,
    template_folder='../templates/timetables'
)

# --- ADMIN: LIST ALL TIMETABLES ---
@timetable_bp.route('/list')
@admin_required
def timetable_list(): # Colon is definitely here
    timetables = []
    try: # Standard indentation
        # Fetch all timetable documents, order by name
        tt_ref = db.collection('timetables').order_by('name').stream()
        timetables = [tt.to_dict() | {'id': tt.id} for tt in tt_ref]
    except Exception as e:
        flash(f'Error fetching timetables: {e}. Check index errors.', 'error')

    return render_template('timetable_list.html', timetables=timetables)

# --- ADMIN: CREATE NEW TIMETABLE STRUCTURE ---
@timetable_bp.route('/create', methods=['GET', 'POST'])
@admin_required
def create_timetable():
    if request.method == 'POST':
        try:
            name = request.form.get('name')
            description = request.form.get('description', '') # Optional description

            if not name:
                flash('Timetable Name is required.', 'error')
                return redirect(request.url)

            timetable_data = {
                'name': name,
                'description': description,
                'created_at': datetime.datetime.now(timezone.utc), # Use timezone aware
                'schedule': { # Initialize empty schedule structure
                    'Monday': [], 'Tuesday': [], 'Wednesday': [],
                    'Thursday': [], 'Friday': [], 'Saturday': [], 'Sunday': []
                 }
            }
            tt_ref = db.collection('timetables').add(timetable_data)
            new_timetable_id = tt_ref[1].id

            flash('Timetable structure created successfully! Now manage its schedule.', 'success')
            # Redirect to the page for managing this specific timetable's schedule
            return redirect(url_for('timetable.manage_schedule', timetable_id=new_timetable_id))

        except Exception as e:
            flash(f'Error creating timetable: {e}', 'error')

    # --- SHOW THE FORM (GET) ---
    return render_template('timetable_form.html', form_action='create', timetable={})

# --- ADMIN: EDIT TIMETABLE STRUCTURE ---
@timetable_bp.route('/edit/<string:timetable_id>', methods=['GET', 'POST'])
@admin_required
def edit_timetable(timetable_id):
    timetable_ref = db.collection('timetables').document(timetable_id)

    if request.method == 'POST':
        try:
            name = request.form.get('name')
            description = request.form.get('description', '')

            if not name:
                flash('Timetable Name cannot be empty.', 'error')
                return redirect(request.url)

            timetable_ref.update({
                'name': name,
                'description': description
            })
            flash('Timetable details updated successfully!', 'success')
            return redirect(url_for('timetable.timetable_list'))

        except Exception as e:
            flash(f'Error updating timetable: {e}', 'error')

    # GET Request: Fetch current data
    try:
        timetable = timetable_ref.get()
        if not timetable.exists:
            flash('Timetable not found.', 'error')
            return redirect(url_for('timetable.timetable_list'))
        timetable_data = timetable.to_dict()
    except Exception as e:
        flash(f'Error fetching timetable details: {e}', 'error')
        return redirect(url_for('timetable.timetable_list'))

    # Reuse the timetable_form.html template for editing
    return render_template('timetable_form.html',
                           form_action='edit',
                           timetable=timetable_data,
                           timetable_id=timetable_id)

# --- ADMIN: DELETE TIMETABLE STRUCTURE ---
@timetable_bp.route('/delete/<string:timetable_id>', methods=['POST'])
@admin_required
def delete_timetable(timetable_id):
    try:
        timetable_ref = db.collection('timetables').document(timetable_id)
        # Optional but recommended: Delete subcollections (like schedule entries) first if needed
        # For simplicity, we'll just delete the main document now.
        # Be aware this leaves schedule data orphaned if not handled.
        timetable_ref.delete()
        flash('Timetable deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting timetable: {e}', 'error')
        traceback.print_exc() # Print error details to terminal

    return redirect(url_for('timetable.timetable_list'))

# --- ADMIN: MANAGE SCHEDULE FOR A TIMETABLE ---
@timetable_bp.route('/manage/<string:timetable_id>', methods=['GET', 'POST'])
@admin_required
def manage_schedule(timetable_id):
    timetable_ref = db.collection('timetables').document(timetable_id)

    # --- Handle Adding a New Schedule Entry (POST) ---
    if request.method == 'POST':
        try:
            day = request.form.get('day')
            time_slot = request.form.get('time_slot') # e.g., "09:00 - 10:00"
            course_id = request.form.get('course_id')
            teacher_id = request.form.get('teacher_id')
            room_no = request.form.get('room_no', '') # Optional room number

            if not all([day, time_slot, course_id, teacher_id]):
                flash('Day, Time Slot, Course, and Teacher are required.', 'error')
                return redirect(request.url)

            # --- Prepare the new entry data ---
            # Fetch course name and teacher name for storage (makes display easier later)
            course_name = db.collection('courses').document(course_id).get().to_dict().get('name', 'N/A')
            teacher_name = db.collection('teachers').document(teacher_id).get().to_dict().get('name', 'N/A')

            new_entry = {
                'time_slot': time_slot,
                'course_id': course_id,
                'course_name': course_name,
                'teacher_id': teacher_id,
                'teacher_name': teacher_name,
                'room_no': room_no
            }

            # --- Update the specific day's list in the schedule map ---
            # Use FieldValue.array_union to add the entry if it doesn't exist (or just append)
            # For simplicity, we'll read, append, and write (less safe for concurrency)
            current_timetable = timetable_ref.get().to_dict()
            current_schedule = current_timetable.get('schedule', {})
            day_schedule = current_schedule.get(day, [])

            # Optional: Check for conflicts before adding (more complex)

            day_schedule.append(new_entry)
            current_schedule[day] = day_schedule # Put the updated list back

            timetable_ref.update({'schedule': current_schedule})

            flash(f'Schedule entry added for {day} at {time_slot}.', 'success')
            return redirect(request.url) # Reload the same page

        except Exception as e:
            flash(f'Error adding schedule entry: {e}', 'error')
            traceback.print_exc() # Print error to terminal

    # --- Show the Manage Schedule Page (GET) ---
    try:
        # Fetch the timetable
        timetable = timetable_ref.get()
        if not timetable.exists:
            flash('Timetable not found.', 'error')
            return redirect(url_for('timetable.timetable_list'))
        timetable_data = timetable.to_dict()

        # Fetch all courses for the dropdown
        courses_ref = db.collection('courses').order_by('name').stream()
        all_courses = [c.to_dict() | {'id': c.id} for c in courses_ref]

        # Fetch all linked teachers for the dropdown
        teachers_ref = db.collection('teachers').order_by('name').stream()
        all_teachers = [t.to_dict() | {'id': t.id} for t in teachers_ref if t.to_dict().get('user_id')] # Only linked teachers

        # Define days and time slots (customize as needed)
        days_of_week = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        time_slots = [
            "08:00 - 09:00", "09:00 - 10:00", "10:00 - 11:00", "11:00 - 12:00",
            "12:00 - 13:00", "13:00 - 14:00", "14:00 - 15:00", "15:00 - 16:00"
        ]

    except Exception as e:
        flash(f'Error loading schedule data: {e}. Check index errors.', 'error')
        traceback.print_exc() # Print error to terminal
        return redirect(url_for('timetable.timetable_list'))

    return render_template('manage_schedule.html',
                           timetable=timetable_data,
                           timetable_id=timetable_id,
                           all_courses=all_courses,
                           all_teachers=all_teachers,
                           days_of_week=days_of_week,
                           time_slots=time_slots)

# --- Add route to delete a schedule entry ---
@timetable_bp.route('/manage/<string:timetable_id>/delete_entry', methods=['POST'])
@admin_required
def delete_schedule_entry(timetable_id):
    try:
        day = request.form.get('day')
        # We need a unique identifier for the entry to remove it reliably.
        # Let's use the time_slot and course_id as a composite key for now.
        time_slot_to_delete = request.form.get('time_slot')
        course_id_to_delete = request.form.get('course_id')

        if not day or not time_slot_to_delete or not course_id_to_delete:
            flash('Missing data to identify schedule entry for deletion.', 'error')
            return redirect(url_for('timetable.manage_schedule', timetable_id=timetable_id))

        timetable_ref = db.collection('timetables').document(timetable_id)
        current_timetable = timetable_ref.get().to_dict()
        current_schedule = current_timetable.get('schedule', {})
        day_schedule = current_schedule.get(day, [])

        # Find and remove the matching entry
        updated_day_schedule = [
            entry for entry in day_schedule
            if not (entry.get('time_slot') == time_slot_to_delete and entry.get('course_id') == course_id_to_delete)
        ]

        if len(updated_day_schedule) < len(day_schedule): # Check if something was actually removed
            current_schedule[day] = updated_day_schedule
            timetable_ref.update({'schedule': current_schedule})
            flash('Schedule entry deleted.', 'success')
        else:
            flash('Schedule entry not found for deletion.', 'warning')

    except Exception as e:
        flash(f'Error deleting schedule entry: {e}', 'error')
        traceback.print_exc()

    return redirect(url_for('timetable.manage_schedule', timetable_id=timetable_id))

# --- Routes for Teacher/Student Views (Coming Later) ---