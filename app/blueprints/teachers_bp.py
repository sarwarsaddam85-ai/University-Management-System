from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app import db
from app.decorators import admin_required

# Define the blueprint
teachers_bp = Blueprint(
    'teachers', 
    __name__, 
    template_folder='../templates/teachers'
)

def get_teacher_users():
    """Helper function to fetch all users with the role 'teacher'."""
    users_list = []
    try:
        # Query the 'users' collection for anyone with role == 'teacher'
        users_ref = db.collection('users').where('role', '==', 'teacher').stream()
        for user in users_ref:
            users_list.append(user.to_dict())
    except Exception as e:
        flash(f'Error fetching teacher users: {e}', 'error')
    return users_list

# Route to list all teachers (READ)
@teachers_bp.route('/')
@admin_required
def index():
    teachers_list = []
    try:
        teachers_ref = db.collection('teachers').stream()
        for teacher in teachers_ref:
            teacher_data = teacher.to_dict()
            teacher_data['id'] = teacher.id
            
            # Get linked user email for display
            user_id = teacher_data.get('user_id')
            if user_id:
                user_doc = db.collection('users').document(user_id).get()
                if user_doc.exists:
                    teacher_data['email'] = user_doc.to_dict().get('email', 'N/A')
                else:
                    teacher_data['email'] = 'User not found'
            else:
                teacher_data['email'] = 'Not Linked'

            teachers_list.append(teacher_data)
            
    except Exception as e:
        flash(f'Error fetching teachers: {e}', 'error')
        
    return render_template('teacher_list.html', teachers=teachers_list)

# Route for adding a new teacher (CREATE)
@teachers_bp.route('/add', methods=['GET', 'POST'])
@admin_required
def add_teacher():
    if request.method == 'POST':
        try:
            data = {
                'name': request.form['name'],
                'user_id': request.form['user_id'], # Store the linked UID
                'department': request.form['department'],
                'subjects': request.form['subjects'] 
            }
            # We will use the 'user_id' as the document ID for the teacher
            # This creates a strong 1-to-1 link
            teacher_ref = db.collection('teachers').document(request.form['user_id'])
            teacher_ref.set(data)
            
            flash('Teacher added and linked successfully!', 'success')
            return redirect(url_for('teachers.index'))
            
        except Exception as e:
            flash(f'Error adding teacher: {e}', 'error')
    
    # GET: Fetch teacher users for the dropdown
    teacher_users = get_teacher_users()
    return render_template('teacher_form.html', form_action='add', teacher={}, teacher_users=teacher_users)

# Route for editing a teacher (UPDATE)
@teachers_bp.route('/edit/<string:teacher_id>', methods=['GET', 'POST'])
@admin_required
def edit_teacher(teacher_id):
    # 'teacher_id' is now the user's UID
    teacher_ref = db.collection('teachers').document(teacher_id)
    
    if request.method == 'POST':
        try:
            updated_data = {
                'name': request.form['name'],
                'user_id': request.form['user_id'], # Store the linked UID
                'department': request.form['department'],
                'subjects': request.form['subjects']
            }
            # Note: If you change the 'user_id', you're linking it to a new user.
            # This logic assumes the 'user_id' link might change.
            # A simpler model would be to use the URL 'teacher_id' and not allow user_id to be edited.
            # But for simplicity, we'll just update.
            teacher_ref.update(updated_data)
            flash('Teacher updated successfully!', 'success')
            return redirect(url_for('teachers.index'))
            
        except Exception as e:
            flash(f'Error updating teacher: {e}', 'error')
    
    # GET: Fetch current data and teacher users
    try:
        teacher = teacher_ref.get()
        if not teacher.exists:
            flash('Teacher not found.', 'error')
            return redirect(url_for('teachers.index'))
        
        teacher_users = get_teacher_users()
        teacher_data = teacher.to_dict()
        teacher_data['id'] = teacher.id # Pass the doc ID
        
        return render_template('teacher_form.html', 
                               form_action='edit', 
                               teacher=teacher_data, 
                               teacher_id=teacher.id, # The doc ID (which is the user_id)
                               teacher_users=teacher_users)
                               
    except Exception as e:
        flash(f'Error fetching teacher: {e}', 'error')
        return redirect(url_for('teachers.index'))

# Route for deleting a teacher (DELETE)
@teachers_bp.route('/delete/<string:teacher_id>', methods=['GET'])
@admin_required
def delete_teacher(teacher_id):
    # 'teacher_id' is now the user's UID
    try:
        db.collection('teachers').document(teacher_id).delete()
        flash('Teacher deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting teacher: {e}', 'error')
        
    return redirect(url_for('teachers.index'))