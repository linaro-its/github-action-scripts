const redirect = require("./index.js")

function createRequest(uri) {
    return {
        "Records": [
            {
                "cf": {
                    "config": {
                        "distributionId": "EXAMPLE"
                    },
                    "request": {
                        "uri": `${uri}`,
                        "method": "GET",
                        "clientIp": "2001:cdba::3257:9652",
                        "headers": {
                            "host": [
                                {
                                    "key": "Host",
                                    "value": "d123.cf.net"
                                }
                            ]
                        }
                    }
                }
            }
        ]
    }
}

describe("correctly applies rules on linaro website request", () => {
    test("wiki", () => {
        const cb = function (_, res) {
            expect(res.headers.location[0].value).toBe("https://wiki.linaro.org/FrontPage")
        };
        redirect.handler(createRequest("/wiki"), null, cb)
    })

    test("about", () => {
        const cb = function (_, res) {
            expect(res.headers.location[0].value).toBe("/about/")
        };
        redirect.handler(createRequest("/why-linaro"), null, cb)
    })

    test("latest", () => {
        const cb = function (_, res) {
            console.log(res)
            expect(res.headers.location[0].value).toBe("/23.0.1/index.html")
        };
        redirect.handler(createRequest("/latest/"), null, cb)
    })

    test("latest twice", () => {
        const cb = function (_, res) {
            console.log(res)
            expect(res.headers.location[0].value).toBe("/23.0.1/arm-forge-23.0.1-linux.tar")
        };
        redirect.handler(createRequest("/latest/arm-forge-latest-linux.tar"), null, cb)
    })
    
})