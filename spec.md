# Requirements

## MVP - Minimum requirements
1. Account creation/closure
2. Transfers
3. Persistent SQL backend
4. reccurring transfers
5. Proxy accounts
6. Administrative account.


## Stuff that'll probably be needed before deployment
1. Citizenship:
	- Accounts will need to be "owned" by a discord server to ensure correct taxation etc.
	- Admin accounts will also need to be restricted to operate only within their "country"
2. Wealth tax:
	- Was a feature of taubot V1 not sure if it'll be wanted again.
3. Income tax:
	- Was not a feature of taubot V1 but was heavily requested, will need to categorise types of recurring transfers tho.
4. Account Classes:
	- Bit like the old auth levels stuff just for corpo and gov proxy accounts - they were a retrofit in taubot V1 would rather they were defined within the codebase




## Stuff I'd like to do but can wait till after release if needs be
1. API - allow people to write bots that interface with their account



# Plan


## The bot
- bot.py
	- Registers commands with discord using the new API
	- Will not support reddit APIs like taubot V1

- api.py
	- probably will be run on a seperate proccess to the bot 
	- Will use the backend singleton exposed by backend.py
	- will expose an unsecure HTTP API, that can later be protected by something like NGINX.
	- Hosters will need to ensure not to expose the internal port the API is exposed on.
	- Not sure if I want a site with Oauth2 for key management or to do it through discord commands.
	- Not needed for MVP

- backend.py
	- Maintains and manages the SQL database - will probably use SQLAlchemy like in V1, this worked well enough 
	- exposes a Backend singleton that can be used in different frontend implementations


## SQL Schema
I've taken some liberties with permission management since we can build this from the ground up now rather than retrofitting everything.
Column types are just placeholders and don't necessarily line up with SQL types.


**economies**

| Column Name    | Column Type | Primary Key | Foreign Key |
|----------------|-------------|-------------|-------------|
| economy\_id    | UUID        | True        |             |
| currency\_name | CHAR(32)    |             |             |
| currency\_unit | CHAR(32)    |             |             |


**guild_economies**

| Column Name | Column Type | Primary Key | Foreign Key           |
|-------------|-------------|-------------|-----------------------|
| guild\_id   | u64         | True        |                       |
| economy\_id | UUID        |             | economies.economy\_id |



**accounts**

| Column Name   | Column Type | Primary Key | Foreign Key           |
|---------------|-------------|-------------|-----------------------|
| account\_id   | UUID        | True        |                       |
| account\_name | CHAR(32)    |             |                       |
| owner\_id     | u64         |             |                       |
| account\_type | Enum        |             |                       |
| balance\*     | number      |             |                       |
| economy\_id   | UUID        |             | economies.economy\_id |

\* balance will be stored in cents to avoid floating point arithmetic fuckery, I don't want the hassle supporting balances of arbitrary decimal percision like in V1. To display the balance in tau ensure you do something like this f'{bal//100}.{bal%100}t'


**permissions**

| Column Name      | Column Type | Primary Key | Foreign Key           |
|------------------|-------------|-------------|-----------------------|
| entry\_id        | UUID        | True        |                       |
| account\_id      | UUID        |             | accounts.account\_id  |
| user\_id         | u64         |             |                       |
| permission\_type | Enum        |             |                       |
| allowed          | boolean     |             |                       |
| economy\_id      | UUID        |             | economies.economy\_id |


**taxes**

| Column Name    | Column Type | Primary Key | Foreign Key           |
|----------------|-------------|-------------|-----------------------|
| entry\_id      | UUID        | True        |                       |
| economy\_id    | UUID        |             | economies.economy\_id |
| tax\_type      | Enum        |             |                       |
| bracket\_start | number      |             |                       |
| bracket\_end   | number      |             |                       |
| rate           | number      |             |                       |


**recurring_transfers**

| Column Name               | Column Type | Primary Key | Foreign Key          |
|---------------------------|-------------|-------------|----------------------|
| entry\_id                 | UUID        | True        |                      |
| from\_account             | UUID        |             | accounts.account\_id |
| to\_account               | UUID        |             | accounts.account\_id |
| amount                    | number      |             |                      |
| last\_payment\_timestamp  | DATE        |             |                      |
| next\_payment\_timestamp  | DATE        |             |                      |
| final\_payment\_timestamp | DATE        |             |                      |
| payment\_interval         | number      |             |                      |



































