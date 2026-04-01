from flask import Blueprint, render_template, session, flash, jsonify
from app.decorators import login_required, admin_required, teacher_required
from app import db
import datetime
from datetime import timezone # Import timezone
import traceback

# Define the blueprint
dashboard_bp = Blueprint(
    'dashboard',
    __name__,
    template_folder='../templates/dashboards'
)

# --- Admin Dashboard (with Fee Chart AND Attendance Chart Data) ---
@dashboard_bp.route('/admin')
@admin_required
def admin_dashboard():
    stats = {}
    fee_chart_data = {}
    attendance_chart_data = {} # For Attendance Bar Chart

    try:
        # --- 1. Fetch Stats (Optimized) ---
        students_query = list(db.collection('students').stream())
        courses_query = list(db.collection('courses').stream())
        
        stats['student_count'] = len(students_query)
        stats['teacher_count'] = len(list(db.collection('teachers').stream()))
        stats['course_count'] = len(courses_query)
        
        # --- 2. Process Data for Fee Chart ---
        fee_statuses = {'Paid': 0, 'Unpaid': 0, 'Partially Paid': 0, 'Not Assigned': 0}
        for student in students_query: # Reuse the student query
            status = student.to_dict().get('fee_status', 'Not Assigned')
            if status in fee_statuses:
                fee_statuses[status] += 1
            else:
                 fee_statuses['Not Assigned'] += 1 
        
        fee_chart_data = {
            'labels': list(fee_statuses.keys()),
            'data': list(fee_statuses.values())
        }

        # --- 3. Process Data for Attendance Chart ---
        course_attendance_counts = {} # Format: {course_id: {'present': 0, 'total': 0}}
        course_names = {} # Format: {course_id: 'Course Name'}

        for course in courses_query: # Reuse the course query
            course_id = course.id
            course_names[course_id] = course.to_dict().get('name', 'N/A')
            course_attendance_counts[course_id] = {'present': 0, 'total': 0}

        # Fetch ALL attendance records
        attendance_records = db.collection('attendance').stream()

        for record in attendance_records:
            record_data = record.to_dict()
            course_id = record_data.get('course_id')
            if course_id in course_attendance_counts:
                for student_id, status in record_data.get('students', {}).items():
                    course_attendance_counts[course_id]['total'] += 1
                    if status == 'present':
                        course_attendance_counts[course_id]['present'] += 1
        
        # Calculate percentages
        att_chart_labels = []
        att_chart_data = []
        for course_id, counts in course_attendance_counts.items():
            att_chart_labels.append(course_names.get(course_id, 'Unknown'))
            if counts['total'] > 0:
                percentage = (counts['present'] / counts['total']) * 100
                att_chart_data.append(round(percentage, 1))
            else:
                att_chart_data.append(0) # No attendance taken = 0%
        
        attendance_chart_data = {
            'labels': att_chart_labels,
            'data': att_chart_data
        }
        # --- End Attendance Chart Data ---
        
    except Exception as e:
        flash(f'Error fetching dashboard data: {e}', 'error')
        traceback.print_exc() # Print full error to terminal
        stats = {'student_count': 'N/A', 'teacher_count': 'N/A', 'course_count': 'N/A'}
        fee_chart_data = {'labels': [], 'data': []}
        attendance_chart_data = {'labels': [], 'data': []} # Send empty chart on error
        
    return render_template('admin_dashboard.html', 
                           user_email=session['email'], 
                           stats=stats, 
                           fee_chart_data=fee_chart_data,
                           attendance_chart_data=attendance_chart_data)


# --- Teacher Dashboard (with Schedule and Chart Data) ---
@dashboard_bp.route('/teacher')
@teacher_required
def teacher_dashboard():
    teacher_user_id = session.get('user_id')
    my_courses = []
    my_schedule = {}
    attendance_chart_data = {}
    days_of_week = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    course_ids_for_teacher = []
    course_name_map = {}

    try:
        # --- 1. Fetch Assigned Courses ---
        courses_ref = db.collection('courses').where('teacher_id', '==', teacher_user_id).stream()
        for course in courses_ref:
            course_data = course.to_dict(); course_data['id'] = course.id
            course_id = course.id
            enrolled_ids = course_data.get('enrolled_students', [])
            course_data['student_count'] = len(enrolled_ids)
            my_courses.append(course_data)
            course_ids_for_teacher.append(course_id)
            course_name_map[course_id] = course_data.get('name', 'N/A')

        # --- 2. Fetch Teacher's Schedule ---
        for day in days_of_week: my_schedule[day] = []
        timetables_ref = db.collection('timetables').stream()
        for tt in timetables_ref:
            schedule = tt.to_dict().get('schedule', {})
            for day, entries in schedule.items():
                if day in days_of_week:
                    teacher_entries = [entry for entry in entries if entry.get('teacher_id') == teacher_user_id]
                    if teacher_entries:
                        my_schedule[day].extend(teacher_entries)
        for day in days_of_week:
            my_schedule[day].sort(key=lambda x: x.get('time_slot', ''))

        # --- 3. Calculate Attendance Chart Data ---
        if course_ids_for_teacher:
            attendance_records = db.collection('attendance').where('course_id', 'in', course_ids_for_teacher).stream()
            course_attendance_counts = {course_id: {'present': 0, 'total': 0} for course_id in course_ids_for_teacher}
            
            for record in attendance_records:
                record_data = record.to_dict()
                course_id = record_data.get('course_id')
                if course_id in course_attendance_counts:
                    for student_id, status in record_data.get('students', {}).items():
                        course_attendance_counts[course_id]['total'] += 1
                        if status == 'present':
                            course_attendance_counts[course_id]['present'] += 1
            
            att_chart_labels = []
            att_chart_data = []
            for course_id, counts in course_attendance_counts.items():
                att_chart_labels.append(course_name_map.get(course_id, 'Unknown'))
                if counts['total'] > 0:
                    percentage = (counts['present'] / counts['total']) * 100
                    att_chart_data.append(round(percentage, 1))
                else:
                    att_chart_data.append(0)
            
            attendance_chart_data = {'labels': att_chart_labels, 'data': att_chart_data}
        else:
             attendance_chart_data = {'labels': [], 'data': []}
        # --- End Attendance Chart Data ---

    except Exception as e:
        flash(f'Error fetching dashboard data: {e}. Check for Firebase index errors.', 'error')
        traceback.print_exc()
        for day in days_of_week: my_schedule[day] = []
        my_courses = []
        attendance_chart_data = {'labels': [], 'data': []}

    return render_template('teacher_dashboard.html',
                           user_email=session['email'],
                           my_courses=my_courses,
                           my_schedule=my_schedule,
                           days_of_week=days_of_week,
                           attendance_chart_data=attendance_chart_data)

# --- Student Dashboard (Corrected) ---
@dashboard_bp.route('/student')
@login_required
def student_dashboard():
    student_id = session.get('user_id')
    
    # --- ## MOVED THIS TO THE TOP ## ---
    # Define variables with default values *before* the try block
    my_courses = []
    recent_quiz_results = []
    recent_assignment_results = []
    student_fee_data = {'fee_assigned': 0.0, 'fee_paid': 0.0, 'fee_status': 'Error'}
    my_schedule = {}
    attendance_percentages = {}
    latest_notifications_by_type = []
    processed_types = set()
    days_of_week = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    for day in days_of_week: my_schedule[day] = [] # Pre-fill schedule
    
    course_cache = {}
    quiz_cache = {}
    assignment_cache = {}
    hostel_room_data = None # <-- Add hostel data
    # --- ## END OF MOVED BLOCK ## ---

    try:
        # --- Fetch student document ---
        student_ref = db.collection('students').document(student_id)
        student_doc = student_ref.get()
        student_data = student_doc.to_dict() if student_doc.exists else {}

        # --- 1. Fetch enrolled courses ---
        course_ids_enrolled_in = []
        courses_query = db.collection('courses').where('enrolled_students', 'array_contains', student_id).stream()
        for course in courses_query:
            course_data = course.to_dict(); course_data['id'] = course.id
            course_id = course.id
            course_ids_enrolled_in.append(course_id)
            course_cache[course_id] = course_data.get('name', 'N/A')
            my_courses.append(course_data)

        # --- 2. Fetch recent quiz submissions ---
        submissions_query = db.collection('quiz_submissions').where('student_id', '==', student_id).order_by('submitted_at', direction='DESCENDING').limit(5).stream()
        for sub in submissions_query:
            submission_data = sub.to_dict(); quiz_id = submission_data.get('quiz_id'); course_id = submission_data.get('course_id')
            if quiz_id not in quiz_cache:
                quiz_doc = db.collection('quizzes').document(quiz_id).get()
                quiz_cache[quiz_id] = quiz_doc.to_dict().get('title', 'N/A') if quiz_doc.exists else 'N/A'
            submission_data['quiz_title'] = quiz_cache.get(quiz_id)
            submission_data['course_name'] = course_cache.get(course_id, 'Unknown Course')
            recent_quiz_results.append(submission_data)
            
        # --- 3. Fetch Recent GRADED Assignments ---
        assignment_subs_query = db.collection('submissions').where('student_id', '==', student_id).order_by('submitted_at', direction='DESCENDING').stream()
        for sub in assignment_subs_query:
            submission_data = sub.to_dict()
            if submission_data.get('grade'): 
                assignment_id = submission_data.get('assignment_id')
                if assignment_id not in assignment_cache:
                    assign_doc = db.collection('assignments').document(assignment_id).get()
                    assignment_cache[assignment_id] = assign_doc.to_dict().get('title', 'N/A') if assign_doc.exists else 'N/A'
                
                submission_data['assignment_title'] = assignment_cache.get(assignment_id)
                recent_assignment_results.append(submission_data)
                if len(recent_assignment_results) == 5: break 

        # --- 4. Extract Fee Data ---
        student_fee_data = {
            'fee_assigned': student_data.get('fee_assigned', 0.0),
            'fee_paid': student_data.get('fee_paid', 0.0),
            'fee_status': student_data.get('fee_status', 'Not Assigned')
        }

        # --- 5. Fetch Student's Timetable ---
        timetable_id = student_data.get('timetable_id')
        if timetable_id:
            tt_doc = db.collection('timetables').document(timetable_id).get()
            if tt_doc.exists:
                my_schedule = tt_doc.to_dict().get('schedule', {})
                for day in days_of_week:
                     if day in my_schedule:
                        my_schedule[day].sort(key=lambda x: x.get('time_slot', ''))
            else: print(f"--- Warning: Timetable ID {timetable_id} assigned to student {student_id} not found. ---")
        
        # --- 6. Calculate Attendance Percentages ---
        if course_ids_enrolled_in:
            attendance_records = db.collection('attendance').where('course_id', 'in', course_ids_enrolled_in).stream()
            course_attendance_counts = {course_id: {'present': 0, 'total': 0} for course_id in course_ids_enrolled_in}
            for record in attendance_records:
                record_data = record.to_dict()
                course_id = record_data.get('course_id')
                student_status = record_data.get('students', {}).get(student_id)
                if course_id in course_attendance_counts:
                    course_attendance_counts[course_id]['total'] += 1
                    if student_status == 'present':
                        course_attendance_counts[course_id]['present'] += 1
            for course_id, counts in course_attendance_counts.items():
                if counts['total'] > 0:
                    percentage = (counts['present'] / counts['total']) * 100
                    attendance_percentages[course_id] = round(percentage, 1)
                else:
                    attendance_percentages[course_id] = None

        # --- 7. Fetch LATEST Notification PER CATEGORY ---
        notif_query = db.collection('notifications') \
            .where('student_id', '==', student_id) \
            .where('is_read', '==', False) \
            .order_by('created_at', direction='DESCENDING') \
            .limit(20) \
            .stream()
        
        for notif_doc in notif_query:
            notification = notif_doc.to_dict() | {'id': notif_doc.id}
            notif_type = notification.get('type', 'general')
            if notif_type not in processed_types:
                latest_notifications_by_type.append(notification)
                processed_types.add(notif_type)
        
        # --- 8. Fetch Hostel Info ---
        hostel_room_id = student_data.get('hostel_room_id')
        if hostel_room_id:
            room_doc = db.collection('hostel_rooms').document(hostel_room_id).get()
            if room_doc.exists:
                hostel_room_data = room_doc.to_dict()

    except Exception as e:
        flash(f'Error fetching dashboard data: {e}. Check for Firebase index errors.', 'error')
        traceback.print_exc() 
        # All variables are already initialized, so the page won't crash

    return render_template('student_dashboard.html',
                           user_email=session['email'],
                           my_courses=my_courses,
                           recent_quiz_results=recent_quiz_results,
                           recent_assignment_results=recent_assignment_results,
                           student_fee_data=student_fee_data,
                           unread_notifications=latest_notifications_by_type, 
                           my_schedule=my_schedule,
                           days_of_week=days_of_week, # Now defined even if try block fails
                           attendance_percentages=attendance_percentages,
                           hostel_room_data=hostel_room_data)

# --- API ROUTE TO GET NOTIFICATIONS ---
@dashboard_bp.route('/notifications/get')
@login_required
def get_notifications():
    student_id = session.get('user_id')
    if not student_id or session.get('role') != 'student':
        return jsonify({'unread_count': 0, 'notifications': []})

    try:
        # Index: student_id (ASC), is_read (ASC), created_at (DESC)
        query = db.collection('notifications') \
            .where('student_id', '==', student_id) \
            .where('is_read', '==', False) \
            .order_by('created_at', direction='DESCENDING')

        all_unread_docs = list(query.stream())
        unread_count = len(all_unread_docs)

        recent_notifications = []
        for doc in all_unread_docs[:5]: # Get first 5
            notif = doc.to_dict()
            created_at_dt = notif.get('created_at')
            date_str = created_at_dt.strftime('%b %d, %Y') if isinstance(created_at_dt, datetime.datetime) else 'Someday'
            
            recent_notifications.append({
                'id': doc.id,
                'message': notif.get('message', 'No message content.'),
                'link': notif.get('link', '#'),
                'created_at': date_str
            })
        
        return jsonify({
            'unread_count': unread_count,
            'notifications': recent_notifications
        })
    except Exception as e:
        print(f"Error fetching notifications: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# --- API ROUTE TO MARK NOTIFICATIONS AS READ ---
@dashboard_bp.route('/notifications/mark_read', methods=['POST'])
@login_required
def mark_read():
    student_id = session.get('user_id')
    if not student_id or session.get('role') != 'student':
        return jsonify({'success': False, 'message': 'Invalid user'}), 403

    try:
        query = db.collection('notifications') \
            .where('student_id', '==', student_id) \
            .where('is_read', '==', False) \
            .stream()

        batch = db.batch()
        doc_count = 0
        for doc in query:
            batch.update(doc.reference, {'is_read': True})
            doc_count += 1
        
        batch.commit()

        print(f"--- Marked {doc_count} notifications as read for student {student_id} ---")
        return jsonify({'success': True, 'marked_read_count': doc_count})
    
    except Exception as e:
        print(f"Error marking notifications as read: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500