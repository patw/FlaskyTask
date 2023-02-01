from flask import Flask, render_template, redirect, url_for, request
from flask_bootstrap import Bootstrap
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, TextAreaField, DateField, SelectField, HiddenField
from wtforms.validators import DataRequired
import os
import pymongo
from bson import ObjectId
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Get environment variables
load_dotenv()

app = Flask(__name__)

app.config['SECRET_KEY'] = os.environ["SECRET_KEY"]

# Connect to mongo
conn = os.environ["MONGO_CON"]
database = os.environ["MONGO_DB"]
collection = os.environ["MONGO_COL"]
client = pymongo.MongoClient(conn)
db = client[database]
col = db[collection]

# Make it pretty because I can't :(
Bootstrap(app)

class TaskForm(FlaskForm):
    task_name = StringField('Task Name', validators=[DataRequired()])
    task_project = StringField('Task Category')
    task_priority = SelectField('Priority', choices=[(2, 'Normal'), (1, 'Urgent'), (3, 'Low')])
    task_desc = TextAreaField('Task Description')
    task_due = DateField('Task Due')
    submit = SubmitField('Submit')

class SearchForm(FlaskForm):
    search_string = StringField('Search', validators=[DataRequired()])
    submit = SubmitField('Submit')

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
                        "score": { "boost": { "value": 2 } } 
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
                        "score": { "boost": { "value": 0.3 } } 
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


@app.route('/', methods=['GET', 'POST'])
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

@app.route('/task', methods=['GET', 'POST'])
@app.route('/task/<id>', methods=['GET', 'POST'])
def task(id=None):
    form = TaskForm()
    if request.method == "POST":
        # Get the form result back and clean up the data set
        form_result = request.form.to_dict(flat=True)
        form_result.pop('csrf_token')
        form_result.pop('submit')
        form_result["status"] = "Open"
        form_result["task_priority"] = int(form_result["task_priority"])

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
            if task["task_due"]:
                date_object = datetime.strptime(task["task_due"], "%Y-%m-%d" ).date()
                form.task_due.data = date_object
    return render_template('task.html',form=form)

@app.route('/task_close/<id>')
def task_close(id):
    task_status = { "$set": { "status": "Closed" } }
    col.update_one({'_id': ObjectId(id)}, task_status)
    return redirect('/')

@app.route('/task_up/<id>')
def task_up(id):
    task_status = { "$set": { "task_priority": 1 } }
    col.update_one({'_id': ObjectId(id)}, task_status)
    return redirect('/')

@app.route('/task_down/<id>')
def task_down(id):
    task_status = { "$set": { "task_priority": 3 } }
    col.update_one({'_id': ObjectId(id)}, task_status)
    return redirect('/')

@app.route('/task_reschedule/<id>')
def task_reschedule(id):
    # Set new due date 7 days ahead
    new_date = datetime.now() + timedelta(days = 7)
    task_due = { "$set": { "task_due": str(new_date.date()) } }
    col.update_one({'_id': ObjectId(id)}, task_due)
    return redirect('/')
