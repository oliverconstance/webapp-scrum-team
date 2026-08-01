from google import genai
from google.genai import types

client = genai.Client(vertexai=True, project='multi-agent-dev-team-502213', location='europe-west2')
state = {'pr_url': None}

def update_state(pr_url: str) -> str:
    '''Updates the PR URL in state.'''
    state['pr_url'] = pr_url
    return 'State updated.'

res = client.models.generate_content(
    model='gemini-2.5-flash',
    contents='Please call update_state with https://github.com/abc/1',
    config=types.GenerateContentConfig(tools=[update_state])
)

print('LLM Output:', res.text)
print('State:', state)
