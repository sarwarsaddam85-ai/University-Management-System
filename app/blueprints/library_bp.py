from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app import db
from app.decorators import admin_required, login_required # Make sure login_required is included
import datetime
from datetime import timezone # <-- Import timezone
import traceback # For detailed error printing

# --- Define Penalty Rate ---
PENALTY_RATE_PER_DAY = 0.50 # Example: $0.50 per day overdue
# -------------------------

# Define the blueprint
library_bp = Blueprint(
    'library',
    __name__,
    template_folder='../templates/library'
)

# --- ADMIN: LIST ALL BOOKS ---
@library_bp.route('/books')
@admin_required
def book_list():
    books = []
    try:
        books_ref = db.collection('books').order_by('title').stream()
        for book in books_ref:
            books.append(book.to_dict() | {'id': book.id})
    except Exception as e:
        flash(f'Error fetching books: {e}', 'error')
    return render_template('book_list.html', books=books)

# --- ADMIN: ADD NEW BOOK ---
@library_bp.route('/books/add', methods=['GET', 'POST'])
@admin_required
def add_book():
    if request.method == 'POST':
        try:
            title = request.form.get('title')
            author = request.form.get('author')
            isbn = request.form.get('isbn')
            quantity_total = int(request.form.get('quantity_total', 0))

            if not title or not author:
                flash('Book Title and Author are required.', 'error')
                return redirect(request.url)

            quantity_available = quantity_total # Starts equal to total

            book_data = {
                'title': title, 'author': author, 'isbn': isbn,
                'quantity_total': quantity_total,
                'quantity_available': quantity_available,
                'added_at': datetime.datetime.now(timezone.utc) # Use timezone-aware UTC
            }
            db.collection('books').add(book_data)
            flash('Book added successfully!', 'success')
            return redirect(url_for('library.book_list'))
        except ValueError:
             flash('Invalid input for Quantity. Please enter a whole number.', 'error')
        except Exception as e:
            flash(f'Error adding book: {e}', 'error')
    return render_template('book_form.html', form_action='add', book={})

# --- ADMIN: EDIT BOOK ---
@library_bp.route('/books/edit/<string:book_id>', methods=['GET', 'POST'])
@admin_required
def edit_book(book_id):
    book_ref = db.collection('books').document(book_id)
    if request.method == 'POST':
        try:
            title = request.form.get('title')
            author = request.form.get('author')
            isbn = request.form.get('isbn')
            quantity_total = int(request.form.get('quantity_total', 0))

            if not title or not author:
                flash('Book Title and Author are required.', 'error')
                return redirect(request.url)

            update_data = {
                'title': title, 'author': author, 'isbn': isbn,
                'quantity_total': quantity_total,
            }
            book_ref.update(update_data)
            flash('Book updated successfully!', 'success')
            return redirect(url_for('library.book_list'))
        except ValueError:
             flash('Invalid input for Quantity. Please enter a whole number.', 'error')
        except Exception as e:
            flash(f'Error updating book: {e}', 'error')

    # GET Request
    try:
        book = book_ref.get()
        if not book.exists:
            flash('Book not found.', 'error')
            return redirect(url_for('library.book_list'))
        book_data = book.to_dict()
        book_data.setdefault('quantity_total', 0)
    except Exception as e:
        flash(f'Error fetching book data: {e}', 'error')
        return redirect(url_for('library.book_list'))
    return render_template('book_form.html', form_action='edit', book=book_data, book_id=book_id)


# --- ADMIN: DELETE BOOK ---
@library_bp.route('/books/delete/<string:book_id>', methods=['POST'])
@admin_required
def delete_book(book_id):
    try:
        # Add check later: prevent delete if book is currently issued
        db.collection('books').document(book_id).delete()
        flash('Book deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting book: {e}', 'error')
    return redirect(url_for('library.book_list'))

# --- ADMIN: ISSUE BOOK PAGE & ACTION (NO Transaction - For Debugging) ---
@library_bp.route('/issue', methods=['GET', 'POST'])
@admin_required
def issue_book():
    if request.method == 'POST':
        book_ref = None
        try:
            student_id = request.form.get('student_id')
            book_id = request.form.get('book_id')
            due_date_str = request.form.get('due_date')

            if not student_id or not book_id or not due_date_str:
                flash('Student, Book, and Due Date are required.', 'error')
                return redirect(request.url)

            # Convert due_date string to datetime object (naive first)
            due_date_naive = datetime.datetime.strptime(due_date_str, '%Y-%m-%d')
            # Make it timezone-aware (assume UTC or local timezone as appropriate for deadline)
            # For simplicity, let's treat the deadline as end of day UTC
            due_date = due_date_naive.replace(tzinfo=timezone.utc, hour=23, minute=59, second=59)
            issue_date = datetime.datetime.now(timezone.utc) # Use timezone-aware UTC

            book_ref = db.collection('books').document(book_id)
            issue_ref = db.collection('book_issues').document()

            # --- Perform Operations Sequentially ---
            book_snapshot = book_ref.get()
            if not book_snapshot.exists: raise ValueError("Book not found.")
            book_data = book_snapshot.to_dict()
            available = book_data.get('quantity_available', 0)
            if available <= 0: raise ValueError("No copies of this book are currently available.")

            book_ref.update({'quantity_available': available - 1})

            issue_data = {
                'book_id': book_id, 'student_id': student_id,
                'issue_date': issue_date, 'due_date': due_date,
                'return_date': None, 'status': 'Issued'
            }
            issue_ref.set(issue_data)
            # --- End Sequential Operations ---

            flash('Book issued successfully!', 'success')
            return redirect(url_for('library.book_list'))

        except ValueError as ve:
             flash(f'Error issuing book: {ve}', 'error')
             return redirect(request.url)
        except Exception as e:
            flash(f'An unexpected error occurred: {e}', 'error')
            traceback.print_exc()
            return redirect(url_for('library.book_list'))

    # --- SHOW THE FORM (GET) ---
    try:
        students_ref = db.collection('students').order_by('name').stream()
        students = [s.to_dict() | {'id': s.id} for s in students_ref]
        books_ref = db.collection('books').where('quantity_available', '>', 0).order_by('title').stream()
        available_books = [b.to_dict() | {'id': b.id} for b in books_ref]
        default_due_date = (datetime.date.today() + datetime.timedelta(weeks=2)).strftime("%Y-%m-%d")
    except Exception as e:
        flash(f'Error loading issue form data: {e}. Check for Firebase index errors.', 'error')
        students = []; available_books = []
        default_due_date = datetime.date.today().strftime("%Y-%m-%d")

    return render_template('issue_book.html',
                           students=students,
                           available_books=available_books,
                           default_due_date=default_due_date)

# --- ADMIN: VIEW ISSUED BOOKS (Includes Penalty Calculation - TZ Fixed) ---
@library_bp.route('/issued')
@admin_required
def view_issued_books():
    issued_books = []
    student_cache = {}
    book_cache = {}
    now_aware = datetime.datetime.now(timezone.utc) # Use timezone-aware UTC

    try:
        # Fetch records with status 'Issued', order by due date
        issues_ref = db.collection('book_issues').where('status', '==', 'Issued').order_by('due_date').stream()

        for issue in issues_ref:
            issue_data = issue.to_dict()
            issue_data['id'] = issue.id
            student_id = issue_data.get('student_id')
            book_id = issue_data.get('book_id')

            # Fetch Student Details (Cached)
            if student_id not in student_cache:
                student_doc = db.collection('students').document(student_id).get()
                student_cache[student_id] = student_doc.to_dict() if student_doc.exists else {'name': 'Unknown', 'roll_no': 'N/A'}
            issue_data['student_name'] = student_cache[student_id].get('name')
            issue_data['student_roll_no'] = student_cache[student_id].get('roll_no')

            # Fetch Book Title (Cached)
            if book_id not in book_cache:
                book_doc = db.collection('books').document(book_id).get()
                book_cache[book_id] = book_doc.to_dict().get('title', 'Unknown Book') if book_doc.exists else 'Unknown Book'
            issue_data['book_title'] = book_cache.get(book_id)

            # --- Calculate Penalty (TZ Aware) ---
            due_date = issue_data.get('due_date') # Firestore dates are UTC aware
            issue_data['penalty'] = 0.0
            issue_data['is_overdue'] = False
            if isinstance(due_date, datetime.datetime) and due_date < now_aware:
                 issue_data['is_overdue'] = True
                 # Calculate days overdue using date part
                 days_overdue = (now_aware.date() - due_date.date()).days
                 if days_overdue > 0:
                     issue_data['penalty'] = days_overdue * PENALTY_RATE_PER_DAY
            # --- End Penalty Calculation ---

            issued_books.append(issue_data)

    except Exception as e:
        flash(f'Error fetching issued books: {e}. Check for Firebase index errors.', 'error')

    return render_template('issued_books.html', issued_books=issued_books)


# --- ADMIN: RETURN BOOK ACTION ---
@library_bp.route('/return/<string:issue_id>', methods=['POST'])
@admin_required
def return_book(issue_id):
    issue_ref = db.collection('book_issues').document(issue_id)
    book_ref = None

    try:
        # --- Perform Operations Sequentially (NO Transaction) ---
        # 1. Get issue record
        issue_snapshot = issue_ref.get()
        if not issue_snapshot.exists: raise ValueError("Issue record not found.")
        issue_data = issue_snapshot.to_dict()
        if issue_data.get('status') == 'Returned':
            flash('This book has already been marked as returned.', 'info')
            return redirect(url_for('library.view_issued_books'))

        # 2. Get book reference
        book_id = issue_data.get('book_id')
        if not book_id: raise ValueError("Book ID missing from issue record.")
        book_ref = db.collection('books').document(book_id)

        # 3. Update issue record
        issue_ref.update({
            'status': 'Returned',
            'return_date': datetime.datetime.now(timezone.utc) # Use timezone-aware UTC
        })

        # 4. Increment book quantity
        book_snapshot = book_ref.get()
        if book_snapshot.exists:
            current_available = book_snapshot.to_dict().get('quantity_available', 0)
            book_ref.update({'quantity_available': current_available + 1})
        else:
             flash(f'Warning: Book record (ID: {book_id}) not found. Quantity not updated.', 'warning')
        # --- End Sequential Operations ---

        flash('Book marked as returned successfully!', 'success')

    except ValueError as ve:
        flash(f'Error returning book: {ve}', 'error')
    except Exception as e:
        flash(f'An unexpected error occurred while returning the book: {e}', 'error')
        traceback.print_exc()

    return redirect(url_for('library.view_issued_books'))

# --- STUDENT: VIEW MY ISSUED BOOKS (Includes Penalty Calculation - TZ Fixed) ---
@library_bp.route('/my_issued')
@login_required
def my_issued_books():
    student_id = session.get('user_id')
    my_issued_books = []
    book_cache = {}
    now_aware = datetime.datetime.now(timezone.utc) # Use timezone-aware UTC

    try:
        # Fetch issue records for student, status 'Issued', order by due date
        issues_ref = db.collection('book_issues') \
            .where('student_id', '==', student_id) \
            .where('status', '==', 'Issued') \
            .order_by('due_date') \
            .stream()

        for issue in issues_ref:
            issue_data = issue.to_dict()
            issue_data['id'] = issue.id
            book_id = issue_data.get('book_id')

            # Fetch Book Details (Cached)
            if book_id not in book_cache:
                book_doc = db.collection('books').document(book_id).get()
                book_cache[book_id] = book_doc.to_dict() if book_doc.exists else {'title': 'Unknown', 'author': 'N/A'}
            issue_data['book_title'] = book_cache[book_id].get('title')
            issue_data['book_author'] = book_cache[book_id].get('author')

            # --- Calculate Penalty (TZ Aware) ---
            due_date = issue_data.get('due_date') # Firestore dates are UTC aware
            issue_data['penalty'] = 0.0
            issue_data['is_overdue'] = False
            if isinstance(due_date, datetime.datetime) and due_date < now_aware:
                 issue_data['is_overdue'] = True
                 days_overdue = (now_aware.date() - due_date.date()).days
                 if days_overdue > 0:
                     issue_data['penalty'] = days_overdue * PENALTY_RATE_PER_DAY
            # --- End Penalty Calculation ---

            my_issued_books.append(issue_data)

    except Exception as e:
        flash(f'Error fetching your issued books: {e}. Check for Firebase index errors.', 'error')

    return render_template('my_issued_books.html', my_issued_books=my_issued_books)