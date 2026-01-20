
// I hate this language with a passion, if anybody wants to rework any of this pretty stuff be my guest
function submit() {
    result = {
        "permissions" : {},
        "spending_limit": null
    }
    accounts = document.getElementsByClassName('account-object')
    console.log(accounts)
    for (let i=0; i< accounts.length; i++) {
        var acc = accounts[i]
        inps = acc.getElementsByTagName('input')
        console.log(acc)
        result["permissions"][acc.id] = []
        for (let i=0; i<inps.length; i++) {
            if (inps[i].checked) {
                result["permissions"][acc.id].push(inps[i].id)
            }
        }
    }

    result["spending_limit"] = Number(document.getElementById("spending_limit").value)
    fetch(
        '/api/oauth/issue',
        {
            method: "POST",
            credentials: "include",
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            body: JSON.stringify(result)
        }
    ).then((response) => {
        if (response.ok) {
            alert('Successfully Issued Token, Go back to the application that sent you here - you may safely close this page')
        } else {
            alert('Something went wrong issuing that token')
        }
    })
}