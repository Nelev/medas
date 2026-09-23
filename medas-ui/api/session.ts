import { auth } from "@clerk/nextjs/server"

// The signed-in user's Clerk session token, as the header medas-api verifies.
// Who is asking travels only as this: the API reads the user from the token
// and ignores anything the request says about it.
//
// Server-side only, like every caller of the API. A session token lives for
// about a minute, so it is fetched per request rather than held. Signed out,
// there is no token to fetch, which is the one check this needs.
const authorization = async () => {
  const token = await (await auth()).getToken()

  if (!token) {
    throw new Error("Not signed in")
  }

  return { Authorization: `Bearer ${token}` }
}

export { authorization }
