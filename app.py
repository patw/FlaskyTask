from flask import Flask, render_template, redirect, url_for, request, session
from flask_bootstrap import Bootstrap
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, TextAreaField, DateField, SelectField, IntegerField, PasswordField
from wtforms.validators import DataRequired, NumberRange
import os
import json
import pymongo
from bson import ObjectId
from datetime import datetime, timedelta
from dotenv import load_dotenv
import functools

# Get environment variables
load_dotenv()

# Create the Flask app object
app = Flask(__name__)

# Need this for storing anything in session object
app.config['SECRET_KEY'] = os.environ["SECRET_KEY"]

# Load users from .env file
users_string = os.environ["USERS"]
users = json.loads(users_string)

# Connect to mongo
conn = os.environ["MONGO_CON"]
database = os.environ["MONGO_DB"]
collection = os.environ["MONGO_COL"]
client = pymongo.MongoClient(conn)
db = client[database]
col = db[collection]

# Make it pretty because I can't :(
Bootstrap(app)

# Flask forms is magic
class TaskForm(FlaskForm):
    task_name = StringField('Task Name', validators=[DataRequired()])
    task_project = StringField('Task Category')
    task_priority = SelectField(
        'Priority', choices=[(2, 'Normal'), (1, 'Urgent'), (3, 'Low')])
    task_desc = TextAreaField('Task Description')
    task_due = DateField('Task Due')
    task_repeat = IntegerField('Repeat Every X Days', validators=[
                               NumberRange(min=1, max=365)])
    submit = SubmitField('Submit')

# Amazing
class SearchForm(FlaskForm):
    search_string = StringField('Search', validators=[DataRequired()])
    submit = SubmitField('Submit')

# Astounding
class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

# Atlas search query for task search
# Lucene english analyzer, boosting on task name over description
# and searching on project name with bury
# Compound filter on open/closed with a min match of 1 in the shoulds
def search_tasks(search_string, closed):

    # For the search filter
    if closed:
        status = "Closed"
    else:
        status = "Open"

    search_query = [
        {
            "$search": {
                "compound": {
                    "should": [{
                        "text": {
                            "query": search_string,
                            "path": "task_name",
                            "score": {"boost": {"value": 2}}
                        }
                    },
                        {
                        "text": {
                            "query": search_string,
                            "path": "task_desc"
                        }
                    },
                        {
                        "text": {
                            "query": search_string,
                            "path": "task_project",
                            "score": {"boost": {"value": 0.3}}
                        }
                    }],
                    "minimumShouldMatch": 1,
                    "filter": [{
                        "text": {
                            "query": status,
                            "path": "status"
                        }
                    }]
                }
            }
        },
        {
            "$limit": 25
        },
        {
            "$project": {
                "_id": 1,
                "task_name": 1,
                "task_project": 1,
                "task_priority": 1,
                "task_due": 1,
                "task_desc": 1,
                "score": {"$meta": "searchScore"}
            }
        }]

    return col.aggregate(search_query)

# Define a decorator to check if the user is authenticated
# No idea how this works...
def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if session.get("user") is None:
            return redirect(url_for('login'))
        return view(**kwargs)
    return wrapped_view

# The default task view, ordered by priority and highlighted in red if overdue
@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    # User wants open tasks or closed tasks
    closed = request.args.get("closed")

    # We're doing a search here
    form = SearchForm()
    if request.method == "POST":
        form_result = request.form.to_dict(flat=True)
        # Wildcard search across multiple paths, normal english tokens
        tasks = search_tasks(form_result["search_string"], closed)
        return render_template('search.html', tasks=tasks)

    # Query the task list by open or closed status
    if closed:
        task_query = col.find({"status": "Closed"}).sort("task_priority")
    else:
        task_query = col.find({"status": "Open"}).sort("task_priority")

    # Process the output data with some dynamic fields
    tasks = []
    for task_item in task_query:
        task_item["overdue"] = False
        # Find out if tasks are overdue so they can be marked in red
        if task_item["task_due"]:
            due = datetime.strptime(task_item["task_due"], "%Y-%m-%d")
            today = datetime.now()
            if (today - due).days >= 0:
                task_item["overdue"] = True
        tasks.append(task_item)

    # Spit out the template
    return render_template('index.html', tasks=tasks, form=form)

# Create or edit tasks
@app.route('/task', methods=['GET', 'POST'])
@app.route('/task/<id>', methods=['GET', 'POST'])
@login_required
def task(id=None):
    form = TaskForm()
    if request.method == "POST":
        # Get the form result back and clean up the data set
        form_result = request.form.to_dict(flat=True)
        form_result.pop('csrf_token')
        form_result.pop('submit')
        form_result["status"] = "Open"
        form_result["task_priority"] = int(form_result["task_priority"])

        # If they set a repeat on a task, and not a due date, we can fix that
        if form_result["task_repeat"] != "" and form_result["task_due"] == "":
            tomorrow = datetime.now() + timedelta(days=1)
            form_result["task_due"] = str(tomorrow.date())

        # Store the result in mongo collection
        if id:
            col.replace_one({'_id': ObjectId(id)}, form_result)
        else:
            col.insert_one(form_result)
            # Back to the task view
        return redirect("/")
    else:
        if id:
            task = col.find_one({'_id': ObjectId(id)})
            form.task_name.data = task["task_name"]
            form.task_desc.data = task["task_desc"]
            form.task_priority.data = task["task_priority"]
            form.task_project.data = task["task_project"]
            if "task_repeat" in task:
                form.task_repeat.data = task["task_repeat"]
            if task["task_due"]:
                date_object = datetime.strptime(
                    task["task_due"], "%Y-%m-%d").date()
                form.task_due.data = date_object
    return render_template('task.html', form=form)

# Task is done!  Set it's status to Closed
@app.route('/task_close/<id>')
@login_required
def task_close(id):
    update_doc = {
        "status": "Closed",
        "closed_on": datetime.now()
    }

    task_data = col.find_one({'_id': ObjectId(id)})
    # We need to have a due date and a repeat in X days value set
    # If we do set the task_reopen_date field so we can run a task
    # in the background to open this task again
    if "task_repeat" in task_data and "task_due" in task_data:
        if task_data["task_repeat"] != "" and "task_due" != "":
            days_to_push = int(task_data["task_repeat"])
            due_date = datetime.strptime(task_data["task_due"], "%Y-%m-%d")
            task_reopen_date = due_date + timedelta(days=days_to_push)
            update_doc["task_reopen_date"] = task_reopen_date

    # Now we close the task and mark the date it closed
    col.update_one({'_id': ObjectId(id)}, {"$set": update_doc})
    return redirect('/')

# Tasks can only go up to 1 or down to 3
# Terrible... why do I do these things.
@app.route('/task_up/<id>')
@login_required
def task_up(id):
    task_status = {"$set": {"task_priority": 1}}
    col.update_one({'_id': ObjectId(id)}, task_status)
    return redirect('/')

# This is awful
@app.route('/task_down/<id>')
@login_required
def task_down(id):
    task_status = {"$set": {"task_priority": 3}}
    col.update_one({'_id': ObjectId(id)}, task_status)
    return redirect('/')

# Reschedules tasks next week when clicking on the date
# Why 7 days?  No idea.  Seems fine.
@app.route('/task_reschedule/<id>')
@login_required
def task_reschedule(id):
    # Set new due date 7 days ahead
    new_date = datetime.now() + timedelta(days=7)
    task_due = {"$set": {"task_due": str(new_date.date()), "status": "Open"}}
    col.update_one({'_id': ObjectId(id)}, task_due)
    return redirect('/')

# Login/logout routes that rely on the user being stored in session
@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        if form.username.data in users:
            if form.password.data == users[form.username.data]:
                session["user"] = form.username.data
                return redirect(url_for('index'))
    return render_template('login.html', form=form)


@app.route('/logout')
def logout():
    session["user"] = None
    return redirect(url_for('login'))

# Called from cron with curl to re-open tasks that need to come back
# should be safe to call manually
@app.route('/cron')
def cron():
    closed_tasks_to_open = {
        "status": "Closed",
        "task_reopen_date": {'$lte': datetime.now()}
    }
    task_status = {
        "$set": {
            "status": "Open",
            "task_reopen_date": "",
            "task_due": str(datetime.now().date())
        }
    }
    col.update_many(closed_tasks_to_open, task_status)
    return {"status": "Done"}
