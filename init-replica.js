// Safe to rerun: preserve the existing replica-set configuration and data.
let status;
try { status = rs.status(); }
catch (error) {
    if (error.code !== 94 && error.codeName !== "NotYetInitialized") throw error;
    printjson(rs.initiate({
        _id: "rs0",
        members: [
            { _id: 0, host: "mongo1:27017" },
            { _id: 1, host: "mongo2:27017" },
            { _id: 2, host: "mongo3:27017" }
        ]
    }));
}
const deadline = Date.now() + 90000;
while (Date.now() < deadline) {
    const hello = db.hello();
    if (hello.primary) { print("PRIMARY elected: " + hello.primary); quit(0); }
    sleep(500);
}
throw new Error("No primary elected within 90 seconds");
