import { auth, currentUser } from "@clerk/nextjs/server"

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

// The name the greeting addresses: the first name, as a greeting would say
// it. The page previews the greeting and the first ask stores it, and both
// take the name from here so the two cannot differ. Undefined when sign-up
// did not ask for one, and the API decides what the greeting says then.
//
// Not who is asking -- that is the token above. This only picks the words.
const greetingName = async () => (await currentUser())?.firstName || undefined

export { authorization, greetingName }
