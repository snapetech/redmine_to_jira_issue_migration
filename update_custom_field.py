import requests
import base64
import json
import os

# Jira settings
JIRA_URL = 'https://jira.url'
JIRA_USERNAME = 'email@address.foo'
JIRA_API_TOKEN = 'jira_api' 
OUTPUT_FILE = "jira_fields_output.json"
JIRA_PROJECT_KEY = 'PROJECT_ID'
CUSTOM_FIELD_ID = 'customfield_10083' #custom field to be mirrored

# Basic Authorization header for Jira
auth_str = f"{JIRA_USERNAME}:{JIRA_API_TOKEN}"
base64_auth_str = base64.b64encode(auth_str.encode()).decode("utf-8")
headers = {
    'Authorization': f'Basic {base64_auth_str}',
    'Accept': 'application/json',
    'Content-Type': 'application/json'
}

# Redmine settings
REDMINE_URL = 'https://redmine.url'
REDMINE_API_TOKEN = 'api_redmine'  # Replace with your actual API token
PROJECT_ID = 'redmine-project'

# Redmine Authentication Header
REDMINE_HEADERS = {
    'X-Redmine-API-Key': REDMINE_API_TOKEN
}

def get_all_fields():
    response = requests.get(f'{JIRA_URL}/rest/api/2/field', headers=headers)
    if response.status_code != 200:
        print(f"Error! Received status code {response.status_code}: {response.text}")
        return {}

    fields = response.json()
    field_data = {}
    for field in fields:
        field_info = {
            "Field Name": field['name'],
            "Custom": field.get('custom', False)
        }
        if 'schema' in field:
            schema = field['schema']
            field_info["Schema Type"] = schema.get('type', 'N/A')
            items = schema.get('items')
            if items:
                field_info["Schema Items"] = items
            custom = schema.get('custom')
            if custom:
                field_info["Custom Type"] = custom
        field_data[field['id']] = field_info
    return field_data

def get_issues_from_project(project_key):
    jql = f'project="{project_key}"'
    start_at = 0
    max_results = 100
    all_issues = []
    
    while True:
        response = requests.get(f'{JIRA_URL}/rest/api/2/search?jql={jql}&startAt={start_at}&maxResults={max_results}', headers=headers)
        if response.status_code != 200:
            print(f"Error fetching issues! Received status code {response.status_code}: {response.text}")
            break

        issues = response.json().get('issues', [])
        if not issues:
            break
        all_issues.extend(issues)
        start_at += max_results

    return all_issues

def get_redmine_issues(project_id):
    all_redmine_issues = []
    for status_id in range(1, 26):  # Iterate through status IDs from 1 to 25
        start_offset = 0
        limit = 100

        while True:
            redmine_url = f'{REDMINE_URL}/issues.json?project_id={project_id}&status_id={status_id}&limit={limit}&offset={start_offset}'
            response = requests.get(redmine_url, headers=REDMINE_HEADERS)

            if response.status_code != 200:
                print(f"Error for status ID {status_id}! Received status code {response.status_code}: {response.text}")
                break  # Skip to the next status ID if there's an error

            redmine_issues = response.json().get('issues', [])
            if not redmine_issues:
                break  # Break if there are no more issues for this status ID

            all_redmine_issues.extend(redmine_issues)
            total_count = response.json().get('total_count', 0)
            start_offset += limit

            if start_offset >= total_count:
                break

    return all_redmine_issues

def normalize(text):
    return text.lower().replace(" ", "")

def update_jira_issue(issue_key, custom_field_id, value):
    jira_issue_url = f'{JIRA_URL}/rest/api/2/issue/{issue_key}'
    value = str(value)
    jira_issue_data = {"fields": {custom_field_id: value}}
    response = requests.put(jira_issue_url, json=jira_issue_data, headers=headers)
    if response.status_code != 204:
        print(f"Error updating Jira issue {issue_key}! Received status code {response.status_code}: {response.text}")

if __name__ == "__main__":
    fields = get_all_fields()

    issues = get_issues_from_project(JIRA_PROJECT_KEY)
    jira_summaries = [normalize(issue['fields']['summary']) for issue in issues]

    redmine_issues = get_redmine_issues(PROJECT_ID)
    redmine_issues_found = 0
    redmine_issues_with_additional_info = 0

    for redmine_issue in redmine_issues:
        redmine_issue_subject = normalize(redmine_issue['subject'])
        if redmine_issue_subject in jira_summaries:
            redmine_issues_found += 1
            steps_to_reproduce = next((field['value'] for field in redmine_issue['custom_fields'] if field['id'] == 1), '')
            if steps_to_reproduce:
                redmine_issues_with_additional_info += 1
                jira_issue = next(issue for issue in issues if normalize(issue['fields']['summary']) == redmine_issue_subject)
                update_jira_issue(jira_issue['key'], CUSTOM_FIELD_ID, steps_to_reproduce)

    print(f"Jira Issues Total: {len(issues)}")
    print(f"Jira Issues With Data: {redmine_issues_with_additional_info}")
    print(f"Redmine Issues Total: {len(redmine_issues)}")
    print(f"Redmine Issues Found in Jira: {redmine_issues_found}")
    print("Script completed successfully!")
