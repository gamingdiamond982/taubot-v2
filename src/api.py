from enum import Enum

import aiohttp, asyncio
import discord.errors
from aiohttp import web
import jwt
import os
import time
import re
from uuid import UUID

from aiohttp.web_request import Request
from aiohttp.web_urldispatcher import SystemRoute

from backend import StubUser, Permissions, Account, BackendError
from backend import Backend, Transaction, Application, KeyType, APIKey
from backend import CONSOLE_USER_ID
from utils import load_config
from jinja2 import Environment, FileSystemLoader, select_autoescape

env = Environment(
    loader = FileSystemLoader('./jinja_templates/'),
    autoescape= select_autoescape()
)

auth_cache = {}

config = {}
API_URL = "https://discord.com/api/v10"
CALLBACK_URL = API_URL + "/oauth2/token"


trusted_public_keys = {}
private_key = None
routes = web.RouteTableDef()
INSECURE = (
    re.compile('^/api/oauth/'),
)
backend: Backend = None


class APIStubUser(StubUser):
    @classmethod
    def from_key(cls, key : APIKey):
        self = cls(key.key_id)
        self.mention = f"<@{key.issuer_id}>"
        return self


def generate_key(key_id):
    if key_id == CONSOLE_USER_ID:
        raise web.HTTPUnauthorized(reason="Almost had me there") # purely for the sake of my sanity making it impossible to accidentally issue a god key
    claims = {
        "iss": "TB",
        "kid": str(key_id),
    }
    return jwt.encode(claims, private_key, algorithm="RS512")


async def get_actor(actor_id, economy):
    try:
        actor = await backend.get_member(actor_id, economy.owner_guild_id)
    except discord.errors.NotFound:
        actor = StubUser(actor_id)
    return actor


def needs_discord(coro):
    async def result(request: Request, **kwargs):
        token = request.cookies.get('token')
        if token is None:
            raise web.HTTPFound('/api/oauth/login')
        return await coro(
            request,
            discord_id=await get_user_id(token), 
            **kwargs
        )
    return result


def needs(*types: KeyType):
    def decorator(coro):
        async def result(request: Request, key: APIKey = None, **kwargs):
            if key.type not in types:
                raise web.HTTPUnauthorized()
            return await coro(request, key=key, **kwargs)
        return result
    return decorator


@web.middleware
async def authenticate(request, handler):
    rel_url = request.rel_url
    print(rel_url)
    if [regex.match(str(rel_url)) for regex in INSECURE] != [None] * len(INSECURE):
        return await handler(request)
    try:
        token = request.headers["authorization"]
    except KeyError:
        raise web.HTTPUnauthorized()
    claims = jwt.decode(token, options={"verify_signature": False})
    public_key = trusted_public_keys[claims['iss'] + '.pub']
    options = {
        "require": ["kid", "iss"]
    }
    try:
        claims = jwt.decode(token, public_key, algorithms=["RS512"], options=options)
    except:
        raise web.HTTPUnauthorized()

    try:
        key_id = int(claims["kid"])
    except (ValueError, TypeError):
        raise web.HTTPUnauthorized()

    key = backend.get_key_by_id(key_id)
    if key is None or not key.enabled:
        raise web.HTTPUnauthorized()
    try:
        return await handler(request, key=key)
    except TypeError:
        raise web.HTTPNotFound() # Feeling a bit lazy iwl - this is technically pythonic tho


@routes.post('/api/oauth-references')
@needs(KeyType.MASTER)
async def create_reference(request: Request, key: APIKey):
    if not auth_cache.get(key.application_id):
        auth_cache[key.application_id] = {}
    # TODO: minimum required perms
    data = await request.json()
    if not set(data.keys()).issubset({'ref_id'}):
        raise web.HTTPBadRequest()
    try:
        ref_id = UUID(data['ref_id'])
    except:
        raise web.HTTPBadRequest()
    auth_cache[key.application_id][ref_id] = {}
    return web.HTTPCreated()


@routes.get('/api/retrieve-key/{ref_id}')
@needs(KeyType.MASTER)
async def retrieve_key(request, key: APIKey=None):
    app = key.application
    try:
        ref_id = UUID(request.match_info["ref_id"])
    except (TypeError, ValueError):
        raise web.HTTPBadRequest()

    to_be_issued = auth_cache.get(app.application_id)
    existing_key = backend.get_key(app, ref_id)
    if to_be_issued is None:
        to_be_issued = {}


    key_meta = to_be_issued.get(ref_id)
    if key_meta is None and existing_key is not None:
        key = existing_key
    else:
        if key_meta is None:
            raise web.HTTPNotFound()
        data = key_meta.get('request_data')
        key = APIKey(application=app, internal_app_id=ref_id, issuer_id=key_meta.get('issuer_id'), spending_limit=data.get('spending_limit'))
        backend.session.add(key)
        perms = data['permissions']
        key.activate()
        for acc in perms.keys():
            acc = backend.get_account_by_id(UUID(acc))
            backend.change_many_permissions(
                StubUser(CONSOLE_USER_ID),
                key.key_id,
                *[Permissions[p] for p in perms[str(acc.account_id)]],
                account=acc
            )
        auth_cache[app.application_id].pop(ref_id)


    res = {
        "key": generate_key(key.key_id)
    }

    return web.json_response(res)


@routes.get('/api/oauth/grant')
async def start_linking(request):
    oauth = config.get("oauth")
    if oauth is None:
        raise web.HTTPNotFound()
    redirect_url = oauth.get("redirect_url")
    if redirect_url is None:
        raise web.HTTPNotFound()
    resp = web.HTTPSeeOther(redirect_url)

    try:
        reference_id = UUID(request.query.get('ref'))   # allow consumers of an API to set a reference code unique to the application when the user grants the token so they can later call taubot asking for it
                                                        # It is the responsibility of API consumers to ensure their reference codes do not clash.
                                                        # TODO: allow API consumer to specify minimum required scopes - i.e. don't bother granting the token unless I can at least do this
        application_id = UUID(request.query.get('aid'))
        app = backend.get_application(application_id)
        if app is None:
            raise web.HTTPBadRequest()
    except (ValueError, TypeError):
        raise web.HTTPBadRequest()



    resp.set_cookie('aid', str(application_id))
    resp.set_cookie('ref_code', str(reference_id))
    return resp

async def get_access_token(code: str) -> str:
    oauth = config.get("oauth")
    auth = aiohttp.BasicAuth(oauth.get('client_id'), oauth.get('client_secret'))
    data = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': oauth.get('redirect_uri')
    }
    
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(CALLBACK_URL, data=data, auth=auth, headers=headers) as resp:
            if resp.status != 200:
                raise web.HTTPBadRequest()
            data = await resp.json()
    
    return data.get('access_token')


async def get_user_id(token: str) -> int:
    async with aiohttp.ClientSession() as session:
        async with session.get(API_URL + '/users/@me', headers={'Authorization': 'Bearer ' + token}) as resp:
            if resp.status != 200:
                raise web.HTTPBadRequest()
            user_id = int((await resp.json()).get('id'))
    return user_id


@routes.get('/api/oauth/oauth-callback')
async def start_linking(request: web.Request):
    token = await get_access_token(request.rel_url.query.get('code'))
    if token is None:
        
        raise web.HTTPBadRequest()

    r = web.HTTPFound('/api/oauth/protected/grant')
    r.set_cookie('token', token)
    return r


@routes.post('/api/oauth/issue')
@needs_discord
async def issue_token(request, discord_id=None):
    try:
        ref_code = UUID(request.cookies.get('ref_code'))
        aid = UUID(request.cookies.get('aid'))
    except (ValueError, TypeError):
        raise web.HTTPBadRequest()

    app = backend.get_application(aid)

    if app is None:
        raise web.HTTPBadRequest()

    if not auth_cache.get(aid):
        raise web.HTTPUnauthorized()

    meta = auth_cache[aid].get(ref_code)
    if meta is None:
        raise web.HTTPForbidden(reason="Ref Code has not been registered")

    if meta.get('issuer_id') and meta.get('issuer_id') != discord_id:
        raise web.HTTPForbidden(reason="ref code has already been claimed") # I'm letting the user modify the perms granted as much as they want until the token is issued
    key = backend.get_key(app, ref_code)
    if key and key.issuer_id != discord_id: # You are not able to re-issue a ref code to a different issuer
        raise web.HTTPForbidden(reason="ref code has already been claimed") # Once a key is issued it's ref code is tied to the user that issued it

    granter = await backend.get_member(discord_id, app.economy.owner_guild_id)
    data: dict = await request.json()
    if set(data.keys()) != {"permissions", "spending_limit"}:
        raise web.HTTPBadRequest()

    for account_id in data["permissions"].keys():
        perms = data["permissions"][account_id]

        if not isinstance(perms, list):
            raise web.HTTPBadRequest()

        if not type(data.get('spending_limit')) in {int, type(None)}:
            raise web.HTTPBadRequest()
        if (data.get("spending_limit")) and data.get("spending_limit") < 0:
            raise web.HTTPBadRequest()
        if not set(perms).issubset({"VIEW_BALANCE", "TRANSFER_FUNDS"}):
            raise web.HTTPBadRequest()
        try:
            account_id = UUID(account_id)
        except (ValueError, TypeError):
            raise web.HTTPBadRequest()

        account = backend.get_account_by_id(account_id)
        if account is None:
            raise web.HTTPBadRequest()

        for perm in perms:
            if not backend.has_permission(granter, Permissions[perm], account=account):
                raise web.HTTPUnauthorized()

    auth_cache[aid][ref_code] = {
        "issuer_id": granter.id,
        "request_data": data
    }
    return web.HTTPCreated()




@routes.get('/api/oauth/protected/grant')
@needs_discord
async def grant_page(request, discord_id=None):
    ref_code = request.cookies.get('ref_code')
    if ref_code is None:
        
        raise web.HTTPBadRequest()
    try:
        aid = UUID(request.cookies.get('aid'))
    except ValueError:
        raise web.HTTPBadRequest()
    app: Application = backend.get_application(aid)

    if app is None:
        raise web.HTTPBadRequest()
    auth_granter = await backend.get_member(discord_id, app.economy.owner_guild_id)
    if auth_granter is None:
        auth_granter = StubUser(discord_id)

    def has_perm(pid, account):
        return backend.has_permission(auth_granter, list(Permissions)[pid], account=account)

    accs = backend.get_authable_accounts(auth_granter, app.economy)
    
    result = env.get_template('grant_page.html').render(issuer=auth_granter, app=app, accounts=accs, has_perm=has_perm)
    return web.Response(text=result, content_type='text/html')



@routes.get('/api/users/{user_id}')
@needs(KeyType.GRANT, KeyType.MASTER)
async def get_account_id(request, key: APIKey=None):
    try:
        user_id = request.match_info["user_id"]
        user_id = key.issuer_id if user_id == "me" else int(user_id)
    except ValueError:
        raise web.HTTPNotFound()

    economy = key.application.economy
    account = backend.get_user_account(user_id, economy)
    if account is None:
        raise web.HTTPNotFound()
    return web.json_response(await encode_account(key, account))

async def encode_account(key:APIKey, account: Account):
    return {
        "account_id": str(account.account_id),
        "owner_id": str(account.owner_id),
        "account_name": account.account_name,
        "account_type": account.account_type.name,
        "balance": account.balance if await backend.key_has_permission(key, Permissions.VIEW_BALANCE, account=account) else None
    }


@routes.get("/api/accounts/by-name/{account_name}")
@needs(KeyType.GRANT, KeyType.MASTER)
async def get_account_by_name(request, key: APIKey=None):
    try:
        account_name = request.match_info["account_name"]
    except ValueError:
        raise web.HTTPNotFound()
    economy = key.application.economy
    account = backend.get_account_by_name(account_name, economy)
    if account is None:
        raise web.HTTPNotFound()
    return web.json_response(await encode_account(key, account))


@routes.get("/api/accounts/{account_id}")
@needs(KeyType.GRANT)
async def get_account(request, key: APIKey=None):
    try:
        account_id = UUID(request.match_info["account_id"])
    except ValueError:
        raise web.HTTPNotFound()
    account = backend.get_account_by_id(account_id)
    if account is None:
        raise web.HTTPNotFound()

    return web.json_response(await encode_account(key, account))


def encode_transaction(t: Transaction):
    """
    :param t: A transaction
    :return: an encoded transaction as a dictionary
    """

    return {
            "actor_id": str(t.actor_id),
            "timestamp": t.timestamp.timestamp(),
            "from_account": str(t.target_account_id),
            "to_account": str(t.destination_account_id),
            "amount": t.amount
        }

@routes.get("/api/accounts/{account_id}/transactions")
@needs(KeyType.GRANT)
async def get_account_transactions(request, key: APIKey = None):
    try:
        account_id = UUID(request.match_info["account_id"])
    except ValueError:
        raise web.HTTPNotFound()

    account = backend.get_account_by_id(account_id)
    if account is None:
        raise web.HTTPNotFound()

    actor = APIStubUser.from_key(key)
    if not await backend.key_has_permission(key, Permissions.VIEW_BALANCE, account=account):
        raise web.HTTPUnauthorized()

    transactions = backend.get_transaction_log(actor, account, limit=request.query.get("limit"))
    result = [encode_transaction(t) for t in transactions]
    return web.json_response(result)

@routes.post("/api/transactions/")
async def create_transaction(request, key: APIKey=None):
    transaction_data = await request.json()
    if set(transaction_data.keys()) != {"from_account", "to_account", "amount"}:
        raise web.HTTPBadRequest()

    actor = APIStubUser.from_key(key)

    from_account = backend.get_account_by_id(UUID(transaction_data["from_account"]))
    to_account = backend.get_account_by_id(UUID(transaction_data["to_account"]))
    amount = int(transaction_data["amount"])
    if from_account is None or to_account is None:
        raise web.HTTPNotFound()
    try:
        if key.spent_to_date + amount > key.spending_limit:
            raise web.HTTPUnauthorized()
        if await backend.key_has_permission(key, Permissions.TRANSFER_FUNDS, account=from_account):
            key.spent_to_date += amount
            backend.perform_transaction(actor, from_account, to_account, amount)
    except BackendError:
        raise web.HTTPBadRequest()
    return web.HTTPOk()


def init_app():
    global config, trusted_public_keys, private_key

    trusted_pubk_fps = os.listdir('./keys/public-keys/')
    private_key = open('./keys/jwt-key', 'rb').read()
    for fp in trusted_pubk_fps:
        trusted_public_keys[fp] = open('./keys/public-keys/' + fp, 'rb').read()
    config = load_config()
    env.globals['static_uri'] = config.get('static_uri')
    app = web.Application(middlewares=[authenticate])
    app.add_routes(routes)

    return app

async def main():
    global backend
    runner = web.AppRunner(init_app())
    db_uri = config.get('database_uri')
    backend = Backend(db_uri if db_uri else 'sqlite:///database.db')
    await runner.setup()
    site = web.TCPSite(runner, 'localhost', 8080)
    await site.start()

if __name__ == '__main__':
    print('starting API')
    asyncio.set_event_loop(asyncio.new_event_loop())
    asyncio.get_event_loop().create_task(main())
    asyncio.get_event_loop().run_forever()
