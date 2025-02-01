from aiohttp import web
import jwt
import os
import time
import re
from uuid import UUID
from backend import StubUser, Permissions

trusted_public_keys = {}
private_key = b''
routes = web.RouteTableDef()
INSECURE = (
    re.compile('^/mc/'),
)
backend = None

trusted_pubk_fps = os.listdir('./keys/public-keys/')
for fp in trusted_pubk_fps:
    trusted_public_keys[fp] = open('./keys/public-keys/'+fp,'rb').read()
private_key = open('./keys/jwt-key', 'rb').read()

def generate_key(user_id):
    claims = {
        "iss": "TB",
        "iat": time.time(),
        "exp": time.time() + 60*60*24,
        "uid": str(user_id)
    }
    return jwt.encode(claims, private_key, algorithm="RS512")

@web.middleware
async def authenticate(request, handler):
    rel_url = request.rel_url
    print(str(rel_url))
    if [regex.match(str(rel_url)) for regex in INSECURE] != [None]*len(INSECURE):
        return await handler(request)
    try:
        token = request.headers["authorization"]
    except KeyError:
        raise web.HTTPUnauthorized()
    claims = jwt.decode(token, options={"verify_signature": False})
    print(claims)
    public_key = trusted_public_keys[claims['iss']+'.pub']
    options = {
        "require": ["exp", "iat", "uid"],
        "verify_iss": True,
        "verify_exp": True,
    }
    claims = jwt.decode(token, public_key, algorithms=["RS512"])
    return await handler(request, actor_id=int(claims["uid"]))

@routes.get('/mc/{mc_token}')
async def get_user_id(request):
    print(backend.get_economies()[0].economy_id)
    user_id = backend.get_discord_id(request.match_info["mc_token"])
    if user_id is None:
        raise web.HTTPNotFound()
    return web.json_response({"user_id": str(user_id)})


@routes.get('/economies/{economy_id}/users/{user_id}')
async def get_account_id(request, actor_id=None):
    try:
        economy_id = UUID(request.match_info["economy_id"])
        user_id = request.match_info["user_id"]
        user_id = actor_id if user_id == "me" else int(user_id)
    except ValueError:
        raise web.HTTPNotFound()

    economy = backend.get_economy_by_id(economy_id)
    if economy is None:
        raise web.HTTPNotFound()

    account = backend.get_user_account(user_id, economy)
    if account is None:
        raise web.HTTPNotFound()

    return web.json_response({"personal_account_id": str(account.account_id)})

@routes.get("/economies/{economy_id}/accounts/by-name/{account_name}")
async def get_account_by_name(request, actor_id=None):
    try:
        economy_id = UUID(request.match_info["economy_id"])
        account_name = request.match_info["account_name"]
    except ValueError:
        raise web.HTTPNotFound()
    economy = backend.get_economy_by_id(economy_id)
    if economy is None:
        raise web.HTTPNotFound()
    account = backend.get_account_by_name(account_name, economy)
    actor = await backend.get_member(actor_id, economy.owner_guild_id)
    actor = actor if actor else StubUser(actor_id)
    result = {"account_id": str(account.account_id)}

    if backend.has_permission(actor, Permissions.VIEW_BALANCE, account=account):
        result["balance"] = account.balance
    print(result)
    return web.json_response(result)



@routes.get("/economies/{economy_id}/accounts/{account_id}")
async def get_account(request, actor_id=None):
    try:
        economy_id = UUID(request.match_info["economy_id"])
        account_id = UUID(request.match_info["account_id"])
    except ValueError:
        raise web.HTTPNotFound()

    economy = backend.get_economy_by_id(economy_id)
    if economy is None:
        raise web.HTTPNotFound()

    account = backend.get_account_by_id(account_id)
    if account is None:
        raise web.HTTPNotFound()

    actor = await backend.get_member(actor_id, economy.owner_guild_id)
    actor = actor if actor else StubUser(actor_id)
    result = {"account_name": account.account_name}

    if backend.has_permission(actor, Permissions.VIEW_BALANCE, account=account):
        result["balance"] = account.balance

    return web.json_response(result)


@routes.post("/economies/{economy_id}/transactions/")
async def create_transaction(request, actor_id=None):
    try:
        economy_id = UUID(request.match_info["economy_id"])
    except ValueError:
        raise web.HTTPNotFound()
    economy = backend.get_economy_by_id(economy_id)
    if economy is None:
        raise web.HTTPNotFound()

    transaction_data = await request.json()
    if set(transaction_data.keys()) != {"from_account", "to_account", "amount"}:
        raise web.HTTPBadRequest()

    user = await backend.get_member(actor_id, economy.owner_guild_id)
    user = user if user else StubUser(actor_id)

    from_account = backend.get_account_by_id(UUID(transaction_data["from_account"]))
    to_account = backend.get_account_by_id(UUID(transaction_data["to_account"]))
    amount = int(transaction_data["amount"])
    if from_account is None or to_account is None:
        raise web.HTTPNotFound()

    backend.perform_transaction(user, from_account, to_account, amount)
    return web.Response(text="200")



def init_app():
    app = web.Application(middlewares=[authenticate])
    app.add_routes(routes)
    return app


