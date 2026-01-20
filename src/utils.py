import sys
import json
import csv
import io
import uuid
import discord
from middleman import frmt

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

def generate_transaction_csv(transactions: list, filename=None, *, currency='t', as_discord_file: bool = True):
    filename = filename or (str(uuid.uuid4()) + '.csv')
    with io.StringIO() as buffer:
        writer = csv.writer(buffer)
        writer.writerow(["Timestamp", "From", f"Amount ({currency})", "To"]) # header
        if len(transactions) > 0:
            writer.writerows(
                [
                    t.timestamp.strftime("%d/%m/%y %H:%M"),
                    t.target_account.get_name(),
                    frmt(t.amount),
                    t.destination_account.get_name()
                ] for t in transactions
            )

        buffer.seek(0)
        byte = io.BytesIO(buffer.getvalue().encode("utf-8"))
    
    if as_discord_file:
        return discord.File(byte, filename=filename)
    else:
        return byte