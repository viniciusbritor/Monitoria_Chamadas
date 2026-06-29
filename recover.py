import json
log_path = r'C:\Users\vinic\.gemini\antigravity\brain\3cd89df2-fa5c-4d5c-afbf-36f09b4477d7\.system_generated\logs\transcript_full.jsonl'
for line in open(log_path, 'r', encoding='utf-8'):
    try:
        data = json.loads(line)
        if 'tool_calls' in data:
            for call in data['tool_calls']:
                if call.get('name') == 'write_to_file':
                    target = call.get('args', {}).get('TargetFile', '')
                    code = call.get('args', {}).get('CodeContent', '')
                    if not code:
                        continue
                    if 'App.jsx' in target:
                        with open('frontend/src/App.jsx', 'w', encoding='utf-8') as f:
                            f.write(code)
                        print('Recovered App.jsx')
                    if 'Dashboard.jsx' in target:
                        with open('frontend/src/components/Dashboard.jsx', 'w', encoding='utf-8') as f:
                            f.write(code)
                        print('Recovered Dashboard.jsx')
                    if 'CallInspector.jsx' in target:
                        with open('frontend/src/components/CallInspector.jsx', 'w', encoding='utf-8') as f:
                            f.write(code)
                        print('Recovered CallInspector.jsx')
                    if 'main.jsx' in target:
                        with open('frontend/src/main.jsx', 'w', encoding='utf-8') as f:
                            f.write(code)
                        print('Recovered main.jsx')
    except Exception as e:
        print("Error:", e)
