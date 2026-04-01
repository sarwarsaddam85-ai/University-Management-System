from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app import db
from app.decorators import admin_required # Only admins manage hostel rooms
import datetime
import traceback

# Define the blueprint
hostel_bp = Blueprint(
    'hostel',
    __name__,
    template_folder='../templates/hostel'
)

# --- ADMIN: LIST ALL HOSTEL ROOMS ---
@hostel_bp.route('/rooms')
@admin_required
def room_list():
    rooms = []
    try:
        # Fetch all rooms, order by room number
        rooms_ref = db.collection('hostel_rooms').order_by('room_number').stream()
        for room in rooms_ref:
            room_data = room.to_dict()
            room_data['id'] = room.id
            # Calculate current occupancy
            room_data['occupancy'] = len(room_data.get('students_assigned', []))
            rooms.append(room_data)
            
    except Exception as e:
        flash(f'Error fetching hostel rooms: {e}. Check index errors.', 'error')
        traceback.print_exc()

    return render_template('room_list.html', rooms=rooms)

# --- ADMIN: ADD NEW ROOM ---
@hostel_bp.route('/rooms/add', methods=['GET', 'POST'])
@admin_required
def add_room():
    if request.method == 'POST':
        try:
            room_number = request.form.get('room_number')
            capacity = int(request.form.get('capacity', 0))
            hostel_block = request.form.get('hostel_block', '') # e.g., 'A Block'

            if not room_number or capacity <= 0:
                flash('Room Number and a valid Capacity are required.', 'error')
                return redirect(request.url)

            room_data = {
                'room_number': room_number,
                'capacity': capacity,
                'hostel_block': hostel_block,
                'students_assigned': [], # Starts empty
                'created_at': datetime.datetime.now(datetime.timezone.utc)
            }
            db.collection('hostel_rooms').add(room_data)
            flash('Hostel room created successfully!', 'success')
            return redirect(url_for('hostel.room_list'))

        except ValueError:
             flash('Invalid input for Capacity. Please enter a whole number.', 'error')
        except Exception as e:
            flash(f'Error adding room: {e}', 'error')
            traceback.print_exc()

    # --- SHOW THE FORM (GET) ---
    return render_template('room_form.html', form_action='add', room={})

# --- ADMIN: EDIT ROOM ---
@hostel_bp.route('/rooms/edit/<string:room_id>', methods=['GET', 'POST'])
@admin_required
def edit_room(room_id):
    room_ref = db.collection('hostel_rooms').document(room_id)

    if request.method == 'POST':
        try:
            room_number = request.form.get('room_number')
            capacity = int(request.form.get('capacity', 0))
            hostel_block = request.form.get('hostel_block', '')

            if not room_number or capacity <= 0:
                flash('Room Number and a valid Capacity are required.', 'error')
                return redirect(request.url)

            # Note: This does not check if new capacity is less than current occupancy.
            # Admin must be careful, or we add a check later.
            update_data = {
                'room_number': room_number,
                'capacity': capacity,
                'hostel_block': hostel_block,
            }
            room_ref.update(update_data)
            flash('Room details updated successfully!', 'success')
            return redirect(url_for('hostel.room_list'))

        except ValueError:
             flash('Invalid input for Capacity. Please enter a whole number.', 'error')
        except Exception as e:
            flash(f'Error updating room: {e}', 'error')
            traceback.print_exc()

    # --- SHOW THE EDIT FORM (GET) ---
    try:
        room = room_ref.get()
        if not room.exists:
            flash('Room not found.', 'error')
            return redirect(url_for('hostel.room_list'))
        room_data = room.to_dict()
    except Exception as e:
        flash(f'Error fetching room data: {e}', 'error')
        return redirect(url_for('hostel.room_list'))

    return render_template('room_form.html', 
                           form_action='edit', 
                           room=room_data, 
                           room_id=room_id)

# --- ADMIN: DELETE ROOM ---
@hostel_bp.route('/rooms/delete/<string:room_id>', methods=['POST'])
@admin_required
def delete_room(room_id):
    try:
        room_ref = db.collection('hostel_rooms').document(room_id)
        room_data = room_ref.get().to_dict()
        
        # Safety Check: Don't delete a room if students are assigned
        if room_data.get('students_assigned'):
             flash('Cannot delete room. Please re-assign all students first.', 'error')
             return redirect(url_for('hostel.room_list'))

        room_ref.delete()
        flash('Room deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting room: {e}', 'error')
        traceback.print_exc()

    return redirect(url_for('hostel.room_list'))

# --- (Routes for assigning students will be added next) ---