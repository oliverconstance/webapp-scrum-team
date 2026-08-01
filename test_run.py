import os
os.environ['GOOGLE_CLOUD_PROJECT'] = 'multi-agent-dev-team-502213'
os.environ['GOOGLE_CLOUD_LOCATION'] = 'europe-west2'
import logging
logging.basicConfig(level=logging.INFO)
from orchestration.scrum_master import create_scrum_team_orchestrator
pipeline = create_scrum_team_orchestrator()
print('Running pipeline...')
res = pipeline.query(ticket_id='TICKET-999', ticket_type='BACKEND', description='Test', repo_name='oliverconstance/test', branch_name='test')
print(res)
