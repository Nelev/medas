// A stand-in for medas-api, used only so `next build` can prerender /.
//
// The page fetches the greeting during the build. With no API reachable the
// build dies with ECONNREFUSED, and an unreachable URL is no better than
// none -- so this answers with the one shape that request needs.
//
// Deliberately dumb: it does not read the query, does not route, and knows
// nothing about conversations. Anything more would be a second, drifting
// implementation of the API rather than a build fixture.
import { createServer } from "node:http"

const PORT = Number(process.env.STUB_API_PORT ?? 8000)

const GREETING = {
  messages: [{ role: "assistant", text: "Hi, how can I help you?" }],
}

createServer((_request, response) => {
  response.writeHead(200, { "Content-Type": "application/json" })
  response.end(JSON.stringify(GREETING))
}).listen(PORT, () => {
  console.log(`stub api listening on ${PORT}`)
})
