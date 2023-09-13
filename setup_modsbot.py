import os
import shutil
import sqlite3

from ruamel import yaml  # type: ignore

DATABASES_TO_CREATE = [
    """
    CREATE TABLE problems (
        idproblems INTEGER PRIMARY KEY,
        problem_statement TEXT,
        extra_links TEXT,
        answer TEXT,
        source TEXT
    );
    """,
    """
    CREATE TABLE messages (
        discord_message_id INTEGER PRIMARY KEY,
        discord_channel_id INTEGER,
        discord_user_id INTEGER,
        message_length INTEGER,
        message_date TEXT
    );
    """,
    """
    CREATE TABLE settings (
        setting TEXT PRIMARY KEY,
        value TEXT
    );
    """,
    """
    CREATE TABLE potd_ping2 (
        user_id INTEGER PRIMARY KEY,
        criteria TEXT
    );
    """,
    """
    CREATE TABLE potd_info (
        potd_id INTEGER PRIMARY KEY,
        problem_msg_id INTEGER,
        source_msg_id INTEGER,
        ping_msg_id INTEGER
    );
    """,
    """
    CREATE TABLE potd_solves (
        discord_user_id INTEGER,
        potd_id INTEGER,
        create_date TEXT,
        PRIMARY KEY (discord_user_id, potd_id)
    );
    """,
    """
    CREATE TABLE potd_read (
        discord_user_id INTEGER,
        potd_id INTEGER,
        create_date TEXT,
        PRIMARY KEY (discord_user_id, potd_id)
    );
    """,
    """
    CREATE TABLE potd_todo (
        discord_user_id INTEGER,
        potd_id INTEGER,
        create_date TEXT,
        PRIMARY KEY (discord_user_id, potd_id)
    );
    """,
    """
    CREATE TABLE ratings (
        prob INTEGER,
        userid INTEGER,
        rating INTEGER,
        PRIMARY KEY (prob, userid)
    );
    """,
]


def ensure_correct_directory() -> None:
    if "modsbot.py" not in os.listdir("."):
        print(
            "Please run this script from the root directory of the cloned "
            "repository."
        )
        exit(1)


def create_databases(db_file_name: str) -> None:
    os.makedirs("data", exist_ok=True)
    if db_file_name in os.listdir("data"):
        print(
            "Database already exists. Skipping this stage.\n"
            f"To avoid skipping this stage, delete `data/{db_file_name}` and "
            "run this script again."
        )
        return
    conn = sqlite3.connect(f"data/{db_file_name}")
    cursor = conn.cursor()
    for database_creation_command in DATABASES_TO_CREATE:
        cursor.execute(database_creation_command)
    conn.commit()
    conn.close()


def request_integer_input(prompt: str) -> int:
    while True:
        try:
            return int(input(prompt))
        except ValueError:
            print("Please enter an integer.")


def create_config_copy_with_essential_changes() -> None:
    if "config.yml" in os.listdir("config"):
        print(
            "Config file already exists. Skipping this stage.\n"
            "To avoid skipping this stage, delete `config/config.yml` and run "
            "this script again."
        )
        return

    guild_id = request_integer_input("Enter the ID of the guild: ")
    channel_id = request_integer_input("Enter the ID of the channel: ")

    shutil.copyfile("config/modsbot_config.yml", "config/config.yml")

    with open("config/config.yml") as config_file_read:
        config = yaml.safe_load(config_file_read)

    config["mods_guild"] = guild_id
    config["tech_garage"] = channel_id

    with open("config/config.yml", "w") as config_file_write:
        yaml.dump(config, config_file_write)


def write_token_file() -> None:
    with open("config/config.yml") as config_file:
        config = yaml.safe_load(config_file)

    token_file_name = config["token"]

    if token_file_name in os.listdir("config"):
        print(
            "Token file already exists. Skipping token file creation stage.\n"
            f"To avoid skipping this stage, delete `config/{token_file_name}` "
            "and run this script again."
        )
        return

    token = input("Enter the bot token: ")

    with open(f"config/{token_file_name}", "w") as token_file:
        token_file.write(token)


if __name__ == "__main__":
    ensure_correct_directory()
    create_databases("modsdb.db")
    create_config_copy_with_essential_changes()
    write_token_file()
