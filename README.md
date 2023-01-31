# FlaskyTask
A task tracker / todo list written in Flask using a Mongo Atlas back end

FlaskyTask allows you to:

* Display all tasks by priority, or urgency
* Enter new tasks with names, project, descriptions and due dates
* Update existing tasks to set as completed or to edit existing fields
* Search for tasks by name or description

## Installation

```pip install -r requirements.txt```

## Running App

Copy sample.env to .env and modify with connection string to your Atlas instance

```flask -e .env run```


## Atlas Search Index Mapping

```
{
  "analyzer": "lucene.english",
  "searchAnalyzer": "lucene.english",
  "mappings": {
    "dynamic": false,
    "fields": {
      "status": {
        "analyzer": "lucene.keyword",
        "searchAnalyzer": "lucene.keyword",
        "type": "string"
      },
      "task_desc": {
        "analyzer": "lucene.english",
        "searchAnalyzer": "lucene.english",
        "type": "string"
      },
      "task_name": {
        "analyzer": "lucene.english",
        "searchAnalyzer": "lucene.english",
        "type": "string"
      },
      "task_project": {
        "analyzer": "lucene.english",
        "searchAnalyzer": "lucene.english",
        "type": "string"
      }
    }
  }
}
```

