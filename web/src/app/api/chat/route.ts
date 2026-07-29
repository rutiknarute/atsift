import { convertToModelMessages, type UIMessage } from "ai"

import { createJobScout } from "@/lib/job-agent"

export const maxDuration = 60

export async function POST(request: Request) {
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
