import { auth } from "@clerk/nextjs/server"

// The signed-in user's Clerk session token, for medas-api to verify. Who is
// asking travels only as this: the API reads the user from the token and
// ignores anything the request says about it.
//
// Server-side only, like every caller of the API. A session token lives for
// about a minute, so it is fetched per request rather than held.
const sessionToken = async (): Promise<string> => {
  const { userId, getToken } = await auth()

  if (!userId) {
    throw new Error("Not signed in")
  }

  const token = await getToken()

  if (!token) {
    throw new Error("Not signed in")
  }

  return token
}

const authorization = async () => ({
  Authorization: `Bearer ${await sessionToken()}`,
})

export { authorization }
