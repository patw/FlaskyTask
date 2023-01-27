from flask import Flask, render_template, redirect, url_for, request
from flask_bootstrap import Bootstrap
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, TextAreaField, DateField, SelectField, HiddenField
from wtforms.validators import DataRequired
import os
import pymongo
from bson import ObjectId
from datetime import datetime

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

@app.route('/', methods=['GET', 'POST'])
def index():
    # Load all open tasks
    tasks = col.find({"status": "Open"}).sort("task_priority")
    return render_template('index.html', tasks=tasks)

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

