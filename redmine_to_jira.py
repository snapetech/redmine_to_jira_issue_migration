import requests
import json
import logging
import base64
from io import BytesIO

# Configure logging to capture API responses
logging.basicConfig(filename='migration.log', level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

REDMINE_URL = 'https://path.to.host'
API_TOKEN = 'api_redmine'
PROJECT_ID = 'redmine-oroject'
HEADERS = {'X-Redmine-API-Key': API_TOKEN}

JIRA_URL = 'https://jira.host'
JIRA_USERNAME = 'email@login.foo'
JIRA_API_TOKEN = 'api_jira'
JIRA_PROJECT_KEY = 'PROJECT_KEY'
ISSUE_TYPE_ID = '10010' #bug reports

field_mapping = {
    'Languages': 'customfield_10001',
    'Platforms': 'customfield_10002',
    'Platform': 'customfield_10003',
    'Severity': 'customfield_10004',
    'Reproducibility': 'customfield_10005',
    'Steps to reproduce': 'customfield_10006',
    'Reported on build': 'customfield_10007',
    'Claim fixed on build': 'customfield_10008'
##
}

def get_redmine_issue_attachments(issue_id):
    url = f'{REDMINE_URL}/issues/{issue_id}.json?include=attachments'
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        attachments = response.json()['issue']['attachments']
        return attachments
    else:
        logging.error(f'Failed to fetch attachments for Redmine issue {issue_id}: {response.text}')
        return []

def download_attachment(attachment_url):
    response = requests.get(attachment_url, headers=HEADERS)
    return BytesIO(response.content) if response.status_code == 200 else None

def get_redmine_issues(page=1):
    url = f'{REDMINE_URL}/projects/{PROJECT_ID}/issues.json?status_id=*&page={page}'
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        issues = response.json()['issues']
        logging.info(f'Retrieved {len(issues)} issues from Redmine (page {page}).')
        return issues
    else:
        logging.error(f'Failed to fetch Redmine issues on page {page}: {response.text}')
        return []

def get_jira_severity_values():
    auth_str = f'{JIRA_USERNAME}:{JIRA_API_TOKEN}'
    auth_str_base64 = base64.b64encode(auth_str.encode('utf-8')).decode('utf-8')

    url = f'{JIRA_URL}/rest/api/3/field/customfield_10073/options'
    headers = {
        "Accept": "application/json",
        "Authorization": f'Basic {auth_str_base64}'
    }

    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        logging.error(f'Failed to fetch Jira severity values: {response.text}')
        return None

def probe_additional_info_and_steps(issue_id):
    url = f'{REDMINE_URL}/issues/{issue_id}.json'
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        issue_data = response.json()['issue']
        additional_info = ''
        steps_to_reproduce = ''

        for custom_field in issue_data.get('custom_fields', []):
            if custom_field['name'] == 'Additional information':
                additional_info = custom_field['value']
            if custom_field['name'] == 'Steps to reproduce':
                steps_to_reproduce = custom_field['value']

        return additional_info, steps_to_reproduce
    else:
        logging.error(f'Failed to fetch Redmine issue {issue_id}: {response.text}')
        return '', ''

def populate_custom_fields(jira_issue_id, redmine_issue):
    auth_str = f'{JIRA_USERNAME}:{JIRA_API_TOKEN}'
    auth_str_base64 = base64.b64encode(auth_str.encode('utf-8')).decode('utf-8')

    url = f'{JIRA_URL}/rest/api/3/issue/{jira_issue_id}'
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f'Basic {auth_str_base64}'
    }

    additional_info, steps_to_reproduce = probe_additional_info_and_steps(redmine_issue['id'])

    custom_fields_data = {}
    for redmine_custom_field in redmine_issue.get('custom_fields', []):
        if 'value' in redmine_custom_field:
            jira_custom_field = field_mapping.get(redmine_custom_field['name'])
            if jira_custom_field:
                custom_field_value = redmine_custom_field['value']

                logging.debug(f'Working on custom field: {redmine_custom_field["name"]}')
                logging.debug(f'Original value: {custom_field_value}')

                if jira_custom_field == 'customfield_10073':
                    jira_severity_values = get_jira_severity_values()
                    if jira_severity_values:
                        valid_severity_ids = [option['id'] for option in jira_severity_values]
                        if custom_field_value in valid_severity_ids:
                            custom_field_value = {"id": custom_field_value}
                        else:
                            logging.error(f'Invalid Severity value: {custom_field_value}')
                            continue

                if jira_custom_field in ('customfield_10080', 'customfield_10081', 'customfield_10082'):
                    custom_field_value = [{'value': value} for value in custom_field_value]
                    custom_fields_data[jira_custom_field] = custom_field_value
                    logging.debug(f'Populating {jira_custom_field} with value: {custom_fields_data[jira_custom_field]}')

                if jira_custom_field == 'customfield_10035':
                    custom_fields_data[jira_custom_field] = [{"version": 1, "type": "doc", "content": [{"type": "paragraph", "content": [{"text": additional_info, "type": "text"}]}]}]

                if jira_custom_field == 'customfield_10034':
                    custom_fields_data[jira_custom_field] = steps_to_reproduce

    payload = {
        "fields": custom_fields_data
    }

    response = requests.put(url, json=payload, headers=headers)
    if response.status_code == 204:
        logging.info(f'Successfully populated custom fields for Jira issue ID {jira_issue_id}')
    else:
        logging.error(f'Failed to populate custom fields for Jira issue ID {jira_issue_id}')
        logging.error(f'Error details: {response.text}')

def create_jira_issue(redmine_issue):
    auth_str = f'{JIRA_USERNAME}:{JIRA_API_TOKEN}'
    auth_str_base64 = base64.b64encode(auth_str.encode('utf-8')).decode('utf-8')

    url = f'{JIRA_URL}/rest/api/3/issue'
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f'Basic {auth_str_base64}'
    }

    additional_info, steps_to_reproduce = probe_additional_info_and_steps(redmine_issue['id'])

    description_adf = {
        "version": 1,
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"text": redmine_issue.get('description', ''), "type": "text"}
                ]
            }
        ]
    }

    payload = {
        "fields": {
            "project": {"key": JIRA_PROJECT_KEY},
            "issuetype": {"id": ISSUE_TYPE_ID},
            "summary": redmine_issue['subject'],
            "description": description_adf
        }
    }

    response = requests.post(url, json=payload, headers=headers)
    if response.status_code == 201:
        jira_issue_id = response.json()['id']
        logging.info(f'Successfully created Jira issue ID {jira_issue_id}')
        return jira_issue_id
    else:
        logging.error(f'Failed to create Jira issue for Redmine issue ID {redmine_issue["id"]}')
        logging.error(f'Error details: {response.text}')
        return None

def attach_files_to_jira(jira_issue_id, redmine_issue_id, auth_str_base64):
    attachments = get_redmine_issue_attachments(redmine_issue_id)
    if attachments:
        url = f'{JIRA_URL}/rest/api/3/issue/{jira_issue_id}/attachments'
        headers = {
            "X-Atlassian-Token": "no-check",
            "Authorization": f'Basic {auth_str_base64}'
        }
        for attachment in attachments:
            attachment_file = download_attachment(attachment['content_url'])
            if attachment_file:
                files = {'file': (attachment['filename'], attachment_file)}
                response = requests.post(url, files=files, headers=headers)
                if response.status_code != 201:
                    logging.error(f'Failed to attach file {attachment["filename"]} to Jira issue ID {jira_issue_id}')
                    logging.error(f'Error details: {response.text}')

def migrate_issues():
    page = 1
    auth_str = f'{JIRA_USERNAME}:{JIRA_API_TOKEN}'
    auth_str_base64 = base64.b64encode(auth_str.encode('utf-8')).decode('utf-8')

    while True:
        redmine_issues = get_redmine_issues(page)
        
        if not redmine_issues:
            break
        
        for redmine_issue in redmine_issues:
            jira_issue_id = create_jira_issue(redmine_issue)
            if jira_issue_id:
                populate_custom_fields(jira_issue_id, redmine_issue)
                attach_files_to_jira(jira_issue_id, redmine_issue['id'], auth_str_base64)
        
        page += 1

if __name__ == '__main__':
    logging.info("Script started.")
    migrate_issues()
    logging.info("Script completed.")
