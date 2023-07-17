# Getting Started

The following are some instructions to help setting up a local version of modsbot.
The instructions are made for linux (but should nevertheless be useful for other operating systems) and some of the commands may have errors which you may need to try googling.

1. Clone this repository and enter the directory. Ideally you should use python3.9 (python3.11 definitely doesn't work but I don't know exactly which versions work).
2. Setup a python venv, source it and install the requirements
   ```zsh
   python3.9 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
3. Create a discord bot and keep the token safe, or just regenerate it in the next step. [Follow this guide if you are unsure how to create a discord bot](https://www.freecodecamp.org/news/create-a-discord-bot-with-python/). You should also create a server for the bot and add it to it.
4. Make sure the venv is activated and that the current directory is the root directory of the cloned repository. Then, run the setup script:
   ```zsh
   python setup_modsbot.py
   ```
5. Setup a google API service account
    1. Create a gmail account if you don't already have one.
    2. Go to https://console.cloud.google.com/ and agree to terms of service.
    3. At the top of the screen, click `select a project` and then click `NEW PROJECT` and give the project a suitable name like `MODSBOT testing`. You don't need to add an organisation.
        ![image of google cloud console website](https://github.com/Mathematical-Olympiads-Discord-Server/modsbot-rewrite/blob/master/images/google_cloud_console_setup_1.png?raw=true)
    4. After waiting a few seconds, you should be able to click `select a project` at the top of the screen and then select the project we just created. Under Quick access, click `APIs and services`, and then click `ENABLE APIS AND SERVICES` on the next page
        ![image of google cloud console website](https://github.com/Mathematical-Olympiads-Discord-Server/modsbot-rewrite/blob/master/images/google_cloud_console_setup_2.png?raw=true)
        ![image of google cloud console website](https://github.com/Mathematical-Olympiads-Discord-Server/modsbot-rewrite/blob/master/images/google_cloud_console_setup_3.png?raw=true)
    5. In the search box, search for "drive" and hit enter. Select "Google Drive API" and then enable it. Repeat this also for the "Google Sheets API".
        ![image of google cloud console website](https://github.com/Mathematical-Olympiads-Discord-Server/modsbot-rewrite/blob/master/images/google_cloud_console_setup_4.png?raw=true)
    6. Now click the `Credentials` button on the left of the screen
        ![image of google cloud console website](https://github.com/Mathematical-Olympiads-Discord-Server/modsbot-rewrite/blob/master/images/google_cloud_console_setup_5.png?raw=true)
    7. Click `CREATE CREDENTIALS` and then `Service account`. The only required details in the first section is the service addount ID which can be anything.
        ![image of google cloud console website](https://github.com/Mathematical-Olympiads-Discord-Server/modsbot-rewrite/blob/master/images/google_cloud_console_setup_6.png?raw=true)
    8. The other steps can be skipped.
        ![image of google cloud console website](https://github.com/Mathematical-Olympiads-Discord-Server/modsbot-rewrite/blob/master/images/google_cloud_console_setup_7.png?raw=true)
    9. You should now be back on the Credentials page from earlier. Under the `Service Accounts` list, select the new entry. Then click `KEYS` at the top of the screen
        ![image of google cloud console website](https://github.com/Mathematical-Olympiads-Discord-Server/modsbot-rewrite/blob/master/images/google_cloud_console_setup_8.png?raw=true)
    10. Now click `ADDKEY` then `Create new key` and select `JSON` for the key type. Click `CREATE` and then save the file into `config/credentials.json` in the directory where you cloned this repository.
        ![image of google cloud console website](https://github.com/Mathematical-Olympiads-Discord-Server/modsbot-rewrite/blob/master/images/google_cloud_console_setup_9.png?raw=true)
    11. All done for this section!
6. You should now be able to run the bot with `python modsbot.py` (just make sure you've activated the venv).
