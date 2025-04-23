import sys
import json

syncing = False

def load_config():
    global syncing
    if len(sys.argv) > 3:
        print('Usage: main.py config_path -[S]')
        sys.exit(1)

    path = 'config.json' if len(sys.argv) < 2 else sys.argv[1]
    if len(sys.argv) == 3:
        if sys.argv[2] != "-S":
            print('Usage: main.py config_path -[S]')
            sys.exit(1)
        syncing = True

    try:
        with open(path) as file:
            return json.load(file)
    except:
        return {}
