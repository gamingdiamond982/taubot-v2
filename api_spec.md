# Taubot API specification v0.0.1

## Authorization

In order to interface with the API you will need to set an "authorization" header.

This header should simply include the JWT api key you were issued by Stoner.

Example cURL request:
```shell
$ curl "https://qwrky.dev/api/.../" -H "authorization: eyJhbGciOiJSUzUxMiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJUQiIsImlhdCI6MTc0MTYyNzUyNi45OTgwNiwiZXhwIjoxNzQxNzEzOTI2Ljk5ODA2MDUsInVpZCI6IjUyOTY3NjEzOTgzNzUyMTkyMCJ9.pZystJZ7TRmf_2Tf--VAyRtPiVPEURMQ0LG_EYAVqazEGWQvnONmsLd64UfRjo6tAxy5UV6Y26vmxCrusitImIdtNJZGjcpO8sAOi-GYDZEi_8TnXLNLBCJEZXGQJb3Sn--8bBW_QhQaKnIy6TkYD71rp8hFDz-bELEHzq3HFBQhtf2ZZ3RYfPyeXPd2brKVY3tsSdq_MFhACOjuWgIjgst6s2_je2f56FiEcJsrtY-UciOL5vNhSYZgTkzx9mRW4SLLen-Gy6KiKNF0CyCnGUdQ5pGlDehG3j4wf4uRTuufOFXqmE4W3BvH8DR3wdhlUE25Y0rVaQgy8xR7OVhCtg"
```

As you can see auth tokens are extremely long, this is a tradeoff for ease of implementation, although it shouldn't really matter since you should be storing this in a config file.

This authorization header should be sent with every request you make to taubot, each token is tied to a set of permissions similar to a user account - some tokens may even be tied directly to your user account.

## The {economy_id} parameter

Since taubot has been designed to support multiple economies running on the same database, you will need to specify which economy you wish to interface with.

This value can probably be hardcoded in most implementations considering there is currently only one economy using taubot.

```py
TAUBOT_ECONOMY_ID = "5fb29676-ba8d-4e00-b430-8394cb48ddb8"
```

*Example using taubot's economy id*

## API objects

### AccountType - Enum:

> | USER | GOVERNMENT | CORPORATION | CHARITY |
> |------|------------|-------------|---------|

### Account

> | json key     | value                                              | type         |
> |--------------|----------------------------------------------------|--------------|
> | account_id   | The id of the account being returned               | uuid         |
> | account_name | The name of the account                            | string       |
> | owner_id     | The discord id of the person that owns the account | string       |
> | account_type | The accounts type                                  | Account Type |
> | balance\*    | The balance in cents of the account                | integer      |

*\* balance is only returned when the actor has the VIEW_BALANCE permission on the account*

### Transaction
> | json key     | value                                                                                    | type    |
> |--------------|------------------------------------------------------------------------------------------|---------|
> | actor_id     | the discord user id of the person who authorised this transaction                        | string  |
> | timestamp    | the unix timestamp of when the transaction occurred, may be used to check for equality   | float   |
> | from_account | the account_id of the account money was removed from                                     | uuid    |
> | to_account   | the account_id of the account                                                            | uuid    |
> | amount       | the amount of money transferred in cents                                                 | integer |

## Getting an account by account id
> `GET` **`/economies/{economy_id}/accounts/by-name/{account_name}`**

##### Parameters

> | key        | value                                         |
> |------------|-----------------------------------------------|
> | economy_id | the uuid of the economy that owns the account |
> | account_id | the uuid of the account                       |

##### Responses

> | http code | content-type                     | response                |
> |-----------|----------------------------------|-------------------------|
> | `200`     | `application/json;charset=UTF-8` | Account object          |
> | `400`     | `text/text;charset=UTF-8`        | Error code Unauthorised |
> | `404`     | `text/text;charset=UTF-8`        | Error code not found    |

##### Example cURL

> ```sh
>  $ curl "https://qwrky.dev/api/economies/5fb29676-ba8d-4e00-b430-8394cb48ddb8/accounts/5fb29676-ba8d-4e00-b430-8394cb48ddb8" -H "Authorization: auth_token"
> ```




## Getting an account by name

> `GET` **`/economies/{economy_id}/accounts/by-name/{account_name}`**

##### Parameters

> | key          | value                                       |
> |--------------|---------------------------------------------|
> | economy_id   | the id of the economy that owns the account |
> | account_name | the name of the account urlencoded          |

##### Responses

> | http code | content-type                     | response                |
> |-----------|----------------------------------|-------------------------|
> | `200`     | `application/json;charset=UTF-8` | Account object          |
> | `400`     | `text/text;charset=UTF-8`        | Error code Unauthorised |
> | `404`     | `text/text;charset=UTF-8`        | Error code not found    |

##### Example cURL

> ```sh
>  $ curl "https://qwrky.dev/api/economies/5fb29676-ba8d-4e00-b430-8394cb48ddb8/accounts/by-name/Government%20Reserve" -H "Authorization: auth_token"
> ```

## Getting an account's transaction log

> `GET` **`/economies/{economy_id}/accounts/{account_id}/transactions?limit={limit}`**
##### Parameters

> | key        | value                                            |
> |------------|--------------------------------------------------|
> | economy_id | the uuid of the economy that owns the account    |
> | account_id | the uuid of the account                          |
> | limit      | the upper limit to reply with - defaults to all  |

##### Responses

> | http code | content-type       | response            |
> |-----------|--------------------|---------------------|
> | `200`     | `application/json` | Transaction[]       |
> | `400`     | `text`             | Error: Unauthorized |
> | `404`     | `text`             | Error: Not Found    |


##### Example cURL

> ```sh
>  $ curl "https://qwrky.dev/api/economies/5fb29676-ba8d-4e00-b430-8394cb48ddb8/accounts/cc6ca82d-752a-44c9-81c6-f61accae35a0/transactions?limit=10" -H "Authorization: auth_token"
> ```
may also be performed without the limit paramater in which case all entries will be returned.

> ```sh
>  $ curl "https://qwrky.dev/api/economies/5fb29676-ba8d-4e00-b430-8394cb48ddb8/accounts/cc6ca82d-752a-44c9-81c6-f61accae35a0/transactions" -H "Authorization: auth_token"
> ```

## Getting a user's personal account

> `GET` **`/economies/{economy_id}/users/{user_id}`**

##### Parameters

> | key        | value                                                                                                                            |
> |------------|----------------------------------------------------------------------------------------------------------------------------------|
> | economy_id | the uuid of the economy that the user owns an account in                                                                         |
> | user_id    | the discord user id of the owner of the personal account, may be replaced with "me" if you wish to get your own personal account |


##### Responses

> | http code  | content-type       | response            |
> |------------|--------------------|---------------------|
> | `200`      | `application/json` | Account             |
> | `400`      | `text`             | Error: Unauthorized |
> | `404`      | `text`             | Error: Not Found    |

##### Example cURL

> ```sh
> $ curl "https://qwrky.dev/api/economies/5fb29676-ba8d-4e00-b430-8394cb48ddb8/users/529676139837521920" -H "authorization: auth_token"
> ```

## Creating a transaction
> `POST` **`/economies/{economy_id}/accounts/transactions`**

##### Parameters

> | key        | value                                                                                       |
> |------------|---------------------------------------------------------------------------------------------|
> | economy_id | the uuid of the economy that the user owns an account in                                    |


##### POST Data

> | key          | value                                             |
> |--------------|---------------------------------------------------|
> | from_account | the uuid of the account you are transferring from |
> | to_account   | the uuid of the account you are transferring to   |
> | amount       | the amount in cents you plan to transfer          |


##### Responses

> | http code  | content-type       | response            |
> |------------|--------------------|---------------------|
> | `200`      | `application/json` | Account             |
> | `400`      | `text`             | Error: Unauthorized |
> | `404`      | `text`             | Error: Not Found    |

##### Example cURL

> ```sh
> $ curl -X POST -d '{ \
>   "from_account": "97e27ebf-5741-4dc9-9793-5642474f5eea",\
>   "to_account": "8c28351f-6106-4db9-a7a1-c02df7a24b8b" \
> }' "https://qwrky.dev/api/economies/5fb29676-ba8d-4e00-b430-8394cb48ddb8/users/529676139837521920" -H "authorization: auth_token"
> ```



