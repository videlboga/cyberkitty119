import re

with open('max_bot/native_handlers.py', 'r') as f:
    content = f.read()

# Replace _get_or_create_user_from_event with async version that uses core_api_client
# Wait, native_handlers.py has sync process_event_async ? Let's check handle_event

