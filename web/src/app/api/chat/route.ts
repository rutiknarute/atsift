import { convertToModelMessages, type UIMessage } from "ai"

import { createJobScout } from "@/lib/job-agent"
import { allowAttempt } from "@/server/auth"
import { sessionRole } from "@/server/guard"

export const maxDuration = 60

/*
  The demo account keeps the Scout — it is the most interesting thing here and
  a demo without it shows nothing. But every message is a paid call on the
  owner's OpenRouter key, and anyone can mint a demo session, so demo traffic
  is capped where the owner's is not.
*/
const DEMO_MESSAGES_PER_HOUR = 12

export async function POST(request: Request) {
  const role = await sessionRole()

  if (!role) {
    return Response.json({ error: "Not signed in." }, { status: 401 })
  }

  if (role === "demo") {
    const forwarded = request.headers.get("x-forwarded-for")
    const key = forwarded?.split(",")[0]?.trim() || "local"

    if (!allowAttempt(`chat:${key}`, DEMO_MESSAGES_PER_HOUR, 60 * 60_000)) {
      return Response.json(
        {
          error:
            "The demo has reached its message limit for now. Try again later.",
        },
        { status: 429 },
      )
    }
  }

  const { messages }: { messages: UIMessage[] } = await request.json()

  try {
    const agent = createJobScout()

    const result = await agent.stream({
      messages: await convertToModelMessages(messages),
    })

    return result.toUIMessageStreamResponse()
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "The Job Scout is unavailable."

    return Response.json({ error: message }, { status: 503 })
  }
}
