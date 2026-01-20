
API
===

Taubot exposes a HTTPS API available at https://tau.work.gd/api/.

All data unless otherwise specified should be sent using JSON encoding.


Authentication
--------------

DM SoTech Lon to get a master application key and it's associated application ID.


Types of keys:

.. list-table::
   :widths: 50 50
   :header-rows: 1
   
   * - Master Key
     - Grant Key
   * - Master keys are issued to applications, if requested they can be granted certain taubot permissions, but are notable for their ability to create GRANT keys
     - Grant keys are issued by a user to an application, it allows them to grant a subset of their taubot permissions to an application


The key being used to make a request should be set as the :code:`authorization` HTTP header.


Oauth-like flow overview
------------------------

(name suggestions are greatly appreciated)

This section pretains to the distribution of Grant Keys to applications.


The flow is as follows:
  
  1. Application initiates proccess py posting a UUID identifier to :code:`/api/oauth-references`, and sends the user a link containing the UUID in a query string along with their application ID.
  
  2. User clicks link and sets the grant scopes they wish to grant to the API.

  3. User returns to application and confirms that they've completed the grant process.

  4. Application gets :code:`/api/retrieve-key/{reference_id}` where reference ID is the ID they set in their post request. 


Starting the oauth-like flow
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

As mentioned above the application should send a post request to :code:`/api/oauth-references` 
containing a UUID used to identify this particular flow.

This UUID should be sent in the POST body json encoded with the key :code:`ref_id`.

Afterwards, a URL should be sent to the user granting the application permissions. The same reference ID should be included in the querystring, labelled :code:`ref_id`. the application ID should also be sent in the querystring and labelled :code:`aid`.


*Example Python Code using requests*

.. code-block:: python

   import requests
   from uuid import UUID

   # for obvious reasons these should be loaded from a config rather than hardcoded
   master_key: str = "master key goes here"
   application_id: UUID = UUID("application ID goes here")

   def get_auth_link(ref_id: UUID) -> str:
       resp = requests.post(
            "https://qwrky.dev/api/oauth-references",
            data={"ref_id": str(ref_id)},
            headers={"Authorization": master_key}
       )
       resp.raise_for_status()

       # since uuids are urlsafe this is fine
       return f"https://qwrky.dev/api/oauth/grant?ref={str(ref_id)}&aid={str(application_id)}"


Once the user has completed the grant process, they should inform the application somehow so that the application can then retrieve their token.


Retrieving a token
^^^^^^^^^^^^^^^^^^

Now that the user has confirmed with the application the token has been isued and it's time for the application to retrieve it's token

This should be done by sending a get request to :code:`/api/retrieve-key/{ref_id}` where :code:`ref_id` is the same UUID used to initiate the claim process. 

The response will be json data with the new auth key set as the :code:`key` attribute.

This key will have the same permissions the user set.

*Example Python code using requests*

.. code-block:: python

   import requests
   from uuid import UUID

   # for obvious reasons these should be loaded from a config rather than hardcoded
   master_key: str = "master key goes here"
   application_id: UUID = UUID("application ID goes here")

   def retrieve_key(ref_id: UUID) -> str:
      # since UUIDs are urlsafe this is fine
      resp = requests.get(
           f"https://qwrky.dev/api/retrieve-key/{str(ref_id)}",
           headers = {}
      )
      resp.raise_for_status()

      return resp.json()["key"]


This token should be persisted somewhere, and used to make requests on behalf of the issuer.

API Reference
-------------


Response Types
^^^^^^^^^^^^^^

Account
~~~~~~~


.. list-table:: Account Response Structure
   :widths: 20 20 50
   :header-rows: 1
   :stub-columns: 1

   * - Key
     - Type
     - Description
   * - account_id
     - String
     - The account's UUID encoded as a string
   * - owner_id
     - String
     - The owner's discord id encoded as a string since some programming languages can mess up ints that big
   * - account_name
     - String
     - The name of the account
   * - account_type
     - String
     - The type of account, see the Account Type section below for more info
   * - balance
     - Integer
     - The balance of the account in cents - i.e. 100 would be 1t and 101 would be 1.01t

Account Type
~~~~~~~~~~~~

.. list-table:: Account Type
   :widths: 20 50
   :header-rows: 1
   :stub-columns: 1

   * - Name
     - Description
   * - USER
     - An account type used to represent user accounts on the discord, is used exclusively for personal accounts
   * - GOVERNMENT
     - An account type used to represent government accounts
   * - CORPORATION
     - An account type used to represent corporate accounts
   * - CHARITY
     - An account type used by non-profit accounts


Transaction
~~~~~~~~~~~

.. list-table:: Transaction
   :widths: 20 20 50
   :header-rows: 1
   :stub-columns: 1

   * - Key
     - Type
     - Description
   * - actor_id
     - String
     - The person who performed the transactions discord user id encoded as a string
   * - timestamp
     - Integer
     - The unix timestamp of when the transaction took place
   * - from_account
     - String
     - The account UUID of the account the money was transferred from
   * - to_account
     - String
     - The account UUID of the account the money was sent to
   * - amount
     - Integer
     - The amount in cents that was transferred


Endpoints
^^^^^^^^^


Here's an overview of all the requests you can currently make to the API.

.. http:get:: /api/users/(int:user_id)

   Returns the personal account of :code:`user_id` if it could be found.

   :statuscode 200: Returns an Account object
   :statuscode 404: A personal account registered to that user could not be found.


.. http:get:: /api/accounts/by-name/(str:account_name)
   
   Returns the account of name :code:`account_name` if it could be found

   :statuscode 200: Returns an Account object
   :statuscode 404: An account by that name could not be found

.. http:get:: /api/accounts/(UUID:account_id)

   Returns the account of uuid :code:`account_id` if it could be found

   :statuscode 200: Retruns an Account object
   :statuscode 404: An account by that name could not be found

.. http:get:: /api/accounts/(UUID:account_id)/transactions

   Returns a list of the Transactions to and from that account

   :query limit: optional limit paramater, specifies the maximum number of transactions to return
   
   :statuscode 200: Returns a JSON list of Transaction objects
   :statuscode 404: The account specified could not be found
   :statuscode 401: You do not have the necessary permissions (:code:`VIEW_BALANCE`) to view the transaction log


.. http:post:: /api/transactions/
   
   Creates a new transaction

   :jsonparam string from_account: The account UUID to transfer money from
   :jsonparam string to_account: The account UUID to transfer money to
   :jsonparam int amount: The amount in cents to transfer

   :statuscode 200: Transaction was created sucessfully
   :statuscode 404: One of the accounts could not be found
   :statuscode 401: Your key doesn't grant you sufficient permissions to make this transaction
