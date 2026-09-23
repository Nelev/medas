import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server"

// The routes someone signed out can reach: the two ways in. Listed this way
// round so a page added later is behind the login until it is named here.
const isPublicRoute = createRouteMatcher(["/sign-in(.*)", "/sign-up(.*)"])

// Signed out on anything else is a redirect to /sign-in. This is the
// optimistic check; the page and the Server Action each check again.
export default clerkMiddleware(async (auth, req) => {
  if (!isPublicRoute(req)) {
    await auth.protect()
  }
})

export const config = {
  matcher: [
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
}
