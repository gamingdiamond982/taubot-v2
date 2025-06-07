Usage
=====

.. _prerequisites:

Prerequisites
-------------

There are some programs that are needed, to install taubot namely git, python3.12+ and a matching version python3-venv

For deployment of a production server it's recommended you install postgres, but any SQL database should work although only postgres and sqlite are supported, using another dbms may result in undefined behaviour.

Sqlite is recommended for local development environments as it's setup and overhead are significantly less invasive

.. _installation:

Installation
------------


First clone the repo and cd into it:

.. code-block:: console 

   $ git clone https://github.com/gamingdiamond982/taubot-v2.git && cd taubot-v2


Next you should create a virtualenv to store all of the projects dependencies and activate it:

.. code-block:: console

   $ python3 -m venv ./.venv && . ./.venv/bin/activate


Now it's time for you to install the dependencies:

.. code-block:: console

   $ python3 -m pip install -r requirements.txt



Once you've this done you should create your config.json, a redacted version of the one used in production is provided for your convenience

.. code-block:: json

    {
        "discord_token": "Your bot token here",
        "database_uri": "postgresql://username:password@localhost/taubot",
        "private_webhook_url": "Webhook URL for all transaction logs to be sent too",
        "public_webhook_url": "Webhook URL for transactions by government officials to be sent too",
        "api": true,
        "oauth": {
                "redirect_url": "https://discord.com/oauth2/authorize?client_id=1236137854128623677&response_type=code&redirect_uri=https%3A%2F%2Fqwrky.dev%2Fapi%2Foauth%2Foauth-callback&scope=identify",
                "redirect_uri": "https://qwrky.dev/api/oauth/oauth-callback",
                "client_id": "1236137854128623677",
                "client_secret": "Your oauth secret here"
        },
        "static_uri": "https://qwrky.dev/static"
    }


Now your ready to go you can start taubot with the `-S` flag to sync the commands with discord, this flag should only be used after taubot is newly installed or if it has had new commands added


.. code-block:: console

   $ python3 src/main.py config.json -S 


If you wish to run taubot in the background you can run:

.. code-block:: console
   
    $ python3 src/main.py &>>./out.log &










