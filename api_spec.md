# Taubot API specification v0.0.1

## Authorization

In order to interface with the API you will need to set an "authorization" header.

This header should simply include the JWT api key you were issued by Stoner.

Example curl request:
```shell
$ curl https://qwrky.dev/api/.../ -H "authorization: eyJhbGciOiJSUzUxMiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJUQiIsImlhdCI6MTc0MTYyNzUyNi45OTgwNiwiZXhwIjoxNzQxNzEzOTI2Ljk5ODA2MDUsInVpZCI6IjUyOTY3NjEzOTgzNzUyMTkyMCJ9.pZystJZ7TRmf_2Tf--VAyRtPiVPEURMQ0LG_EYAVqazEGWQvnONmsLd64UfRjo6tAxy5UV6Y26vmxCrusitImIdtNJZGjcpO8sAOi-GYDZEi_8TnXLNLBCJEZXGQJb3Sn--8bBW_QhQaKnIy6TkYD71rp8hFDz-bELEHzq3HFBQhtf2ZZ3RYfPyeXPd2brKVY3tsSdq_MFhACOjuWgIjgst6s2_je2f56FiEcJsrtY-UciOL5vNhSYZgTkzx9mRW4SLLen-Gy6KiKNF0CyCnGUdQ5pGlDehG3j4wf4uRTuufOFXqmE4W3BvH8DR3wdhlUE25Y0rVaQgy8xR7OVhCtg"
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

## Getting an account by name



<details>
 <summary><code>GET</code> <code><b>/</b></code></summary>

##### Parameters

> None

##### Responses

> | http code     | content-type                      | response                                                            |
> |---------------|-----------------------------------|---------------------------------------------------------------------|
> | `200`         | `text/plain;charset=UTF-8`        | YAML string                                                         |

##### Example cURL

> ```javascript
>  curl -X GET -H "Content-Type: application/json" http://localhost:8889/
> ```

</details>




